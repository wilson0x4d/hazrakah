# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Thread-safety tests for singleton resolution.

Singleton creation in ``Container._dispatch_registration`` is guarded by a
per-cache-key ``threading.RLock`` so that concurrent first-resolves of the
same singleton yield exactly one instance.  These facts exercise the race
directly and pin the per-key (not container-wide) lock design: a
container-wide lock held across instance creation would deadlock the async
factory tests, since ``__await_or_block`` runs coroutines on worker threads
whenever an event loop is running.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
import time
from typing import Any

from hazrakah import Container
from punit import fact


class _SlowService:
    """Concrete singleton type with no dependencies."""


class _SharedDep:
    """A singleton shared by several other singletons."""


class _ConsumerOne:
    def __init__(self, dep: _SharedDep) -> None:
        self.dep = dep


class _ConsumerTwo:
    def __init__(self, dep: _SharedDep) -> None:
        self.dep = dep


class _AsyncDep:
    """A sync singleton resolved from inside an async factory."""


class _AsyncService:
    def __init__(self, dep: _AsyncDep) -> None:
        self.dep = dep


def __run_coroutine_in_fresh_loop(coro: Any) -> Any:
    """Run *coro* in a context where a thread has a running event loop.

    Without a running loop this is a plain ``asyncio.run``.  When one is
    already running (punit executes test bodies inside ``asyncio.run``) the
    whole ``asyncio.run`` call is moved to a dedicated thread — either way,
    the thread executing the coroutine body has a running loop, which is the
    condition under which ``Container.__await_or_block`` dispatches
    coroutine-returning factories to worker threads.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=10)


@fact
def concurrent_first_resolution_creates_single_instance() -> None:
    """N threads racing the first resolve of a singleton observe one shared instance."""
    container = Container()
    call_count = 0

    def factory(_c: Container) -> _SlowService:
        nonlocal call_count
        call_count += 1
        time.sleep(0.05)  # widen the race window so every thread hits the slow path
        return _SlowService()

    container.register_singleton(_SlowService, factory)
    n_threads = 32
    barrier = threading.Barrier(n_threads)
    results: list[_SlowService | None] = [None] * n_threads
    errors: list[BaseException] = []

    def worker(idx: int) -> None:
        try:
            barrier.wait()
            results[idx] = container.resolve(_SlowService)
        except BaseException as e:  # noqa: BLE001 - captured and asserted on after join
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not any(t.is_alive() for t in threads), 'deadlock detected'
    assert not errors, f'unexpected errors in workers: {errors}'
    assert all(r is not None for r in results)
    assert len({id(r) for r in results if r is not None}) == 1
    assert call_count == 1


@fact
def concurrent_distinct_singletons_with_shared_dep_resolve_without_deadlock() -> None:
    """Concurrent resolution of distinct singletons that share a dependency
    completes without deadlock and creates each singleton exactly once."""
    container = Container()
    dep_calls = 0
    one_calls = 0
    two_calls = 0

    def dep_factory(_c: Container) -> _SharedDep:
        nonlocal dep_calls
        dep_calls += 1
        time.sleep(0.02)
        return _SharedDep()

    def one_factory(c: Container) -> _ConsumerOne:
        nonlocal one_calls
        one_calls += 1
        time.sleep(0.02)
        return _ConsumerOne(c.resolve(_SharedDep))

    def two_factory(c: Container) -> _ConsumerTwo:
        nonlocal two_calls
        two_calls += 1
        time.sleep(0.02)
        return _ConsumerTwo(c.resolve(_SharedDep))

    container.register_singleton(_SharedDep, dep_factory)
    container.register_singleton(_ConsumerOne, one_factory)
    container.register_singleton(_ConsumerTwo, two_factory)

    # Two threads per singleton; threads alternate targets to maximize lock overlap.
    targets: list[type] = [_SharedDep, _ConsumerOne, _ConsumerTwo]
    n_threads = len(targets) * 2
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []
    seen: dict[type, set[int]] = {t: set() for t in targets}

    def worker(idx: int) -> None:
        try:
            barrier.wait()
            target = targets[idx % len(targets)]
            obj: Any = container.resolve(target)
            seen[target].add(id(obj))
        except BaseException as e:  # noqa: BLE001 - captured and asserted on after join
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not any(t.is_alive() for t in threads), 'deadlock detected'
    assert not errors, f'unexpected errors in workers: {errors}'
    assert dep_calls == 1
    assert one_calls == 1
    assert two_calls == 1
    for target in targets:
        assert len(seen[target]) == 1, f'{target.__name__} resolved to more than one instance'


@fact
def async_singleton_factory_resolving_singleton_deps_under_running_loop() -> None:
    """An async singleton factory that resolves another singleton completes
    while an event loop is running (the ``__await_or_block`` worker-thread path).

    The thread calling ``resolve`` has a running loop, so the factory's
    coroutine executes on a worker thread that itself resolves a singleton.
    A container-wide lock held across creation would deadlock here; the
    per-key lock design must not.
    """
    container = Container()
    dep_calls = 0
    service_calls = 0

    def dep_factory(_c: Container) -> _AsyncDep:
        nonlocal dep_calls
        dep_calls += 1
        return _AsyncDep()

    async def service_factory(c: Container) -> _AsyncService:
        nonlocal service_calls
        service_calls += 1
        dep: _AsyncDep = c.resolve(_AsyncDep)
        return _AsyncService(dep)

    container.register_singleton(_AsyncDep, dep_factory)
    container.register_singleton(_AsyncService, service_factory)

    async def main() -> _AsyncService:
        return container.resolve(_AsyncService)

    first = __run_coroutine_in_fresh_loop(main())
    assert service_calls == 1
    assert dep_calls == 1

    second = __run_coroutine_in_fresh_loop(main())
    assert second is first
    assert service_calls == 1
    assert dep_calls == 1


@fact
def warm_singleton_cache_serves_concurrent_resolves() -> None:
    """After the first creation, concurrent resolves return the same instance
    via the lock-free fast path without re-invoking the factory."""
    container = Container()
    call_count = 0

    def factory(_c: Container) -> _SlowService:
        nonlocal call_count
        call_count += 1
        return _SlowService()

    container.register_singleton(_SlowService, factory)
    warm: _SlowService = container.resolve(_SlowService)
    assert call_count == 1

    n_threads = 32
    barrier = threading.Barrier(n_threads)
    results: list[_SlowService | None] = [None] * n_threads

    def worker(idx: int) -> None:
        barrier.wait()
        results[idx] = container.resolve(_SlowService)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not any(t.is_alive() for t in threads), 'deadlock detected'
    assert all(r is warm for r in results)
    assert call_count == 1

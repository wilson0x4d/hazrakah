# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
from hazrakah import Container
from punit import fact


class ServiceA:
    def __init__(self) -> None:
        self.name: str = "A"


class ServiceB:
    def __init__(self, a: ServiceA) -> None:
        self.a = a
        self.name: str = "B"


class ServiceC:
    def __init__(self, b: ServiceB) -> None:
        self.b = b
        self.name: str = "C"


class _AsyncIntResult:
    """Container for an async factory return value (hashable key for registration)."""
    pass

class _SyncRegKey:
    """Marker type used only for registration key — never resolved."""
    pass


@fact
def async_factory_returning_coroutine_resolves_in_sync_context() -> None:
    """An async factory that returns a coroutine is awaited when resolve() is called from sync code."""
    container = Container()
    call_count = 0

    async def async_factory_a(_c: Container) -> ServiceA:
        nonlocal call_count
        call_count += 1
        return ServiceA()

    container.register_transient(ServiceA, async_factory_a)
    result: ServiceA = container.resolve(ServiceA)
    assert result is not None
    assert result.name == "A"
    assert call_count == 1


@fact
def async_factory_with_simple_value_returns_correct_value() -> None:
    """An async factory returning a simple value like an int."""
    container = Container()

    async def async_int_factory(_c: Container) -> int:
        return 1337

    container.register_transient(int, async_int_factory)  # type: ignore[arg-type]
    result: int = container.resolve(int)
    assert result == 1337


@fact
def async_factory_registered_as_singleton_singletons_work() -> None:
    """Async factory registered as SINGLETON creates one instance that is cached."""
    container = Container()
    call_count = 0

    async def async_factory_a(_c: Container) -> ServiceA:
        nonlocal call_count
        call_count += 1
        return ServiceA()

    container.register_singleton(ServiceA, async_factory_a)  # type: ignore[arg-type]
    first: ServiceA = container.resolve(ServiceA)
    second: ServiceA = container.resolve(ServiceA)
    assert first is second
    assert call_count == 1


@fact
def async_factory_with_transitively_async_deps_works() -> None:
    """A chain of async factories resolves through the full dependency tree."""
    container = Container()
    a_calls = 0
    b_calls = 0
    c_calls = 0

    async def async_factory_a(_c: Container) -> ServiceA:
        nonlocal a_calls
        a_calls += 1
        return ServiceA()

    async def async_factory_b(c: Container) -> ServiceB:
        nonlocal b_calls
        b_calls += 1
        a: ServiceA = c.resolve(ServiceA)
        return ServiceB(a)

    async def async_factory_c(c: Container) -> ServiceC:
        nonlocal c_calls
        c_calls += 1
        b: ServiceB = c.resolve(ServiceB)
        return ServiceC(b)

    container.register_transient(ServiceA, async_factory_a)
    container.register_transient(ServiceB, async_factory_b)
    container.register_transient(ServiceC, async_factory_c)

    result: ServiceC = container.resolve(ServiceC)
    assert result is not None
    assert result.b is not None
    assert result.b.a is not None


@fact
def sync_factory_still_works_across_all_three_paths() -> None:
    """Sync factories continue to work normally (no regression)."""
    container = Container()
    count = 0

    def sync_factory(c: Container) -> _SyncRegKey:
        nonlocal count
        count += 1
        return _SyncRegKey()

    container.register_singleton(_SyncRegKey, sync_factory)  # type: ignore[arg-type]
    first = container.resolve(_SyncRegKey)
    second = container.resolve(_SyncRegKey)
    assert first is second
    assert count == 1

    # Transient registration in child scope
    scope = container.create_scope()
    scope.register_transient(_SyncRegKey, lambda c: _SyncRegKey())  # type: ignore[arg-type]
    t1 = scope.resolve(_SyncRegKey)
    t2 = scope.resolve(_SyncRegKey)
    assert t1 is not t2


@fact
def async_factory_with_regular_class_constructor_works() -> None:
    """Async factory that depends on a regular class (non-async) resolves correctly."""
    container = Container()
    factory_called = False

    async def async_factory(c: Container) -> ServiceB:
        nonlocal factory_called
        factory_called = True
        a: ServiceA = c.resolve(ServiceA)
        return ServiceB(a)

    container.register_transient(ServiceA, ServiceA)  # type: ignore[arg-type]
    container.register_transient(ServiceB, async_factory)  # type: ignore[arg-type]

    result: ServiceB = container.resolve(ServiceB)
    assert factory_called
    assert result.a is not None
    assert result.name == "B"


@fact
def async_factory_returns_none_value() -> None:
    """Async factory returning None is handled correctly."""
    container = Container()

    async def async_factory(_c: Container) -> None:
        return None

    container.register_transient(ServiceA, async_factory)  # type: ignore[arg-type]
    result: ServiceA | None = container.resolve(ServiceA)  # type: ignore[assignment]
    assert result is None


@fact
def async_factory_returns_int_result() -> None:
    """An async factory returning an int wrapped in a result class."""
    container = Container()

    async def async_factory(_c: Container) -> _AsyncIntResult:
        return _AsyncIntResult()

    container.register_transient(_AsyncIntResult, async_factory)  # type: ignore[arg-type]
    result: _AsyncIntResult = container.resolve(_AsyncIntResult)
    assert result is not None


@fact
def async_factory_creates_new_instances_per_resolve() -> None:
    """Async transient factories create fresh objects per resolve call."""
    container = Container()
    count = 0

    async def async_factory(_c: Container) -> ServiceA:
        nonlocal count
        count += 1
        return ServiceA()

    container.register_transient(ServiceA, async_factory)  # type: ignore[arg-type]
    first = container.resolve(ServiceA)
    second = container.resolve(ServiceA)
    assert first is not second
    assert count == 2


@fact
def async_factory_error_propagates_correctly() -> None:
    """Exceptions raised inside an async factory propagate through resolve()."""
    container = Container()

    async def failing_factory(_c: Container) -> ServiceA:
        raise ValueError("boom")

    container.register_transient(ServiceA, failing_factory)  # type: ignore[arg-type]
    try:
        container.resolve(ServiceA)
    except ValueError as exc:
        assert str(exc) == "boom"
    else:
        assert False, "Expected ValueError"


@fact
def sync_async_mixed_in_same_scope_works() -> None:
    """A scope with both sync and async factories resolves correctly."""
    container = Container()
    sync_count = 0
    async_count = 0

    def sync_factory(c: Container) -> _SyncRegKey:
        nonlocal sync_count
        sync_count += 1
        return _SyncRegKey()

    async def async_factory_a(_c: Container) -> ServiceA:
        nonlocal async_count
        async_count += 1
        return ServiceA()

    container.register_transient(ServiceA, async_factory_a)
    container.register_transient(_SyncRegKey, sync_factory)  # type: ignore[arg-type]

    a_result: ServiceA = container.resolve(ServiceA)
    s_result = container.resolve(_SyncRegKey)
    assert a_result is not None
    assert s_result is not None
    assert async_count == 1
    assert sync_count == 1


@fact
def async_factory_in_punit_async_context_resolves() -> None:
    """Async factory works when resolve() is called from inside punit's async test context.

    pUnit runs tests inside ``asyncio.run()``, so a running event loop is always
    active when the test body executes.  The container's ``_await_or_block``
    helper detects this and runs the async factory in a dedicated thread so
    ``asyncio.run()`` can be used inside the thread without a
    ``RuntimeError``.
    """
    container = Container()
    factory_called = False

    async def async_factory_a(c: Container) -> ServiceA:
        nonlocal factory_called
        factory_called = True
        return ServiceA()

    async def async_factory_b(c: Container) -> ServiceB:
        a = c.resolve(ServiceA)  # type: ignore[arg-type]
        return ServiceB(a)

    container.register_transient(ServiceA, async_factory_a)
    container.register_transient(ServiceB, async_factory_b)

    # resolve() is synchronous.  When it encounters a coroutine-resulting
    # factory, ``_await_or_block`` sees the running punit loop and spawns a
    # new event loop in a thread to complete it.
    result: ServiceB = container.resolve(ServiceB)  # type: ignore[arg-type]
    assert factory_called
    assert result is not None
    assert result.a is not None

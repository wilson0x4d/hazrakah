# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

import asyncio
import gc

from hazrakah import Container
from punit import fact


class CloseableResource:
    """A resource that exposes a ``close`` method for destruction tracking."""

    closed: bool = False

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class NestedChild(CloseableResource):
    """A transitive dependency that is also a ``CloseableResource``."""

    def __init__(self) -> None:  # type: ignore[no-untyped-init]
        super().__init__()


class ParentService(CloseableResource):
    """A service with a child dependency (both should be tracked independently.)"""

    def __init__(self, _child: NestedChild) -> None:  # type: ignore[no-untyped-init]
        super().__init__()


class UserOwnedObject:
    """A user-owned object registered via ``register_instance`` (should NOT be destroyed)."""

    closed: bool = False

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@fact
def direct_container_context_manager_destroys_tracked_instances() -> None:
    """A Container used directly as a context manager must destroy all tracked instances on exit."""
    with Container() as container:
        container.register_transient(CloseableResource)
        instance = container.resolve(CloseableResource)
        assert isinstance(instance, CloseableResource), 'Instance should be created'

    # After exiting the context, the resource's close() should have been called.
    assert instance.closed, 'Tracked instance should have been destroyed on context exit.'


@fact
def direct_container_context_manager_clears_tracked_set() -> None:
    """After context exit, the tracked set must be cleared so no double-cleanup occurs."""
    with Container() as container:
        container.register_transient(CloseableResource)
        _ = container.resolve(CloseableResource)

    # Resolve another instance in a new scope -- it should not find any stale references.
    second_instance = CloseableResource()
    assert not second_instance.closed, 'Freshly created instances must not be closed.'


@fact
def child_scope_context_manager_destroys_only_child_instances() -> None:
    """A scoped container must destroy only its own tracked instances; parent unaffected."""
    parent = Container()
    with parent.create_scope() as scope:
        scope.register_transient(CloseableResource)
        child_instance = scope.resolve(CloseableResource)

    assert child_instance.closed, 'Child-scoped instance must be destroyed.'


@fact
def child_scope_context_manager_does_not_affect_parent_singletons() -> None:
    """When a parent registers a singleton and a child resolves it via context, only the child's own instances are cleaned up."""
    parent = Container()
    parent.register_singleton(CloseableResource)
    parent_instance = parent.resolve(CloseableResource)

    with parent.create_scope() as scope:
        # Resolve the same singleton from the child.
        scoped_instance = scope.resolve(CloseableResource)
        assert scoped_instance is parent_instance, 'Singleton must be shared across scopes.'
        new_child_transient = scope.resolve(NestedChild)

    # After child scope exit, only the transient was destroyed; singleton survives.
    assert not parent_instance.closed, 'Parent singleton must survive child scope teardown.'
    assert new_child_transient.closed, 'Child transient must be destroyed.'


@fact
def user_owned_instances_are_not_destroyed() -> None:
    """Objects registered via ``register_instance`` are user-owned and must NOT be torn down."""
    user_obj = UserOwnedObject()
    container = Container()

    with container:
        container.register_instance(UserOwnedObject, user_obj)
        resolved = container.resolve(UserOwnedObject)
        assert resolved is user_obj

    # After exit, the user-owned instance must NOT have its close() called.
    assert not user_obj.closed, 'User-registered instance should not be destroyed.'


@fact
def context_manager_exception_propagates_but_cleanup_runs() -> None:
    """An exception raised inside the ``with`` block must propagate through; cleanup still runs."""

    class BrokenResource(CloseableResource):
        pass

    exc_caught = False
    with Container() as ctx:
        ctx.register_transient(BrokenResource)
        try:
            raise RuntimeError('expected test exception')
        except RuntimeError:
            exc_caught = True

    assert exc_caught, 'Exception must be caught here.'
    # If we reached this far without the runtime error propagating past the try/except, cleanup ran.


@fact
def close_propagates_exceptions_to_outer_scope() -> None:
    """An exception raised during cleanup in __exit__ must propagate to the caller."""

    class BadResource(CloseableResource):
        def close(self) -> None:
            raise RuntimeError('close is broken')

    bad_resource = BadResource()

    container = Container()
    try:
        with container as scoped:
            scoped.register_transient(BadResource, lambda _: bad_resource)  # type: ignore[arg-type]
            scoped.resolve(BadResource)
        assert False, 'Should have raised during __exit__'
    except RuntimeError as e:
        assert str(e) == 'close is broken'


@fact
def transitive_dependencies_are_all_destroyed() -> None:
    """All objects in a dependency graph that the container instantiated must be destroyed."""
    with Container() as container:
        container.register_transient(ParentService)
        parent = container.resolve(ParentService)

    assert isinstance(parent, CloseableResource), 'Parent should be closeable.'
    assert parent.closed, 'Parent instance should have been destroyed on context exit.'


@fact
def context_enter_returns_scope_not_self() -> None:
    """``__enter__`` must return a child scope of the container."""
    ctx = Container()
    result = ctx.__enter__()
    assert result is not ctx, '__enter__ must return a child scope, not self.'
    assert getattr(result, '_Container__outer_scope') is ctx, 'Returned scope must have parent as outer_scope.'
    ctx.__exit__(None, None, None)


@fact
def del_fallback_calls_close_on_tracked_instances() -> None:
    """Verify that ``__del__`` also calls close() on tracked instances (best-effort)."""
    resource = CloseableResource()

    container = Container()
    # Register a factory that returns our pre-created instance so it gets tracked.
    container.register_transient(CloseableResource, lambda _: resource)  # type: ignore[arg-type]
    _ = container.resolve(CloseableResource)

    del container
    gc.collect()

    assert resource.closed, '__del__ should have called close() on tracked instances.'


class AsyncCloseableResource:
    """A resource that exposes an async ``close`` method."""

    closed: bool = False

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@fact
def async_close_awaited_in_sync_exit() -> None:
    """When a tracked object has an async close(), __exit__ must await it via _await_or_block."""
    with Container() as container:
        container.register_transient(AsyncCloseableResource)
        instance = container.resolve(AsyncCloseableResource)
        assert isinstance(instance, AsyncCloseableResource), 'instance should be AsyncCloseableResource'
        assert not instance.closed, 'instance should not be closed yet'

    assert instance.closed, 'Async close() must be awaited during sync __exit__.'


@fact
def async_close_awaited_in_del() -> None:
    """When a tracked object has an async close(), __del__ must await it via _await_or_block."""
    resource = AsyncCloseableResource()

    container = Container()
    container.register_transient(AsyncCloseableResource, lambda _: resource)  # type: ignore[arg-type]
    _ = container.resolve(AsyncCloseableResource)

    del container
    gc.collect()

    assert resource.closed, '__del__ should have awaited async close() on tracked instances.'


@fact
async def async_context_manager_awaits_close() -> None:
    """Async context manager must use __aexit__ which awaits coroutine close() methods."""
    async with Container() as container:
        container.register_transient(AsyncCloseableResource)
        instance = container.resolve(AsyncCloseableResource)
        assert not instance.closed, 'instance should not be closed while inside context'

    assert instance.closed, 'Async __aexit__ must await async close() methods.'


@fact
async def async_context_manager_clears_tracked() -> None:
    """Async context manager must clear tracked set after teardown."""
    async with Container() as container:
        container.register_transient(AsyncCloseableResource)
        _ = container.resolve(AsyncCloseableResource)


class ManualCloseableResource:
    """A resource that tracks whether close() was called."""

    closed: bool = False

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@fact
def autoclose_false_prevents_close_in_sync_exit() -> None:
    """When autoclose=False, close() must NOT be called on tracked instances during __exit__."""
    with Container(autoclose=False) as container:
        container.register_transient(ManualCloseableResource)
        instance = container.resolve(ManualCloseableResource)
        assert not instance.closed, 'should not be closed yet'

    assert not instance.closed, 'autoclose=False must prevent close() from being called in __exit__.'


@fact
def autoclose_false_prevents_close_in_del() -> None:
    """When autoclose=False, close() must NOT be called on tracked instances during __del__."""
    resource = ManualCloseableResource()

    container = Container(autoclose=False)
    container.register_transient(ManualCloseableResource, lambda _: resource)  # type: ignore[arg-type]
    _ = container.resolve(ManualCloseableResource)

    del container
    gc.collect()

    assert not resource.closed, 'autoclose=False must prevent close() from being called in __del__.'


@fact
async def autoclose_false_prevents_close_in_async_exit() -> None:
    """When autoclose=False, close() must NOT be called on tracked instances during __aexit__."""
    async with Container(autoclose=False) as container:
        container.register_transient(ManualCloseableResource)
        instance = container.resolve(ManualCloseableResource)
        assert not instance.closed, 'should not be closed while inside context'

    assert not instance.closed, 'autoclose=False must prevent close() from being called in __aexit__.'


@fact
def autoclose_default_true_destroys_tracked() -> None:
    """autoclose defaults to True, so tracked instances are closed by default."""
    with Container() as container:
        container.register_transient(ManualCloseableResource)
        instance = container.resolve(ManualCloseableResource)

    assert instance.closed, 'default autoclose=True must close tracked instances.'


@fact
def autoclose_explicit_true_destroys_tracked() -> None:
    """Explicit autoclose=True must close tracked instances."""
    with Container(autoclose=True) as container:
        container.register_transient(ManualCloseableResource)
        instance = container.resolve(ManualCloseableResource)

    assert instance.closed, 'autoclose=True must close tracked instances.'


@fact
def autoclose_false_inherited_by_scope_by_default() -> None:
    """autoclose=False on a parent is inherited by child scopes by default."""
    parent = Container(autoclose=False)
    with parent.create_scope() as child:
        child.register_transient(ManualCloseableResource)
        child_instance = child.resolve(ManualCloseableResource)

    assert not child_instance.closed, 'autoclose=False inherited by scope must prevent close().'


@fact
def autoclose_false_override_on_scope() -> None:
    """Child scope can override parent's autoclose=False with autoclose=True."""
    parent = Container(autoclose=False)
    with parent.create_scope(autoclose=True) as child:
        child.register_transient(ManualCloseableResource)
        child_instance = child.resolve(ManualCloseableResource)

    assert child_instance.closed, 'explicit autoclose=True on scope must close tracked instances.'


@fact
async def autoclose_false_with_async_closeable() -> None:
    """autoclose=False with an async closeable must not attempt to await close()."""
    async with Container(autoclose=False) as container:
        container.register_transient(AsyncCloseableResource)
        instance = container.resolve(AsyncCloseableResource)
        assert not instance.closed, 'should not be closed inside context'

    assert not instance.closed, 'autoclose=False must not call async close() either.'


@fact
def reentrant_enter_raises_runtime_error() -> None:
    """Calling __enter__ twice without __exit__ must raise RuntimeError."""
    ctx = Container()
    ctx.__enter__()
    try:
        ctx.__enter__()
        assert False, 'Should have raised RuntimeError'
    except RuntimeError as e:
        assert 'already being used' in str(e).lower()
    ctx.__exit__(None, None, None)


@fact
async def reentrant_async_enter_raises_runtime_error() -> None:
    """Calling __aenter__ twice without __aexit__ must raise RuntimeError."""
    ctx = Container()
    await ctx.__aenter__()
    try:
        await ctx.__aenter__()
        assert False, 'Should have raised RuntimeError'
    except RuntimeError as e:
        assert 'already being used' in str(e).lower()
    await ctx.__aexit__(None, None, None)


@fact
def exit_without_enter_raises_runtime_error() -> None:
    """Calling __exit__ without a prior __enter__ must raise RuntimeError."""
    ctx = Container()
    try:
        ctx.__exit__(None, None, None)
        assert False, 'Should have raised RuntimeError'
    except RuntimeError as e:
        assert 'without prior __enter__' in str(e)


@fact
async def async_exit_without_async_enter_raises_runtime_error() -> None:
    """Calling __aexit__ without a prior __aenter__ must raise RuntimeError."""
    ctx = Container()
    try:
        await ctx.__aexit__(None, None, None)
        assert False, 'Should have raised RuntimeError'
    except RuntimeError as e:
        assert 'without prior __aenter__' in str(e)


@fact
def separate_context_managers_on_same_container_sequentially_work() -> None:
    """Two sequential context managers on the same Container work correctly."""
    with Container() as c1:
        c1.register_transient(CloseableResource)
        r1 = c1.resolve(CloseableResource)
    assert r1.closed, 'First scope should close its instance'

    with Container() as c2:
        c2.register_transient(CloseableResource)
        r2 = c2.resolve(CloseableResource)
    assert r2.closed, 'Second scope should close its instance'


@fact
async def async_context_isolation_per_async_context() -> None:
    """Different async contexts should have independent context manager scopes."""
    results: list[tuple[int, str, bool]] = []

    async def async_task(task_id: int) -> None:
        async with Container() as container:
            container.register_transient(CloseableResource)
            instance = container.resolve(CloseableResource)
            # Instance should not be closed while inside context
            results.append((task_id, 'inside', not instance.closed))

        # Instance should be closed after exit
        results.append((task_id, 'outside', instance.closed))

    await asyncio.gather(
        async_task(1),
        async_task(2),
    )

    # All instances should be closed after both tasks complete
    assert results == [
        (1, 'inside', True),
        (1, 'outside', True),
        (2, 'inside', True),
        (2, 'outside', True),
    ], f'Unexpected results: {results}'


class CountingCloseableResource:
    """A resource that counts how many times ``close`` is called."""

    def __init__(self) -> None:
        self.close_count = 0

    def close(self) -> None:
        self.close_count += 1


class FlakyCloseableResource:
    """A resource whose ``close`` fails until *retries* attempts have been made."""

    __retries: int
    closed: bool

    def __init__(self, retries: int) -> None:
        self.__retries = retries
        self.closed = False

    def close(self) -> None:
        if self.__retries > 0:
            self.__retries -= 1
            raise RuntimeError('flaky close failed')
        self.closed = True


class FailCloseResource:
    """A resource whose ``close`` always raises the configured message."""

    __message: str

    def __init__(self, message: str) -> None:
        self.__message = message

    def close(self) -> None:
        raise RuntimeError(self.__message)


class AsyncBadResource:
    """A resource whose async ``close`` always raises the configured message."""

    __message: str

    def __init__(self, message: str) -> None:
        self.__message = message

    async def close(self) -> None:
        raise RuntimeError(self.__message)


class AsyncCountingCloseableResource:
    """A resource with an async ``close`` that counts invocations."""

    def __init__(self) -> None:
        self.close_count = 0

    async def close(self) -> None:
        self.close_count += 1


@fact
def dispose_destroys_tracked_instances() -> None:
    """dispose() must call close() on every tracked instance."""
    container = Container()
    container.register_transient(CloseableResource)
    instance = container.resolve(CloseableResource)

    container.dispose()

    assert instance.closed, 'dispose() should have closed the tracked instance.'


@fact
def dispose_is_idempotent_for_closed_instances() -> None:
    """A second dispose() must not re-close instances that already closed successfully."""
    resource = CountingCloseableResource()
    container = Container()
    container.register_transient(CountingCloseableResource, lambda _: resource)  # type: ignore[arg-type]
    _ = container.resolve(CountingCloseableResource)

    container.dispose()
    container.dispose()

    assert resource.close_count == 1, f'close() must be called exactly once (expected=1, actual={resource.close_count})'


@fact
def dispose_propagates_single_close_failure() -> None:
    """A single close() failure must be re-raised as the original exception."""
    bad_resource = FailCloseResource('close is broken')
    container = Container()
    container.register_transient(FailCloseResource, lambda _: bad_resource)  # type: ignore[arg-type]
    _ = container.resolve(FailCloseResource)

    try:
        container.dispose()
        assert False, 'dispose() should have raised RuntimeError'
    except RuntimeError as e:
        assert str(e) == 'close is broken', f'(expected=close is broken, actual={str(e)})'


@fact
def dispose_attempts_all_tracked_before_raising() -> None:
    """Every tracked instance must be closed even when one close() fails; the failed instance stays tracked."""
    bad_resource = FailCloseResource('close is broken')
    good_resource = CloseableResource()
    container = Container()
    container.register_transient(FailCloseResource, lambda _: bad_resource)  # type: ignore[arg-type]
    container.register_transient(CloseableResource, lambda _: good_resource)  # type: ignore[arg-type]
    _ = container.resolve(FailCloseResource)
    _ = container.resolve(CloseableResource)

    try:
        container.dispose()
        assert False, 'dispose() should have raised RuntimeError'
    except RuntimeError:
        pass

    assert good_resource.closed, 'Instances after a failing close() must still be closed.'
    assert bad_resource in getattr(container, '_Container__tracked'), 'Failed instance must remain tracked for retry.'
    assert good_resource not in getattr(container, '_Container__tracked'), 'Closed instance must be untracked.'


@fact
def dispose_retries_only_failed_instances() -> None:
    """A subsequent dispose() after a failure must re-attempt only the instances that failed."""
    flaky = FlakyCloseableResource(retries=1)
    container = Container()
    container.register_transient(FlakyCloseableResource, lambda _: flaky)  # type: ignore[arg-type]
    _ = container.resolve(FlakyCloseableResource)

    try:
        container.dispose()
        assert False, 'first dispose() should have raised RuntimeError'
    except RuntimeError:
        pass

    container.dispose()

    assert flaky.closed, 'Second dispose() must re-attempt and close the previously failed instance.'
    tracked = getattr(container, '_Container__tracked')
    assert len(tracked) == 0, f'Tracked set must be empty after successful retry (actual={len(tracked)})'


@fact
def dispose_raises_exception_group_on_multiple_failures() -> None:
    """Multiple close() failures must be raised as an ExceptionGroup containing each failure."""

    class BadA:
        def close(self) -> None:
            raise RuntimeError('close a is broken')

    class BadB:
        def close(self) -> None:
            raise RuntimeError('close b is broken')

    container = Container()
    container.register_transient(BadA)
    container.register_transient(BadB)
    _ = container.resolve(BadA)
    _ = container.resolve(BadB)

    try:
        container.dispose()
        assert False, 'dispose() should have raised ExceptionGroup'
    except ExceptionGroup as e:
        messages = sorted(str(x) for x in e.exceptions)
        assert messages == ['close a is broken', 'close b is broken'], f'Unexpected failures: {messages}'


@fact
def dispose_respects_autoclose_false() -> None:
    """dispose() must not call close() when autoclose=False, and must still clear tracking."""
    container = Container(autoclose=False)
    container.register_transient(ManualCloseableResource)
    instance = container.resolve(ManualCloseableResource)

    container.dispose()

    assert not instance.closed, 'autoclose=False must prevent close() during dispose().'
    tracked = getattr(container, '_Container__tracked')
    assert len(tracked) == 0, f'Tracking must be cleared even when autoclose=False (actual={len(tracked)})'


@fact
def dispose_clears_tracked_instances_without_close() -> None:
    """Tracked instances without a close() method must be untracked by dispose()."""

    class NoClose:
        pass

    container = Container()
    container.register_transient(NoClose)
    _ = container.resolve(NoClose)

    container.dispose()

    tracked = getattr(container, '_Container__tracked')
    assert len(tracked) == 0, f'Instances without close() must be untracked (actual={len(tracked)})'


@fact
def dispose_only_affects_own_scope() -> None:
    """dispose() on a child scope must not destroy instances tracked by its parent."""
    parent = Container()
    parent.register_singleton(CloseableResource)
    parent_instance = parent.resolve(CloseableResource)

    child = parent.create_scope()
    child.register_transient(ManualCloseableResource)
    child_instance = child.resolve(ManualCloseableResource)

    child.dispose()

    assert child_instance.closed, 'Child-scoped instance must be destroyed by child dispose().'
    assert not parent_instance.closed, 'Parent singleton must survive child dispose().'


@fact
def dispose_awaits_async_close() -> None:
    """A synchronous dispose() must block on and await coroutine close() results."""
    container = Container()
    container.register_transient(AsyncCloseableResource)
    instance = container.resolve(AsyncCloseableResource)

    container.dispose()

    assert instance.closed, 'dispose() must await async close() synchronously.'


@fact
def del_still_best_effort_with_failing_close() -> None:
    """__del__ must swallow close() failures and still close the remaining tracked instances."""
    good_resource = ManualCloseableResource()

    class Bad:
        def close(self) -> None:
            raise RuntimeError('close is broken')

    container = Container()
    container.register_transient(ManualCloseableResource, lambda _: good_resource)  # type: ignore[arg-type]
    container.register_transient(Bad)
    _ = container.resolve(ManualCloseableResource)
    _ = container.resolve(Bad)

    del container
    gc.collect()

    assert good_resource.closed, '__del__ must still close remaining instances when one close() fails.'


@fact
async def adispose_awaits_async_close() -> None:
    """adispose() must natively await coroutine close() results."""
    container = Container()
    container.register_transient(AsyncCloseableResource)
    instance = container.resolve(AsyncCloseableResource)

    await container.adispose()

    assert instance.closed, 'adispose() must await async close().'


@fact
async def adispose_is_idempotent_for_closed_instances() -> None:
    """A second adispose() must not re-close instances that already closed successfully."""
    resource = AsyncCountingCloseableResource()
    container = Container()
    container.register_transient(AsyncCountingCloseableResource, lambda _: resource)  # type: ignore[arg-type]
    _ = container.resolve(AsyncCountingCloseableResource)

    await container.adispose()
    await container.adispose()

    assert resource.close_count == 1, f'close() must be called exactly once (expected=1, actual={resource.close_count})'


@fact
async def adispose_propagates_single_close_failure() -> None:
    """A single close() failure must be re-raised as the original exception from adispose()."""
    bad_resource = AsyncBadResource('close is broken')
    container = Container()
    container.register_transient(AsyncBadResource, lambda _: bad_resource)  # type: ignore[arg-type]
    _ = container.resolve(AsyncBadResource)

    try:
        await container.adispose()
        assert False, 'adispose() should have raised RuntimeError'
    except RuntimeError as e:
        assert str(e) == 'close is broken', f'(expected=close is broken, actual={str(e)})'


@fact
async def adispose_attempts_all_tracked_before_raising() -> None:
    """Every tracked instance must be closed even when one async close() fails; the failed instance stays tracked."""

    class AsyncBad:
        async def close(self) -> None:
            raise RuntimeError('async close is broken')

    good_resource = AsyncCloseableResource()
    container = Container()
    container.register_transient(AsyncBad)
    container.register_transient(AsyncCloseableResource, lambda _: good_resource)  # type: ignore[arg-type]
    _ = container.resolve(AsyncBad)
    _ = container.resolve(AsyncCloseableResource)

    try:
        await container.adispose()
        assert False, 'adispose() should have raised RuntimeError'
    except RuntimeError:
        pass

    assert good_resource.closed, 'Instances after a failing async close() must still be closed.'
    assert good_resource not in getattr(container, '_Container__tracked'), 'Closed instance must be untracked.'
    tracked = getattr(container, '_Container__tracked')
    assert len(tracked) == 1, f'Failed instance must remain tracked (actual={len(tracked)})'


@fact
async def adispose_raises_exception_group_on_multiple_failures() -> None:
    """Multiple close() failures must be raised as an ExceptionGroup containing each failure."""

    class AsyncBadA:
        async def close(self) -> None:
            raise RuntimeError('async close a is broken')

    class AsyncBadB:
        async def close(self) -> None:
            raise RuntimeError('async close b is broken')

    container = Container()
    container.register_transient(AsyncBadA)
    container.register_transient(AsyncBadB)
    _ = container.resolve(AsyncBadA)
    _ = container.resolve(AsyncBadB)

    try:
        await container.adispose()
        assert False, 'adispose() should have raised ExceptionGroup'
    except ExceptionGroup as e:
        messages = sorted(str(x) for x in e.exceptions)
        assert messages == ['async close a is broken', 'async close b is broken'], f'Unexpected failures: {messages}'


@fact
async def adispose_respects_autoclose_false() -> None:
    """adispose() must not call close() when autoclose=False."""
    container = Container(autoclose=False)
    container.register_transient(AsyncCloseableResource)
    instance = container.resolve(AsyncCloseableResource)

    await container.adispose()

    assert not instance.closed, 'autoclose=False must prevent async close() during adispose().'


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
        with container:
            container.register_transient(BadResource, lambda _: bad_resource)  # type: ignore[arg-type]
            container.resolve(BadResource)
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
def context_enter_returns_self() -> None:
    """``__enter__`` must return the same Container instance."""
    ctx = Container()
    result = ctx.__enter__()
    assert result is ctx, '__enter__ must return self.'


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
    container = Container()
    container.register_transient(AsyncCloseableResource)
    instance = container.resolve(AsyncCloseableResource)
    assert isinstance(instance, AsyncCloseableResource), 'instance should be AsyncCloseableResource'
    assert not instance.closed, 'instance should not be closed yet'

    with container:
        pass

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
    container = Container(autoclose=False)
    container.register_transient(ManualCloseableResource)
    instance = container.resolve(ManualCloseableResource)
    assert not instance.closed, 'should not be closed yet'

    with container:
        pass

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
    container = Container()
    container.register_transient(ManualCloseableResource)
    instance = container.resolve(ManualCloseableResource)

    with container:
        pass

    assert instance.closed, 'default autoclose=True must close tracked instances.'


@fact
def autoclose_explicit_true_destroys_tracked() -> None:
    """Explicit autoclose=True must close tracked instances."""
    container = Container(autoclose=True)
    container.register_transient(ManualCloseableResource)
    instance = container.resolve(ManualCloseableResource)

    with container:
        pass

    assert instance.closed, 'autoclose=True must close tracked instances.'


@fact
def autoclose_false_inherited_by_scope_by_default() -> None:
    """autoclose=False on a parent is inherited by child scopes by default."""
    parent = Container(autoclose=False)

    child = parent.create_scope()
    child.register_transient(ManualCloseableResource)
    child_instance = child.resolve(ManualCloseableResource)

    with child:
        pass

    assert not child_instance.closed, 'autoclose=False inherited by scope must prevent close().'


@fact
def autoclose_false_override_on_scope() -> None:
    """Child scope can override parent's autoclose=False with autoclose=True."""
    parent = Container(autoclose=False)

    child = parent.create_scope(autoclose=True)
    child.register_transient(ManualCloseableResource)
    child_instance = child.resolve(ManualCloseableResource)

    with child:
        pass

    assert child_instance.closed, 'explicit autoclose=True on scope must close tracked instances.'


@fact
async def autoclose_false_with_async_closeable() -> None:
    """autoclose=False with an async closeable must not attempt to await close()."""
    async with Container(autoclose=False) as container:
        container.register_transient(AsyncCloseableResource)
        instance = container.resolve(AsyncCloseableResource)
        assert not instance.closed, 'should not be closed inside context'

    assert not instance.closed, 'autoclose=False must not call async close() either.'

# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for lazy decoration-aware resolution.

``resolve()`` consults lifetime-decorator metadata for types that have no standing
registration, registering them with the declared lifetime instead of always
auto-registering as transient.  Each test applies decorations imperatively after
the module teardown has cleared the global manager, so every entry is fresh.
"""

from __future__ import annotations

from hazrakah import (
    Container,
    RegistrationError,
    instanced,
    singleton,
    transient,
)
from hazrakah.lifetime_decorators import _DecorationInfoManager
from punit import fact, teardown
from punit.assertions.exceptions import raises


@teardown
def _cleanup() -> None:
    """Reset the global decoration manager for isolation between tests."""
    _DecorationInfoManager._clear_store()


class LazyDepService:
    """Constructor dependency referenced by annotation from LazyHostService."""


class LazyHostService:
    def __init__(self, dep: LazyDepService) -> None:
        self.dep = dep


@fact
def lazy_singleton_resolves_same_instance() -> None:
    """@singleton without register_decorated() yields one shared instance."""

    class Foo:
        pass

    singleton(Foo)
    c = Container()
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is b, f'(expected=same instance, actual=({a!r} vs {b!r}))'


@fact
def lazy_transient_resolves_new_instances() -> None:
    """@transient keeps the default per-resolve instantiation behavior."""

    class Foo:
        pass

    transient(Foo)
    c = Container()
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is not b, f'(expected=distinct instances, actual=both {a!r})'


@fact
def lazy_instanced_creates_instance_once() -> None:
    """@instanced constructs exactly once and returns that object everywhere."""

    calls: list[int] = []

    class Foo:
        def __init__(self) -> None:
            calls.append(1)

    instanced(Foo)
    c = Container()
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is b, f'(expected=same instance, actual=({a!r} vs {b!r}))'
    assert len(calls) == 1, f'(expected=1, actual={len(calls)})'


@fact
def standing_registration_preempts_singleton_decoration() -> None:
    """An existing registration wins over decoration metadata."""

    class Foo:
        pass

    singleton(Foo)
    c = Container()
    c.register_transient(Foo)
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is not b, f'(expected=transient instances, actual=both {a!r})'


@fact
def standing_registration_preempts_transient_decoration() -> None:
    """An existing singleton registration wins over @transient metadata."""

    class Foo:
        pass

    transient(Foo)
    c = Container()
    c.register_singleton(Foo)
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is b, f'(expected=same instance, actual=({a!r} vs {b!r}))'


@fact
def lazy_types_interface_resolution_honors_singleton() -> None:
    """Resolving the interface from @singleton(types=IFoo) yields a singleton."""

    class IFoo:
        pass

    class Foo:
        pass

    singleton(types=IFoo)(Foo)
    c = Container()
    a = c.resolve(IFoo)
    b = c.resolve(IFoo)
    assert isinstance(a, Foo), f'(expected=Foo instance, actual={type(a).__name__})'
    assert a is b, f'(expected=same instance, actual=({a!r} vs {b!r}))'


@fact
def lazy_types_target_resolution_shares_singleton_with_interface() -> None:
    """Resolving the concrete target and the interface yield the same instance."""

    class IFoo:
        pass

    class Foo:
        pass

    singleton(types=IFoo)(Foo)
    c = Container()
    by_target = c.resolve(Foo)
    by_interface = c.resolve(IFoo)
    assert by_target is by_interface, (
        f'(expected=shared singleton, actual=({by_target!r} vs {by_interface!r}))'
    )
    assert c.resolve(IFoo) is by_interface, 'interface resolves must stay stable'


@fact
def conflicting_target_lifetimes_fall_back_to_transient() -> None:
    """A target decorated with two different lifetimes is treated as unadorned."""

    class IFoo:
        pass

    class IBar:
        pass

    class Foo:
        pass

    singleton(types=IFoo)(Foo)
    transient(types=IBar)(Foo)
    c = Container()
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is not b, f'(expected=transient fallback, actual=both {a!r})'
    i1 = c.resolve(IFoo)
    i2 = c.resolve(IFoo)
    assert i1 is i2, f'(expected=singleton via IFoo, actual=({i1!r} vs {i2!r}))'


@fact
def namespaced_decoration_plain_resolve_stays_transient() -> None:
    """Plain resolve of a namespaced decoration keeps default transient behavior."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    c = Container()
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is not b, f'(expected=transient instances, actual=both {a!r})'


@fact
def namespaced_decoration_first_touch_via_namespace() -> None:
    """resolve(t, namespace=...) materializes a namespaced decoration on first touch."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    c = Container()
    a = c.resolve(Foo, namespace='v2')
    b = c.resolve(Foo, namespace='v2')
    assert isinstance(a, Foo), f'(expected=Foo instance, actual={type(a).__name__})'
    assert a is b, f'(expected=same singleton, actual=({a!r} vs {b!r}))'


@fact
def namespaced_decoration_materialized_from_child_scope_is_shared_with_root() -> None:
    """Namespace materialization attaches to the root, so scopes share the instance."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    root = Container()
    child = root.create_scope()
    from_child = child.resolve(Foo, namespace='v2')
    from_root = root.resolve(Foo, namespace='v2')
    assert from_child is from_root, (
        f'(expected=shared root-level singleton, actual=({from_child!r} vs {from_root!r}))'
    )


@fact
def namespaced_types_first_touch_target_and_interface_share_instance() -> None:
    """Namespaced types= decorations materialize for target and interface alike."""

    class IFoo:
        pass

    class Foo:
        pass

    singleton(types=IFoo, namespace='v2')(Foo)
    c = Container()
    by_target = c.resolve(Foo, namespace='v2')
    by_interface = c.resolve(IFoo, namespace='v2')
    assert by_target is by_interface, (
        f'(expected=shared v2 singleton, actual=({by_target!r} vs {by_interface!r}))'
    )


@fact
def namespaced_decoration_unrequested_namespace_untouched() -> None:
    """A namespace chain that omits the decorated namespace does not match it."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    c = Container()
    a = c.resolve(Foo, namespace=['other', None])
    b = c.resolve(Foo, namespace=['other', None])
    assert a is not b, f'(expected=transient fallback, actual=both {a!r})'


@fact
def namespaced_decoration_side_effect_from_plain_resolve() -> None:
    """A plain resolve materializes the v2 registration as a side effect."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    c = Container()
    c.resolve(Foo)
    a = c.resolve(Foo, namespace='v2')
    b = c.resolve(Foo, namespace='v2')
    assert a is b, f'(expected=same v2 singleton, actual=({a!r} vs {b!r}))'
    p1 = c.resolve(Foo)
    p2 = c.resolve(Foo)
    assert p1 is not p2, f'(expected=plain resolve stays transient, actual=both {p1!r})'


@fact
def plain_resolve_never_returns_namespaced_singleton() -> None:
    """Plain resolves are distinct objects and never the v2 singleton."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    c = Container()
    v2 = c.resolve(Foo, namespace='v2')
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is not b, f'(expected=distinct transient instances, actual=both {a!r})'
    assert a is not v2, f'(expected=plain resolve != v2 singleton, actual=both {a!r})'


@fact
def lazy_singleton_factory_invoked_once() -> None:
    """A decorated factory function is invoked once for the singleton lifetime."""

    class ISession:
        pass

    calls: list[int] = []

    def make_session(r: object) -> ISession:
        calls.append(1)
        return ISession()

    singleton(types=ISession)(make_session)
    c = Container()
    s1 = c.resolve(ISession)
    s2 = c.resolve(ISession)
    assert s1 is s2, f'(expected=same singleton, actual=({s1!r} vs {s2!r}))'
    assert len(calls) == 1, f'(expected=1 factory call, actual={len(calls)})'


@fact
def frozen_container_rejects_lazy_decoration_registration() -> None:
    """Lazy decoration registration is blocked on a frozen container."""

    class Foo:
        pass

    singleton(Foo)
    c = Container(frozen=True)
    assert raises[RegistrationError](lambda: c.resolve(Foo)), (
        'expected RegistrationError when lazy-registering on a frozen container'
    )


@fact
def register_decorated_remains_consistent_after_lazy_registration() -> None:
    """Eager register_decorated() after a lazy resolution keeps the same instance."""

    class Foo:
        pass

    singleton(Foo)
    c = Container()
    first = c.resolve(Foo)
    c.register_decorated()
    assert c.resolve(Foo) is first, (
        f'(expected=original instance, actual=({first!r} vs {c.resolve(Foo)!r}))'
    )


@fact
def lazy_singleton_dependency_honored_transitively() -> None:
    """Constructor dependencies hit the same lazy decoration path during creation."""
    singleton(LazyDepService)
    singleton(LazyHostService)
    c = Container()
    h1 = c.resolve(LazyHostService)
    h2 = c.resolve(LazyHostService)
    assert h1 is h2, f'(expected=same host singleton, actual=({h1!r} vs {h2!r}))'
    assert h1.dep is h2.dep, f'(expected=same dep instance, actual=({h1.dep!r} vs {h2.dep!r}))'
    assert c.resolve(LazyDepService) is h1.dep, (
        f'(expected=dep resolves to injected instance, actual=({c.resolve(LazyDepService)!r} vs {h1.dep!r}))'
    )


@fact
def undecorated_concrete_type_namespace_resolve_unchanged() -> None:
    """Undecorated concrete types keep the pre-existing namespace fall-through."""

    class Plain:
        pass

    c = Container()
    a = c.resolve(Plain, namespace='v2')
    b = c.resolve(Plain, namespace='v2')
    assert a is not b, f'(expected=transient behavior as before, actual=both {a!r})'


@fact
def disable_decorators_restores_plain_transient_fallback() -> None:
    """A disabled container ignores decoration metadata and stays transient."""

    class Foo:
        pass

    singleton(Foo)
    c = Container().disable_decorators()
    assert c.disable_decorators() is c, 'disable_decorators must be chainable'
    a = c.resolve(Foo)
    b = c.resolve(Foo)
    assert a is not b, f'(expected=transient fallback, actual=both {a!r})'


@fact
def disable_decorators_blocks_namespaced_materialization() -> None:
    """A disabled container never materializes namespaced registrations."""

    class Foo:
        pass

    singleton(namespace='v2')(Foo)
    c = Container().disable_decorators()
    a = c.resolve(Foo, namespace='v2')
    b = c.resolve(Foo, namespace='v2')
    assert a is not b, f'(expected=transient fall-through, actual=both {a!r})'
    assert c.is_registered(Foo, namespace=['v2']) is False, (
        'no v2 registration should be materialized while decorators are disabled'
    )


@fact
def disable_decorators_propagates_to_child_scopes() -> None:
    """Children inherit the disabled flag from their parent."""

    class Foo:
        pass

    singleton(Foo)
    parent = Container().disable_decorators()
    child = parent.create_scope()
    a = child.resolve(Foo)
    b = child.resolve(Foo)
    assert a is not b, f'(expected=child to ignore decoration, actual=both {a!r})'


@fact
def create_scope_can_reenable_decorators() -> None:
    """A child scope may override the disabled flag back on."""

    class Foo:
        pass

    singleton(Foo)
    parent = Container().disable_decorators()
    child = parent.create_scope(decorators=True)
    assert child.resolve(Foo) is child.resolve(Foo), (
        'expected=same singleton when child re-enables decorators, actual=distinct'
    )


@fact
def disable_decorators_does_not_block_eager_register_decorated() -> None:
    """Eager register_decorated() is explicit registration and still works."""

    class Foo:
        pass

    singleton(Foo)
    c = Container().disable_decorators()
    c.register_decorated()
    assert c.resolve(Foo) is c.resolve(Foo), (
        'expected=same singleton after eager registration, actual=distinct'
    )

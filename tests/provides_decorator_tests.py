# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for the @provides marker decorator.

The @provides decorator stores interface metadata on the decorated class as
__hazrakah_provides. Mutation methods (register_singleton, register_transient,
register_instance) discover this metadata at call site and multi-register.

Each test defines its own protocol types inline to avoid cross-test pollution
from _DecorationInfoManager shared state.
"""

from hazrakah import RegistrationError, singleton, transient, instanced
from punit import fact, fails
from typing import Protocol

from hazrakah import Container, provides
from hazrakah.lifetime_decorators import _DecorationInfoManager


def _reset_decorations():
    """Reset the global decoration info manager for test isolation."""
    _DecorationInfoManager._clear_store()


@fact
def provides_decorator_sets_hidden_attribute():
    """@provides stores a non-empty tuple under __hazrakovh_provides."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MarkedClass:
        pass

    assert hasattr(MarkedClass, '__hazrakah_provides')
    prov = getattr(MarkedClass, '__hazrakah_provides')
    assert isinstance(prov, tuple)
    assert IFoo in prov


@fact
def provides_decorator_no_args_stores_empty_tuple():

    @provides()
    class EmptyMarker:
        pass

    prov = getattr(EmptyMarker, '__hazrakah_provides')
    assert isinstance(prov, tuple)
    assert prov == ()


@fact
def register_singleton_with_provides_multi_registers():
    """Multi-registered interfaces share the same singleton instance."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyWidget:
        def __init__(self):
            self.answer = 42

    c = Container()
    c.register_singleton(MyWidget)

    assert c.is_registered(IFoo)
    assert c.is_registered(IBar)

    w1 = c.resolve(IFoo)  # type: ignore[arg-type]
    w2 = c.resolve(IBar)  # type: ignore[arg-type]
    assert w1 is w2  # same singleton instance
    assert isinstance(w1, MyWidget)


@fact
def register_singleton_with_provides_adopts_singleton_lifetime():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        def __init__(self):
            pass

    c = Container()
    c.register_singleton(MyClass)

    w1 = c.resolve(IFoo)  # type: ignore[arg-type]
    w2 = c.resolve(IFoo)  # type: ignore[arg-type]
    assert w1 is w2


@fact
def register_transient_with_provides_multi_registers():
    """Transient multi-registration creates new instances for each resolve."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyClass:
        def __init__(self):
            self.value = 'a'

    c = Container()
    c.register_transient(MyClass)

    assert c.is_registered(IFoo)
    assert c.is_registered(IBar)
    assert c.is_registered(MyClass)

    w1 = c.resolve(IFoo)  # type: ignore[arg-type]
    w2 = c.resolve(IBar)  # type: ignore[arg-type]
    assert isinstance(w1, MyClass)
    assert isinstance(w2, MyClass)


@fact
def register_transient_with_provides_creates_new_instances():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        def __init__(self):
            self.value = 'a'

    c = Container()
    c.register_transient(MyClass)

    w1 = c.resolve(IFoo)  # type: ignore[arg-type]
    w2 = c.resolve(IFoo)  # type: ignore[arg-type]
    assert isinstance(w1, MyClass)
    assert w1 is not w2



@fact
def provides_without_lifecycle_decorator_via_mutations_works():
    """Standalone @provides works when registered via mutation methods."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class StandaloneClass:
        def __init__(self):
            self.value = 'standalone'

    c = Container()
    c.register_singleton(StandaloneClass)

    f = c.resolve(IFoo)  # type: ignore[arg-type]
    assert isinstance(f, StandaloneClass)


@fact
def register_singleton_without_provides_unchanged_behavior():

    class PlainWidget:
        def __init__(self):
            self.value = 'plain'

    c = Container()
    c.register_singleton(PlainWidget)

    w = c.resolve(PlainWidget)  # type: ignore[arg-type]
    assert isinstance(w, PlainWidget)


@fact
@fails(reason='unsupported registration, regression test.')
def register_decorated_does_not_support_provides_because_it_would_be_ambiguous_for_singleton():
    """@singleton + @provides is incompatible; error fires at decoration time."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IBar)
    class MyClass:
        def __init__(self) -> None:
            self.value = 'composed'

    singleton(types=IFoo)(MyClass),  # type: ignore[arg-type]


@fact
@fails(reason='unsupported registration, regression test.')
def register_decorated_does_not_support_provides_because_it_would_be_ambiguous_for_transient():
    """@transient + @provides is incompatible; error fires at decoration time."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IBar)
    class MyClass:
        def __init__(self) -> None:
            self.value = 'composed'

    transient(types=IFoo)(MyClass),  # type: ignore[arg-type]


@fact
@fails(reason='unsupported registration, regression test.')
def register_decorated_does_not_support_provides_because_it_would_be_ambiguous_for_instanced():
    """@instanced + @provides is incompatible; error fires at decoration time."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IBar)
    class MyClass:
        def __init__(self) -> None:
            self.value = 'composed'

    instanced(types=IFoo)(MyClass),  # type: ignore[arg-type]


@fact
def register_singleton_without_provides_does_not_mutate_target():
    """register_singleton on concrete class without @provides works as before."""

    class MyClass:
        def __init__(self):
            self.value = 'plain'

    c = Container()
    c.register_singleton(MyClass)

    m1 = c.resolve(MyClass)  # type: ignore[arg-type]
    m2 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert m1 is m2  # singleton


@fact
def provides_empty_is_backward_compatible():

    @provides()
    class EmptyMarker:
        def __init__(self):
            self.value = 'empty'

    c = Container()
    c.register_singleton(EmptyMarker)

    m = c.resolve(EmptyMarker)  # type: ignore[arg-type]
    assert isinstance(m, EmptyMarker)


@fact
def provides_does_not_set_lifecycle_attribute():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        pass

    assert not hasattr(MyClass, '__hazrakah_lifecycle')


@fact
def provides_with_single_interface_registers_under_it():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class OneInterface:
        def __init__(self):
            self.value = 'one'

    c = Container()
    c.register_singleton(OneInterface)

    f = c.resolve(IFoo)  # type: ignore[arg-type]
    assert isinstance(f, OneInterface)


@fact
def provides_with_fluent_chaining_works():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class Widget:
        def __init__(self):
            self.value = 'chain'

    c = (
        Container()
        .register_singleton(Widget)
        .register_transient(str)
    )

    assert c.is_registered(IFoo)
    assert c.is_registered(IBar)


@fact
def provides_without_lifetime_decorator_must_not_crash_register_decorated():
    """Orphan @provides (no lifecycle decorator) is safe during register_decorated."""
    _reset_decorations()

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class OrphanClass:
        def __init__(self):
            self.value = 'orphan'

    c = Container()
    # Should complete without raising.
    c.register_decorated()


@fact
def provides_stored_as_tuple_not_list():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        pass

    prov = getattr(MyClass, '__hazrakah_provides')
    assert type(prov) is tuple  # noqa: E721


@fact
def provides_with_instance_lifetime_adopts_correct_lifetime_for_instance():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        def __init__(self):
            self.value = 'instance'

    instance1 = MyClass()
    instance2 = MyClass()
    c = Container()
    c.register_instance(instance1)

    # Resolving IFoo returns the registered instance.
    r1 = c.resolve(IFoo)  # type: ignore[arg-type]
    r2 = c.resolve(IFoo)  # type: ignore[arg-type]
    r3 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert r1 is r2, 'expected multi-resolve to yield same instance.'
    assert r1 is r3, 'expected MyClass to resolve to same instance.'
    # A new register_instance call overwrites.
    c.register_instance(instance2)
    r4 = c.resolve(IFoo)  # type: ignore[arg-type]
    r5 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert r1 is not r4, 'expected new IFoo reg.'
    assert r3 is not r5, 'expected new MyClass reg..'


@fact
def provides_with_instance_lifetime_adopts_correct_lifetime_for_type():

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        def __init__(self):
            self.value = 'instance'

    @provides(IFoo)
    class MyOtherClass:
        def __init__(self):
            self.value = 'instance'

    c = Container()
    c.register_instance(MyClass)

    # Resolving IFoo returns the registered instance.
    r1 = c.resolve(IFoo)  # type: ignore[arg-type]
    r2 = c.resolve(IFoo)  # type: ignore[arg-type]
    r3 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert r1 is r2, 'expected multi-resolve to yield same instance.'
    assert r1 is r3, 'expected MyClass to resolve to same instance.'
    # A new register_instance call overwrites.
    c.register_instance(MyOtherClass)
    r4 = c.resolve(IFoo)  # type: ignore[arg-type]
    r5 = c.resolve(MyOtherClass)  # type: ignore[arg-type]
    assert r1 is not r4, 'expected new IFoo reg.'
    assert r3 is not r5, 'expected new MyClass reg..'


@fact
def provides_registers_under_both_t_and_extra_interfaces():
    """Provides interfaces AND the decorated class are all registered."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IBar)
    class MyClass:
        def __init__(self):
            self.value = 'dual'

    c = Container()
    c.register_singleton(MyClass)

    # MyClass itself should also be registered (as primary key).
    assert c.is_registered(MyClass)
    assert c.is_registered(IBar)

    m = c.resolve(MyClass)  # type: ignore[arg-type]
    b = c.resolve(IBar)  # type: ignore[arg-type]
    assert m is b  # same singleton (target=MyClass cached under MyClass key)


@fact
def provides_with_no_args_is_backward_compatible():

    @provides()
    class EmptyMarker:
        def __init__(self):
            self.value = 'empty'

    c = Container()
    c.register_singleton(EmptyMarker)

    m = c.resolve(EmptyMarker)  # type: ignore[arg-type]
    assert isinstance(m, EmptyMarker)
    assert m.value == 'empty'


@fact
def provides_singleton_shares_across_scopes_and_types():
    """Singletons from @provides are shared across scopes."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyClass:
        def __init__(self):
            self.value = 'scoped'

    parent = Container()
    parent.register_singleton(MyClass)

    child = parent.create_scope()
    f1 = parent.resolve(IFoo)  # type: ignore[arg-type]
    b1 = parent.resolve(IBar)  # type: ignore[arg-type]
    f2 = child.resolve(IFoo)  # type: ignore[arg-type]
    b2 = child.resolve(IBar)  # type: ignore[arg-type]

    assert f1 is f2
    assert b1 is b2
    assert f1 is b1


@fact
def provides_on_singleton_decorated_class_raises():
    """regression: @provides on an already-@singleton class must raise."""
    _reset_decorations()

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @singleton(types=IFoo)  # noqa: F811
    class AlreadySingleton:
        pass

    try:
        provides(IFoo)(AlreadySingleton)  # type: ignore[arg-type]
        assert False, 'Should have raised RegistrationError'
    except RegistrationError as exc:
        assert 'cannot apply' in str(exc).lower()


@fact
def clear_store_resets_manager():
    """regression: _clear_store() resets the manager for fresh registration."""
    _reset_decorations()

    class IFooClear:
        pass

    @singleton(types=IFooClear)  # noqa: F811
    class TempClass:
        pass

    assert IFooClear in [e.interface for e in _DecorationInfoManager.instance().get_all()]

    _reset_decorations()
    assert not _DecorationInfoManager.instance().get_all()

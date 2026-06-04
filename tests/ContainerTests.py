# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import ABC
from hazrakah import Container, DependencyResolver
from typing import Optional, Protocol, TypeVar
from punit import fact
from punit.assertions.exceptions import raises

_T = TypeVar('_T')


class ProtocolDroid(Protocol):
    ...


class IService(ABC):
    """Abstract service interface used for registration tests."""
    ...


class ServiceA(IService):
    """Concrete implementation of ``IService`` with no dependencies."""

    def __init__(self) -> None:
        self.id: int = 1


class ServiceB(IService):
    """Concrete implementation that depends on ``ServiceA``."""

    def __init__(self, a: ServiceA) -> None:
        self.dependency: ServiceA = a


class ServiceC(IService):
    """Concrete implementation that depends on ``ServiceB``, but is not itself registered to the container."""

    def __init__(self, b: ServiceB) -> None:
        self.dependency: ServiceB = b


class ClassHavingDefaultInit:

    def foo(self) -> None:
        assert True


def __factory_without_resolver() -> ServiceA:
    """Factory deliberately missing the required ``Container`` argument."""
    return ServiceA()


def __factory_with_resolver(_resolver: DependencyResolver) -> ServiceA:
    """Correctly-typed factory that returns a new ``ServiceA``."""
    return ServiceA()


@fact
def register_instance_resolves_instance() -> None:
    """``register_instance`` stores the instance and ``resolve`` returns it."""
    container: Container = Container()
    instance: ServiceA = ServiceA()
    container.register_instance(IService, instance)

    resolved: IService = container.resolve(IService)
    assert resolved is instance, 'Resolved instance should be the same object that was registered.'


@fact
def when_incorrect_type_then_raises_TypeError() -> None:
    """A ``TypeError`` is raised when the instance does not match the abstract."""
    container: Container = Container()
    wrong_instance = Container()

    assert raises[TypeError](
        lambda: container.register_instance(IService, wrong_instance)
    ), 'Expected TypeError when registering a mismatched instance.'


@fact
def singleton_registrations_must_memoize() -> None:
    """A ``SINGLETON`` registration yields the same object for every ``resolve``."""
    container: Container = Container()
    container.register_singleton(IService, ServiceA)

    first: IService = container.resolve(IService)
    second: IService = container.resolve(IService)

    assert first is second, 'Singleton services must be cached and reused.'


@fact
def transient_registrations_must_not_memoize() -> None:
    """A ``TRANSIENT`` registration creates a fresh object on each call."""
    container: Container = Container()
    container.register_transient(IService, ServiceA)

    first: IService = container.resolve(IService)
    second: IService = container.resolve(IService)

    assert first is not second, 'Transient services must not be cached.'
    assert isinstance(first, ServiceA) and isinstance(second, ServiceA)


@fact
def singleton_is_global_across_scopes() -> None:
    """A SINGLETON registration returns the same instance across parent and child scopes."""
    outer_scope: Container = Container()
    inner_scope: Container = outer_scope.create_scope()
    outer_scope.register_singleton(IService, ServiceA)
    outer_scope_instance: IService = outer_scope.resolve(IService)
    inner_scope_instance: IService = inner_scope.resolve(IService)
    assert outer_scope_instance is inner_scope_instance, 'Singleton should be shared across scopes'


@fact
def scopes_must_resolve_non_scoped_registration_from_outer() -> None:
    """A scoped container falls back to its outer_scope for non-scoped registrations."""
    outer_scope: Container = Container()
    inner_scope: Container = outer_scope.create_scope()

    outer_scope.register_singleton(IService, ServiceA)   # not scoped
    # inner_scope does *not* register anything for ``IService``

    outer_scope_obj: IService = outer_scope.resolve(IService)
    inner_scope_obj: IService = inner_scope.resolve(IService)

    # Because the registration is not scoped, the inner scope delegates to the outer scope.
    assert inner_scope_obj is outer_scope_obj
    assert isinstance(inner_scope_obj, ServiceA)


@fact
def nonexistent_registration_when_concrete_must_succeed() -> None:
    class UnregisteredExplosive:
        attr1: int

        def __init(self) -> None:
            self.attr1 = 1
    container = Container()
    obj = container.resolve(UnregisteredExplosive)
    assert obj is not None


@fact
def nonexistent_registration_when_abstract_must_fail() -> None:
    """Attempting to resolve an unregistered abstract raises ``KeyError``."""
    container: Container = Container()

    assert raises[KeyError](
        lambda: container.resolve(IService),
        exact=True
    ), 'Expected KeyError for an unknown registration of an abstract type.'


@fact
def nonexistent_registration_when_protocol_must_fail() -> None:
    """Attempting to resolve an unregistered abstract raises ``KeyError``."""
    container: Container = Container()

    assert raises[KeyError](
        lambda: container.resolve(ProtocolDroid),
        exact=True
    ), 'Expected KeyError for an unknown registration of an abstract type.'


@fact
def factories_must_resolve_successfully() -> None:
    """A well-typed factory is invoked and its product is returned."""
    container: Container = Container()
    container.register_transient(IService, __factory_with_resolver)

    result: IService = container.resolve(IService)
    assert isinstance(result, ServiceA), 'Factory should produce a ServiceA instance.'


@fact
def type_when_default_init_then_must_succeed() -> None:
    """confirm that a type with a default initializer does not result in failure"""
    container: Container = Container()
    _ = container.resolve(ClassHavingDefaultInit)


@fact
def child_overrides_non_scoped_registrations() -> None:
    """
    confirm that a child scope that registers its own transient, singleton, or
    instance will use its own registration, not the parent's.
    """
    class ChildServiceA(ServiceA):
        pass

    parent = Container()
    child = parent.create_scope()

    # Parent registers a transient implementation of IService.
    parent.register_transient(IService, ServiceA)
    parent_instance = parent.resolve(IService)

    # Child registers *its own* transient implementation (different class).
    child.register_transient(IService, ChildServiceA)
    child_inst1 = child.resolve(IService)
    child_inst2 = child.resolve(IService)

    # Expectations:
    assert child_inst1 is not child_inst2, 'child transient should create a new object each resolve'
    assert child_inst1 is not parent_instance, 'child transient must not reuse the parents instance'

    class ChildSingleton(ServiceA):
        pass

    parent.register_singleton(IService, ServiceA)
    parent_singleton = parent.resolve(IService)

    child.register_singleton(IService, ChildSingleton)
    child_single1 = child.resolve(IService)

    parent_singleton2 = parent.resolve(IService)

    assert child_single1 is not parent_singleton, 'singleton instances are expected to allow shadowing'
    assert parent_singleton is parent_singleton2, 'singletons must remain stable/consistent even when shadowed in child scopes'

    class ChildInstance(ServiceA):
        pass

    parent_instance_obj = ServiceA()
    child_instance_obj = ChildInstance()

    parent.register_instance(IService, parent_instance_obj)
    child.register_instance(IService, child_instance_obj)

    resolved_child = child.resolve(IService)
    resolved_parent = parent.resolve(IService)

    assert resolved_child is child_instance_obj, 'child instance registration must be returned'
    assert resolved_child is not resolved_parent, 'child instance must not resolve to the parents instance'


@fact
def test_hierarchical_singletons() -> None:
    """Verify that singleton registrations respect container hierarchy.

    * A singleton registered in a parent container should be resolved from any child.
    * A singleton registered in a child container should be cached in that child and not be visible to the parent.
    """

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class Foo:
        def foo(self) -> None:
            pass

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    class Bar:
        def bar(self) -> None:
            pass

    parent = Container()
    child = Container(outer_scope=parent)

    # Register singleton in parent
    parent.register_singleton(IFoo, Foo)
    # Resolve from both parent and child – should be the same instance
    foo_parent = parent.resolve(IFoo)
    foo_child = child.resolve(IFoo)
    assert foo_parent is foo_child, 'Singleton from parent should be shared across child scopes'

    # Register a different singleton in child
    child.register_singleton(IBar, Bar)
    bar_child_first = child.resolve(IBar)
    bar_child_second = child.resolve(IBar)
    assert bar_child_first is bar_child_second, 'Singleton in child should be cached within child'
    # Parent should not resolve IBar
    try:
        parent.resolve(IBar)
    except KeyError:
        pass
    else:
        raise AssertionError('Parent container should not resolve child-registered singleton')


@fact
def optional_types_must_resolve() -> None:
    class EthicalNarrative:
        cracked_wheat: object | None

        def __init__(self, lumnum: Optional[object] = None) -> None:
            self.cracked_wheat = lumnum
    container = Container()
    obj = container.resolve(EthicalNarrative)
    assert obj is not None
    assert obj.cracked_wheat is not None


@fact
def unresolvable_optional_types_must_resolve_none() -> None:
    class BadCop:
        def __init__(self) -> None:
            raise Exception('robble, robble, robble')

    class GoodCop:
        cracked_wheat: object | None

        def __init__(self, lumnum: Optional[BadCop] = None) -> None:
            self.cracked_wheat = lumnum
    container = Container()
    obj = container.resolve(GoodCop)
    assert obj is not None
    assert obj.cracked_wheat is None

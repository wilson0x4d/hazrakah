# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import ABC
from hazrakah import (
    Container,
    DependencyRegistry,
    DependencyResolver,
    RegistrationError,
    ResolutionError,
    ScopedDependencyResolver,
    Target,
    provides,
)
from typing import Any, Optional, Protocol, Type, TypeVar, runtime_checkable
from punit import fact
from punit.assertions.exceptions import raises

_T = TypeVar('_T')


@runtime_checkable
class ProtocolDroid(Protocol):

    def optimus(self) -> None:
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
    """Attempting to resolve an unregistered abstract raises ``ResolutionError``."""
    container: Container = Container()

    assert raises[ResolutionError](
        lambda: container.resolve(IService),
        exact=True
    ), 'Expected ResolutionError for an unknown registration of an abstract type.'


@fact
def nonexistent_registration_when_protocol_must_fail() -> None:
    """Attempting to resolve an unregistered Protocol raises ``ResolutionError``."""
    container: Container = Container()

    assert raises[ResolutionError](
        lambda: container.resolve(ProtocolDroid),  # type: ignore[type-abstract]
        exact=True
    ), 'Expected ResolutionError for an unknown registration of a Protocol type.'


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
def proto_subclass_no_init_must_resolve() -> None:
    """confirm that a type extending a proto, and having a default initializer, does not result in failure"""

    @runtime_checkable
    class PSNIMR(Protocol):
        def foo(self) -> None:
            ...

    class PSNI(PSNIMR):
        def foo(self) -> None:  # type: ignore[missing-override-decorator]
            pass

    container = Container()
    container.register_transient(PSNIMR, PSNI)
    obj = container.resolve(PSNIMR)  # type: ignore[type-abstract]
    assert obj is not None


@fact
def unregistered_proto_subclass_no_init_must_resolve() -> None:
    """confirm that a type extending a proto, and having a default initializer, does not result in failure"""

    @runtime_checkable
    class UPSNIMR(Protocol):
        def foo(self) -> None:
            ...

    class UPSNI(UPSNIMR):
        def foo(self) -> None:  # type: ignore[missing-override-decorator]
            pass

    container = Container()
    obj = container.resolve(UPSNI)
    assert obj is not None


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
    # Resolve from both parent and child - should be the same instance
    foo_parent = parent.resolve(IFoo)  # type: ignore[type-abstract]
    foo_child = child.resolve(IFoo)  # type: ignore[type-abstract]
    assert foo_parent is foo_child, 'Singleton from parent should be shared across child scopes'

    # Register a different singleton in child
    child.register_singleton(IBar, Bar)
    bar_child_first = child.resolve(IBar)  # type: ignore[type-abstract]
    bar_child_second = child.resolve(IBar)  # type: ignore[type-abstract]
    assert bar_child_first is bar_child_second, 'Singleton in child should be cached within child'
    # Parent should not resolve IBar
    try:
        parent.resolve(IBar)  # type: ignore[type-abstract]
    except ResolutionError:
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


IFoo = IService | ServiceA  # union type alias: IService | ServiceA
IBar = IService | ServiceB  # union type alias: IService | ServiceB


@fact
def non_optional_union_with_single_match_resolves() -> None:
    """A union with exactly one registered member resolves to it."""
    container: Container = Container()
    container.register_transient(IService, ServiceA)
    resolved = container.resolve(IService | ServiceA)  # type: ignore[arg-type]
    assert isinstance(resolved, ServiceA), 'Should resolve to the single registered implementation'


@fact
def non_optional_union_with_no_match_raises_resolution_error() -> None:
    """A union with no registrations and all abstract members raises ResolutionError."""
    container: Container = Container()

    class IFake1(ABC):
        def do_something(self) -> int:
            return 1

    class IFake2(ABC):
        def do_other(self) -> str:
            return 'one'

    assert raises[ResolutionError](
        lambda: container.resolve(IFake1 | IFake2),  # type: ignore[arg-type]
        exact=True
    ), 'Expected ResolutionError for an unknown union of abstract types.'


@fact
def non_optional_union_with_multiple_different_targets_raises() -> None:
    """A union with two different concrete targets raises ResolutionError."""
    container: Container = Container()
    container.register_transient(IService, ServiceA)
    container.register_singleton(ServiceA, ServiceB)

    assert raises[ResolutionError](
        lambda: container.resolve(IService | ServiceA),  # type: ignore[arg-type]
        exact=True
    ), 'Expected ResolutionError for a union with multiple registered implementations.'


@fact
def non_optional_union_auto_resolves_concrete_member() -> None:
    """If one member is concrete and unregistered, it auto-registers silently."""
    container: Container = Container()
    container.register_transient(IService, ServiceA)
    resolved = container.resolve(IService | ServiceB)  # type: ignore[arg-type]
    assert isinstance(resolved, ServiceB), 'Should auto-resolve the concrete unregistered member'


@fact
def union_with_pep695_alias_in_error_message_works_on_312_plus() -> None:
    """Named type aliases set __name__, giving clean error messages on 3.12+."""
    container: Container = Container()

    class IFakeA(ABC):
        def x(self) -> int:
            return 2

    class IFakeB(ABC):
        def y(self) -> str:
            return 'two'

    assert raises[ResolutionError](
        lambda: container.resolve(IFakeA | IFakeB),  # type: ignore[arg-type]
        exact=True
    )


@fact
def union_optional_types_still_work() -> None:
    """Optional[T] unions should still work as before (regression guard)."""
    container: Container = Container()

    class WithOptional:
        value: object | None

        def __init__(self, opt: Optional[ServiceA] = None) -> None:
            self.value = opt

    obj = container.resolve(WithOptional)
    assert obj is not None, 'resolve should succeed'


@fact
def union_both_unregistered_concrete_resolves_first() -> None:
    """When both members are concrete and unregistered, resolves first one."""
    container: Container = Container()

    class ConcreteA:
        def __init__(self) -> None:
            self.tag = 'A'

    class ConcreteB:
        def __init__(self) -> None:
            self.tag = 'B'

    resolved = container.resolve(ConcreteA | ConcreteB)  # type: ignore[arg-type]
    assert isinstance(resolved, ConcreteA), 'Should resolve the first concrete member'

    """`is_registered` should reflect registrations in the current container and its ancestors."""
    base: Container = Container()
    assert not base.is_registered(IService), 'Unregistered type should return False'
    base.register_transient(IService, ServiceA)
    assert base.is_registered(IService), 'After transient registration, should be True'
    child: Container = base.create_scope()
    assert child.is_registered(IService), 'Child should inherit registration visibility from parent'
    child.register_singleton(IService, ServiceB)
    assert child.is_registered(IService), 'Child sees its own registration as True'
    assert base.is_registered(IService), 'Parent registration status remains True after child registers'

    class DummyDroid(ProtocolDroid):
        """Simple concrete class implementing ProtocolDroid (which has no members)."""

        def optimus(self) -> None:  # type: ignore[missing-override-decorator]
            pass

    child.register_instance(ProtocolDroid, DummyDroid())
    assert child.is_registered(ProtocolDroid), 'Child should report its own instance registration'
    assert not base.is_registered(ProtocolDroid), 'Parent should not see child-only registration'


@fact
def register_instance_returns_self() -> None:
    """register_instance returns self, enabling chaining."""
    container: Container = Container()
    instance: ServiceA = ServiceA()
    result = container.register_instance(IService, instance)
    assert result is container, 'register_instance should return self'


@fact
def register_instance_when_imlicit_type():
    """implicit bindings (those without an explicit type arg) should bing to type(obj) + ``@provides`` types."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    instance = MyClass()
    c = Container()
    c.register_instance(instance)

    assert c.is_registered(IFoo)
    assert c.is_registered(IBar)
    assert c.is_registered(MyClass)

    r1 = c.resolve(IFoo)  # type: ignore[arg-type]
    r2 = c.resolve(IBar)  # type: ignore[arg-type]
    r3 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert r1 is instance
    assert r2 is instance
    assert r3 is instance


@fact
def register_instance_when_explicit_type():
    """binding to an explcit type must only register the for type specified."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    instance = MyClass()
    c = Container()
    c.register_instance(IFoo, instance)

    assert c.is_registered(IFoo)
    assert not c.is_registered(IBar)

    r1 = c.resolve(IFoo)  # type: ignore[arg-type]
    assert r1 is instance


@fact
def register_singleton_returns_self() -> None:
    """register_singleton returns self, enabling chaining."""
    container: Container = Container()
    result = container.register_singleton(IService, ServiceA)
    assert result is container, 'register_singleton should return self'


@fact
def register_singleton_when_implicit_type():
    """implicit bindings (those without an explicit type arg) should bing to ``target`` type + ``@provides`` types."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    c = Container()
    c.register_singleton(MyClass)

    assert c.is_registered(IFoo)
    assert c.is_registered(IBar)
    assert c.is_registered(MyClass)

    r1 = c.resolve(IFoo)  # type: ignore[arg-type]
    r2 = c.resolve(IBar)  # type: ignore[arg-type]
    r3 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert r1 is not None
    assert r2 is not None
    assert r3 is not None


@fact
def register_singleton_when_exlicit_type():
    """binding to an explcit type must only register the for type specified."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IBar)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    c = Container()
    c.register_singleton(IFoo, MyClass)

    assert c.is_registered(IFoo), 'explicit registration for IFoo only.'
    assert not c.is_registered(IBar), 'explicit registrations do not incorporate `@provides` types.'

    r1 = c.resolve(IFoo)
    assert r1 is not None
    assert raises[KeyError](lambda: c.resolve(IBar))


@fact
def register_singleton_with_provides_same_interface_ignores_marker():
    """when @provides declares the same interface as the explicit registration key,
    ``@provides`` must still be ignored. only the explicitly registered type gets a binding.

    this is the 'identity case' gap test: it confirms that even when the provided type
    equals the registration key passed to register_*, no extra or duplicate registrations
    occur from ``@provides`` metadata -- because explicit registrations completely bypass
    the ``@provides`` discovery path.
    """

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    @provides(IFoo)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    c = Container()
    # Explicit registration for the same interface that @provides declares.
    c.register_singleton(IFoo, MyClass)

    # IFoo is registered (from the explicit registration).
    assert c.is_registered(IFoo), 'IFoo should be registered via the explicit argument.'

    # MyClass itself must NOT be auto-registered -- when target is provided,
    # @provides metadata is completely bypassed per design.
    assert not c.is_registered(MyClass), 'MyClass should NOT be auto-registered when an explicit type arg is provided; @provides only activates with no explicit type argument.'

    r1 = c.resolve(IFoo)
    assert r1 is not None
    assert isinstance(r1, MyClass)


@fact
def register_transient_returns_self() -> None:
    """register_transient returns self, enabling chaining."""
    container: Container = Container()
    result = container.register_transient(IService, ServiceA)
    assert result is container, 'register_transient should return self'


@fact
def register_transient_when_implicit_type():
    """implicit bindings (those without an explicit type arg) should bing to ``target`` type + ``@provides`` types."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IFoo, IBar)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    c = Container()
    c.register_transient(MyClass)

    assert c.is_registered(IFoo)
    assert c.is_registered(IBar)
    assert c.is_registered(MyClass)

    r1 = c.resolve(IFoo)  # type: ignore[arg-type]
    r2 = c.resolve(IBar)  # type: ignore[arg-type]
    r3 = c.resolve(MyClass)  # type: ignore[arg-type]
    assert r1 is not None
    assert r2 is not None
    assert r3 is not None


@fact
def register_transient_when_explicit_type():
    """binding to an explcit type must only register the for type specified."""

    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> None:
            ...

    @provides(IBar)
    class MyClass:
        def __init__(self):
            self.value = 'x'

    c = Container()
    c.register_transient(IFoo, MyClass)

    assert c.is_registered(IFoo), 'explicit registration for IFoo only.'
    assert not c.is_registered(IBar), 'explicit registrations do not incorporate `@provides` types.'

    r1 = c.resolve(IFoo)
    assert r1 is not None
    assert raises[KeyError](lambda: c.resolve(IBar))


@fact
def register_transient_when_instance_target():
    """Attempting to register an object instance via `register_transient` should fail."""
    c = Container()
    assert raises[RegistrationError](lambda: c.register_transient(IService, ServiceA()))  # type: ignore
    assert not c.is_registered(IService), 'registration should have been blocked.'
    assert raises[KeyError](lambda: c.resolve(IService)), 'instance should not be resolvable.'


@fact
def chained_registrations_all_resolve() -> None:
    """A chain of registration methods correctly registers every type."""
    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class Foo:
        def foo(self) -> None:
            ...

    class IBar(Protocol):
        def bar(self) -> str:
            ...

    class Bar:
        def bar(self) -> str:
            return 'bar'

    container: Container = Container()
    iservice_instance: ServiceA = ServiceA()

    (container
     .register_transient(IFoo, Foo)
     .register_singleton(IBar, Bar)
     .register_instance(IService, iservice_instance))

    resolved_ifoo: IFoo = container.resolve(IFoo)  # type: ignore[type-abstract]
    assert isinstance(resolved_ifoo, Foo), 'transient registration should resolve via chain'

    resolved_ibar: IBar = container.resolve(IBar)  # type: ignore[type-abstract]
    assert isinstance(resolved_ibar, Bar), 'singleton registration should resolve via chain'

    resolved_iservice: IService = container.resolve(IService)
    assert resolved_iservice is iservice_instance, 'instance registration should resolve via chain'


@fact
def singleton_singleton_via_chain_memoizes() -> None:
    """Singleton registrations within a chain memoize correctly."""
    container: Container = Container()
    container.register_singleton(IService, ServiceA).register_transient(IService, ServiceB)

    # The last registration wins (IService now maps to ServiceB transiently)
    first: IService = container.resolve(IService)
    second: IService = container.resolve(IService)
    assert first is not second, 'Last registration should override previous ones'


@fact
def mixed_chain_across_scopes_shares_singletons() -> None:
    """Singleton registrations in a parent chain are shared by child scopes."""
    class IFoo(Protocol):
        def foo(self) -> None:
            ...

    class Foo:
        def foo(self) -> None:
            ...

    parent: Container = Container()
    child: Container = parent.create_scope()

    (parent
     .register_singleton(IFoo, Foo)
     .register_transient(IService, ServiceA))

    parent_foo: IFoo = parent.resolve(IFoo)  # type: ignore[type-abstract]
    child_foo: IFoo = child.resolve(IFoo)  # type: ignore[type-abstract]
    assert parent_foo is child_foo, 'Singleton from parent should be shared across scopes via chain'


@fact
def register_decorated_returns_self() -> None:
    """register_decorated returns self for chaining."""
    from hazrakah.lifetime_decorators import _DecorationInfoManager

    # Reset to avoid interference from prior tests
    manager = _DecorationInfoManager.instance()
    manager.get_all()  # warm up if needed
    result = Container().register_decorated()
    assert isinstance(result, Container), 'register_decorated should return self'


@fact
def resolve_dependency_registry_returns_self() -> None:
    """"Resolving for ``DependencyRegistry`` returns the container itself."""

    c1: Container = Container()
    result: DependencyRegistry = c1.resolve(DependencyRegistry)  # type: ignore[arg-type, type-abstract]
    assert result is c1, 'resolve(DependencyRegistry) should return self'


@fact
def resolve_dependency_resolver_returns_self() -> None:
    """Resolving for ``DependencyResolver`` returns the container itself."""

    c1: Container = Container()
    result: DependencyResolver = c1.resolve(DependencyResolver)  # type: ignore[arg-type, type-abstract]
    assert result is c1, 'resolve(DependencyResolver) should return self'


@fact
def resolve_scoped_dependency_resolver_returns_self() -> None:
    """Resolving for ``ScopedDependencyResolver`` returns the container itself."""

    c1: Container = Container()
    result: ScopedDependencyResolver = c1.resolve(ScopedDependencyResolver)  # type: ignore[arg-type, type-abstract]
    assert result is c1, 'resolve(ScopedDependencyResolver) should return self'


@fact
def resolve_interface_types_are_idempotent() -> None:
    """Every resolve of the same interface returns the identical container."""

    c = Container()

    r1: DependencyRegistry = c.resolve(DependencyRegistry)  # type: ignore[arg-type, type-abstract]
    r2: DependencyRegistry = c.resolve(DependencyRegistry)  # type: ignore[arg-type, type-abstract]
    assert r1 is r2, 'Should return the same object on every resolve'

    r3: DependencyResolver = c.resolve(DependencyResolver)  # type: ignore[arg-type, type-abstract]
    assert r1 is r3


@fact
def resolve_interface_type_can_be_used_as_dependency() -> None:
    """"A class depending on ``DependencyResolver`` gets injected the container."""

    class IDependent(Protocol):
        def start(self) -> None:
            ...

    class DependentImpl:
        def __init__(self, resolver: DependencyResolver) -> None:  # type: ignore[arg-type]
            self.resolver = resolver

        def start(self) -> None:
            assert isinstance(self.resolver, Container)

    c = Container()
    obj: IDependent = c.resolve(DependentImpl)
    obj.start()


@fact
def resolve_interface_type_can_be_used_as_scoped_dependency() -> None:
    """"A class depending on ``ScopedDependencyResolver`` gets injected the container."""

    class IScopedDependent(Protocol):
        def build_scope(self) -> ScopedDependencyResolver:
            ...

    class ScopedDependentImpl:
        def __init__(self, resolver: ScopedDependencyResolver) -> None:  # type: ignore[arg-type]
            self.resolver = resolver

        def build_scope(self) -> ScopedDependencyResolver:
            return self.resolver.create_scope()

    c = Container()
    obj = c.resolve(ScopedDependentImpl)
    scope = obj.build_scope()
    assert scope is not None


@fact
def resolve_interface_type_in_scopes_is_same_as_parent() -> None:
    """Resolving an interface type in a child scope returns the parent container."""

    parent = Container()
    parent.register_instance(IService, ServiceA())
    child = parent.create_scope()

    parent_result = parent.resolve(IService)  # type: ignore[arg-type]
    child_result = child.resolve(IService)  # type: ignore[arg-type]

    assert parent_result is child_result, 'Child scope should return the same container for interface types'


@fact
def resolve_interface_type_with_explicit_instance_registration() -> None:
    """When an explicit instance is registered, that instance wins over self-return."""

    class FakeRegistry(DependencyRegistry):
        def resolve(self, t: Type[Any]) -> Any:  # type: ignore
            ...

        def is_registered(self, t: Type[Any]) -> bool:  # type: ignore
            ...

        def register_instance(self, t: Type[Any], instance: Any) -> DependencyRegistry:  # type: ignore
            ...

        def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = None) -> DependencyRegistry:  # type: ignore
            ...

        def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> DependencyRegistry:  # type: ignore
            ...

    c = Container()
    fake = FakeRegistry()
    c.register_instance(DependencyResolver, fake)

    result: DependencyResolver = c.resolve(DependencyResolver)  # type: ignore[arg-type, type-abstract]
    assert result is fake, 'Explicit instance registration should take precedence'


# ── self_resolve=False tests ────────────────────────────────────────────────────


@fact
def resolve_interface_fails_when_self_resolve_false() -> None:
    """Resolving for a DI interface raises ResolutionError when self_resolve is disabled."""

    c = Container(self_resolve=False)

    assert raises[ResolutionError](lambda: c.resolve(DependencyRegistry))  # type: ignore[arg-type, type-abstract]
    assert raises[ResolutionError](lambda: c.resolve(DependencyResolver))  # type: ignore[arg-type, type-abstract]
    assert raises[ResolutionError](lambda: c.resolve(ScopedDependencyResolver))  # type: ignore[arg-type, type-abstract]


@fact
def explicit_registration_overrides_self_resolve_false() -> None:
    """An explicit registration for a DI interface still resolves even when self_resolve=False."""

    class FakeRegistry(DependencyRegistry):
        def resolve(self, t: Type[Any]) -> Any: ...  # type: ignore
        def is_registered(self, t: Type[Any]) -> bool: ...  # type: ignore
        def register_instance(self, t: Type[Any], instance: Any) -> DependencyRegistry: ...  # type: ignore
        def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = None) -> DependencyRegistry: ...  # type: ignore
        def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> DependencyRegistry: ...  # type: ignore

    c = Container(self_resolve=False)
    fake = FakeRegistry()
    c.register_instance(DependencyResolver, fake)

    result: DependencyResolver = c.resolve(DependencyResolver)  # type: ignore[arg-type, type-abstract]
    assert result is fake


@fact
def normal_resolves_unaffected_by_self_resolve_false() -> None:
    """Non-DI resolves continue to work normally when self_resolve=False."""

    class Foo:
        def bar(self) -> int:
            return 42

    c = Container(self_resolve=False)
    c.register_transient(Foo)

    obj = c.resolve(Foo)
    assert isinstance(obj, Foo)
    assert obj.bar() == 42

    assert raises[ResolutionError](
        lambda: c.resolve(DependencyResolver),  # type: ignore[arg-type, type-abstract]
        exact=True,
    )


@fact
def resolve_all_three_interfaces_fail_when_self_resolve_false() -> None:
    """All three interface types fail with self_resolve=False."""

    c = Container(self_resolve=False)

    for iface in (DependencyRegistry, DependencyResolver, ScopedDependencyResolver):  # type: ignore[arg-type]
        assert raises[ResolutionError](
            lambda i=iface: c.resolve(i),  # type: ignore[misc]
            exact=True,
        )

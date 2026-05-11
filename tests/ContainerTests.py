# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import ABC
from hazrakah import Container
from typing import TypeVar
from punit import fact
from punit.assertions.exceptions import raises

_T = TypeVar('_T')


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


def __factory_without_container() -> ServiceA:
    """Factory deliberately missing the required ``Container`` argument."""
    return ServiceA()


def __factory_with_container(container: Container) -> ServiceA:
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
    wrong_instance =  Container()

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
def scoped_registrations_must_isolate() -> None:
    """A ``SCOPED`` registration is not shared with outer scopes."""
    outer_scope: Container = Container()
    inner_scope: Container = outer_scope.create_scope()

    outer_scope.register_scoped(IService, ServiceA)
    inner_scope.register_scoped(IService, ServiceA)

    outer_scope_instance: IService = outer_scope.resolve(IService)
    inner_scope_instance: IService = inner_scope.resolve(IService)

    # Same type but different objects because each container has its own scope cache.
    assert outer_scope_instance is not inner_scope_instance
    assert isinstance(outer_scope_instance, ServiceA)
    assert isinstance(inner_scope_instance, ServiceA)


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
    container: Container = Container()

    container.resolve(ServiceC)


@fact
def nonexistent_registration_when_abstract_must_fail() -> None:
    """Attempting to resolve an unregistered abstract raises ``KeyError``."""
    container: Container = Container()

    assert raises[KeyError](
        lambda: container.resolve(IService),
        exact=True
    ), 'Expected KeyError for an unknown registration of an abstract type.'


@fact
def factories_must_resolve_successfully() -> None:
    """A well-typed factory is invoked and its product is returned."""
    container: Container = Container()
    container.register_transient(IService, __factory_with_container)

    result: IService = container.resolve(IService)
    assert isinstance(result, ServiceA), 'Factory should produce a ServiceA instance.'

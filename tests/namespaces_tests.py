# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from hazrakah import (
    Container,
    RegistrationError,
    ResolutionError,
    singleton,
    transient,
    provides,
    instanced,
)
from typing import Protocol, runtime_checkable
from punit import fact
from punit.assertions.exceptions import raises


@runtime_checkable
class IDb(Protocol):
    def connect(self) -> str: ...


@runtime_checkable
class IFoo(Protocol):
    def do_foo(self) -> str: ...


class Postgres(IDb):
    def connect(self) -> str:
        return 'postgres'


class MySQL(IDb):
    def connect(self) -> str:
        return 'mysql'


class SQLite(IDb):
    def connect(self) -> str:
        return 'sqlite'


class ServiceDependsOnDb:
    def __init__(self, _db: IDb) -> None:
        self.db = _db


@fact
def create_scope_with_namespace_creates_child() -> None:
    """create_scope(namespace='v2') creates a scope child stored in parent's __namespaces."""
    root = Container()
    ns_child = root.create_scope(namespace='v2')
    assert root._Container__namespaces['v2'] is ns_child  # type: ignore[attr-defined]


@fact
def register_into_namespace_uses_same_child() -> None:
    """register(..., namespace='v2') reuses existing namespace child."""
    root = Container()
    root.register_transient(IDb, Postgres, namespace='v2')  # type: ignore[arg-type,type-abstract]
    first = root._Container__namespaces.get('v2')  # type: ignore[attr-defined]

    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]
    second = root._Container__namespaces.get('v2')  # type: ignore[attr-defined]

    assert first is second, 'Namespace scoped container must be reused'


@fact
def resolve_default_without_namespace_arg() -> None:
    """Resolving without namespace arg uses the default (unnamespaced) registration."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    result = root.resolve(IDb)  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, Postgres)


@fact
def resolve_with_namespace_string() -> None:
    """resolve(T, namespace='v2') resolves from the namespace scope."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    result = root.resolve(IDb, namespace='v2')  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, MySQL)


@fact
def resolve_namespace_falls_back_to_default() -> None:
    """[namespace, None] tries namespace first, falls back to default scope chain."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    # Clear v2 so None fallback kicks in
    root._Container__namespaces['v2']._Container__registrations.clear()  # type: ignore[attr-defined]
    result = root.resolve(IDb, namespace=['v2', None])  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, Postgres)


@fact
def resolve_namespace_priority_chain() -> None:
    """resolve(T, namespace=['v2', 'v1', None]) tries each in order."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v1')  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, SQLite, namespace='v2')  # type: ignore[arg-type,type-abstract]

    # v2 hit
    result = root.resolve(IDb, namespace=['v2', 'v1', None])  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, SQLite)

    # v1 hit (v2 miss)
    root._Container__namespaces['v2']._Container__registrations.clear()  # type: ignore[attr-defined]
    result = root.resolve(IDb, namespace=['v2', 'v1', None])  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, MySQL)

    # final None fallback
    root._Container__namespaces['v1']._Container__registrations.clear()  # type: ignore[attr-defined]
    result = root.resolve(IDb, namespace=['v2', 'v1', None])  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, Postgres)


@fact
def resolve_empty_namespace_list_fallbacks_to_default() -> None:
    """resolve(T, namespace=[]) treats [] as [None] - falls back to standard resolution."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]

    result = root.resolve(IDb, namespace=[])  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, Postgres)


@fact
def register_into_nonexistent_namespace_creates_container() -> None:
    """register(..., namespace='newns') auto-creates the namespace container."""
    root = Container()
    root.register_transient(IDb, MySQL, namespace='newns')  # type: ignore[arg-type,type-abstract]
    assert 'newns' in root._Container__namespaces  # type: ignore[attr-defined]
    assert root._Container__namespaces['newns']._Container__outer_scope is root  # type: ignore[attr-defined]


@fact
def resolve_transitive_propagates_namespace() -> None:
    """Namespace context flows into constructor parameter sub-resolves."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]
    root.register_transient(ServiceDependsOnDb)

    result = root.resolve(ServiceDependsOnDb, namespace=['v2'])  # type: ignore[arg-type,type-abstract]
    assert isinstance(result.db, MySQL)


@fact
def resolve_without_namespace_unaffected() -> None:
    """Resolve without namespace arg ignores namespace registrations entirely."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    result = root.resolve(IDb)  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, Postgres)


@fact
def is_registered_with_namespace() -> None:
    """is_registered(T, namespace='v2') checks the namespace scope."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    assert root.is_registered(IDb) is True  # type: ignore[arg-type,type-abstract]
    assert root.is_registered(IDb, namespace='v2') is True  # type: ignore[arg-type,type-abstract]
    assert root.is_registered(IDb, namespace=['v2', None]) is True  # type: ignore[arg-type,type-abstract]
    assert root.is_registered(IDb, namespace=['v3']) is False  # type: ignore[arg-type,type-abstract]
    # [] is treated as [None] per design, so checks default container
    assert root.is_registered(IDb, namespace=[]) is True  # type: ignore[arg-type,type-abstract]  # root has IDb registered


@fact
def is_registered_fallback_with_none_in_list() -> None:
    """is_registered with [None] checks only the default container."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    assert root.is_registered(IDb, namespace=[None]) is True  # type: ignore[arg-type,type-abstract]
    assert root.is_registered(IDb, namespace=['v2', None]) is True  # type: ignore[arg-type,type-abstract]


@fact
def is_registered_empty_list_treated_as_default() -> None:
    """is_registered with namespace=[] is treated as [None]."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    assert root.is_registered(IDb, namespace=[]) is True  # type: ignore[arg-type,type-abstract]


@fact
def freeze_propagates_to_namespaces() -> None:
    """container.freeze() also freezes all namespace children."""
    root = Container()
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]
    root.freeze()

    assert raises[RegistrationError](  # type: ignore[type-abstract]
        lambda: root._Container__namespaces['v2'].register_transient(IDb, SQLite),  # type: ignore[attr-defined,arg-type]
    )


@fact
def namespace_created_on_caller_container() -> None:
    """register(..., namespace='v2') creates __namespaces on the container it is called from."""
    parent = Container()
    child = parent.create_scope()

    child.register_transient(IDb, MySQL, namespace='my_ns')  # type: ignore[arg-type,type-abstract]
    assert 'my_ns' in child._Container__namespaces  # type: ignore[attr-defined]
    assert child._Container__namespaces['my_ns']._Container__outer_scope is child  # type: ignore[attr-defined]


@fact
def namespace_registration_resides_in_namespace_container() -> None:
    """A type registered with namespace='v2' is not in the parent's default registrations."""
    root = Container()
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    reg, _ = root._Container__get_registration(IDb)  # type: ignore[attr-defined]
    assert reg is None, 'Default container should not have the registration'

    ns_reg, _ = root._Container__namespaces['v2']._Container__get_registration(IDb)  # type: ignore[attr-defined]
    assert ns_reg is not None


@fact
def resolve_with_single_string_equals_list_with_fallback() -> None:
    """resolve(T, namespace='v2') is equivalent to resolve(T, namespace=['v2', None])."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]

    result_a = root.resolve(IDb, namespace='v2')  # type: ignore[arg-type,type-abstract]
    result_b = root.resolve(IDb, namespace=['v2', None])  # type: ignore[arg-type,type-abstract]

    assert type(result_a) is type(result_b)


@fact
def tuple_namespace_works_same_as_list() -> None:
    """Namespace argument works with tuple as well as list."""
    root = Container()
    root.register_transient(IDb, Postgres)  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, MySQL, namespace='v2')  # type: ignore[arg-type,type-abstract]
    root.register_transient(IDb, SQLite, namespace='v1')  # type: ignore[arg-type,type-abstract]

    result = root.resolve(IDb, namespace=('v1', 'v2', None))  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, SQLite)


@fact
def namespace_decorator_singleton() -> None:
    """@singleton(namespace='v2') registers into namespace via register_decorated."""
    from hazrakah.lifetime_decorators import _DecorationInfoManager

    @singleton(namespace='v2')
    class FooService:
        def get(self) -> str:
            return 'singleton-v2'

    root = Container()
    root.register_decorated()

    result = root.resolve(FooService, namespace='v2')
    assert result.get() == 'singleton-v2'

    _DecorationInfoManager._clear_store()


@fact
def namespace_decorator_transient() -> None:
    """@transient(namespace='v2') registers into namespace via register_decorated."""
    from hazrakah.lifetime_decorators import _DecorationInfoManager

    @transient(namespace='v2')
    class MyTransient:
        pass

    root = Container()
    root.register_decorated()

    a = root.resolve(MyTransient, namespace='v2')
    b = root.resolve(MyTransient, namespace='v2')
    assert a is not b

    _DecorationInfoManager._clear_store()


@fact
def namespace_decorator_provides() -> None:
    """@provides(IDb) + register_transient(..., namespace='v2') registers IDb into namespace."""
    root = Container()

    @provides(IDb)
    class MyProvider:
        def connect(self) -> str:
            return 'provided'

    root.register_transient(MyProvider, namespace='v2')

    result = root.resolve(IDb, namespace='v2')  # type: ignore[arg-type,type-abstract]
    assert isinstance(result, MyProvider)


@fact
def instanced_decorator_with_namespace() -> None:
    """@instanced(namespace='v2') creates instance into namespace scope."""
    from hazrakah.lifetime_decorators import _DecorationInfoManager

    @instanced(namespace='v2')
    class MyBootStamp:
        pass

    root = Container()
    root.register_decorated()

    stamp = root.resolve(MyBootStamp, namespace='v2')
    assert stamp is not None
    stamp2 = root.resolve(MyBootStamp, namespace='v2')
    assert stamp is stamp2

    _DecorationInfoManager._clear_store()


@fact
def decorator_namespace_none_goes_to_default() -> None:
    """@singleton(namespace=None) goes to the default container."""
    from hazrakah.lifetime_decorators import _DecorationInfoManager

    @singleton(namespace=None)
    class DefaultSingleton:
        def get(self) -> str:
            return 'default'

    root = Container()
    root.register_decorated()

    result = root.resolve(DefaultSingleton)
    assert result is not None

    _DecorationInfoManager._clear_store()


@fact
def resolve_fallbacks_to_concrete_auto_register() -> None:
    """If namespace resolution fails and type is concrete, auto-register as transient."""
    root = Container()

    class Concrete:
        pass

    result = root.resolve(Concrete, namespace=['v2', None])
    assert isinstance(result, Concrete)


@fact
def singleton_in_namespace_scope() -> None:
    """Singleton registrations in a namespace scope share the same instance."""
    from hazrakah.lifetime_decorators import _DecorationInfoManager

    root = Container()

    @singleton(namespace='ns')
    class MyService:
        def get(self) -> str:
            return 'svc'

    root.register_decorated()

    a = root.resolve(MyService, namespace='ns')
    b = root.resolve(MyService, namespace='ns')
    assert a is b

    _DecorationInfoManager._clear_store()

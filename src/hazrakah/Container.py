# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import ABC
from enum import IntEnum
import inspect
import sys
from types import NoneType
from typing import (
    _SpecialForm,
    Any,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    overload
)

from .RegistrationError import RegistrationError
from .DependencyRegistry import DependencyRegistry, Target, Factory
from .DependencyResolver import DependencyResolver, ScopedDependencyResolver


T = TypeVar('T')


class Lifetime(IntEnum):
    TRANSIENT = 1
    SINGLETON = 2
    INSTANCE = 3


class Registration:

    __slots__ = ('__t', '__target', '__instance', '__lifetime')
    __t: Type[Any]
    __target: Optional[Target[Any]]
    __instance: Optional[Any]
    __lifetime: Lifetime

    def __init__(self, lifetime: Lifetime, t: Type[Any], target: Optional[Target[Any]] = None, instance: Optional[Any] = None) -> None:
        self.__t = t
        self.__target = target
        self.__instance = instance
        self.__lifetime = lifetime

    @property
    def t(self) -> Type[Any]:
        return self.__t

    @property
    def target(self) -> Optional[Target[Any]]:
        return self.__target

    @property
    def instance(self) -> Optional[Any]:
        return self.__instance

    @property
    def lifetime(self) -> Lifetime:
        return self.__lifetime


class Container(DependencyRegistry, DependencyResolver, ScopedDependencyResolver):

    __frozen: bool
    __singletons: dict[Type[Any], Any]
    __outer_scope: Optional[Container]
    __registrations: dict[Type[Any], Registration]

    def __init__(self, outer_scope: Optional[Container] = None, frozen: bool = False) -> None:
        super().__setattr__('__frozen', False)
        self.__singletons = {}
        self.__outer_scope = outer_scope
        self.__registrations = {}
        super().__setattr__('__frozen', frozen is True)

    def __setattr__(self, name: str, value: Any):
        if getattr(self, '__frozen'):
            raise AttributeError(f'Cannot modify attribute {name!r} on a frozen Container.')
        super().__setattr__(name, value)

    def __delattr__(self, name: str):
        if getattr(self, '__frozen'):
            raise AttributeError(f'Cannot delete attribute {name!r} on a frozen Container.')
        super().__delattr__(name)

    @staticmethod
    def __unwrap_forward_ref(annotation: Any, owner: Type[Any]) -> Any:
        """
        Evaluate string forward references in the context of *owner*.

        :param annotation: Type annotation.
        :param owner: Annotation owner.
        :return: A Type matching the annotation.
        """
        if isinstance(annotation, str):
            globals_ = getattr(owner, '__globals__', {})
            if not globals_:
                globals_ = globals()
            try:
                return eval(annotation, globals_, {})
            except Exception:
                mod = sys.modules[owner.__module__]
                if hasattr(mod, annotation):
                    return getattr(mod, annotation)
        return annotation

    def __check_frozen(self, t: Type[T]) -> None:
        """
        Checks if the container is frozen, if frozen blocks registration by raising ``RegistrationError``.

        :param t: A reference to the type attempting to be registered.
        :raises RegistrationError: When the container is frozen.
        """
        if getattr(self, '__frozen'):
            raise RegistrationError(
                f'Cannot modify a frozen container; '
                f'While creating a registration for type {t!r}'
            )

    def __create_instance(self, t: Type[T], registration: Registration) -> T:
        """
        Create an instance of *registration* by recursively resolving ``__init__`` parameters.

        :param t: The type being solved for.
        :param registration: The registration details.
        :raises RegistrationError: When the registration is malformed and instancing is not possible.
        :return: An instance of *T*.
        """
        if t is not registration.t:
            raise RegistrationError(f'Type mismatch in registration for {t!r}')
        if registration.target is None:
            raise RegistrationError('creating instances from targetless registrations is not supported')
        if isinstance(registration.target, type):
            return self.__resolve(cast(Type[T], registration.target))
        else:
            factory = registration.target
            return factory(self)

    def __is_concrete(self, t: Type[Any]) -> bool:
        """
        Return ``True`` if *t* represents a concrete, instantiable class.
        """
        if isinstance(t, _SpecialForm):
            return False
        if isinstance(t, TypeVar):
            return False
        if get_origin(t) is not None:
            return False
        if not isinstance(t, type):
            return False
        if issubclass(t, Protocol):  # type: ignore[arg-type]
            return False
        if inspect.isabstract(t) or (hasattr(t, '__bases__') and ABC in t.__bases__):
            return False
        return True

    def __register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        if target is None:
            target = t
        self.__registrations[t] = Registration(
            t=t,
            lifetime=Lifetime.TRANSIENT,
            target=target
        )

    def __resolve(self, t: type[T]) -> T:
        if not inspect.isclass(t):
            raise TypeError(f'Cannot instantiate non-class type {t!r}')
        if t.__init__ is object.__init__:
            return t()
        ctor = t.__init__
        sig = inspect.signature(ctor)
        kwargs: dict[str, Any] = {}
        for name, param in list(sig.parameters.items())[1:]:
            if param.annotation is inspect.Parameter.empty:
                raise TypeError(
                    f'Cannot resolve parameter {name!r} of {t.__name__}; '
                    'missing type annotation.'
                )
            dep_type = self.__unwrap_forward_ref(param.annotation, t)
            kwargs[name] = self.resolve(dep_type)
        return t(**kwargs)

    def __get_registration(self, t: Type[Any]) -> tuple[Registration, Container] | tuple[None, None]:
        """get a tuple containing a matching registration and the scope the registration was discovered in."""
        scope: Container | None = self
        while scope is not None:
            registration = scope.__registrations.get(t)
            if registration is not None:
                return registration, scope
            scope = scope.__outer_scope
        return None, None

    @overload
    def register_instance(self, t: Type[T], instance: T) -> None:
        ...

    @overload
    def register_instance(self, t: Type[Any], instance: Any) -> None:
        ...

    def register_instance(self, t: Type[Any], instance: Any) -> None:
        """
        Create an INSTANCE type registration for type *t*.

        Every resolve of *t* will result in the specified object instance.

        :param t: The type to register for.
        :param instance: The instance to register.
        :raises TypeError: When the provided instance is not an instance of type *t* (type mismatch.)
        """
        self.__check_frozen(t)
        if not isinstance(instance, t):
            raise TypeError(f'{instance!r} is not an instance of type {t!r}')
        self.__registrations[t] = Registration(
            t=t,
            lifetime=Lifetime.INSTANCE,
            instance=instance,
        )

    @overload
    def register_singleton(self, t: Type[T], target: Optional[Target[Any]] = ...) -> None:
        ...

    @overload
    def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = ...) -> None:
        ...

    def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        """
        Create a SINGLETON type registration for type *t*.

        Every resolve of *t* will result in a single, shared instance of *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*.  Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        self.__check_frozen(t)
        if target is None:
            target = t
        self.__registrations[t] = Registration(
            t=t,
            lifetime=Lifetime.SINGLETON,
            target=target,
        )

    @overload
    def register_transient(self, t: Type[T], target: Optional[Target[Any]] = ...) -> None:
        ...

    @overload
    def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = ...) -> None:
        ...

    def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        """
        Create a TRANSIENT type registration for type *t*.

        Every resolve of *t* will result in a new instance of *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*.  Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        self.__check_frozen(t)
        self.__register_transient(t, target)

    @overload
    def resolve(self, t: Type[T]) -> T:
        ...

    @overload
    def resolve(self, t: Type[Any]) -> Any:
        ...

    def resolve(self, t: Type[Any]) -> Any:
        """
        Resolve type *t* using available registrations.

        If *t* has no explicit registration but is a concrete class, create a TRANSIENT instance.

        :param t: The type to resolve.
        :raises KeyError: When type *t* is not a concrete class and has no registration.
        :raises RuntimeError: When a registration is malformed.
        :return: The object instance resolved for type *t*.
        """
        is_optional = isinstance(t, str) and t.startswith('Optional')
        if get_origin(t) is Union:
            # an attempt to deunionize from `Optional[T]` to `T`` -- won't work for string annotations)
            # if we cannot instantiate the resulting type, because it is Optional (unioned with `None`)
            # we will allow the passing of None in leiu.
            org_args = get_args(t)
            is_optional = org_args[-1] is None
            t = [e for e in get_args(t) if e is not NoneType][0]
        registration, scope = self.__get_registration(t)
        if registration is None:
            if self.__is_concrete(t):
                # implicit reg for concrete types
                self.__register_transient(t, t)
                return self.resolve(t)
            else:
                if is_optional:
                    return None
                else:
                    raise KeyError(f'No registration for {t!r}')
        match registration.lifetime:
            case Lifetime.INSTANCE:
                return registration.instance
            case Lifetime.SINGLETON:
                if scope is None:
                    raise RuntimeError('Singleton registration found without owning container')
                obj = scope.__singletons.get(t)
                if obj is None:
                    obj = scope.__create_instance(t, registration)
                    scope.__singletons[t] = obj
                return obj
            case Lifetime.TRANSIENT:
                return self.__create_instance(t, registration)
            case _:  # pragma: no cover
                raise RuntimeError(f'Unexpected lifetime {registration.lifetime!r}')

    def create_scope(self, frozen: Optional[bool] = False) -> Container:
        """
        Create a new scope as a :class:`Container` instance.

        :return: A :class:`Container` instance to use for the the scope.
        """
        return Container(outer_scope=self, frozen=frozen or getattr(self, '__frozen'))

    def freeze(self) -> None:
        """
        Freeze the Container.

        Any attempt to create registrations after the container has been frozen will result in a :class:`RegistrationError`.
        """
        super().__setattr__('__frozen', True)


__all__ = [
    'Container',
    'RegistrationError',
    'Factory',
    'Target'
]

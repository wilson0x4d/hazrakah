# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from enum import IntEnum
import inspect
from typing import (
    Any,
    Callable,
    Optional,
    Type,
    TypeAlias,
    TypeVar,
    Union,
    cast,
    overload
)

T = TypeVar('T')
Factory: TypeAlias = Callable[['Container'], Any]
Target: TypeAlias = Union[Type[T], Factory]


class Lifetime(IntEnum):
    TRANSIENT = 1
    SINGLETON = 2
    SCOPED = 3
    INSTANCE = 4


class RegistrationError(RuntimeError):
    """
    Raised when a registration cannot be processed.

    Typical situations that trigger this error:

    * Attempting to create an instance from a registration that has no
      ``target`` (e.g. a ``Lifetime.INSTANCE`` registration without an
      associated object).
    * Supplying a factory that does not conform to the expected signature
      ``Callable[[Container], T]``.
    * Providing an instance to :meth:`Container.register_instance` that is
      not an instance of the registration type.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        """
        Create the exception.

        :param message: Human-readable description of the problem.
        :param cause: Optional original exception that led to this error.  It is stored as ``__cause__`` so that traceback chaining works automatically.
        """
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


class Registration:

    __slots__ = ('__t', '__target', '__instance', '__lifetime')
    __t: Type[Any]
    __target: Optional[Target]
    __instance: Optional[Any]
    __lifetime: Lifetime

    def __init__(self, lifetime: Lifetime, t: Type[Any], target: Optional[Target] = None, instance: Optional[Any] = None) -> None:
        self.__t = t
        self.__target = target
        self.__instance = instance
        self.__lifetime = lifetime

    @property
    def t(self) -> Type[Any]:
        return self.__t

    @property
    def target(self) -> Optional[Target]:
        return self.__target

    @property
    def instance(self) -> Optional[Any]:
        return self.__instance

    @property
    def lifetime(self) -> Lifetime:
        return self.__lifetime


class Container:

    __frozen:bool
    __singletons: dict[Type[Any], Any]
    __outer_scope: Optional[Container]
    __registrations: dict[Type[Any], Registration]

    def __init__(self, outer_scope: Optional[Container] = None, frozen:Optional[bool] = False) -> None:
        super().__setattr__('__frozen', False)
        self.__singletons = {}
        self.__outer_scope = outer_scope
        self.__registrations = {}
        super().__setattr__('__frozen', frozen if frozen is not None else False)

    def __setattr__(self, name, value):
        if getattr(self, '__frozen'):
            raise AttributeError(f'Cannot modify attribute {name!r} on a frozen Container.')
        super().__setattr__(name, value)

    def __delattr__(self, name):
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
            return eval(annotation, globals_, {})
        return annotation

    def __check_frozen(self, t:Type[T]) -> None:
        """
        Checks if the container is frozen, if frozen blocks registration by raising ``RegistrationError``.

        :param t: A reference to the type attempting to be registered.
        :raises RegistrationError: When the container is frozen.
        """
        if getattr(self, '__frozen'):
            raise RegistrationError(
                f'Cannot modify a frozen container.'
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
            raise RegistrationError(f'creating instances from targetless registrations is not supported')
        if isinstance(registration.target, type):
            return self.__resolve(cast(Type[T], registration.target))
        else:
            factory = cast(Factory, registration.target)
            return factory(self)

    def __resolve(self, t: type[T]) -> T:
        """
        Resolves the target type *t* according to registrations.

        :param t: The type to solve for.
        :raises TypeError: When *t* is not a class-type, and does not support construction.
        :raises TypeError: When any parameter of *t*'s ctor lacks necessary typing.
        :return: _description_
        """
        if not inspect.isclass(t):
            raise TypeError(f'Cannot instantiate non-class type {t!r}')
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

    def __get_registration(self, t: Type[T]) -> Registration | None:
        """
        gets the registartion for the type **t**, if available.

        :param t: The type to get the registration for.
        :return: The registration, or None.
        """
        registration = self.__registrations.get(t, None)
        if registration is None and self.__outer_scope is not None:
            registration = self.__outer_scope.__get_registration(t)
        return registration

    @overload
    def register_instance(self, t: Type[T], instance: T) -> None: ...
    @overload
    def register_instance(self, t: Type[Any], instance: Any) -> None: ...
    def register_instance(self, t: Type[Any], instance: Any) -> None:
        """
        Create an INSTANCE type registration for type *t*.

        This ensures that resolve attempt for *t* will yield *instance*.

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
            instance=instance
        )

    @overload
    def register_scoped(self, t: Type[T], target: Optional[Target] = ...) -> None: ...
    @overload
    def register_scoped(self, t: Type[Any], target: Optional[Target] = ...) -> None: ...
    def register_scoped(self, t: Type[Any], target: Optional[Target] = None) -> None:
        """
        Create a SCOPED type registration for type *t*.

        This ensures that a container acquired from ``create_scope(...)`` will resolve NEW instances for type *t* without affecting instances created in a higher scope.

        Scoped registrations also function as singletons within their respective scopes.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*. Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        self.__check_frozen(t)
        if target is None:
            target = t
        self.__registrations[t] = Registration(
            t=t,
            lifetime=Lifetime.SCOPED,
            target=target
        )

    @overload
    def register_singleton(self, t: Type[T], target: Optional[Target] = ...) -> None: ...
    @overload
    def register_singleton(self, t: Type[Any], target: Optional[Target] = ...) -> None: ...
    def register_singleton(self, t: Type[Any], target: Optional[Target] = None) -> None:
        """
        Create a SINGLETON type registration for type *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*. Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        self.__check_frozen(t)
        if target is None:
            target = t
        self.__registrations[t] = Registration(
            t=t,
            lifetime=Lifetime.SINGLETON,
            target=target
        )

    @overload
    def register_transient(self, t: Type[T], target: Optional[Target] = ...) -> None: ...
    @overload
    def register_transient(self, t: Type[Any], target: Optional[Target] = ...) -> None: ...
    def register_transient(self, t: Type[Any], target: Optional[Target] = None) -> None:
        """
        Create a TRANSIENT type registration

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*. Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        self.__check_frozen(t)
        if target is None:
            target = t
        self.__registrations[t] = Registration(
            t=t,
            lifetime=Lifetime.TRANSIENT,
            target=target
        )

    @overload
    def resolve(self, t: Type[T]) -> T: ...
    @overload
    def resolve(self, t: Type[Any]) -> Any: ...
    def resolve(self, t: Type[Any]) -> Any:
        """
        Resolve type *t* using available registrations.

        :param t: The type to resolve.
        :raises KeyError: When type *t*, or a type that *t* depends on, has no registration.
        :raises RuntimeError: When a registration is malformed.
        :return: The object instance resolved for type *t*.
        """
        registration = self.__get_registration(t)
        if registration is None:
            raise KeyError(f'No registration for {t!r}')
        # if `__outer_scope` is set, and registration is not `scoped`, defer to `__outer_scope`
        if registration.lifetime != Lifetime.SCOPED and self.__outer_scope is not None:
            return self.__outer_scope.resolve(t)
        # handle resolution according to lifetime semantics
        match registration.lifetime:
            case Lifetime.INSTANCE:
                return registration.instance
            case Lifetime.SCOPED | Lifetime.SINGLETON:
                obj = self.__singletons.get(t, None)
                if obj is None:
                    obj = self.__create_instance(t, registration)
                    self.__singletons[t] = obj
                return obj
            case Lifetime.TRANSIENT:
                return self.__create_instance(t, registration)
            case _:  # pragma: no cover
                raise RuntimeError(
                    f'Unexpected lifetime {registration.lifetime!r}')  # pragma: no cover

    def create_scope(self, frozen: Optional[bool] = False) -> 'Container':
        """
        Create a new scope as a :class:`Container` instance.

        :return: A :class:`Container` instance to use for the the scope.
        """
        return Container(outer_scope=self, frozen=frozen or getattr(self, '__frozen'))

    def freeze(self) -> None:
        """
        Freezes the Container.

        Attempts to create registrations after the container has been frozen will result in a :class:`RegistrationError`.
        """
        super().__setattr__('__frozen', True)


__all__ = [
    'Container',
    'RegistrationException',
    'Factory',
    'Target'
]

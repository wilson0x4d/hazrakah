# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from abc import ABC
from enum import IntEnum
import inspect
import re
import sys
from types import NoneType, TracebackType, UnionType
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
from .ResolutionError import ResolutionError
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


class Container(DependencyRegistry, ScopedDependencyResolver, DependencyResolver):
    """
    A dependency-injection container that supports hierarchical scopes and deterministic destruction.

    Containers track every object they directly instantiate (via ``__create_instance``) in an internal
    ``set``. When a container is used as a context manager (either directly or via ``create_scope()``,
    all tracked objects are torn down by calling their ``close()`` method at the end of the scope.

    Example (Basic)
    ---------------

    .. code:: python

        container = Container()
        container.register_transient(Foo)
        foo = container.resolve(Foo)

        # supports scopes:
        scoped_container = container.create_scope()
        scoped_container.register_transient(Foo)
        foo = scoped_container.resolve(Foo)

    Example (Fluent)
    ----------------

    Registrations return ``self``, so they can be chained. The following demonstrates this:


    .. code:: python

        container = (
            Container()
            .register_singleton(Greeter, GreeterImpl)
            .register_transient(Formatter)
        )
        greeter = c.resolve(Greeter)

    Example (Context Manager)
    -------------------------

    The container can be used as a context manager for both direct scoping and nested scopes:


    .. code:: python

        with Container() as container:
            container.register_transient(Foo)
            with Container() as scoped:
                scoped.register_transient(Bar)
                foo = scoped.resolve(Foo)
                assert foo is not None
            bar = container.resolve(Bar)  # raises Error (not in scope)
            assert foo.is_closed is True  # context manager scope closes

    :ivar outer_scope: The parent container, or ``None`` for the root.
    :vartype outer_scope: Optional[Container]


    .. automethod:: __enter__
    .. automethod:: __exit__
    """

    __frozen: bool
    __singletons: dict[Type[Any], Any]
    __outer_scope: Optional[Container]
    __registrations: dict[Type[Any], Registration]
    __proto_co_code: Any
    __tracked: set[Any]

    def __init__(self, outer_scope: Optional[Container] = None, frozen: bool = False) -> None:
        super().__setattr__('__frozen', False)
        self.__singletons = {}
        self.__outer_scope = outer_scope
        self.__registrations = {}
        self.__tracked: set[Any] = set()

        class _proto(Protocol):
            pass
        self.__proto_co_code = _proto.__init__.__code__.co_code

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

    def __check_frozen(self, t: Type[T] | object) -> None:
        """
        Checks if the container is frozen, if frozen blocks registration by raising ``RegistrationError``.

        :param t: A reference to the type attempting to be registered.
        :raises RegistrationError: When the container is frozen.
        """
        if getattr(self, '__frozen'):
            raise RegistrationError(
                f'Cannot modify a frozen container; '
                f'While creating a registration for {t!r}'
            )

    def __create_instance(
        self,
        t: Type[T],
        registration: Registration,
        scope: Optional[Container] = None,
    ) -> T:
        """
        Create an instance of *registration* by recursively resolving ``__init__`` parameters.

        :param t: The type being solved for.
        :param registration: The registration details.
        :param scope: (OPTIONAL) The Container that owns this instance for lifecycle tracking.
                       Defaults to ``self`` when not provided.
        :raises RegistrationError: When the registration is malformed and instancing is not possible.
        :return: An instance of *T*.
        """
        if t is not registration.t:
            raise RegistrationError(f'Type mismatch in registration for {t!r}')
        if registration.target is None:
            raise RegistrationError('creating instances from targetless registrations is not supported')
        instance: T
        if isinstance(registration.target, type):
            instance = self.__resolve(cast(Type[T], registration.target))
        else:
            factory = registration.target
            instance = factory(self)
        owner: Container = scope if scope is not None else self
        tracked = getattr(owner, '_Container__tracked', None)  # type: ignore[attr-defined]
        if tracked is not None:
            tracked.add(instance)
        return instance

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
            if isinstance(t, type):
                if Protocol in getattr(t, '__bases__', ()):
                    return False
                elif issubclass(t, Protocol) and getattr(t, '__abstractmethods__', None):  # type: ignore[arg-type]
                    return False
        if inspect.isabstract(t) or (hasattr(t, '__bases__') and ABC in t.__bases__):
            return False
        return True

    def __get_provided_types(self, t: Type[Any] | object) -> set[type] | None:
        """
        Discover ``__hazrakah_provides`` metadata from *t*.

        :returns: None if not found, otherwise a ``set`` of types that are provided by `t`.
        """
        provided_types = getattr(t, '__hazrakah_provides', None)
        if provided_types is None:
            return None
        else:
            types = set[type]()
            for provides_t in provided_types:
                types.add(provides_t)
            return types if len(types) > 0 else None

    def __resolve(self, t: type[T]) -> T:
        if not inspect.isclass(t):
            raise TypeError(f'Cannot instantiate non-class type {t!r}')
        if t.__init__ is object.__init__ or t.__init__.__code__.co_code is self.__proto_co_code:
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

    def is_registered(self, t: Type[Any]) -> bool:
        r, c = self.__get_registration(t)
        return r is not None

    def register_instance(self, t: Type[Any] | object, instance: Optional[Any] = None) -> Container:
        """
        Register a pre-existing *instance* for type *t*.

        :param t: The type to bind the instance to.
        :param instance: (OPTIONAL) An object that must be an instance of *t*.  Omit to construct a `t` instance automatically.
        :returns: ``self`` for method chaining.
        :raises TypeError: When *instance* is not an instance of *t*.

        Note on @provides
        -----------------
        The ``@provides`` decorator on the target type is **only discovered when *instance* is omitted**
        (no explicit second argument). In that case, the container discovers ``__hazrakah_provides``
        metadata and multi-registers the target under every provided interface.

        When *instance* IS provided (explicit registration), @provides metadata on the target class
        is **completely ignored**. Only the type specified by *t* is registered. This applies
        regardless of whether the concrete class implements additional interfaces via @provides.
        """
        self.__check_frozen(t)
        if instance is not None:
            # explicit `instance` --> `t` registration logic
            if not isinstance(t, type):
                # in this use-case, `t` must be a type arg because `instance` was provided (explicit registration.)
                raise RegistrationError(
                    '`t` must be a valid type arg when `instance` is provided.'
                )
            # skip isinstance for Protocol types that aren't @runtime_checkable;
            # this is a "best attempt" at type enforcement, but we can't enforce the unenforcable.
            try:
                isinstance(instance, t)
            except TypeError:
                pass  # not a runtime-checkable type; nothing to validate
            else:
                if not isinstance(instance, t):
                    raise TypeError(f'{instance!r} is not an instance of type {t!r}')
            self.__register_for_lifetime(t, Lifetime.INSTANCE, instance)
        else:
            # inferred `instance` registration logic
            instance = self.resolve(t) if isinstance(t, type) else t
            # inspect for `@provides` usage
            provided_types = self.__get_provided_types(t)
            if provided_types is not None:
                # `t` has `@provides`, so register `instance` for all provided types
                for provides_t in provided_types | {t}:
                    self.__register_for_lifetime(provides_t, Lifetime.INSTANCE, instance)  # type: ignore[bad-argument-type, arg-type]
            if isinstance(t, type):
                self.__register_for_lifetime(t, Lifetime.INSTANCE, instance)
            else:
                # when `t` is an instance, the type identify of the instance is registered
                t = type(t)
                self.__register_for_lifetime(t, Lifetime.INSTANCE, instance)
        return self

    def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = None) -> Container:
        """
        Create a SINGLETON type registration for type *t*.

        Every resolve of *t* will result in a single, shared instance of *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*.  Omit to use *t* as the target (requires *t* to be a concrete type.)
        :returns: ``self`` for method chaining.

        Note on @provides
        -----------------
        The ``@provides`` decorator on *target* is **only discovered when *target* is omitted**
        (no explicit second argument). In that case, the container discovers ``__hazrakah_provides``
        metadata and multi-registers *t* under every provided interface.

        When *target* IS provided (explicit registration), @provides metadata on the target class
        is **completely ignored**. Only the type specified by *t* is registered. This applies
        regardless of whether the concrete class implements additional interfaces via @provides.

        Examples
        --------
        # @provides activates -- multi-registers under IFoo, IBar, and MyImpl:

        @provides(IFoo, IBar)
        class MyImpl: ...
        c.register_singleton(MyImpl)  # no second arg

        # @provides does NOT activate -- only IFoo is registered:

        c.register_singleton(IFoo, MyImpl)  # explicit type override
        """
        self.__check_frozen(t)
        if target is not None:
            # explicit `t` --> `target` registration logic
            if not isinstance(t, type):
                # in this use-case, `t` must be a type arg because `target` was provided (explicit registration.)
                raise RegistrationError(
                    '`t` must be a valid type arg when `target` is provided.'
                )
            self.__register_for_lifetime(t, Lifetime.SINGLETON, target)
        else:
            # inferred `target` registration logic
            provided_types = self.__get_provided_types(t)
            if provided_types is not None:
                # `t` has `@provides`, so register `t` for all provided types
                for provides_t in provided_types | {t}:
                    self.__register_for_lifetime(provides_t, Lifetime.SINGLETON, t)  # type: ignore[bad-argument-type]
            else:
                # `t` does not have `@provides`, so self-register `t`
                self.__register_for_lifetime(t, Lifetime.SINGLETON, t)
        return self

    def __register_for_lifetime(self, t: Type[Any], lifetime: Lifetime, target: Any) -> None:
        if lifetime == Lifetime.INSTANCE:
            self.__registrations[t] = Registration(
                t=t,
                lifetime=lifetime,
                instance=target
            )
        else:
            if not isinstance(target, type) and not callable(target):
                raise RegistrationError(
                    f'{lifetime} Registration for {t} cannot be bound to {target} (must be Type or Callable.)'
                )
            self.__registrations[t] = Registration(
                t=t,
                lifetime=lifetime,
                target=target
            )

    def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> Container:
        """
        Create a TRANSIENT type registration for type *t*.

        Every resolve of *t* will result in a new instance of *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*.  Omit to use *t* as the target (requires *t* to be a concrete type.)
        :returns: ``self`` for method chaining.

        Note on @provides
        -----------------
        The ``@provides`` decorator on *target* is **only discovered when *target* is omitted**
        (no explicit second argument). In that case, the container discovers ``__hazrakah_provides``
        metadata and multi-registers *t* under every provided interface.

        When *target* IS provided (explicit registration), @provides metadata on the target class
        is **completely ignored**. Only the type specified by *t* is registered. This applies
        regardless of whether the concrete class implements additional interfaces via @provides.

        Examples
        --------
        # @provides activates -- multi-registers under IFoo, IBar, and MyImpl:

        @provides(IFoo, IBar)
        class MyImpl: ...
        c.register_transient(MyImpl)  # no second arg

        # @provides does NOT activate -- only IFoo is registered:

        c.register_transient(IFoo, MyImpl)  # explicit type override
        """
        self.__check_frozen(t)
        if target is not None:
            # explcit `t` --> `target` registration logic
            if not isinstance(t, type):
                # in this use-case, `t` must be a type arg because `target` was provided (explicit registration.)
                raise RegistrationError(
                    '`t` must be a valid type arg when `target` is provided.'
                )
            self.__register_for_lifetime(t, Lifetime.TRANSIENT, target)
        else:
            # inferred `target` registration logic
            provided_types = self.__get_provided_types(t)
            if provided_types is not None:
                # @provides discovered -- register under *t* and all provided interfaces.
                for provides_t in provided_types | {t}:
                    self.__register_for_lifetime(provides_t, Lifetime.TRANSIENT, t)  # type: ignore[bad-argument-type]
            else:
                # `t` does not have `@provides`, so self-register `t`
                self.__register_for_lifetime(t, Lifetime.TRANSIENT, t)
        return self

    def _union_display_name(self, t: Type[Any]) -> str:
        """Return a human-readable name for a union type alias, if available."""
        return getattr(t, '__name__', str(t))

    def _resolve_union(self, t: Type[Any]) -> Any:
        """Resolve a non-Optional union type alias -- find the single matching registration.

        For each union member, checks for an explicit registration. If no registration
        is found and the member is a concrete class, auto-registers it as transient
        (silent happy path). After iterating all members:

        - **One distinct target** → returns the resolved instance.
        - **Multiple distinct targets** → raises :class:`ResolutionError` with details.
          Registrations that map to the same concrete class are collapsed (e.g.
          ``@provides(IFoo, IBar)`` on one implementation is not ambiguous).
        - **Zero matches** → raises :class:`ResolutionError` describing the unresolved types.

        Union type aliases containing ``None`` (i.e. ``Optional[T]``) are handled by
        :meth:`resolve` before reaching this method, so this only processes non-Optional unions.
        """
        args = get_args(t)

        matches: list[tuple[Type[Any], Container, Lifetime, Registration]] = []
        unresolved: list[Type[Any]] = []  # members with no reg and not concrete

        for member in args:
            reg, scope = self.__get_registration(member)
            if reg is not None and scope is not None:
                matches.append((member, scope, reg.lifetime, reg))
            elif self.__is_concrete(member):
                # Auto-register + resolve; silent happy path
                self.register_transient(member)  # type: ignore[arg-type]
                return self.resolve(member)       # type: ignore[arg-type]
            else:
                unresolved.append(member)

        # dedupe for target:
        # - multiple union members MAY map to the same concrete concrete target.
        # - only "distinct targets" constitute true ambiguity.
        target_groups: dict[type, tuple[Type[Any], Container, Lifetime, Registration]] = {}
        for member, scope, lifetime, reg in matches:
            tgt = reg.target  # Registration.target property (line 57)
            key = tgt if isinstance(tgt, type) else None
            if key is not None and key in target_groups:
                continue  # same concrete target already recorded
            elif key is not None:
                target_groups[key] = (member, scope, lifetime, reg)

        if len(target_groups) == 0:
            # All registrations have non-type targets (factories); treat as normal multi-match
            distinct_matches = matches
        else:
            distinct_matches = list(target_groups.values())

        if len(distinct_matches) == 1:
            member, scope, _lifetime, _reg = distinct_matches[0]
            return scope.resolve(member)         # type: ignore[arg-type]

        if len(distinct_matches) > 1:
            parts = []
            for member, _, lifetime, _reg in distinct_matches:
                name = getattr(member, '__name__', str(member))
                parts.append(f'  - {name} ({lifetime.name})')
            display_name = self._union_display_name(t)
            raise ResolutionError(
                f'No unique registration for {display_name}:\n' + '\n'.join(parts),
                matched=matches,
            )

        # zero matches
        names = ' | '.join(getattr(m, '__name__', str(m)) for m in unresolved)
        display_name = self._union_display_name(t)
        raise ResolutionError(f'No registration found for {display_name}: {names}')

    @overload
    def resolve(self, t: Type[T]) -> T:
        ...

    @overload
    def resolve(self, t: Type[Any]) -> Any:
        ...

    def resolve(self, t: Type[Any]) -> Any:
        """Resolve a type to its registered implementation.

        For **union types** (e.g. ``IFoo | IBar``):

        * If the union is ``Optional[T]`` (contains ``NoneType``), unwraps to ``T``
          and resolves normally; returns ``None`` if ``T`` is unresolvable.
        * For **non-Optional unions** (e.g. ``IFoo | IBar``): finds the single
          registered implementation among the union members. If multiple distinct
          targets are registered, raises :class:`ResolutionError`. Unregistered concrete
          classes are auto-registered as transient.

        For non-union types, looks up the registration and dispatches by lifetime:

        * ``INSTANCE`` – returns the stored instance.
        * ``SINGLETON`` – creates or returns a shared instance per container scope.
        * ``TRANSIENT`` – creates and returns a new instance each time.
        """
        is_optional = isinstance(t, str) and t.startswith('Optional')
        origin = get_origin(t)
        if origin is Union or origin is UnionType:
            # an attempt to deunionize from `Optional[T]` to `T`` -- won't work for string annotations)
            # if we cannot instantiate the resulting type, because it is Optional (unioned with `None`)
            # we will allow the passing of None in leiu.
            org_args = get_args(t)
            if NoneType in org_args:
                t = [e for e in org_args if e is not NoneType][0]
            else:
                return self._resolve_union(t)
        registration, scope = self.__get_registration(t)
        if registration is None:
            if self.__is_concrete(t):
                # implicit reg for concrete types
                self.register_transient(t)
                return self.resolve(t)
            else:
                if is_optional:
                    return None
                raise ResolutionError(f'No registration found for {t!r}')
        match registration.lifetime:
            case Lifetime.INSTANCE:
                return registration.instance
            case Lifetime.SINGLETON:
                if scope is None:
                    raise RuntimeError('Singleton registration found without owning container')
                # When target is a concrete type, use it as the shared singleton cache key
                # so all provided interfaces sharing this registration get the same instance.
                cache_key = t
                tgt = registration.target
                if tgt is not None and isinstance(tgt, type) and tgt is not t:
                    cache_key = tgt
                obj = scope.__singletons.get(cache_key)
                if obj is None:
                    obj = scope.__create_instance(t, registration, scope=scope)  # type: ignore[arg-type]
                    scope.__singletons[cache_key] = obj
                return obj
            case Lifetime.TRANSIENT:
                return self.__create_instance(t, registration, scope=scope)  # type: ignore[arg-type]
            case _:  # pragma: no cover
                raise RuntimeError(f'Unexpected lifetime {registration.lifetime!r}')

    def register_decorated(
        self,
        namespace_pattern: Optional[str] = None,
        class_pattern: Optional[str] = None,
    ) -> Container:
        """
        Create registrations based on discovered decorators ``@singleton``, ``@transient``, and ``@instanced``.

        This method is idempotent -- repeated calls overwrite registrations (last-in-wins).

        :param namespace_pattern: A regular expression pattern used to filter which decorated types are registered.
            The pattern is compiled once and matched against the **namespace** (i.e. ``__module__``) of both
            each entry's *interface* type and *target* callable/class. If **either** matches, registration proceeds.
            When ``None`` (the default), all decorated types are registered with no filtering.

            Usage::

                # only register types defined in the "myapp.services" module tree
                container.register_decorated(namespace_pattern=r"myapp\\.services\\..*")

        :param class_pattern: A regular expression pattern used to filter by **class name** (i.e. ``__qualname__``) of
            each entry's *interface* and *target*. If **either** matches, registration proceeds for that info.
            When ``None`` (the default), no class-name filtering is applied.

        :returns: ``self`` for method chaining.
        """

        def _get_namespace(obj: Any) -> str:
            """Return the module name of *obj*, which is either a type or a callable."""
            return getattr(obj, '__module__', '')

        def _get_class_name(obj: Any) -> str:
            """Return the class/function name of *obj* (sans namespace/scope).

            For nested classes and local definitions, ``__qualname__`` may include
            the enclosing scope (e.g. ``_func.<locals>.ClassName``).  We extract
            only the final dotted component to get the bare class/function name.
            """
            qual = getattr(obj, '__qualname__', '') or getattr(obj, '__name__', '')
            return qual.rsplit('.', 1)[-1] if qual else ''

        ns_pattern: Optional[re.Pattern[str]] = None
        if namespace_pattern is not None:
            ns_pattern = re.compile(namespace_pattern)

        cls_pattern: Optional[re.Pattern[str]] = None
        if class_pattern is not None:
            cls_pattern = re.compile(class_pattern)

        # Import lazily to avoid circular import at module load time.
        from .lifetime_decorators import _DecorationInfoManager, _sort_decoration_infos

        infos = _DecorationInfoManager.instance().get_all()
        sorted_infos = _sort_decoration_infos(infos)
        for info in sorted_infos:
            # Namespace filter: skip if neither interface nor target matches
            if ns_pattern is not None:
                iface_ns = _get_namespace(info.interface)
                target_ns = _get_namespace(info.target)
                if not ns_pattern.search(iface_ns) and not ns_pattern.search(target_ns):
                    continue

            # Class name filter: skip if neither interface nor target matches
            if cls_pattern is not None:
                iface_cls = _get_class_name(info.interface)
                target_cls = _get_class_name(info.target)
                if not cls_pattern.search(iface_cls) and not cls_pattern.search(target_cls):
                    continue

            match info.lifetime:
                case Lifetime.SINGLETON:
                    self.register_singleton(info.interface, info.target)  # type: ignore[arg-type]
                case Lifetime.TRANSIENT:
                    self.register_transient(info.interface, info.target)  # type: ignore[arg-type]
                case Lifetime.INSTANCE:
                    self.register_instance(
                        info.interface,
                        (
                            self.resolve(info.target)
                            if isinstance(info.target, type)
                            else info.target(self)  # type: ignore[call-arg]
                        )
                    )

        return self

    def create_scope(self, frozen: Optional[bool] = False) -> Container:
        return Container(outer_scope=self, frozen=frozen or getattr(self, '__frozen'))

    def freeze(self) -> None:
        """
        Freeze the Container.

        Any attempt to create registrations after the container has been frozen will result in a :class:`RegistrationError`.
        """
        super().__setattr__('__frozen', True)

    def __enter__(self) -> Container:
        """Return *self* to enable context manager usage."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],  # type: ignore[name-defined]
    ) -> None:
        """
        Destroy all tracked instances.

        Every object that was directly instantiated by this container (via ``__create_instance``) is
        torn down by calling its ``close()`` method, if present. The tracked set is then cleared so
        no object is double-cleaned.

        :param exc_type: (OPTIONAL) Exception type, if one was raised inside the ``with`` block.
        :param exc_val: (OPTIONAL) The exception instance, if one was raised.
        :param exc_tb: (OPTIONAL) Traceback object, if one was raised.
        """
        for obj in getattr(self, '_Container__tracked', set()):  # type: ignore[attr-defined]
            close = getattr(obj, 'close', None)
            if close is not None:
                close()
        tracked = getattr(self, '_Container__tracked', None)  # type: ignore[attr-defined]
        if tracked is not None:
            tracked.clear()

    def __del__(self) -> None:
        """Best-effort cleanup on GC."""
        for obj in getattr(self, '_Container__tracked', []):  # type: ignore[attr-defined]
            try:
                close = getattr(obj, 'close', None)
                if close is not None:
                    close()
            except Exception:
                pass
        tracked = getattr(self, '_Container__tracked', None)  # type: ignore[attr-defined]
        if tracked is not None:
            tracked.clear()


__all__ = [
    'Container',
    'RegistrationError',
    'Factory',
    'Target'
]

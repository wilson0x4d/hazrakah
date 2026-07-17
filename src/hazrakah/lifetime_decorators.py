# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""
Ergonomic decorator registration for dependency-injection lifetimes.

Decorators mark intent; ``register_decorated()`` performs actual registration.
Each decorator is a no-op at decoration time -- it stores metadata in a global
:class:`_DecorationInfoManager` singleton which
:meth:`Container.register_decorated` reads to populate the container.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from types import BuiltinFunctionType, BuiltinMethodType, FunctionType, MethodType
from typing import (
    Any,
    Callable,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from .Container import Lifetime  # noqa: F401  # re-exported by this module
from .RegistrationError import RegistrationError

logger = logging.getLogger(__name__)


T = TypeVar('T')


@dataclass(frozen=True)
class DecorationInfo:
    """
    Metadata emitted by a decorator for one interface of the decorated target.

    :ivar lifetime: The lifecycle type (singleton, transient, or instance).
    :ivar target: The original callable / class that was decorated.
    :ivar interface: The single interface this entry registers for.
    :ivar depends_on: Ordering hints -- references to other registered interfaces.
    :ivar namespace: (Optional) Namespace to register into.
    """

    lifetime: Lifetime
    target: Union[
        FunctionType,
        MethodType,
        BuiltinFunctionType,
        BuiltinMethodType,
        Callable[..., object],
        type,
    ]
    interface: type
    depends_on: tuple[type, ...]
    namespace: Optional[str] = None


class _DecorationInfoManager:
    """Shared global registry for all :class:`DecorationInfo` entries."""

    __instance: Optional[_DecorationInfoManager] = None
    __store: dict[type, DecorationInfo] = {}

    @classmethod
    def instance(cls) -> _DecorationInfoManager:
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance

    def register(self, info: DecorationInfo) -> None:
        """
        Store or replace an entry for *info.interface*.

        If an entry already exists for the same interface a warning is logged.
        If the existing entry has a different lifetime a :class:`RegistrationError`
        is raised -- one lifetime per interface is enforced.
        """
        if info.interface in _DecorationInfoManager.__store:
            existing = _DecorationInfoManager.__store[info.interface]
            if existing.lifetime is not info.lifetime:
                raise RegistrationError(
                    f'cannot both decorate interface {info.interface.__name__!r} as '
                    f'{existing.lifetime.name} and {info.lifetime.name}. '
                    f'Target "{existing.target.__name__}" vs "{info.target.__name__}".'
                )
            logger.warning(
                'Overwriting decoration for %s (was registered for %s).',
                info.interface,
                existing.target.__name__,
            )
        _DecorationInfoManager.__store[info.interface] = info

    def get_all(self) -> list[DecorationInfo]:
        """Return a snapshot of all stored entries."""
        return list(_DecorationInfoManager.__store.values())

    @classmethod
    def _clear_store(cls) -> None:
        """Clear all stored decoration info. For testing use only."""
        cls.__instance = None
        cls.__store.clear()


_HAZRAKAH_LIFECYCLE_ATTR = '__hazrakah_lifecycle'


def _raise_if_provides_decorated(unwrapped: Any) -> None:
    if hasattr(unwrapped, '__hazrakah_provides'):
        raise RegistrationError(
            f'cannot apply ``@{unwrapped.__name__}`` to a class already decorated with ``@provides``. '
            'Use either a lifecycle decorator (@singleton/@transient/@instanced) OR @provides — not both.'
        )


def _infer_depends_on(cls: type) -> tuple[type, ...]:
    """
    Return unique class-referencing types from *cls*.__init__ annotations.

    Walks every parameter annotation in ``__init__`` and collects any entry that is a concrete
    class (not a generic, TypeVar, protocol, or abstract base).  Preserves insertion order so
    early constructor params become earlier dependencies.
    """
    seen: set[type] = set()
    deps: list[type] = []
    ctor = getattr(cls, "__init__", None)
    if ctor is None or ctor is object.__init__:
        return ()

    # Resolve string forward references (e.g. from __future__ import annotations)
    try:
        hints = dict(inspect.get_annotations(ctor, eval_str=True))
    except Exception:
        return ()

    module = inspect.getmodule(cls)

    for _name, ann in hints.items():
        if isinstance(ann, str):
            # Last-resort manual resolution for unresolvable forward refs.
            # Try the class's module namespace as a fallback.
            resolved: Optional[type] = None
            if module is not None:
                resolved = getattr(module, '__dict__', {}).get(ann)
            if resolved is not None and isinstance(resolved, type):
                ann = resolved  # type: ignore[assignment]
            else:
                continue

        origin = get_origin(ann)
        if origin is not None:
            # generic (list, dict, Optional, etc.) -- walk args for nested classes
            for arg in get_args(ann):
                if isinstance(arg, type) and arg not in seen:
                    deps.append(arg)
                    seen.add(arg)
            continue

        if isinstance(ann, type) and ann not in seen:
            # Skip primitives / builtins
            if ann is bool or ann is int or ann is float or ann is str or ann is bytes:
                continue
            if ann in (list, dict, set, tuple, frozenset, slice, type, object):
                continue
            deps.append(ann)
            seen.add(ann)

    return tuple(deps)


def _validate_factory(target: Callable[..., object]) -> None:
    """Validate that *target* declares exactly one positional parameter."""
    sig = inspect.signature(inspect.unwrap(target))
    params = list(sig.parameters.values())
    positional = [
        p for p in params
        if p.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD
        )
    ]
    if len(positional) != 1:
        raise RegistrationError(
            f'Factory function "{target.__name__}" must declare exactly one '
            f'positional parameter. Received {len(positional)}.'
        )


def singleton(
    target: Optional[Union[Type[T], Callable[..., T]]] = None,
    *,
    types: Optional[Union[type, tuple[type, ...]]] = None,
    depends_on: tuple[type, ...] = (),
    namespace: Optional[str] = None,
) -> Any:
    """
    Register *target* as a singleton.

    Usage::

        @singleton                  →  self-as (classes only)
        @singleton(types=IFoo)         →  explicit interface
        @singleton(types=(IFoo, IBar)) →  multiple interfaces

    :raises RegistrationError: If *target* is already decorated with ``@provides`` — the two decorators are incompatible.
    """
    if target is None:
        # @singleton() or @singleton(types=IFoo) -- return proxy capturing types/depends_on.
        _types = types
        _dep = depends_on
        _ns = namespace

        def __proxy(_target: Type[T]) -> type[T]:
            _inferred = (
                _infer_depends_on(_target)
                if isinstance(_target, type)
                else ()
            )
            _merged = _dep + tuple(d for d in _inferred if d not in set(_dep))
            return singleton(_target, types=(_types or _target), depends_on=_merged, namespace=_ns)  # type: ignore[return-value]
        return __proxy  # type: ignore[return-value]

    unwrapped = inspect.unwrap(target)  # type: ignore[arg-type]
    is_class = isinstance(unwrapped, type)

    if not is_class:
        _validate_factory(target)

    _raise_if_provides_decorated(unwrapped)

    inferred_types: Optional[Union[type, tuple[type, ...]]] = None
    if types is None:
        if is_class:
            inferred_types = unwrapped  # type: ignore[assignment]
        else:
            raise RegistrationError(
                f'``as=`` is required for factory function "{target.__name__}".'
            )

    if types is None:
        assert inferred_types is not None
        assert isinstance(inferred_types, type)
        interfaces = (inferred_types,)  # type: ignore[assignment]
    elif isinstance(types, tuple):
        interfaces = types  # type: ignore[assignment]
    else:
        interfaces = (types,)

    for iface in interfaces:
        info_entry = DecorationInfo(
            lifetime=Lifetime.SINGLETON,
            target=unwrapped,  # type: ignore[arg-type]
            interface=iface,
            depends_on=depends_on,
            namespace=namespace,
        )
        _DecorationInfoManager.instance().register(info_entry)

    setattr(unwrapped, _HAZRAKAH_LIFECYCLE_ATTR, Lifetime.SINGLETON)
    return target  # type: ignore[return-value]


def transient(
    target: Optional[Union[Type[T], Callable[..., T]]] = None,
    *,
    types: Optional[Union[type, tuple[type, ...]]] = None,
    depends_on: tuple[type, ...] = (),
    namespace: Optional[str] = None,
) -> Any:
    """Register *target* as a transient."""
    if target is None:
        _types = types
        _dep = depends_on
        _ns = namespace

        def __proxy(_target: Type[T]) -> type[T]:
            _inferred = (
                _infer_depends_on(_target)
                if isinstance(_target, type)
                else ()
            )
            _merged = _dep + tuple(d for d in _inferred if d not in set(_dep))
            return transient(_target, types=(_types or _target), depends_on=_merged, namespace=_ns)  # type: ignore[return-value]

        return __proxy  # type: ignore[return-value]

    unwrapped = inspect.unwrap(target)  # type: ignore[arg-type]
    is_class = isinstance(unwrapped, type)

    if not is_class:
        _validate_factory(target)

    _raise_if_provides_decorated(unwrapped)

    inferred_types: Optional[Union[type, tuple[type, ...]]] = None
    if types is None:
        if is_class:
            inferred_types = unwrapped  # type: ignore[assignment]
        else:
            raise RegistrationError(
                f'``as=`` is required for factory function "{target.__name__}".'
            )

    interfaces: tuple[type, ...]
    if types is None:
        assert inferred_types is not None
        assert isinstance(inferred_types, type)
        interfaces = (inferred_types,)  # type: ignore[assignment]
    elif isinstance(types, tuple):
        interfaces = types
    else:
        interfaces = (types,)

    for iface in interfaces:
        info_entry = DecorationInfo(
            lifetime=Lifetime.TRANSIENT,
            target=unwrapped,  # type: ignore[arg-type]
            interface=iface,
            depends_on=depends_on,
            namespace=namespace,
        )
        _DecorationInfoManager.instance().register(info_entry)

    setattr(unwrapped, _HAZRAKAH_LIFECYCLE_ATTR, Lifetime.TRANSIENT)
    return target  # type: ignore[return-value]


def instanced(
    target: Optional[Union[Type[T], Callable[..., T]]] = None,
    *,
    types: Optional[Union[type, tuple[type, ...]]] = None,
    depends_on: tuple[type, ...] = (),
    namespace: Optional[str] = None,
) -> Any:
    """Register *target* as an instance (created once at decoration time)."""
    if target is None:
        _types = types
        _dep = depends_on
        _ns = namespace

        def __proxy(_target: Type[T]) -> type[T]:
            _inferred = (
                _infer_depends_on(_target)
                if isinstance(_target, type)
                else ()
            )
            _merged = _dep + tuple(d for d in _inferred if d not in set(_dep))
            return instanced(_target, types=(_types or _target), depends_on=_merged, namespace=_ns)  # type: ignore[return-value]
        return __proxy  # type: ignore[return-value]

    unwrapped = inspect.unwrap(target)  # type: ignore[arg-type]
    is_class = isinstance(unwrapped, type)

    if not is_class:
        _validate_factory(target)

    _raise_if_provides_decorated(unwrapped)

    inferred_types: Optional[Union[type, tuple[type, ...]]] = None
    if types is None:
        if is_class:
            inferred_types = unwrapped  # type: ignore[assignment]
        else:
            raise RegistrationError(
                f'``as=`` is required for factory function "{target.__name__}".'
            )

    interfaces: tuple[type, ...]
    if types is None:
        assert inferred_types is not None
        assert isinstance(inferred_types, type)
        interfaces = (inferred_types,)  # type: ignore[assignment]
    elif isinstance(types, tuple):
        interfaces = types
    else:
        interfaces = (types,)

    for iface in interfaces:
        info_entry = DecorationInfo(
            lifetime=Lifetime.INSTANCE,
            target=unwrapped,  # type: ignore[arg-type]
            interface=iface,
            depends_on=depends_on,
            namespace=namespace,
        )
        _DecorationInfoManager.instance().register(info_entry)

    setattr(unwrapped, _HAZRAKAH_LIFECYCLE_ATTR, Lifetime.INSTANCE)
    return target  # type: ignore[return-value]


def _sort_decoration_infos(
    decoration_infos: list[DecorationInfo],
) -> list[DecorationInfo]:
    """Sort decorations by ``depends_on`` ordering hints.

    Returns a topologically-sorted list.  Items with unresolvable
    dependencies (no corresponding manager entry) fall to the end.
    If a circular dependency is detected a warning is logged and remaining
    items are appended unsorted.
    """
    results: dict[type, DecorationInfo] = {}
    max_cycles = len(decoration_infos)

    # add ordered
    while len(results) < len(decoration_infos) and max_cycles > 0:
        max_cycles -= 1
        for current in decoration_infos:
            if current.interface in results:
                continue
            if any(e not in results for e in current.depends_on):
                continue
            results[current.interface] = current

    # fill remaining
    results.update({
        d.interface: d
        for d in decoration_infos
        if d.interface not in results
    })

    return list(results.values())


__all__ = [
    'DecorationInfo',
    'Lifetime',
    'singleton',
    'transient',
    'instanced',
]

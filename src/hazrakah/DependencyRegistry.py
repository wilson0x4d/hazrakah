# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from typing import Any, Callable, Optional, Protocol, Type, TypeAlias, TypeVar, Union, runtime_checkable

from .DependencyResolver import DependencyResolver


T = TypeVar('T')
Factory: TypeAlias = Callable[[DependencyResolver], T]
Target: TypeAlias = Union[Type[T], Factory[T]]


@runtime_checkable
class DependencyRegistry(Protocol):
    """
    A protocol for dependency registration without exposing resolution methods.
    """

    def register_instance(self, t: Type[Any], instance: Any) -> None:
        ...

    def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        ...

    def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        ...


__all__ = [
    'DependencyRegistry',
    'Factory',
    'Target'
]

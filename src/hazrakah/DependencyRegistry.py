# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from typing import Any, Callable, Optional, Protocol, Type, TypeAlias, TypeVar, Union, runtime_checkable

from .DependencyResolver import DependencyResolver


T = TypeVar('T')
Factory: TypeAlias = Callable[[DependencyResolver], T]
Target: TypeAlias = Union[Type[T], Factory[T]]


@runtime_checkable
class DependencyRegistry(DependencyResolver, Protocol):
    """
    A protocol for dependency registration (and resolution) tasks.
    """

    def is_registered(self, t: Type[Any]) -> bool:
        """
        Check if type *t* has a registration already.

        :param t: The type to check for.
        :return: True if a registration exists.
        """
        ...

    def register_instance(self, t: Type[Any], instance: Any) -> None:
        """
        Create an INSTANCE type registration for type *t*.

        Every resolve of *t* will result in the specified object instance.

        :param t: The type to register for.
        :param instance: The instance to register.
        :raises TypeError: When the provided instance is not an instance of type *t* (type mismatch.)
        """
        ...

    def register_singleton(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        """
        Create a SINGLETON type registration for type *t*.

        Every resolve of *t* will result in a single, shared instance of *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*.  Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        ...

    def register_transient(self, t: Type[Any], target: Optional[Target[Any]] = None) -> None:
        """
        Create a TRANSIENT type registration for type *t*.

        Every resolve of *t* will result in a new instance of *t*.

        :param t: The type to register for.
        :param target: The type or factory to be used when resolving type *t*.  Omit to use *t* as the target (requires *t* to be a concrete type.)
        """
        ...


__all__ = [
    'DependencyRegistry',
    'Factory',
    'Target'
]

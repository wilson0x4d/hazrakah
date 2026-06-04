# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Any, Protocol, Type, runtime_checkable


@runtime_checkable
class DependencyResolver(Protocol):
    """
    A protocol for dependency resolution without exposing registration methods.
    """

    def resolve(self, t: Type[Any]) -> Any:
        """
        Resolve type *t* using available registrations.

        If *t* has no explicit registration but is a concrete class, create a TRANSIENT instance.

        :param t: The type to resolve.
        :raises KeyError: When type *t* is not a concrete class and has no registration.
        :raises RuntimeError: When a registration is malformed.
        :return: The object instance resolved for type *t*.
        """
        ...


@runtime_checkable
class ScopedDependencyResolver(DependencyResolver, Protocol):

    def create_scope(self) -> ScopedDependencyResolver:
        """
        Create a new scope as a :class:`Container` instance.

        :return: A :class:`Container` instance to use for the the scope.
        """
        ...


__all__ = [
    'DependencyResolver',
    'ScopedDependencyResolver'
]

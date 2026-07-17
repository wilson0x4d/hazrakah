# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Any, Iterable, Protocol, Type, TypeVar, runtime_checkable


T = TypeVar('T')


@runtime_checkable
class DependencyResolver(Protocol):
    """
    A protocol for dependency resolution without exposing registration methods.
    """

    def resolve(self, t: Type[T], namespace: str | Iterable[str | None] | Iterable[str] | None = None) -> T:
        """
        Resolve type *t* using available registrations.

        :param t: The type to resolve.
        :param namespace: (Optional) Namespace resolution priority chain.
        :raises KeyError: When type *t* is not a concrete class and has no registration.
        :raises RuntimeError: When a registration is malformed.
        :return: The object instance resolved for type *t*.
        """
        ...


@runtime_checkable
class ScopedDependencyResolver(DependencyResolver, Protocol):

    def create_scope(
        self,
        frozen: bool | None = None,
        self_resolve: bool | None = None,
        namespace: str | None = None,
    ) -> ScopedDependencyResolver:
        """
        Create a new scope as a :class:`Container` instance.

        :param frozen: (Optional) Freezes the new scope.
        :param self_resolve: (Optional) Enable self-resolve.
        :param namespace: (Optional) Associative namespace string.
        :return: A :class:`Container` instance to use for the the scope.
        """
        ...


__all__ = [
    'DependencyResolver',
    'ScopedDependencyResolver',
]

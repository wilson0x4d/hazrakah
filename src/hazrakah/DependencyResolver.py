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
        ...


@runtime_checkable
class ScopedDependencyResolver(Protocol):

    def resolve(self, t: Type[Any]) -> Any:
        ...

    def create_scope(self) -> ScopedDependencyResolver:
        ...


__all__ = [
    'DependencyResolver',
    'ScopedDependencyResolver'
]

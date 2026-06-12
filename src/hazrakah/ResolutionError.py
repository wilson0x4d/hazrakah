# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT


from __future__ import annotations

from typing import Any, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .Container import Lifetime


class ResolutionError(KeyError):
    """
    Raised when a type cannot be resolved.

    Typical situations that trigger this error:

    * No registration found for a concrete or abstract type during ``resolve()``.
    * Multiple registrations for different implementations of a union type alias,
      making the target ambiguous (e.g. ``IFoo | IBar`` where both are registered
      to different targets).

    The ``matched`` attribute contains all pre-deduplication matches when available,
    allowing callers to inspect which types were considered during resolution.
    """

    matched: list[tuple[Type[Any], Any, Lifetime, Any]] | None

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
        matched: list[tuple[Type[Any], Any, Lifetime, Any]] | None = None,
    ) -> None:
        """
        Create the exception.

        :param message: Human-readable description of the problem.
        :param cause: Optional original exception that led to this error.  It is stored as ``__cause__`` so that traceback chaining works automatically.
        :param matched: Pre-deduplication list of (type, scope, lifetime, registration) tuples for all matches found during resolution.
        """
        super().__init__(message)
        self.matched = matched
        if cause is not None:
            super().__setattr__('__cause__', cause)

# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Marker decorator for declaring which protocols a class implements.

The ``@provides`` decorator stores its provided types as the hidden attribute
``__hazrakah_provides`` on the decorated class. Mutation methods
(``register_singleton``, ``register_transient``, ``register_instance``)
discover this attribute at call site and multi-register accordingly.

This decorator must NOT touch ``_DecorationInfoManager`` or set
``__hazrakah_lifecycle`` -- those are the sole responsibility of lifecycle
decorators (``@singleton``, ``@transient``, ``@instanced``).
"""

from __future__ import annotations

from typing import Any, Callable, Type, TypeVar

from .RegistrationError import RegistrationError


T = TypeVar('T')


def _raise_if_lifetime_decorated(unwrapped: Any) -> None:
    if hasattr(unwrapped, '__hazrakah_lifetime'):
        raise RegistrationError(
            f'cannot apply ``@{unwrapped.__name__}'
            f'`` to a class already decorated with ``@provides``. '
            'Use either a lifecycle decorator (@singleton/@transient/@instanced) '
            'OR @provides — not both.'
        )


def provides(
    *types: Type[Any],
) -> Callable[[T], T]:
    """Marker decorator: declares which protocols *cls* implements.

    Stores metadata on the decorated class via ``__hazrakah_provides``;
    zero registration logic at decoration time. The mutation methods discover
    this attribute and register under each provided interface.

    Usage::

        @provides(IFoo, IBar)   →  registers IFoo and IBar under the decorated class
        @provides()              →  marker-only, no interfaces (backward compatible)

    :param types: Protocol types the decorated class implements. Variadic -- no tuple wrapping.
    """
    def decorator(cls: T) -> T:
        _raise_if_lifetime_decorated(cls)
        if types:
            setattr(cls, '__hazrakah_provides', types)
        else:
            # Bare @provides with no args -- store empty tuple for consistent detection.
            setattr(cls, '__hazrakah_provides', ())
        return cls
    return decorator


__all__ = ['provides']

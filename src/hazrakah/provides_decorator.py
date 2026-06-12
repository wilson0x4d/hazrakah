# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Passive marker decorator for declaring which protocols a class implements.

The ``@provides`` decorator is a **passive** metadata marker -- it does nothing at
decoration time except store its provided types as the hidden attribute
``__hazrakah_provides`` on the decorated class. It has zero registration logic of
its own.

Activation depends entirely on how the container later registers the decorated class:

- If you call ``register_singleton(MyClass)`` (no second argument), the container
  discovers ``__hazrakah_provides`` and multi-registers *MyClass* under all provided
  interfaces.
- If you call ``register_singleton(IFoo, MyClass)`` (with an explicit type override),
  @provides is **completely bypassed** -- only IFoo is registered.

@provides must NOT be combined with lifecycle decorators (@singleton, @transient,
@instanced) on the same class -- those are mutually exclusive by design.
"""

from __future__ import annotations

from typing import Any, Callable, Type, TypeVar

from .RegistrationError import RegistrationError


T = TypeVar('T')


def _raise_if_lifetime_decorated(unwrapped: Any) -> None:
    if hasattr(unwrapped, '__hazrakah_lifecycle'):
        raise RegistrationError(
            f'cannot apply ``@{unwrapped.__name__}`` to a class already decorated with ``@provides``. '
            'Use either a lifecycle decorator (@singleton/@transient/@instanced) OR @provides — not both.'
        )


def provides(
    *types: Type[Any],
) -> Callable[[T], T]:
    """Passive marker decorator: declares which protocols *cls* implements.

    Stores metadata on the decorated class via ``__hazrakah_provides``; zero registration
    logic at decoration time. Activation depends on how the container registers the class:

    - No explicit type arg on register_* --> @provides triggers multi-registration.
    - Explicit type arg on register_* --> @provides is ignored.

    Usage::

        @provides(IFoo, IBar)           # stores metadata only
        class MyClass: ...

        c.register_singleton(MyClass)   # activates: registers IFoo, IBar, MyClass
        c.register_transient(IBaz, ...)  # ignores @provides on other classes

        @provides()                     # marker-only, no interfaces (backward compatible)

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

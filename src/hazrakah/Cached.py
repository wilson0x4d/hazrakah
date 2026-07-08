# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Time-bound value caching generic type.

Provides ``Cached[T]``, a generic wrapper that caches the result of a factory
callable for a configurable TTL window.  The factory signature matches hazrakah's
standard :py:data:`hazrakah.DependencyRegistry.Factory` — it receives a
:py:class:`~hazrakah.DependencyResolver` as its first argument.

Usage::

    from datetime import timedelta
    from hazrakah import Container, Cached

    container = Container()
    cached = Cached(lambda c: create_pool("postgres://localhost/db"), ttl=timedelta(seconds=120))

    # First resolve — factory called once (within TTL).
    pool1 = container.resolve(DBPool, lambda c: cached(c))

    # Second resolve — cached value returned; factory not re-invoked.
    pool2 = container.resolve(DBPool, lambda c: cached(c))
    assert pool1 is pool2
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Callable, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from .DependencyResolver import DependencyResolver as Resolver

T = TypeVar('T')


class Cached(Generic[T]):
    """Caches the result of a factory for a configurable TTL.

    Invoking a ``Cached`` instance via :py:meth:`__call__` returns the cached value
    if the TTL window has not elapsed; otherwise it re-invokes *factory* and records
    a fresh expiry timestamp.  The factory receives the resolver passed to ``__call__``.

    :param factory: Callable that produces the cached value of type ``T``;
        receives the resolver as its first argument.
    :param ttl: Time-to-live — accepts ``float`` (seconds) or :py:class:`timedelta`
        (default ``47.0``).
    """

    __value: Optional[T]
    __value_expiration_timestamp: float | None
    __factory: Callable[[Resolver], T]
    __ttl_seconds: float

    def __init__(
        self,
        factory: Callable[[Resolver], T],
        ttl: float | timedelta = 47.0,
    ) -> None:
        if isinstance(ttl, timedelta):
            ttl = ttl.total_seconds()
        self.__value = None
        self.__value_expiration_timestamp = None
        self.__factory = factory
        self.__ttl_seconds = ttl

    def __call__(self, resolver: Resolver) -> T:
        """Return the cached value, refreshing from *factory* if expired or on first call.

        When the TTL window has elapsed since the value was originally produced, or when
        no value has been cached yet (first call), *factory* is invoked with *resolver*
        and the result recorded along with a fresh expiry timestamp.

        ``None`` is treated as a valid cached value — it is never re-evaluated.

        :param resolver: The owning ``DependencyResolver`` passed through to the factory.
        :returns: The cached or freshly produced value of type ``T``.
        """
        if self.__value is not None and not self.__has_expired():
            return self.__value
        # Expired or first call — re-evaluate
        self.__value = self.__factory(resolver)
        self.__value_expiration_timestamp = (
            datetime.now(timezone.utc).timestamp() + self.__ttl_seconds
        )
        return self.__value

    @property
    def ttl(self) -> timedelta:
        """The TTL window as a :py:class:`timedelta`."""
        return timedelta(seconds=self.__ttl_seconds)

    def reset(self) -> None:
        """Discard the cached value and its expiration timestamp."""
        self.__value = None
        self.__value_expiration_timestamp = None

    def __has_expired(self) -> bool:
        """Return ``True`` if the current value's TTL window has elapsed."""
        if self.__value_expiration_timestamp is None:
            return False
        return self.__value_expiration_timestamp < datetime.now(timezone.utc).timestamp()


__all__ = ['Cached']

# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for the Cached[T] generic type.

Each test defines inline classes and factories to avoid cross-test pollution;
no shared fixtures are used — this matches existing test-file patterns in the
project.
"""

from __future__ import annotations

import time
from datetime import timedelta

from hazrakah import Cached, DependencyResolver
from punit import fact
from punit.mocks import Mock


class _ExpensiveResult:
    """Helper class for type-inference and callable-factory tests."""

    def __init__(self, n: int = 0) -> None:
        self.n = n


# Sentinel that satisfies the DependencyResolver Protocol at runtime.
_resolver_mock = Mock(origin=DependencyResolver)


@fact
def call_invokes_factory_on_first_access() -> None:
    """Factory is called exactly once on first __call__."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return 'hello'

    cached = Cached(factory)  # type: ignore[arg-type]
    result = cached(_resolver_mock)  # type: ignore[arg-type]
    assert result == 'hello'
    assert call_count == 1


@fact
def call_returns_cached_result_without_reinvoking_factory() -> None:
    """Subsequent calls return the same value without calling factory again."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return 'cached_value'

    cached = Cached(factory)  # type: ignore[arg-type]
    r1 = cached(_resolver_mock)  # type: ignore[arg-type]
    r2 = cached(_resolver_mock)  # type: ignore[arg-type]
    assert r1 == 'cached_value'
    assert r1 is r2
    assert call_count == 1, 'Factory should not be called again'


@fact
def call_re_invokes_factory_after_timeout() -> None:
    """Factory is re-invoked when TTL has elapsed."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return f'value_{call_count}'

    cached = Cached(factory, ttl=timedelta(seconds=0))  # type: ignore[arg-type]
    first = cached(_resolver_mock)  # type: ignore[arg-type]
    time.sleep(0.01)
    second = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 2


@fact
def default_ttl_is_47_seconds() -> None:
    """Default ttl is 47.0 seconds (as timedelta)."""
    cached = Cached(lambda c: 42)  # type: ignore[arg-type]
    assert cached.ttl == timedelta(seconds=47)


@fact
def custom_float_ttl_applied_correctly() -> None:
    """Float ttl (seconds) is respected for expiry."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return 'x'

    cached = Cached(factory, ttl=0.0)  # type: ignore[arg-type]
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    time.sleep(0.01)
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 2


@fact
def custom_timedelta_ttl_applied_correctly() -> None:
    """timedelta ttl is converted and respected for expiry."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return 'x'

    cached = Cached(factory, ttl=timedelta(seconds=0))  # type: ignore[arg-type]
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    time.sleep(0.01)
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 2


@fact
def ttl_zero_causes_always_miss() -> None:
    """Zero TTL causes factory to be called on every access."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return call_count

    cached = Cached(factory, ttl=timedelta(seconds=0))  # type: ignore[arg-type]
    first = cached(_resolver_mock)  # type: ignore[arg-type]
    second = cached(_resolver_mock)  # type: ignore[arg-type]
    third = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 3


@fact
def value_handles_none_factory_result() -> None:
    """None from factory is cached and returned correctly."""
    cached = Cached(lambda c: None)  # type: ignore[arg-type]
    result = cached(_resolver_mock)  # type: ignore[arg-type]
    assert result is None
    # Second access should NOT re-call the factory (None is a valid cached value)
    result2 = cached(_resolver_mock)  # type: ignore[arg-type]
    assert result2 is None


@fact
def lambda_factory_is_accepted() -> None:
    """Lambda expressions work as factories."""
    cached = Cached(lambda c: [1, 2, 3])  # type: ignore[arg-type]
    assert cached(_resolver_mock) == [1, 2, 3]  # type: ignore[arg-type]


@fact
def class_callable_as_factory() -> None:
    """Class constructors work as factories."""

    def factory(c):  # noqa: ANN201, ARG001
        return _ExpensiveResult()

    cached = Cached(factory)  # type: ignore[arg-type]
    result = cached(_resolver_mock)  # type: ignore[arg-type]
    assert isinstance(result, _ExpensiveResult)


@fact
def reset_clears_cached_value() -> None:
    """.reset() discards both value and timestamp, causing factory to be re-invoked on next call."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return f'v{call_count}'

    cached = Cached(factory)  # type: ignore[arg-type]
    first = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 1

    cached.reset()
    second = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 2, 'Factory must be re-invoked after reset'
    assert first != second


@fact
def call_forwarding_delegates_to_factory() -> None:
    """Calling the Cached instance forwards the resolver to the factory."""
    received = []

    def factory(c):  # noqa: ANN201
        received.append(c)
        return 'via_call'

    cached = Cached(factory)  # type: ignore[arg-type]
    result = cached(_resolver_mock)  # type: ignore[arg-type]
    assert result == 'via_call'
    assert len(received) == 1
    assert received[0] is _resolver_mock


@fact
def call_caches_across_resolutions() -> None:
    """Multiple __call__ invocations within TTL share the same value."""
    cached = Cached(lambda c: object())  # type: ignore[arg-type]

    r1 = cached(_resolver_mock)  # type: ignore[arg-type]
    r2 = cached(_resolver_mock)  # type: ignore[arg-type]
    assert r1 is r2


@fact
def ttl_property_exposes_timedelta() -> None:
    """Cached exposes ttl as a timedelta property."""
    cache = Cached(lambda c: 42, ttl=timedelta(seconds=120))  # type: ignore[arg-type]
    assert cache.ttl == timedelta(seconds=120)


@fact
def float_ttl_exposes_as_timedelta() -> None:
    """Float TTL is exposed as equivalent timedelta."""
    cache = Cached(lambda c: 42, ttl=90.0)  # type: ignore[arg-type]
    assert cache.ttl == timedelta(seconds=90)


@fact
def factory_receives_resolved_resolver() -> None:
    """Factory is called with the exact resolver passed to __call__."""
    received = []

    def factory(c):  # noqa: ANN201
        received.append(c)
        return 42

    cache = Cached(factory)  # type: ignore[arg-type]
    my_resolver = object()
    _ = cache(my_resolver)  # type: ignore[arg-type]
    assert len(received) == 1
    assert received[0] is my_resolver


@fact
def zero_arg_factory_still_works() -> None:
    """Factories that ignore the resolver argument remain compatible."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return call_count

    cached = Cached(factory, ttl=47.0)  # type: ignore[arg-type]
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 1

    # resolver is still passed — factory just ignores it.
    second = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 1


@fact
def resolver_kwarg_allows_none() -> None:
    """resolver=None explicitly is equivalent to not passing resolver."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return 'ok'

    cached = Cached(factory, ttl=47.0)  # type: ignore[arg-type]
    assert cached(_resolver_mock) == 'ok'  # type: ignore[arg-type]
    assert call_count == 1


@fact
def timedelta_with_microseconds_preserved() -> None:
    """timedelta with microseconds is preserved as float seconds internally."""
    td = timedelta(seconds=47, milliseconds=500, microseconds=123)
    cached = Cached(lambda c: 42, ttl=td)  # type: ignore[arg-type]
    assert cached.ttl == td


@fact
def timedelta_ttl_zero_expires_immediately() -> None:
    """Zero-duration timedelta expires immediately."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return call_count

    cached = Cached(factory, ttl=timedelta(0))  # type: ignore[arg-type]
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    _ = cached(_resolver_mock)  # type: ignore[arg-type]
    assert call_count == 2

# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""
Argument matchers for Mock call verification.

Matchers are lightweight, duck-typed objects that implement ``__eq__`` to dispatch
matching logic. No :class:`typing.Protocol` is used -- any object with a working
``__eq__`` method satisfies the matcher interface. This avoids needing a separate
``.matches()`` API -- Python's equality operator dispatches naturally.

Usage::

    from hazrakah.mocks import Mock, is_any, is_gt, is_in

    mock = Mock()
    mock(42, "hello", ["a", "b"])

    assert mock.was_called_with(
        is_gt(10),           # first arg > 10
        is_any(),             # second arg can be anything
        is_in("a", "b"),     # third arg is "a" or "b"
    )

Custom matchers: subclass :class:`Matcher` and implement ``__eq__``::

    class GreaterThan(Matcher):
        def __init__(self, threshold: int) -> None:
            self._threshold = threshold

        def __eq__(self, other: object) -> bool:
            return isinstance(other, (int, float)) and other > self._threshold
"""

from __future__ import annotations

from typing import Any


class Matcher:
    """Base class for argument matchers.

    Subclasses must implement ``__eq__(self, other: Any) -> bool`` and return
    ``True`` when *other* matches the expected pattern. This allows :meth:`Mock.was_called_with`
    to dispatch via Python's equality operator naturally.
    """


class _IsAny(Matcher):
    """Singleton matcher that matches any value."""

    __slots__ = ()
    _instance: '_IsAny | None' = None

    def __new__(cls) -> '_IsAny':
        if _IsAny._instance is None:
            _IsAny._instance = super().__new__(cls)
        return _IsAny._instance

    def __eq__(self, other: Any) -> bool:
        return True

    def __repr__(self) -> str:
        return 'is_any'


def is_any() -> Matcher:
    """Return a singleton matcher that matches any single value.

    :returns: A :class:`Matcher` instance.
    """
    return _IsAny()


class _Contains(Matcher):
    """Matcher that checks membership via the ``in`` operator."""

    __slots__ = ('_value',)

    def __init__(self, value: Any) -> None:
        object.__setattr__(self, '_value', value)

    @property
    def value(self) -> Any:
        return object.__getattribute__(self, '_value')

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self._value in other  # type: ignore[operator, attr-defined]
        try:
            return self._value in other  # type: ignore[operator, attr-defined]
        except TypeError:
            return False

    def __repr__(self) -> str:
        return f'contains({self._value!r})'  # type: ignore[attr-defined]


def contains(value: Any) -> Matcher:
    """Return a matcher that checks if *value* is a substring of a string or
    an element of a container (list, tuple, set, dict keys).

    :param value: The value to search for.
    :returns: A :class:`Matcher` instance.
    """
    return _Contains(value)


class _IsGt(Matcher):
    """Value is strictly greater than *n*."""

    __slots__ = ('_value',)

    def __init__(self, value: float) -> None:
        object.__setattr__(self, '_value', value)

    @property
    def value(self) -> float:
        return object.__getattribute__(self, '_value')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, (int, float)) and other > self._value  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'is_gt({self._value!r})'  # type: ignore[attr-defined]


def is_gt(n: float) -> Matcher:
    """Return a matcher that checks if the value is strictly greater than *n*.

    :param n: The threshold to compare against.
    :returns: A :class:`Matcher` instance.
    """
    return _IsGt(n)


class _IsGte(Matcher):
    """Value is greater than or equal to *n*."""

    __slots__ = ('_value',)

    def __init__(self, value: float) -> None:
        object.__setattr__(self, '_value', value)

    @property
    def value(self) -> float:
        return object.__getattribute__(self, '_value')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, (int, float)) and other >= self._value  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'is_gte({self._value!r})'  # type: ignore[attr-defined]


def is_gte(n: float) -> Matcher:
    """Return a matcher that checks if the value is greater than or equal to *n*.

    :param n: The threshold to compare against.
    :returns: A :class:`Matcher` instance.
    """
    return _IsGte(n)


class _IsLt(Matcher):
    """Value is strictly less than *n*."""

    __slots__ = ('_value',)

    def __init__(self, value: float) -> None:
        object.__setattr__(self, '_value', value)

    @property
    def value(self) -> float:
        return object.__getattribute__(self, '_value')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, (int, float)) and other < self._value  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'is_lt({self._value!r})'  # type: ignore[attr-defined]


def is_lt(n: float) -> Matcher:
    """Return a matcher that checks if the value is strictly less than *n*.

    :param n: The threshold to compare against.
    :returns: A :class:`Matcher` instance.
    """
    return _IsLt(n)


class _IsLte(Matcher):
    """Value is less than or equal to *n*."""

    __slots__ = ('_value',)

    def __init__(self, value: float) -> None:
        object.__setattr__(self, '_value', value)

    @property
    def value(self) -> float:
        return object.__getattribute__(self, '_value')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, (int, float)) and other <= self._value  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'is_lte({self._value!r})'  # type: ignore[attr-defined]


def is_lte(n: float) -> Matcher:
    """Return a matcher that checks if the value is less than or equal to *n*.

    :param n: The threshold to compare against.
    :returns: A :class:`Matcher` instance.
    """
    return _IsLte(n)


class _IsIn(Matcher):
    """Value equals one of the provided values."""

    __slots__ = ('_values',)

    def __init__(self, *values: Any) -> None:
        object.__setattr__(self, '_values', tuple(values))

    @property
    def values(self) -> tuple[Any, ...]:
        return object.__getattribute__(self, '_values')

    def __eq__(self, other: Any) -> bool:
        return other in self._values  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'is_in({self._values!r})'  # type: ignore[attr-defined]


def is_in(*values: Any) -> Matcher:
    """Return a matcher that checks if the value equals one of the provided values.

    This is the inverse of :func:`contains` -- ``contains(x)`` checks if x is in the arg,
    while ``is_in(a, b, c)`` checks if the arg is one of a, b, or c.

    :param values: The candidate values to check against.
    :returns: A :class:`Matcher` instance.
    """
    return _IsIn(*values)


class _IsType(Matcher):
    """Value is an instance of any given type(s)."""

    __slots__ = ('_types',)

    def __init__(self, *types: type) -> None:
        object.__setattr__(self, '_types', tuple(types))

    @property
    def types(self) -> tuple[type, ...]:
        return object.__getattribute__(self, '_types')

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self._types)  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'is_type({self._types!r})'  # type: ignore[attr-defined]


def is_type(*types: type) -> Matcher:
    """Return a matcher that checks if the value is an instance of any given type(s).

    :param types: One or more types to check against.
    :returns: A :class:`Matcher` instance.
    """
    return _IsType(*types)


class neg(Matcher):
    """
    Wraps another matcher and negates its result.

    This enables composing matchers freely -- e.g. ``neg(is_in("admin", "root"))``
    matches any value that is not "admin" or "root".

    :param inner: The matcher to negate.
    :returns: A :class:`Matcher` instance.
    """

    __slots__ = ('_inner',)

    def __init__(self, inner: Matcher) -> None:
        object.__setattr__(self, '_inner', inner)

    @property
    def inner(self) -> Matcher:
        return object.__getattribute__(self, '_inner')

    def __eq__(self, other: Any) -> bool:
        return not self._inner.__eq__(other)  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        return f'neg({self._inner!r})'  # type: ignore[attr-defined]


__all__ = [
    'Matcher',
    'neg',
    'is_any',
    'contains',
    'is_gt',
    'is_gte',
    'is_lt',
    'is_lte',
    'is_in',
    'is_type',
]

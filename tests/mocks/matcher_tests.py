# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for matcher argument-matching facility (matcher.py).

Matchers use duck-typed ``__eq__`` dispatch — any object with ``__eq__`` can match.
"""

from __future__ import annotations

from hazrakah.mocks.matcher import (
    Matcher,
    neg,
    contains,
    is_any,
    is_gte,
    is_gt,
    is_in,
    is_lte,
    is_lt,
    is_type,
)
from punit import fact


@fact
def is_any_matches_every_value() -> None:
    matcher = is_any()
    assert matcher.__eq__(42) is True
    assert matcher.__eq__('hello') is True
    assert matcher.__eq__(None) is True
    assert matcher.__eq__([1, 2, 3]) is True


@fact
def is_any_is_singleton() -> None:
    """Two calls return the same object."""
    assert is_any() is is_any()


@fact
def is_any_subclass_does_not_break_singleton() -> None:
    """Bug 6 regression: subclassing Matcher must not break _IsAny singleton."""

    class MyMatcher(Matcher):
        def __eq__(self, other: object) -> bool:
            return True

    # is_any() should always return the same singleton regardless of subclass presence
    a = is_any()
    b = is_any()
    c = is_any()
    assert a is b is c


@fact
def contains_works_on_strings() -> None:
    m = contains('world')
    assert m.__eq__('hello world') is True
    assert m.__eq__('goodbye') is False


@fact
def contains_works_on_lists() -> None:
    m = contains(2)
    assert m.__eq__([1, 2, 3]) is True
    assert m.__eq__([1, 4, 5]) is False


@fact
def contains_works_on_dicts_by_key() -> None:
    m = contains('key')
    assert m.__eq__({'key': 'value'}) is True
    assert m.__eq__({'foo': 'bar'}) is False


@fact
def is_gt_matches_strictly_greater() -> None:
    m = is_gt(10)
    assert m.__eq__(11) is True
    assert m.__eq__(10) is False
    assert m.__eq__(5) is False


@fact
def is_gte_matches_equal_or_greater() -> None:
    m = is_gte(10)
    assert m.__eq__(10) is True
    assert m.__eq__(11) is True
    assert m.__eq__(9) is False


@fact
def is_lt_matches_strictly_less() -> None:
    m = is_lt(10)
    assert m.__eq__(9) is True
    assert m.__eq__(10) is False
    assert m.__eq__(15) is False


@fact
def is_lte_matches_equal_or_less() -> None:
    m = is_lte(10)
    assert m.__eq__(10) is True
    assert m.__eq__(9) is True
    assert m.__eq__(11) is False


@fact
def is_in_matches_one_of_values() -> None:
    m = is_in('a', 'b', 'c')
    assert m.__eq__('a') is True
    assert m.__eq__('b') is True
    assert m.__eq__('d') is False


@fact
def is_type_matches_instance_of_types() -> None:
    m = is_type(str, int)
    assert m.__eq__('hello') is True
    assert m.__eq__(42) is True
    assert m.__eq__(3.14) is False


@fact
def neg_negates_inner_matcher() -> None:
    m = neg(is_in('admin', 'root'))
    assert m.__eq__('guest') is True
    assert m.__eq__('admin') is False


class GreaterThan(Matcher):
    """Custom matcher example."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold  # type: ignore[assignment]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, (int, float)) and other > self._threshold


@fact
def custom_matcher_subclass_works_via_eq_dispatch() -> None:
    m = GreaterThan(10)
    assert m.__eq__(11) is True
    assert m.__eq__(10) is False


from hazrakah.mocks import Mock

@fact
def matchers_work_in_positional_was_called_with() -> None:
    mock_obj = Mock()
    mock_obj(42, [1, 2, 3], 'hello world')
    assert mock_obj.was_called_with(is_gt(10), contains(2), contains('world'))


@fact
def matchers_work_in_keyword_was_called_with() -> None:
    mock_obj = Mock()
    mock_obj(42, foo='bar')
    assert mock_obj.was_called_with(is_any(), foo=is_in('bar', 'baz'))


@fact
def non_matching_matcher_returns_false() -> None:
    mock_obj = Mock()
    mock_obj(5)
    assert not mock_obj.was_called_with(is_gt(10))

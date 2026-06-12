# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""
Provides :class:`Mock`, :class:`Matcher` argument matchers, a ``patch`` mechanism,
and convenience functions.

Usage::

    from hazrakah.mocks import Mock, mock, is_any, contains, patch

    # Fluent syntax
    mock = (
        Mock()
        .do_stuff.
        returns(42)
    )

    # Constructor kwargs for fixture-style initialization
    user = Mock(first_name='Alice', email='alice@example.com')
    assert user.first_name == 'Alice'
    assert user.email == 'alice@example.com'

    # Matcher-based verification
    assert mock.was_called_with(
        is_any(),
        neg(contains("foo")),
        is_in(1, 2, 3))

    # Module-level patching
    with patch("some.module.ClassName") as m:
        m.method.returns("result")
"""

from .matcher import (
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
from .mock import CallDetail, Mock, MockError
from .patch import patch

__all__ = [
    'CallDetail',
    'Matcher',
    'Mock',
    'MockError',
    'neg',
    'contains',
    'is_any',
    'is_gte',
    'is_gt',
    'is_in',
    'is_lte',
    'is_lt',
    'is_type',
    'patch',
]

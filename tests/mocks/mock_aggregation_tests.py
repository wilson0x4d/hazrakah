# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for parent-child call aggregation (mock_calls, child_calls)."""

from __future__ import annotations

from hazrakah.mocks import CallEntry, CallEntryList, Mock
from punit import fact


@fact
def mock_calls_contains_leaf_call_on_root() -> None:
    m = Mock()
    m.foo.bar(1, 2)
    assert len(m.mock_calls) == 1
    entry = m.mock_calls[0]
    assert isinstance(entry, CallEntry)
    assert entry.path == 'Mock.foo.bar'
    assert entry.args == (1, 2)
    assert entry.kwargs == {}


@fact
def child_calls_contains_aggregated_child_call() -> None:
    m = Mock()
    m.foo.bar(1, 2)
    assert len(m.child_calls) == 1
    entry = m.child_calls[0]
    assert entry.path == 'Mock.foo.bar'


@fact
def direct_self_call_appears_in_mock_calls_not_child_calls() -> None:
    m = Mock()
    m()
    assert len(m.mock_calls) == 1
    assert len(m.child_calls) == 0
    entry = m.mock_calls[0]
    assert entry.path == 'Mock'


@fact
def direct_self_call_sets_called_property() -> None:
    m = Mock()
    assert not m.called
    m()
    assert m.called


@fact
def child_mock_has_own_mock_calls_with_leaf_entry() -> None:
    m = Mock()
    m.foo.bar(1, 2)
    foo_bar = m.foo.bar
    assert len(foo_bar.mock_calls) == 1
    entry = foo_bar.mock_calls[0]
    assert entry.path == 'Mock.foo.bar'


@fact
def child_mock_has_empty_child_calls_on_leaf() -> None:
    m = Mock()
    m.foo.bar(1, 2)
    assert len(m.foo.bar.child_calls) == 0


@fact
def parent_parent_gets_aggregated_entries() -> None:
    """Grandparent should see child calls via _all_calls and _child_calls."""
    m = Mock()
    a = m.a
    b = a.b
    c = b.c
    d = c.d
    d(42)

    # Grandparent (m) has 3 levels of aggregated entries for d's call
    assert len(m.mock_calls) == 1
    entry = m.mock_calls[0]
    assert entry.path == 'Mock.a.b.c.d'
    assert entry.args == (42,)


@fact
def grandparent_child_calls_contains_leaf() -> None:
    m = Mock()
    m.a.b(1)
    assert len(m.child_calls) == 1
    assert m.child_calls[0].path == 'Mock.a.b'


@fact
def multiple_children_get_separate_entries() -> None:
    m = Mock()
    m.foo(1)
    m.bar(2)

    assert len(m.mock_calls) == 2
    assert m.mock_calls[0].args == (1,)
    assert m.mock_calls[1].args == (2,)


@fact
def called_property_reflects_aggregated_state() -> None:
    m = Mock()
    assert not m.called
    m.foo(1)
    assert m.called


@fact
def partial_sublist_matching_works() -> None:
    m = Mock()
    m.a(1)
    m.b(2)

    # Use CallEntryList for partial-sublist matching via __contains__
    subset = CallEntryList((CallEntry('Mock.a', (1,), {}), CallEntry('Mock.b', (2,), {})))
    assert subset in m.mock_calls


@fact
def partial_sublist_matching_fails_on_wrong_args() -> None:
    m = Mock()
    m.a(1)

    wrong = CallEntryList((CallEntry('Mock.a', (99,), {}),))
    assert wrong not in m.mock_calls


@fact
def reset_mock_clears_all_aggregated_lists() -> None:
    m = Mock()
    m.foo.bar(1)
    assert len(m.mock_calls) == 1
    m.reset_mock()
    assert len(m.mock_calls) == 0
    assert len(m.child_calls) == 0
    assert not m.called


@fact
def reset_clears_aggregated_lists() -> None:
    m = Mock()
    m.foo.bar(1)
    assert len(m.mock_calls) == 1
    m.reset()
    assert len(m.mock_calls) == 0


@fact
def reset_mock_clears_grandchildren_too() -> None:
    m = Mock()
    m.a.b.c(1)

    # Grandchild has its own calls before reset
    assert len(m.a.b.mock_calls) == 1

    m.reset_mock()

    # All levels cleared
    assert len(m.mock_calls) == 0
    assert len(m.a.mock_calls) == 0
    assert len(m.a.b.mock_calls) == 0


@fact
def called_is_false_after_reset_mock() -> None:
    m = Mock()
    m.foo(1)
    assert m.called
    m.reset_mock()
    assert not m.called


@fact
def path_uses_name_value_for_root_mock() -> None:
    m = Mock(name='api')
    m.users.get(1)
    assert len(m.mock_calls) == 1
    assert m.mock_calls[0].path == 'api.users.get'


@fact
def context_manager_clone_is_independent() -> None:
    """Context manager produces a completely independent clone."""
    parent = Mock()
    with parent as child:
        child.foo(1)

    # Parent should NOT see the child's call (clone is independent)
    assert not parent.called
    assert len(parent.mock_calls) == 0


@fact
def call_entry_repr_no_call_prefix() -> None:
    entry = CallEntry(path='Mock.foo', args=(1, 2), kwargs={'key': 'val'})
    assert repr(entry) == 'Mock.foo((1, 2), key=\'val\')'


@fact
def call_entry_repr_empty_args_kwargs() -> None:
    entry = CallEntry(path='Mock.foo', args=(), kwargs={})
    assert repr(entry) == 'Mock.foo()'


@fact
def call_entry_repr_no_path_root_call() -> None:
    entry = CallEntry(path='', args=(1,), kwargs={})
    assert repr(entry) == '(1,)'


@fact
def call_entry_eq_compares_all_fields() -> None:
    e1 = CallEntry('Mock.foo', (1,), {})
    e2 = CallEntry('Mock.foo', (1,), {})
    e3 = CallEntry('Mock.bar', (1,), {})
    e4 = CallEntry('Mock.foo', (2,), {})

    assert e1 == e2
    assert e1 != e3
    assert e1 != e4


@fact
def deep_nesting_propagates_to_all_ancestors() -> None:
    m = Mock()
    m.w.x.y.z(99)

    # Root should have exactly one entry with full path
    assert len(m.mock_calls) == 1
    assert m.mock_calls[0].path == 'Mock.w.x.y.z'
    assert m.mock_calls[0].args == (99,)


@fact
def child_mock_child_calls_does_not_include_self_call() -> None:
    """A mock's child_calls should not include its own direct invocations."""
    m = Mock()
    m.foo()  # direct call on foo stub

    assert len(m.child_calls) == 1  # reached via attr access
    assert m.child_calls[0].path == 'Mock.foo'

    # But foo's own child_calls is empty (no children of foo were called)
    assert len(m.foo.child_calls) == 0


@fact
def multiple_calls_accumulate_in_aggregation() -> None:
    m = Mock()
    m.a(1)
    m.b(2)
    m.c(3)

    assert len(m.mock_calls) == 3
    assert len(m.child_calls) == 3

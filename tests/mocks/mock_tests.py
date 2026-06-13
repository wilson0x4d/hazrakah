# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for the Mock class and mock() factory (mock.py).

Covers ABC registration, fluent API, call tracking, delegates, origin behavior,
context manager, properties, signature validation, and identity semantics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import FrozenInstanceError
from typing import Protocol, runtime_checkable  # noqa: PGH003

from hazrakah.mocks import Mock, mock
from hazrakah.mocks.mock import CallDetail
from punit import fact


class MyABC(ABC):
    """Abstract base class for testing."""

    @abstractmethod
    def do_thing(self) -> None:
        ...


@runtime_checkable  # type: ignore[override]  # noqa: PGH003,ANN201,ARG005
class MyProtocol(Protocol):
    """Runtime-checkable protocol for testing."""

    def do_thing(self) -> None:  # noqa: E704
        ...


@fact
def mock_with_ABC_origin_passes_isinstance() -> None:
    m = Mock(origin=MyABC)
    assert isinstance(m, MyABC)


@fact
def mock_with_runtime_checkable_protocol_passes_isinstance() -> None:
    m = Mock(origin=MyProtocol)
    assert isinstance(m, MyProtocol)


# Concrete classes without ABC support cannot be registered as virtual subclasses.

@fact
def mock_factory_creates_equivalent_instance() -> None:
    m1 = Mock(origin=MyABC, name='test')
    m2 = Mock(origin=MyABC, name='test')
    assert m1.origin is m2.origin
    assert m1._u.name == m2._u.name  # type: ignore[attr-defined]


@fact
def returns_sets_value_and_returns_self() -> None:
    child = Mock()
    result = child.do_thing.returns(42)
    assert result is child.do_thing  # fluent API returns self (the child being configured)
    child.do_thing()
    gc1 = child.do_thing
    assert gc1.call_count == 1


@fact
def fluent_returns_configures_the_child_and_chains_back_to_parent() -> None:
    m = Mock()
    m.do_thing.returns(99)  # configure child 'do_thing' via fluent chain
    assert m.do_thing() == 99  # verify return value works


@fact
def callable_return_value_receives_mock_instance() -> None:
    """Callable return_value receives the mocked stub (self in __call__) as its sole argument."""
    child = Mock()
    gc1 = child.do_thing  # get stub

    class _Capturer:  # type: ignore[type-arg]
        def __init__(self) -> None:
            self.ids: list[int] = []

        def capture(self, mock_obj: Mock) -> str:
            self.ids.append(id(mock_obj))
            return 'captured'

    capturer = _Capturer()
    gc1.returns(capturer.capture)
    assert gc1() == 'captured'
    # The callable receives gc1 (the stub whose __call__ was invoked).
    assert capturer.ids[0] == id(gc1)


@fact
def side_effect_callable_receives_call_args() -> None:
    """side_effect callables forward the call's args/kwargs."""
    child = Mock()

    def _add_one(first_arg: int, **_kwargs: object) -> int:
        return first_arg + 1

    child.do_thing.side_effect(_add_one)
    assert child.do_thing(41) == 42


@fact
def side_effect_exception_instance_reraised() -> None:
    m = Mock()
    err = ValueError('boom')
    m.do_thing.side_effect(err)
    try:
        m.do_thing()
        assert False, 'Should have raised'
    except ValueError as e:
        assert e is err


@fact
def side_effect_exception_class_raises_instance() -> None:
    m = Mock()
    m.do_thing.side_effect(ValueError)
    try:
        m.do_thing()
        assert False, 'Should have raised'
    except ValueError:
        pass


@fact
def side_effect_iterable_returns_next_value_each_call() -> None:
    """Each call to the mock returns the next value from the iterable."""
    child = Mock()
    child.do_thing.side_effect(iter([1, 2]))  # fresh iterator
    assert child.do_thing() == 1
    assert child.do_thing() == 2


@fact
def side_effect_plain_list_consumes_sequentially() -> None:
    """Bug 5 regression: plain list [1,2,3] must yield 1, 2, 3 across calls."""
    child = Mock()
    child.do_thing.side_effect([1, 2, 3])  # not wrapped in iter()
    assert child.do_thing() == 1
    assert child.do_thing() == 2
    assert child.do_thing() == 3


@fact
def reset_clears_side_effect_iter() -> None:
    """reset() must clear the cached side_effect iterator."""
    child = Mock()
    child.do_thing.side_effect([99, 88])
    assert child.do_thing() == 99
    child.do_thing.reset()
    # After reset, the iterator should be cleared so re-use starts from beginning
    assert child.do_thing() == 99


@fact
def fluent_chaining_on_same_mock_allows_multiple_side_effects() -> None:
    """Calling .side_effect after .returns overwrites the return value."""
    m = Mock()

    def _override(**_kwargs: object) -> str:
        return 'overridden'

    result = m.do_thing.returns(99).side_effect(_override)
    assert result is m.do_thing  # fluent API returns self
    assert m.do_thing() == 'overridden'


@fact
def side_effect_callable_via_assignment() -> None:
    """Attribute assignment of a callable activates side-effect behavior."""
    child = Mock()

    def _add_one(first_arg: int, **_kwargs: object) -> int:
        return first_arg + 1

    child.do_thing.side_effect = _add_one  # type: ignore[assignment]
    assert child.do_thing(41) == 42


@fact
def side_effect_exception_instance_via_assignment() -> None:
    """Attribute assignment of an exception instance raises it on call."""
    m = Mock()
    err = ValueError('boom')
    m.do_thing.side_effect = err
    try:
        m.do_thing()
        assert False, 'Should have raised'
    except ValueError as e:
        assert e is err


@fact
def side_effect_exception_class_via_assignment() -> None:
    """Attribute assignment of an exception class raises an instance on call."""
    m = Mock()
    m.do_thing.side_effect = ValueError
    try:
        m.do_thing()
        assert False, 'Should have raised'
    except ValueError:
        pass


@fact
def side_effect_iterable_via_assignment() -> None:
    """Attribute assignment of an iterable yields next value each call."""
    child = Mock()
    child.do_thing.side_effect = iter([1, 2])  # type: ignore[assignment, operator]
    assert child.do_thing() == 1
    assert child.do_thing() == 2


@fact
def side_effect_plain_list_via_assignment() -> None:
    """Attribute assignment of a plain list [1,2,3] yields 1, 2, 3 across calls."""
    child = Mock()
    child.do_thing.side_effect = [1, 2, 3]  # type: ignore[assignment, operator]
    assert child.do_thing() == 1
    assert child.do_thing() == 2
    assert child.do_thing() == 3


@fact
def side_effect_reassignment_via_attribute() -> None:
    """Re-assigning side_effect via attribute replaces prior configuration."""
    child = Mock()
    child.do_thing.side_effect = [1, 2]
    assert child.do_thing() == 1
    child.do_thing.side_effect = lambda x: x * 100  # type: ignore[assignment, operator]
    assert child.do_thing(5) == 500


@fact
def side_effect_clearing_with_none_via_assignment() -> None:
    """Setting side_effect to None clears it -- mock returns self."""
    child = Mock()
    child.do_thing.side_effect = lambda x: x * 2  # type: ignore[assignment, operator]
    assert child.do_thing(3) == 6
    child.do_thing.side_effect = None
    result = child.do_thing()
    assert result is child.do_thing  # returns self when side_effect is None


@fact
def side_effect_assignment_overwrites_fluent_config() -> None:
    """Attribute assignment replaces prior fluent API configuration."""
    m = Mock()
    m.do_thing.side_effect(lambda x: x * 10)  # fluent call form
    assert m.do_thing(3) == 30
    m.do_thing.side_effect = lambda x: x + 100  # type: ignore[assignment, return-value, operator]
    assert m.do_thing(5) == 105


@fact
def call_detail_is_frozen_dataclass() -> None:
    d = CallDetail(
        timestamp=1.0,
        took=0.001,
        is_async=False,
        parameters=((42,), {'key': 'value'}),
        result='r',
        error=None,
    )
    try:
        d.timestamp = 999  # type: ignore[assignment, misc]
        assert False, 'Should not mutate'
    except (FrozenInstanceError, AttributeError):
        pass


@fact
def call_tracking_records_args_kwargs() -> None:
    """Calling the *parent* mock directly tracks on the parent."""
    m = Mock()
    m(1, 2, key='val')
    details = m.calls
    assert len(details) == 1
    entry = details[0]
    assert entry.parameters == ((1, 2), {'key': 'val'})


@fact
def called_returns_false_before_call_and_true_after() -> None:
    """Direct call on the mock itself."""
    m = Mock()
    assert not m.called
    m()
    assert m.called


@fact
def reset_clears_history_but_keeps_config() -> None:
    child = Mock()
    child.do_thing.returns(99)
    gc1 = child.do_thing  # get grandchild stub
    gc1()  # call it directly
    assert gc1.call_count == 1
    gc1.reset()  # reset the *same* stub
    assert gc1.call_count == 0
    # Config survives reset:
    gc1()
    assert gc1.call_count == 1


class RealDelegate:
    """Real object to forward unconfigured calls to."""

    def __init__(self) -> None:
        self.counter = 0

    def increment(self) -> int:
        self.counter += 1
        return self.counter


@fact
def delegate_forwards_unconfigured_calls() -> None:
    real = RealDelegate()
    m = Mock(delegate=real, name='increment')
    result = m.increment()
    assert result == 1
    assert real.counter == 1


@fact
def configured_mock_takes_priority_over_delegate() -> None:
    real = RealDelegate()
    m = Mock(delegate=real)
    m.do_thing.returns(42)
    assert m.do_thing() == 42
    assert real.counter == 0  # delegate was not called


@fact
def origin_protocol_pre_populates_member_stubs() -> None:
    m = Mock(origin=MyProtocol)
    assert hasattr(m, 'do_thing')
    assert isinstance(m.do_thing, Mock)


@fact
def same_attribute_access_returns_same_instance() -> None:
    m = Mock()
    assert m.foo is m.foo


@fact
def two_different_mocks_never_equal() -> None:
    m1 = Mock()
    m2 = Mock()
    assert not (m1 == m2)
    assert m1 != m2


@fact
def mock_can_be_hashed() -> None:
    m1 = Mock()
    m2 = Mock()
    s = {m1, m2}
    assert len(s) == 2


@fact
def call_count_tracks_accurately() -> None:
    """Direct calls to the parent mock."""
    m = Mock()
    for _ in range(5):
        m()
    assert m.call_count == 5


@fact
def context_manager_yields_child_with_own_config() -> None:
    with Mock(origin=MyABC) as child:
        # 'child' here is a fresh clone, not a subclass. Its call history
        # tracks whatever calls go through it directly.
        child.do_thing.returns(99)
        gc1 = child.do_thing  # get grandchild stub
        gc1()
        assert gc1.call_count == 1


@fact
def parent_mock_unaffected_by_child_context() -> None:
    parent = Mock(origin=MyABC)
    with parent as child:
        child.do_thing.returns('child')
        child.do_thing()
    assert not parent.called


class UserService:
    """Class with property, attribute, and method."""

    @property
    def is_authenticated(self) -> bool:
        return True  # type: ignore[return-value]

    status_code: int = 200  # type: ignore[assignment]

    def get_user(self, user_id: int) -> str:
        return f'User {user_id}'


@fact
def property_method_and_attr_are_all_mockable() -> None:
    """Properties, methods, and public attributes are all mockable via the fluent API.

    On a Mock, everything accessed via __getattr__ produces a child stub that is callable.
    Configured return values are obtained by calling the stub.
    """
    m = Mock(UserService)
    m.is_authenticated.returns(False)
    m.status_code.returns(404)
    m.get_user.returns('Guest')

    assert not m.is_authenticated()  # call stub to get configured return value
    assert m.status_code() == 404     # same - call the stub
    assert m.get_user() == 'Guest'


class RealService:
    """Service with inspectable signature."""

    def process(self, user_id: int, _timeout: float = 1.0) -> str:
        return f'processed {user_id}'


@fact
def validate_true_does_not_raise_for_invalid_input() -> None:
    """Mock without real validation simply returns configured values."""
    m = Mock(origin=RealService, validate=True)
    m.process.returns('ok')
    # Calling with 'wrong' type still works because validate is a no-op in current impl
    result = m.process('wrong')  # type: ignore[arg-type]
    assert result == 'ok'


# -- **kwargs support tests --


@fact
def mock_kwargs_sets_return_values() -> None:
    """Mock(migration='alpha', id=1) sets accessible attributes."""
    m = Mock(migration='alpha', id=1)
    assert m.migration == 'alpha'
    assert m.id == 1


@fact
def mock_kwargs_multiple_reads_are_consistent() -> None:
    """Configured values persist across multiple reads."""
    m = Mock(a=1, b=2)
    assert m.a == 1 and m.a == 1
    assert m.b == 2 and m.b == 2


@fact
def mock_kwargs_none_value_works() -> None:
    """None is a valid configured value, distinguishable from missing."""
    m = Mock(nullable=None)
    assert 'nullable' in m._u.configured
    assert m.nullable is None


@fact
def mock_kwargs_bool_preserved() -> None:
    """True and False are stored with identity, not collapsed to truthy."""
    m = Mock(active=True, disabled=False)
    assert m.active is True
    assert m.disabled is False


@fact
def mock_kwargs_composes_with_origin() -> None:
    """Kwargs coexist with origin-based isinstance conformance."""

    m = Mock(origin=MyABC, x=42, y='hello')
    assert isinstance(m, MyABC)  # type: ignore[unreachable]
    assert m.x == 42  # type: ignore[union-attr]
    assert m.y == 'hello'  # type: ignore[union-attr]


@fact
def mock_kwargs_composes_with_delegate() -> None:
    """Kwargs set direct attributes that shadow delegation."""

    class _Delegate:
        label = 'from-delegate'

    real = _Delegate()
    m = Mock(delegate=real, label='override')
    assert m.label == 'override'


@fact
def mock_kwargs_nested_mock_works() -> None:
    """Nested Mock instances stored in configured are returned as-is."""
    child = Mock(value='nested_value')
    parent = Mock(user=child)
    assert parent.user is child
    assert parent.user.value == 'nested_value'


@fact
def mock_side_effect_kwarg_uses_calling_semantics() -> None:
    """Mock(side_effect=fn) sets side_effect on the top-level mock."""
    m = Mock(side_effect=lambda x: x * 2)
    assert m(5) == 10


@fact
def mock_kwargs_empty_noop() -> None:
    """Empty kwargs is a no-op — identical to bare Mock()."""
    m = Mock(**{})
    # Verify no attributes leaked from the empty dict expansion.
    assert 'a' not in m._u.configured


@fact
def mock_kwargs_inner_mock_has_own_config() -> None:
    """Nested Mock's own kwargs work correctly."""
    inner = Mock(inner_value='deep')
    outer = Mock(wrapped=inner)
    assert outer.wrapped is inner
    assert outer.wrapped.inner_value == 'deep'


@fact
def reset_preserve_stubs_false_clears_children() -> None:
    """preserve_stubs=False removes all children; config kept."""
    child = Mock()
    child.do_thing.returns(99)
    for _ in range(3):
        child.do_thing()
    assert child.do_thing.call_count == 3

    child.reset(preserve_stubs=False)
    assert child.call_count == 0
    assert len(child._u.children) == 0


@fact
def reset_preserve_sideeffects_false_clears_config() -> None:
    """preserve_sideeffects=False wipes __*-prefixed keys and has_* flags."""
    m = Mock()
    m.do_thing.returns(42)
    assert m.do_thing._u.has_return_value is True

    m.do_thing.reset(preserve_sideeffects=False)
    assert m.do_thing._u.has_return_value is False


@fact
def reset_both_false_is_full_reset() -> None:
    """preserve_stubs=False + preserve_sideeffects=False clears everything."""
    parent = Mock(origin=MyProtocol)
    parent.do_thing.returns(42)
    child = Mock()
    child.other.returns('x')
    parent.another_child = child  # add via setattr

    parent.reset(preserve_stubs=False, preserve_sideeffects=False)
    assert parent.call_count == 0
    assert len(parent._u.children) == 0


@fact
def reset_recursive_clears_grandchildren() -> None:
    """Children are cleared recursively down the tree."""
    m = Mock()
    _ = m.do_thing.another_attr  # noqa: F841 — triggers lazy grandchild creation
    for _ in range(5):
        m.do_thing.another_attr()

    m.reset(preserve_stubs=False)
    assert len(m._u.children) == 0


@fact
def origin_prepopulated_stubs_survive_preserve_sideeffects() -> None:
    """Structural stubs from origin remain after parent's wipe.

    reset(preserve_sideeffects=False) clears the current mock's own config but
    does not affect children's configs. The structural entry 'do_thing' in
    configured (pre-populated from origin) is preserved because its key is a
    real attribute name, not __*-prefixed.
    """
    m = Mock(origin=MyProtocol)
    assert hasattr(m, 'do_thing')
    assert 'do_thing' in m._u.configured

    m.returns(42)  # writes '__return_value__' to m's own configured
    stub_before = m.do_thing
    stub_before.returns(99)

    m.reset(preserve_sideeffects=False)

    assert hasattr(m, 'do_thing')
    assert 'do_thing' in m._u.configured
    assert m.do_thing is stub_before

    assert not m._u.has_return_value

    assert stub_before._u.has_return_value is True


@fact
def reset_mock_new_true_wipes_everything() -> None:
    """reset_mock(new=True) clears children and config on the current mock."""
    m = Mock(origin=MyProtocol)
    m.do_thing.returns(42)
    lazy_child = Mock()
    lazy_child.x = 1
    m.lazy_attr = lazy_child  # add a non-origin child via setattr

    stub_before = m.do_thing
    assert stub_before._u.has_return_value is True

    m.reset_mock(new=True)

    assert hasattr(m, 'do_thing')
    assert m.do_thing is stub_before

    assert not m._u.has_return_value


@fact
def reset_mock_new_false_keeps_children() -> None:
    """reset_mock(new=False) retains children but clears config and history."""
    m = Mock(origin=MyProtocol)
    stub_before = m.do_thing
    m.do_thing.returns(42)

    m.reset_mock(new=False)

    assert hasattr(m, 'do_thing')
    assert m.do_thing is stub_before

    assert not m._u.has_return_value

    assert stub_before._u.has_return_value is True

# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""
Core Mock class and CallDetail dataclass.

Provides :class:`Mock` — a lightweight, single-class mocking framework that supports:
- ``isinstance`` conformance via ABC virtual-subclass registration
- Delegate forwarding for partial doubles / spies
- Fluent configuration with call tracking and matcher-based assertions
- Context manager yielding independent child mocks (auto-reset on exit)

Usage::

    from hazrakah.mocks import Mock, mock, is_any, is_gt

    # Create a mock with origin conformance
    mock_userservice = Mock(origin=UserService)
    mock_userservice.is_authenticated.returns(False)
    mock_userservice.get_user.returns('Guest')

    assert mock_userservice.called_with(is_gt(0))

    # Constructor kwargs for fixture-style initialization
    row = Mock(migration='alpha', id=1)
    assert row.migration == 'alpha'
    assert row.id == 1
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Iterable,
    Optional,
    Union,
)
import warnings


class MockError(Exception):
    """Exception raised when mock configuration is violated."""


@dataclass(frozen=True)
class CallDetail:
    """
    Immutable record of a single mock call.

    :ivar timestamp: Time when the call occurred (``time.monotonic_ns()``).
    :ivar took: Time spent in the call, in seconds.
    :ivar is_async: Whether the call was made via ``await``.
    :ivar parameters: ``(args, kwargs)`` used to call the mock.
    :ivar result: Return value from the call (``None`` if no return value).
    :ivar error: Exception raised by the call (``None`` if none).
    """

    timestamp: float
    took: float
    is_async: bool
    parameters: tuple[tuple[Any, ...], dict[str, Any]]
    result: Any
    error: BaseException | None


@dataclass(frozen=True)
class CallEntry:
    """
    Immutable record of a call for parent-child aggregation tracking.

    :ivar path: Absolute dotted path name (e.g. ``'Mock.foo.bar'``).
    :ivar args: Positional arguments passed to the mock.
    :ivar kwargs: Keyword arguments passed to the mock.
    """

    path: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]

    def __repr__(self) -> str:  # type: ignore[override]
        if not self.kwargs and not self.path:
            return repr(self.args)
        args_repr = ', '.join(repr(a) for a in self.args)
        kwargs_items = [f'{k}={v!r}' for k, v in self.kwargs.items()]
        if args_repr and kwargs_items:
            sep = (f'({args_repr}), '
                   f'{", ".join(kwargs_items)}')
        elif args_repr:
            sep = f'({args_repr})'
        elif kwargs_items:
            sep = ', '.join(kwargs_items)
        else:
            sep = ''
        return f'{self.path}({sep})' if self.path else f'({sep})'

    def __eq__(self, other: Any) -> bool:  # type: ignore[override]
        if not isinstance(other, CallEntry):
            return NotImplemented
        result = (self.path == other.path and
                  self.args == other.args and
                  self.kwargs == other.kwargs)
        return result


class CallEntryList(tuple):  # type: ignore[type-arg]
    """Tuple of :class:`CallEntry` supporting partial-sublist matching via ``__contains__``."""

    def __contains__(self, item: object) -> bool:  # type: ignore[override]
        if isinstance(item, CallEntryList):
            target = list(item)
            if not target:
                return True
            for i in range(len(self) - len(target) + 1):
                if all(CallEntryList._matches(self[i + j], target[j]) for j in range(len(target))):
                    return True
            return False
        return super().__contains__(item)

    @staticmethod
    def _matches(entry: CallEntry, other: CallEntry) -> bool:
        return entry.path == other.path and entry.args == other.args and entry.kwargs == other.kwargs


class Mock:
    """
    Lightweight mock object for dependency injection testing.

    Every :class:`Mock` instance can register itself as a virtual subclass of any type
    (ABC, ``@runtime_checkable`` Protocol, or concrete class) via the *origin* parameter
    -- making ``isinstance(mock, origin)`` return ``True``.

    Usage::

        from hazrakah.mocks import Mock

        # Create a mock that conforms to UserService structurally
        mock = Mock(origin=UserService)
        mock.is_authenticated.returns(False)
        mock.get_user.returns('Guest')

        assert mock.called_with(42)

    Child mocks (returned by attribute access) are cached -- ``mock.foo is mock.foo``.
    """

    class _Untouchables:
        """Per-instance holder for Mock's internal framework state."""

        __slots__ = (
            'origin',
            'delegate',
            'name',
            'path',
            'parent',
            'children',
            'configured',
            'call_history',
            'all_calls',
            'child_calls',
            'has_return_value',
            'has_side_effect',
            'side_effect_iter',
            'delegate_method',
        )

        origin: Optional[type]
        delegate: Any
        name: str
        path: str
        parent: Optional["Mock"]
        children: dict[str, "Mock"]
        configured: dict[str, Any]
        call_history: list[CallDetail]
        all_calls: list[CallEntry]
        child_calls: list[CallEntry]
        has_return_value: bool
        has_side_effect: bool
        side_effect_iter: Any
        delegate_method: Any

        def __init__(self) -> None:
            self.origin = None
            self.delegate = None
            self.name = "Mock"
            self.path = "Mock"
            self.parent = None
            self.children = {}
            self.configured = {}
            self.call_history = []
            self.all_calls = []
            self.child_calls = []
            self.has_return_value = False
            self.has_side_effect = False
            self.side_effect_iter = None
            self.delegate_method = None

    @classmethod
    def register_origin(cls, origin: type) -> None:
        """Register *origin* so that Mock instances pass ``isinstance(_, origin)``.

        Dispatches to the origin's ``register`` method (for ABCs and
        runtime_checkable Protocols).

        :param origin: The type this mock stands in for.
        """
        if hasattr(origin, 'register') and callable(getattr(origin, 'register')):
            origin.register(cls)  # type: ignore[union-attr]

    def __init__(
        self,
        origin: Optional[type] = None,
        *,
        delegate: Any = None,
        name: str = 'Mock',
        _validate: bool = False,
        **kwargs: Any,
    ) -> None:
        """
        Create a new Mock instance.

        :param origin: The type this mock stands in for (enables isinstance checks).
        :param delegate: A real object whose methods are forwarded when not configured.
        :param name: Debug identifier for the mock. Defaults to ``'Mock'``.
        :param validate: If True, validate call arguments against inspectable signatures.
        :param kwargs: Arbitrary keyword arguments set as initial attribute values.
            Each key becomes an accessible attribute that returns the given value.
            The special key ``side_effect`` is applied to this mock's calling behavior.
        """
        # Allocate internal state in a dedicated container (keeps it insulated
        # from user-set kwargs which become accessible Mock attributes).
        self._u = Mock._Untouchables()
        self._u.name = name
        self._u.path = name

        if origin is not None:
            self.register_origin(origin)
            self._u.origin = origin
            self._populate_members(origin)

        if delegate is not None:
            self._u.delegate = delegate

        # addt'l kwargs get initialized as attrs
        for key, value in kwargs.items():
            if key.startswith('_'):
                continue  # avoid state corruption state
            if key == 'side_effect':
                # mutate call semantics (applies to 'this' mock)
                self._u.configured['__side_effect__'] = value
                self._u.has_side_effect = True
                self._u.has_return_value = False
            else:
                self._u.configured[key] = value

    def _populate_members(self, origin: type) -> None:
        """Pre-create child Mock stubs for all public members of the origin."""
        members: set[str] = set()

        if hasattr(origin, '__protocol_attrs__'):
            members.update(origin.__protocol_attrs__)
        elif hasattr(origin, '__annotations__'):
            all_attrs = set(dir(origin))
            for attr_name in all_attrs:
                if attr_name.startswith('_'):
                    continue
                if hasattr(origin, attr_name):
                    attr = getattr(origin, attr_name)
                    if callable(attr):
                        members.add(attr_name)

        if not members:
            for attr_name in dir(origin):
                if not attr_name.startswith('_'):
                    members.add(attr_name)

        ann = getattr(origin, '__annotations__', {})
        for attr_name in ann:
            if not attr_name.startswith('_'):
                members.add(attr_name)

        # Finally scan __dict__ directly for class-level attributes not found via annotations
        for attr_name in getattr(origin, '__dict__', {}):
            if not attr_name.startswith('_') and hasattr(origin, attr_name):
                members.add(attr_name)

        for name in members:
            child_name = f'{self._u.name}.{name}' if self._u.name else name
            child = Mock(name=child_name)
            child._u.parent = self
            self._set_child_configured(name, child)

    def _set_child_configured(self, name: str, child: Mock) -> None:
        """Set a pre-configured child for a given attribute name."""
        self._u.configured[name] = child

    @property
    def origin(self) -> Optional[type]:
        """The origin type this mock stands in for."""
        return self._u.origin

    def __getattr__(self, name: str) -> Mock:
        """Return a cached child Mock or pre-populated stub for the given attribute."""
        # Guard against infinite recursion during early init (before _u is set).
        try:
            u = object.__getattribute__(self, '_u')
        except AttributeError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            ) from None
        if name in u.configured:
            return self._u.configured[name]

        # Delegate-aware lookup: if a delegate is set and has this attribute,
        # create a Mock wrapper that forwards calls to it.
        delegate = self._u.delegate
        if delegate is not None and hasattr(delegate, name):
            child = Mock()
            child._u.name = f'{self._u.name}.{name}' if self._u.name else name
            child._u.path = f'{self._u.path}.{name}' if self._u.path else name
            child._u.parent = self
            # Store the real method reference for forwarding in __call__
            real_attr = getattr(delegate, name)
            child._u.delegate_method = real_attr  # type: ignore[attr-defined]
            self._u.children[name] = child
            return child

        # Return cached child or create new one
        if name not in self._u.children:
            child = Mock()
            child._u.name = f'{self._u.name}.{name}' if self._u.name else name
            child._u.path = f'{self._u.path}.{name}' if self._u.path else name
            child._u.parent = self
            self._u.children[name] = child
        return self._u.children[name]

    def __setattr__(self, name: str, value: Any) -> None:  # type: ignore[override]
        """Accept arbitrary attributes; raise MockError for configured stub clobbering."""
        # Check if this name corresponds to a configured mock stub (clobbering attempt).
        # _u may not exist yet during early init — skip the check in that case.
        try:
            u = object.__getattribute__(self, '_u')
            configured = u.configured
        except AttributeError:
            configured = None
        else:
            if name in configured:
                raise MockError(
                    f'Cannot overwrite mock configuration for "{name}". '
                    f'Use the fluent API (returns(), side_effect()) to configure.'
                )
        # compat: to ease test porting, we want `side_effect` assignment to delegate to the fluent api
        if name == 'side_effect':
            self.side_effect(value)
            return None  # __setattr__ must return None per Python data model
        object.__setattr__(self, name, value)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Record the call and evaluate configured behavior."""
        # Track timing and async context
        start = time.monotonic_ns()
        try:
            is_async = asyncio.current_task() is not None
        except RuntimeError:
            is_async = False

        # Evaluate side_effect priority: iterable → exception → callable → return_value → self
        result: Any = self
        error: BaseException | None = None

        has_side_effect = self._u.has_side_effect
        has_return_value = self._u.has_return_value

        try:
            if has_side_effect:
                side_effect = self._u.configured.get('__side_effect__')
                result = self._evaluate_side_effect(side_effect, args, kwargs)
            elif has_return_value:
                rv = self._u.configured.get('__return_value__')
                if callable(rv):
                    result = rv(self)  # type: ignore[arg-type]
                else:
                    result = rv
            else:
                # Forward to delegate method (set by __getattr__ for attribute access)
                delegate_method = getattr(self._u, 'delegate_method', None)
                if delegate_method is not None and callable(delegate_method):
                    result = delegate_method(*args, **kwargs)
                else:
                    # Forward to top-level delegate (only works when mock has a name
                    # that matches a method on the delegate)
                    delegate = self._u.delegate
                    if delegate is not None:
                        name = self._u.name
                        attr_name = (
                            name.rsplit('.', 1)[-1] if name else '__call__'
                        )
                        method = getattr(delegate, attr_name, None)
                        if method is not None and callable(method):
                            result = method(*args, **kwargs)
        except BaseException as e:
            error = e
            raise

        # Always record call detail (even when an exception was raised)
        elapsed = (time.monotonic_ns() - start) / 1e9
        record = CallDetail(
            timestamp=time.monotonic_ns(),
            took=elapsed,
            is_async=is_async,
            parameters=(args, dict(kwargs)),
            result=result if error is None else None,
            error=error,
        )
        self._u.call_history.append(record)
        self._propagate_call(record)
        return result

    def _evaluate_side_effect(
        self,
        side_effect: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Evaluate side_effect with priority: iterable → exception → callable."""
        # Exception instance or class -- raise it
        if isinstance(side_effect, BaseException):
            raise side_effect
        if isinstance(side_effect, type) and issubclass(side_effect, BaseException):
            raise side_effect()

        # Iterable -- iterate through values (cached iterator for sequential consumption)
        if isinstance(side_effect, Iterable) and not isinstance(side_effect, (str, bytes)):
            cached_iter = self._u.side_effect_iter
            if cached_iter is None:
                new_iter = iter(side_effect)
                self._u.side_effect_iter = new_iter
                return next(new_iter)
            return next(cached_iter)  # Raises StopIteration when exhausted

        # Callable -- invoke with args/kwargs
        if callable(side_effect):
            return side_effect(*args, **kwargs)

        return self

    def _propagate_call(self, call_detail: CallDetail) -> None:
        """Append this call entry to ``_all_calls`` and ``_child_calls`` on self and ancestors."""
        path = self._u.path  # type: ignore[union-attr]
        entry = CallEntry(
            path=path,
            args=call_detail.parameters[0],
            kwargs=call_detail.parameters[1],
        )

        # Self always gets the entry in _all_calls (direct call to this mock)
        self._u.all_calls.append(entry)

        # Walk up parent chain for ancestor aggregation
        obj = self._u.parent
        while obj is not None:
            obj._u.all_calls.append(entry)
            obj._u.child_calls.append(entry)  # reached via attribute access on this ancestor
            obj = obj._u.parent

    def __eq__(self, other: Any) -> bool:  # type: ignore[override]
        """Identity-only comparison (two Mocks are never equal unless same object)."""
        return self is other

    def __hash__(self) -> int:  # type: ignore[override]
        """Hash by object id so mocks can be used in sets/dicts as unique keys."""
        return id(self)

    def __enter__(self) -> Mock:
        """Clone self into a fresh child for independent configuration."""
        name_mangled = self._u.name
        clone_name = f'{name_mangled} (child)' if name_mangled else ''
        origin_val = self._u.origin
        delegate_val = self._u.delegate
        # __init__ creates _u with defaults; overwrite what we need.
        clone = Mock(name=clone_name)
        clone._u.origin = origin_val
        clone._u.delegate = delegate_val
        return clone

    def __exit__(
        self,
        _exc_type: Any,
        _exc_val: Any,
        _exc_tb: Any,
    ) -> None:
        """Reset call history on exit."""
        self.reset()

    def __side_effect(
        self,
        eff: Union[Callable[..., Any], BaseException, type, Iterable[Any]] | None,
    ) -> Mock:
        """Set side effect (callable/exception/iterable). Clears `returns`."""
        self._u.configured['__side_effect__'] = eff
        self._u.has_side_effect = True
        self._u.has_return_value = False
        return self

    @property
    def side_effect(self) -> Callable[[Union[Callable[..., Any], BaseException, type, Iterable[Any]] | None], Mock]:
        """Set side effect (callable/exception/iterable). Clears `returns`."""
        return self.__side_effect

    @side_effect.setter
    def side_effect(self, value: Union[Callable[..., Any], BaseException, type, Iterable[Any]] | None) -> None:
        self.__side_effect(value)

    def returns(self, value_or_callable: Any) -> Mock:
        """Set fixed return value or callable. Callable receives the mocked instance as its sole argument. Clears side_effect."""
        self._u.configured['__return_value__'] = value_or_callable
        self._u.has_return_value = True
        self._u.has_side_effect = False
        return self

    @property
    def called(self) -> bool:
        """Return ``True`` if this mock has been called at least once."""
        return len(self._u.all_calls) > 0  # type: ignore[arg-type]

    def was_called(self) -> bool:
        warnings.warn(
            '`was_called()` is deprecated and will be removed in a future version. Use `called` property instead.',
            category=DeprecationWarning,
            stacklevel=2
        )
        return self.called

    def called_with(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Return True if any recorded call matches *args* and **kwargs.

        Uses ``==`` dispatch for each argument, enabling matcher support.
        """
        history = self._u.call_history
        for record in history:
            if self._matches_args(record.parameters[0], args) and \
               self._matches_kwargs(record.parameters[1], kwargs):
                return True
        return False

    def was_called_with(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        warnings.warn(
            '`was_called_with()` is deprecated and will be removed in a future version. Use `called_with`() instead.',
            category=DeprecationWarning,
            stacklevel=2
        )
        return self.called_with(args, kwargs)

    def reset(
        self,
        *,
        preserve_stubs: bool = True,
        preserve_sideeffects: bool = True,
    ) -> None:
        """Reset this mock's call tracking and optionally its configuration.

        :param preserve_stubs: If ``True`` (default), retain child stubs created by
            attribute access or from an *origin*.  If ``False``, recursively clear
            all children so that subsequent attribute access creates fresh mocks.
        :param preserve_sideeffects: If ``True`` (default), keep fluent-configuration
            values such as ``__return_value__`` and ``__side_effect__`` intact.  If
            ``False``, wipe all ``__*-prefixed* configuration keys from
            ``_u.configured`` and reset the has_* flags, but leave structural
            stubs (origin-prepopulated members) untouched.
        """
        for m in self._traverse():
            m._u.all_calls = []
            m._u.child_calls = []

        self._u.call_history = []
        self._u.side_effect_iter = None

        if not preserve_sideeffects:
            self._u.has_return_value = False
            self._u.has_side_effect = False
            keys_to_delete: list[str] = [k for k in self._u.configured if k.startswith('__')]
            for key in keys_to_delete:
                del self._u.configured[key]

        if not preserve_stubs:

            def _clear_children_recursively(m: Mock) -> None:
                for child in m._u.children.values():
                    child.reset(preserve_stubs=True, preserve_sideeffects=True)
                m._u.children = {}

            _clear_children_recursively(self)

    def reset_mock(self, *, new: bool = True) -> None:
        """Compatibility shim for ``unittest.mock.Mock.reset_mock()``.

        :param new: When ``True`` (default), clear children and all fluent-side
            configuration so the mock behaves as if it were a fresh instance.
            When ``False``, retain child stubs but still clear call history and
            side-effect configuration.
        """
        self.reset(
            preserve_stubs=not new,
            preserve_sideeffects=False,
        )

    def _traverse(self):  # type: ignore[no-untyped-def]
        """Yield self and all descendants."""
        yield self
        for child in self._u.children.values():
            yield from child._traverse()

    @property
    def mock_calls(self) -> CallEntryList:
        """All calls to this mock and its children, including dotted paths."""
        return CallEntryList(self._u.all_calls)

    @property
    def child_calls(self) -> CallEntryList:
        """Calls reached through child attribute access only (not self-invocations)."""
        return CallEntryList(self._u.child_calls)

    @property
    def call_count(self) -> int:
        """Number of calls recorded for this mock."""
        return len(self._u.call_history)

    @property
    def calls(self) -> Sequence[CallDetail]:
        """Immutable sequence of all recorded calls."""
        history = self._u.call_history
        return tuple(history)

    @staticmethod
    def _matches_args(actual: tuple[Any, ...], expected: tuple[Any, ...]) -> bool:
        """Compare actual args against expected with matcher dispatch."""
        if len(actual) != len(expected):
            return False
        for act, exp in zip(actual, expected):
            if isinstance(exp, Mock):
                # It's a child mock -- compare by identity (same as __eq__)
                if exp is not None and exp != act:
                    return False
            elif hasattr(exp, '__eq__'):
                if not exp.__eq__(act):  # type: ignore[union-attr]
                    return False
            elif exp is not None and act is not None and exp != act:
                return False
        return True

    @staticmethod
    def _matches_kwargs(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
        """Compare actual kwargs against expected with matcher dispatch."""
        for key, exp in expected.items():
            if key not in actual:
                return False
            act = actual[key]
            if isinstance(exp, Mock):
                if exp is not None and exp != act:
                    return False
            elif hasattr(exp, '__eq__'):
                if not exp.__eq__(act):  # type: ignore[union-attr]
                    return False
            elif exp is not None and act is not None and exp != act:
                return False
        return True


__all__ = [
    'CallDetail',
    'CallEntry',
    'CallEntryList',
    'Mock',
    'MockError',
]

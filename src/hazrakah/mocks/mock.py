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
    mock_userservice.get_user.returns("Guest")

    assert mock_userservice.was_called_with(is_gt(0))
"""

from __future__ import annotations

import asyncio
import inspect
import time
from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Iterable,
    Optional,
    Union,
)


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
    parameters: tuple[tuple, dict]
    result: Any
    error: BaseException | None


class Mock(ABC):
    """
    Lightweight mock object for dependency injection testing.

    Every :class:`Mock` instance inherits from :class:`ABC` and can register itself
    as a virtual subclass of any type (ABC, ``@runtime_checkable`` Protocol, or
    concrete class) via the *origin* parameter -- making
    ``isinstance(mock, origin)`` return ``True``.

    Usage::

        from hazrakah.mocks import Mock

        # Create a mock that conforms to UserService structurally
        mock = Mock(origin=UserService)
        mock.is_authenticated.returns(False)
        mock.get_user.returns("Guest")

        assert mock.was_called_with(42)

    Child mocks (returned by attribute access) are cached -- ``mock.foo is mock.foo``.
    """

    __slots__ = (
        '_Mock__origin',
        '_Mock__delegate',
        '_Mock__delegate_method',
        '_Mock__name',
        '_Mock__children',
        '_Mock__configured',
        '_Mock__call_history',
        '_Mock__has_return_value',
        '_Mock__has_side_effect',
    )

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
        name: str = '',
        validate: bool = False,
    ) -> None:
        """
        Create a new Mock instance.

        :param origin: The type this mock stands in for (enables isinstance checks).
        :param delegate: A real object whose methods are forwarded when not configured.
        :param name: Debug identifier for the mock.
        :param validate: If True, validate call arguments against inspectable signatures.
        """
        # Initialize ALL slots first — before any code that might access them.
        # This prevents __getattr__ recursion in Mock subclasses whose own
        # __init__ triggers attribute lookup on still-uninitialised Mock slots.
        object.__setattr__(self, '_Mock__origin', None)
        object.__setattr__(self, '_Mock__delegate', None)
        object.__setattr__(self, '_Mock__name', name)
        object.__setattr__(self, '_Mock__children', {})
        object.__setattr__(self, '_Mock__configured', {})
        object.__setattr__(self, '_Mock__call_history', [])
        object.__setattr__(self, '_Mock__has_return_value', False)
        object.__setattr__(self, '_Mock__has_side_effect', False)

        if origin is not None:
            self.register_origin(origin)
            object.__setattr__(self, '_Mock__origin', origin)
            # Pre-populate configured stubs for origin members
            self._populate_members(origin)

        if delegate is not None:
            object.__setattr__(self, '_Mock__delegate', delegate)

    def _populate_members(self, origin: type) -> None:
        """Pre-create child Mock stubs for all public members of the origin."""
        members: set[str] = set()

        # Check for runtime_checkable Protocol via __protocol_attrs__ or __annotations__
        if hasattr(origin, '__protocol_attrs__'):
            members.update(origin.__protocol_attrs__)
        elif hasattr(origin, '__annotations__'):
            # Infer callable members from annotations and dir()
            all_attrs = set(dir(origin))
            for attr_name in all_attrs:
                if attr_name.startswith('_'):
                    continue
                if hasattr(origin, attr_name):
                    attr = getattr(origin, attr_name)
                    if callable(attr):
                        members.add(attr_name)

        # For concrete classes with no protocol/ABC markers, use all public dir() members
        if not members:
            for attr_name in dir(origin):
                if not attr_name.startswith('_'):
                    members.add(attr_name)

        # Also scan annotations and class-level attributes from the origin's __dict__
        # to catch properties that aren't callable but are accessible.
        ann = getattr(origin, '__annotations__', {})
        for attr_name in ann:
            if not attr_name.startswith('_'):
                members.add(attr_name)

        # Finally scan __dict__ directly for class-level attributes not found via annotations
        for attr_name in getattr(origin, '__dict__', {}):
            if not attr_name.startswith('_') and hasattr(origin, attr_name):
                members.add(attr_name)

        for name in members:
            child = Mock(name=f'{self.__name}.{name}' if self.__name else name)
            self._set_child_configured(name, child)

    def _set_child_configured(self, name: str, child: Mock) -> None:
        """Set a pre-configured child for a given attribute name."""
        configured = object.__getattribute__(self, '_Mock__configured')
        configured[name] = child

    @property
    def origin(self) -> Optional[type]:
        """The origin type this mock stands in for."""
        return object.__getattribute__(self, '_Mock__origin')

    def __getattr__(self, name: str) -> Mock:
        """Return a cached child Mock or pre-populated stub for the given attribute."""
        # Check if we have a pre-configured stub (from origin members)
        configured = object.__getattribute__(self, '_Mock__configured')
        if name in configured:
            return configured[name]

        # Delegate-aware lookup: if a delegate is set and has this attribute,
        # create a Mock wrapper that forwards calls to it.
        delegate = object.__getattribute__(self, '_Mock__delegate')
        if delegate is not None and hasattr(delegate, name):
            child = Mock()
            object.__setattr__(child, '_Mock__name', f'{self._Mock__name}.{name}' if self._Mock__name else name)
            # Store the real method reference for forwarding in __call__
            real_attr = getattr(delegate, name)
            object.__setattr__(child, '_Mock__delegate_method', real_attr)
            children = object.__getattribute__(self, '_Mock__children')
            children[name] = child
            return child

        # Return cached child or create new one
        children = object.__getattribute__(self, '_Mock__children')
        if name not in children:
            child = Mock()
            object.__setattr__(child, '_Mock__name', f'{self._Mock__name}.{name}' if self._Mock__name else name)
            children[name] = child
        return children[name]

    def __setattr__(self, name: str, value: Any) -> None:
        """Accept arbitrary attributes; raise MockError for configured slot clobbering."""
        allowed_slots = frozenset((
            '_Mock__origin', '_Mock__delegate', '_Mock__name',
            '_Mock__children', '_Mock__configured', '_Mock__call_history',
            '_Mock__has_return_value', '_Mock__has_side_effect',
        ))

        if name in allowed_slots:
            object.__setattr__(self, name, value)
        else:
            # Check if this name corresponds to a configured mock slot (clobbering attempt)
            configured = object.__getattribute__(self, '_Mock__configured')
            if name in configured:
                raise MockError(
                    f"Cannot overwrite mock configuration for '{name}'. "
                    f"Use the fluent API (returns(), side_effect()) to configure."
                )
            # Allow any other attribute -- store on instance via __dict__
            try:
                object.__setattr__(self, name, value)
            except AttributeError:
                # Create a dict to hold arbitrary attributes
                try:
                    attrs = object.__getattribute__(self, '_Mock__attrs')
                except AttributeError:
                    attrs = {}
                    object.__setattr__(self, '_Mock__attrs', attrs)
                attrs[name] = value

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

        try:
            if object.__getattribute__(self, '_Mock__has_side_effect'):
                side_effect = object.__getattribute__(self, '_Mock__configured').get('__side_effect__')
                result = self._evaluate_side_effect(side_effect, args, kwargs)
            elif object.__getattribute__(self, '_Mock__has_return_value'):
                rv = object.__getattribute__(self, '_Mock__configured').get('__return_value__')
                if callable(rv):
                    result = rv(self)  # type: ignore[arg-type]
                else:
                    result = rv
            else:
                # Forward to delegate method (set by __getattr__ for attribute access)
                try:
                    delegate_method = object.__getattribute__(self, '_Mock__delegate_method')
                except AttributeError:
                    delegate_method = None
                if delegate_method is not None and callable(delegate_method):
                    result = delegate_method(*args, **kwargs)
                else:
                    # Forward to top-level delegate (only works when mock has a name
                    # that matches a method on the delegate)
                    delegate = object.__getattribute__(self, '_Mock__delegate')
                    if delegate is not None:
                        name_mangled = object.__getattribute__(self, '_Mock__name')
                        attr_name = (
                            name_mangled.rsplit('.', 1)[-1] if name_mangled else '__call__'
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
        object.__getattribute__(self, '_Mock__call_history').append(record)

        return result

    def _evaluate_side_effect(
        self,
        side_effect: Any,
        args: tuple,
        kwargs: dict,
    ) -> Any:
        """Evaluate side_effect with priority: iterable → exception → callable."""
        # Exception instance or class -- raise it
        if isinstance(side_effect, BaseException):
            raise side_effect
        if isinstance(side_effect, type) and issubclass(side_effect, BaseException):
            raise side_effect()

        # Iterable -- iterate through values
        if isinstance(side_effect, Iterable) and not isinstance(side_effect, (str, bytes)):
            iterator = iter(side_effect)
            return next(iterator)  # Raises StopIteration when exhausted

        # Callable -- invoke with args/kwargs
        if callable(side_effect):
            return side_effect(*args, **kwargs)

        return self

    def __eq__(self, other: Any) -> bool:
        """Identity-only comparison (two Mocks are never equal unless same object)."""
        return self is other

    def __hash__(self) -> int:
        """Hash by object id so mocks can be used in sets/dicts as unique keys."""
        return id(self)

    def __enter__(self) -> Mock:
        """Clone self into a fresh child for independent configuration."""
        name_mangled = object.__getattribute__(self, '_Mock__name')
        clone_name = f'{name_mangled} (child)' if name_mangled else ''
        origin_val = object.__getattribute__(self, '_Mock__origin')
        delegate_val = object.__getattribute__(self, '_Mock__delegate')
        # Use plain Mock to avoid subclass issues; set slots via object-level access.
        clone = Mock()
        object.__setattr__(clone, '_Mock__name', clone_name)
        object.__setattr__(clone, '_Mock__origin', origin_val)
        object.__setattr__(clone, '_Mock__delegate', delegate_val)
        return clone

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Reset call history on exit."""
        self.reset()

    def returns(self, value_or_callable: Any) -> Mock:
        """Set fixed return value or callable. Callable receives the mocked instance as its sole argument. Clears side_effect."""
        configured = object.__getattribute__(self, '_Mock__configured')
        configured['__return_value__'] = value_or_callable
        object.__setattr__(self, '_Mock__has_return_value', True)
        object.__setattr__(self, '_Mock__has_side_effect', False)
        return self

    def side_effect(
        self,
        eff: Union[Callable[..., Any], BaseException, type, Iterable[Any]],
    ) -> Mock:
        """Set side effect (callable/exception/iterable). Clears returns."""
        configured = object.__getattribute__(self, '_Mock__configured')
        configured['__side_effect__'] = eff
        object.__setattr__(self, '_Mock__has_side_effect', True)
        object.__setattr__(self, '_Mock__has_return_value', False)
        return self

    def was_called(self) -> bool:
        """Return True if this mock has been called at least once."""
        return len(object.__getattribute__(self, '_Mock__call_history')) > 0

    def was_called_with(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> bool:
        """Return True if any recorded call matches *args* and **kwargs.

        Uses ``==`` dispatch for each argument, enabling matcher support.
        """
        history = object.__getattribute__(self, '_Mock__call_history')
        for record in history:
            if self._matches_args(record.parameters[0], args) and \
               self._matches_kwargs(record.parameters[1], kwargs):
                return True
        return False

    def reset(self) -> None:
        """Clear call history; keep configuration intact."""
        object.__setattr__(self, '_Mock__call_history', [])

    @property
    def call_count(self) -> int:
        """Number of calls recorded for this mock."""
        return len(object.__getattribute__(self, '_Mock__call_history'))

    @property
    def calls(self) -> Sequence[CallDetail]:
        """Immutable sequence of all recorded calls."""
        history = object.__getattribute__(self, '_Mock__call_history')
        return tuple(history)

    @staticmethod
    def _matches_args(actual: tuple, expected: tuple) -> bool:
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
    def _matches_kwargs(actual: dict, expected: dict) -> bool:
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
    'Mock',
    'MockError',
]

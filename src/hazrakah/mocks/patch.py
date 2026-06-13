# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""
Patch mechanism for replacing module-level attributes with :class:`Mock` objects.

Provides both a **decorator** and **context manager** via the same :class:`patch` class,
with full async support. The patch atomically replaces an attribute on a module and
restores the original value when the patch is exited or the decorated function returns.

Usage::

    from hazrakah.mocks import patch, Mock

    # Context manager
    with patch('myapp.database.connect') as mock_connect:
        mock_connect.returns('connected')

    # Decorator (sync)
    @patch('myapp.database.connect')
    def test_something(mock_connect):
        assert mock_connect.was_called()

    # Decorator (async)
    @patch('myapp.database.connect')
    async def test_async(mock_connect):
        assert mock_connect.origin is not None

The patch instance itself is the Mock -- ``with patch(...) as m:`` yields a :class:`Mock`.
"""

from __future__ import annotations

import inspect
import sys
from types import ModuleType
from typing import (
    Any,
    Callable,
    Optional,
    TypeVar,
)

from .mock import Mock

T = TypeVar('T', bound=Callable[..., Any])


def _resolve_path(target_path: str) -> tuple[ModuleType, str]:
    """
    Resolve a dotted path (e.g. ``'myapp.database.connect'``) to ``(module, attr_name)``.

    :param target_path: Dotted attribute path.
    :returns: A tuple of the resolved module and the last segment as *attr_name*.
    :raises AttributeError: If the module or attribute does not exist.
    """
    parts = target_path.split('.')
    module_path_parts: list[str] = []

    for i in range(len(parts)):
        current_module_path = '.'.join(parts[:i + 1])
        try:
            __import__(current_module_path)
        except (ModuleNotFoundError, ImportError):
            break
        module_path_parts = parts[:i + 1]

    if not module_path_parts or len(parts) == len(module_path_parts):
        raise AttributeError(
            f'Cannot find module containing attribute "{target_path}"'
        )

    attr_name = parts[-1]
    resolved_module = sys.modules['.'.join(module_path_parts)]
    return (resolved_module, attr_name)


class patch:
    """
    Patch a module-level attribute with a :class:`Mock`.

    Can be used as both a context manager and a decorator. The same instance
    handles both via ``__enter__/__exit__`` and ``__call__``.

    Usage::

        # As context manager:
        with patch('myapp.db.connect') as mock_connect:
            mock_connect.returns('connected')

        # As decorator:
        @patch('myapp.db.connect')
        def test_something(mock_connect):
            assert mock_connect.was_called()
    """

    def __init__(
        self,
        target_path: str,
        origin: Optional[type] = None,
        **kwargs: Any,
    ) -> None:
        """
        Create a new patch for the given dotted path.

        :param target_path: Dotted attribute path to replace (e.g. ``'myapp.database.connect'``).
        :param origin: Optional type for Mock virtual-subclass registration.
        :param kwargs: Additional keyword arguments forwarded to the Mock constructor.
        """
        self._module, self._attr_name = _resolve_path(target_path)
        self._original = getattr(self._module, self._attr_name)
        self._kwargs = {**kwargs}
        if origin is not None:
            self._kwargs['origin'] = origin
        self._mock = Mock(**self._kwargs)

    def __enter__(self) -> Mock:
        """Replace the module attribute with the Mock and return it."""
        setattr(self._module, self._attr_name, self._mock)
        return self._mock

    def __exit__(
        self,
        _exc_type: Any,
        _exc_val: Any,
        _exc_tb: Any,
    ) -> None:
        """
        Restore the original value after the patch."""
        setattr(self._module, self._attr_name, self._original)

    def __call__(self, func: T) -> T:
        """
        Decorate *func* so each invocation is wrapped in a patch/unpatch cycle.

        Detects async functions and wraps them in an ``async_wrapper`` that
        ensures the mock lives only for the duration of the test call.
        """
        if inspect.iscoroutinefunction(func):

            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                mock_instance = self.__enter__()  # type: ignore[assignment]
                try:
                    return await func(mock_instance, *args, **kwargs)
                finally:
                    self.__exit__(None, None, None)

            async_wrapper.__name__ = func.__name__
            async_wrapper.__doc__ = func.__doc__
            async_wrapper.__wrapped__ = func  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]
        else:

            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                mock_instance = self.__enter__()  # type: ignore[assignment]
                try:
                    return func(mock_instance, *args, **kwargs)
                finally:
                    self.__exit__(None, None, None)

            sync_wrapper.__name__ = func.__name__
            sync_wrapper.__doc__ = func.__doc__
            sync_wrapper.__wrapped__ = func  # type: ignore[attr-defined]
            return sync_wrapper  # type: ignore[return-value]


__all__ = ['patch']

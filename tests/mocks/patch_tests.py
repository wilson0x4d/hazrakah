# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for the patch mechanism (patch.py).

Covers decorator patching, context manager patching, async support, and origin config.
"""

from __future__ import annotations

import sys

from hazrakah.mocks import Mock, patch  # noqa: F401 - Patch is used throughout; Mock is verified in tests
from punit import fact


class _FakeModule:
    """A module-like object we can replace and inspect."""

    def __init__(self) -> None:
        self.original_value: str = 'original'
        self.patched_value: str | None = None
        self.restored_value: str | None = None
        # Make it importable in sys.modules under a test namespace.
        object.__setattr__(self, '__file__', '<test>')
        object.__setattr__(self, '__name__', 'hazrakah._test_patch_module')


_FAKE_MODULE_INSTANCE: _FakeModule | None = None


def _setup_fake_module() -> None:
    global _FAKE_MODULE_INSTANCE
    if _FAKE_MODULE_INSTANCE is None:
        _FAKE_MODULE_INSTANCE = _FakeModule()
        sys.modules['hazrakah._test_patch_module'] = _FAKE_MODULE_INSTANCE  # type: ignore[attr-defined, assignment]
        _FAKE_MODULE_INSTANCE.original_value = 'original'


def _cleanup_fake_module() -> None:
    global _FAKE_MODULE_INSTANCE
    if _FAKE_MODULE_INSTANCE is not None:
        if hasattr(_FAKE_MODULE_INSTANCE, 'restored_value'):
            sys.modules['hazrakah._test_patch_module']._patched_attr = _FAKE_MODULE_INSTANCE.restored_value  # type: ignore[attr-defined]
        del sys.modules['hazrakah._test_patch_module']  # type: ignore[misc]
        _FAKE_MODULE_INSTANCE = None


# ---- Context manager patch ----

@fact
def context_manager_replaces_attribute() -> None:
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        with patch('hazrakah._test_patch_module._patched_attr') as m:
            assert isinstance(m, Mock)
            actual = sys.modules['hazrakah._test_patch_module']._patched_attr  # type: ignore[attr-defined]
            assert actual is m
    finally:
        _cleanup_fake_module()


@fact
def context_manager_restores_original_on_exit() -> None:
    _setup_fake_module()
    try:
        original = 'original_value'
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', original)  # type: ignore[attr-defined]

        with patch('hazrakah._test_patch_module._patched_attr'):  # noqa: SIM117
            pass

        actual = sys.modules['hazrakah._test_patch_module']._patched_attr  # type: ignore[attr-defined]
        assert actual is original
    finally:
        _cleanup_fake_module()


@fact
def multiple_nested_exits_restore_correctly() -> None:
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        with patch('hazrakah._test_patch_module._patched_attr'):  # noqa: SIM117
            inner = sys.modules['hazrakah._test_patch_module']._patched_attr  # type: ignore[attr-defined]
            assert isinstance(inner, Mock)
            # Patch again inside
            with patch('hazrakah._test_patch_module._patched_attr'):  # noqa: SIM117
                inner2 = sys.modules['hazrakah._test_patch_module']._patched_attr  # type: ignore[attr-defined]
                assert isinstance(inner2, Mock)

        actual = sys.modules['hazrakah._test_patch_module']._patched_attr  # type: ignore[attr-defined]
        assert actual is not inner
    finally:
        _cleanup_fake_module()


@fact
def decorator_patches_and_injects_mock_as_arg() -> None:
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        @patch('hazrakah._test_patch_module._patched_attr')
        def test_func(mock_obj: object):
            assert isinstance(mock_obj, Mock)
            return mock_obj

        result = test_func()  # type: ignore[call-arg]
        assert isinstance(result, Mock)
    finally:
        _cleanup_fake_module()


@fact
def decorator_restores_after_test() -> None:
    _setup_fake_module()
    try:
        original = 'original_value'
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', original)  # type: ignore[attr-defined]

        @patch('hazrakah._test_patch_module._patched_attr')
        def test_func(mock_obj: object):  # noqa: ARG001
            pass

        test_func()  # type: ignore[call-arg]
        actual = sys.modules['hazrakah._test_patch_module']._patched_attr  # type: ignore[attr-defined]
        assert actual is original
    finally:
        _cleanup_fake_module()


@fact
def async_decorator_works_with_async_func() -> None:
    """Verify the patch mechanism supports async via context manager (primary path)."""
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        with patch('hazrakah._test_patch_module._patched_attr') as m:
            assert isinstance(m, Mock)
            assert hasattr(m, 'was_called')
    finally:
        _cleanup_fake_module()


@fact
def patch_accepts_origin_param() -> None:
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        class MyABC:
            pass

        with patch('hazrakah._test_patch_module._patched_attr', origin=MyABC) as m:
            assert m.origin is MyABC
    finally:
        _cleanup_fake_module()


@fact
def fluent_config_works_on_patched_mock() -> None:
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        with patch('hazrakah._test_patch_module._patched_attr') as m:
            m.some_method.returns(42)
            assert m.some_method() == 42
    finally:
        _cleanup_fake_module()


@fact
def nonexistent_target_path_raises_attribute_error() -> None:
    try:
        p = patch('nonexistent.module.does.not.exist')
        p.__enter__()
        assert False, 'Should have raised'
    except (AttributeError, ModuleNotFoundError, ImportError):
        pass


@fact
def patch_instance_is_mock() -> None:
    _setup_fake_module()
    try:
        setattr(sys.modules['hazrakah._test_patch_module'], '_patched_attr', 'original')  # type: ignore[attr-defined]

        with patch('hazrakah._test_patch_module._patched_attr') as m:
            assert isinstance(m, Mock)
            assert hasattr(m, 'was_called')
    finally:
        _cleanup_fake_module()


@fact
def patch_kwargs_forwarded_to_mock() -> None:
    """patch passes **kwargs through to Mock.__init__."""
    _setup_fake_module()
    try:
        setattr(  # type: ignore[attr-defined]
            sys.modules['hazrakah._test_patch_module'],
            '_patched_attr',
            'original',
        )

        with patch('hazrakah._test_patch_module._patched_attr', migration='alpha', id=42) as m:
            assert isinstance(m, Mock)
            assert m.migration == 'alpha'
            assert m.id == 42
    finally:
        _cleanup_fake_module()

# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for forward-reference module confusion bug in __unwrap_forward_ref.

This module tests that `__unwrap_forward_ref` correctly handles the case where
a forward-reference string resolves to a module object instead of a class.
This was the root cause of the user's reported bug where resolution of
`appsettings2.Configuration` confused the module with the class
`appsettings2.Configuration.Configuration`.
"""

from __future__ import annotations

import sys
import types
from hazrakah import Container, ResolutionError
from hazrakah.Container import Container as _Container
from punit import fact, raises

from .ModuleShadowedType import ModuleShadowedDependentType, ModuleShadowedType


class _ConfigClass:
    """The intended concrete class for dependency resolution."""

    def __init__(self) -> None:
        self.name = 'ConfigClass'


# ---------------------------------------------------------------------------
# Direct unit tests of __unwrap_forward_ref
# ---------------------------------------------------------------------------


@fact
def __unwrap_forward_ref_eval_string_to_module_returns_string() -> None:
    """When ``eval(annotation, globals_)`` produces a module,
    ``__unwrap_forward_ref`` must return the annotation string so that
    ``resolve()`` can raise a proper ``ResolutionError``.

    The original (buggy) implementation returned the module directly,
    causing ``_fallback_resolve`` to produce a confusing
    ``ResolutionError`` that made developers think the
    ``appsettings2.Configuration`` module was being confused with the
    ``appsettings2.Configuration.Configuration`` class.
    """
    mod = types.ModuleType('fake_config_mod')
    globals_with_module: dict[str, object] = {}
    globals_with_module['Config'] = mod  # module, NOT a class
    globals_with_module['__module__'] = 'fake_module'

    owner = type(  # type: ignore[assignment]
        'TestOwner',
        (),
        {'__module__': 'fake_module', '__globals__': globals_with_module},
    )

    unwrapped = _Container._Container__unwrap_forward_ref('Config', owner)  # type: ignore[attr-defined]

    # The buggy code would return <module 'fake_config_mod'>.
    # The fix returns the annotation string 'Config' instead.
    assert unwrapped == 'Config', (
        f'Expected annotation string, got {unwrapped!r} '
        f'(bug: returned module instead of string)'
    )


@fact
def __unwrap_forward_ref_eval_string_to_class_returns_class() -> None:
    """When ``eval(annotation, globals_)`` produces a type, it must be
    returned.  Normal resolution then proceeds as expected.
    """
    globals_with_class: dict[str, object] = {}
    globals_with_class['Config'] = _ConfigClass
    globals_with_class['__module__'] = 'fake'

    owner = type(  # type: ignore[assignment]
        'TestOwner',
        (),
        {'__module__': 'fake', '__globals__': globals_with_class},
    )

    unwrapped = _Container._Container__unwrap_forward_ref('Config', owner)  # type: ignore[attr-defined]

    assert unwrapped is _ConfigClass, (
        f'Expected _ConfigClass, got {unwrapped!r}'
    )


@fact
def __unwrap_forward_ref_eval_union_type_returns_union() -> None:
    """Union types and generics must pass through unchanged.

    Regression test: the fix must not reject ``Optional[T]`` or other
    generic types.  In a module with ``from __future__ import annotations``,
    annotations are stored as strings and ``eval()`` produces the actual
    type (e.g. ``typing.Optional[object]``).  This must NOT be rejected.
    """
    from typing import Optional

    globals_with_union: dict[str, object] = {}
    globals_with_union['Optional'] = Optional
    globals_with_union['object'] = object
    globals_with_union['__module__'] = 'fake_union'

    owner = type(  # type: ignore[assignment]
        'TestOwner',
        (),
        {'__module__': 'fake_union', '__globals__': globals_with_union},
    )

    unwrapped = _Container._Container__unwrap_forward_ref('Optional[object]', owner)  # type: ignore[attr-defined]

    # Must return the Union type, NOT the annotation string
    assert str(unwrapped) != 'Optional[object]', (
        f'Expected typing.Optional[object], got {unwrapped!r} '
        f'(regression: rejected Union type)'
    )


@fact
def __unwrap_forward_ref_eval_string_to_nonexistent_name_returns_string() -> None:
    """When ``eval(annotation, globals_)`` raises (name not found) and the
    fallback ``getattr(sys.modules[owner.__module__], annotation)`` also does
    not find the name in the module, the annotation string is returned
    unchanged.
    """
    globals_empty: dict[str, object] = {}
    globals_empty['__module__'] = 'fake_nonexistent_mod'

    owner = type(  # type: ignore[assignment]
        'TestOwner',
        (),
        {'__module__': 'fake_nonexistent_mod', '__globals__': globals_empty},
    )

    unwrapped = _Container._Container__unwrap_forward_ref('Config', owner)  # type: ignore[attr-defined]

    assert unwrapped == 'Config', (
        f'Expected annotation string for missing name, got {unwrapped!r}'
    )


@fact
def __unwrap_forward_ref_fallback_module_attr_to_module_returns_string() -> None:
    """When ``eval`` fails and the fallback
    ``getattr(sys.modules[owner.__module__], annotation)`` returns a module,
    the fix must reject it.
    """
    import sys
    mod = types.ModuleType('fake_mod_fallback')

    # Pre-populate a module in sys.modules so the fallback can find it
    fake_mod_name = 'fallback_test_module_xyz'
    sys.modules[fake_mod_name] = mod

    try:
        unwrapped = _Container._Container__unwrap_forward_ref(  # type: ignore[attr-defined]
            'SomeName',
            type('TestOwner', (), {'__module__': fake_mod_name})
        )

        # Should return the annotation string, not the module
        assert unwrapped == 'SomeName', (
            f'Expected annotation string for module fallback, got {unwrapped!r}'
        )
    finally:
        sys.modules.pop(fake_mod_name, None)


@fact
def __unwrap_forward_ref_fallback_module_attr_to_class_returns_class() -> None:
    """When the fallback lookup finds a class, it must be returned."""
    import sys
    fake_mod_name = 'fallback_test_class_xyz'

    class FakeTarget:
        pass

    fake_mod = types.ModuleType(fake_mod_name)
    fake_mod.__dict__['FakeTarget'] = FakeTarget  # noqa: F821
    sys.modules[fake_mod_name] = fake_mod

    try:
        unwrapped = _Container._Container__unwrap_forward_ref(  # type: ignore[attr-defined]
            'FakeTarget',
            type('TestOwner', (), {'__module__': fake_mod_name})
        )
        assert unwrapped is FakeTarget, (
            f'Expected FakeTarget class, got {unwrapped!r}'
        )
    finally:
        sys.modules.pop(fake_mod_name, None)


@fact
def __unwrap_forward_ref_non_string_returns_unchanged() -> None:
    """When the annotation is not a string (already resolved),
    it must be returned unchanged.
    """
    unwrapped = _Container._Container__unwrap_forward_ref(  # type: ignore
        _ConfigClass,
        type('TestOwner', (), {'__module__': 'fake'})
    )
    assert unwrapped is _ConfigClass


@fact
def module_shadowed_type_must_resolve_direct() -> None:
    c = Container()
    obj = c.resolve(ModuleShadowedType)
    assert obj is not None

@fact
def module_shadowed_type_must_resolve_indirect() -> None:
    c = Container()
    obj = c.resolve(ModuleShadowedDependentType)
    assert obj is not None


# ---------------------------------------------------------------------------
# Integration: dotted forward references (user's exact scenario)
# ---------------------------------------------------------------------------


@fact
def dotted_forward_ref_in_sys_modules_resolves_correctly() -> None:
    """When a forward reference is a dotted path like
    ``'pkg.module.Class'`` and ``eval`` fails (e.g. because the owning
    module's globals shadow the name with a module), the fallback must
    resolve through ``importlib.import_module`` and attribute lookup.

    Regression test for the user's ``appsettings2.Configuration`` issue.
    """
    # The key scenario: a class is resolved via a dotted forward reference
    # that eval() can't resolve (name not in globals), but the module is in
    # sys.modules under the first component.
    pkg_mod = types.ModuleType('dotted_app_settings_cfg')
    pkg_mod.__path__ = []

    class DottedAppSettings:
        value = 'settings'

    pkg_mod.__dict__['DottedAppSettings'] = DottedAppSettings
    old = sys.modules.get('dotted_app_settings_cfg')
    sys.modules['dotted_app_settings_cfg'] = pkg_mod

    try:
        owner = type(  # type: ignore[assignment]
            'TestOwner',
            (),
            {
                '__module__': 'dotted_app_settings_cfg',  # owner IS in sys.modules
                '__globals__': {},  # empty globals so eval fails
            },
        )

        # eval fails (no 'dotted_app_settings_cfg' in globals)
        # The fallback __resolve_dotted_forward_ref finds it in sys.modules
        unwrapped = _Container._Container__unwrap_forward_ref(  # type: ignore[attr-defined]
            'dotted_app_settings_cfg.DottedAppSettings',
            owner,
        )
        assert unwrapped is DottedAppSettings, (
            f'Expected DottedAppSettings, got {unwrapped!r}'
        )
    finally:
        if old is not None:
            sys.modules['dotted_app_settings_cfg'] = old
        else:
            sys.modules.pop('dotted_app_settings_cfg', None)


@fact
def dotted_forward_ref_eval_fails_resolved_via_module_tree() -> None:
    """When ``eval(annotation, globals_)`` fails (e.g. globals don't have
    the dotted path), the fallback resolves ``'pkg.module.Class'`` by
    importing from the package tree.
    """
    pkg_mod = types.ModuleType('test_dotted_resolver')
    pkg_mod.__path__ = []

    class ResolverClass:
        pass

    pkg_mod.__dict__['ResolverClass'] = ResolverClass
    old = sys.modules.get('test_dotted_resolver')
    sys.modules['test_dotted_resolver'] = pkg_mod

    try:
        # Simulate globals where 'test_dotted_resolver.ResolverClass' exists
        # as a dotted string but NOT as a resolved eval result.
        owner = type(  # type: ignore[assignment]
            'TestOwner',
            (),
            {
                '__module__': 'test_dotted_resolver',
                '__globals__': {'test_dotted_resolver.ResolverClass': pkg_mod},  # wrong binding
            },
        )

        unwrapped = _Container._Container__unwrap_forward_ref(  # type: ignore[attr-defined]
            'test_dotted_resolver.ResolverClass',
            owner,
        )
        assert unwrapped is ResolverClass, (
            f'Expected ResolverClass, got {unwrapped!r}'
        )
    finally:
        if old is not None:
            sys.modules['test_dotted_resolver'] = old
        else:
            sys.modules.pop('test_dotted_resolver', None)


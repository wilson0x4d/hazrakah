# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for ergonomic decorator registration (@singleton, @transient, @instanced).

Each test that uses decorated classes must call ``_cleanup()`` in a finally block
to reset the global manager between tests.
"""

from __future__ import annotations

from typing import Protocol

from hazrakah import (
    Lifetime,
    RegistrationError,
    Container,
    instanced,
    singleton,
    transient,
)
from hazrakah.lifetime_decorators import (
    DecorationInfo as _DecoInfo,
    _DecorationInfoManager,
    _raise_if_provides_decorated,
    _sort_decoration_infos,
)
from hazrakah.provides_decorator import provides
from punit import fact, teardown


@teardown
def _cleanup() -> None:
    """Reset the global decoration manager for isolation between tests."""
    _DecorationInfoManager._clear_store()


@fact
def clear_store_resets_manager():
    """Bug 4 regression: _clear_store() resets state."""
    class IFooZZ:
        pass

    @singleton(types=IFooZZ)  # noqa: F811
    class TempClassZZ:
        pass

    assert len(_DecorationInfoManager.instance().get_all()) > 0

    _DecorationInfoManager._clear_store()
    assert _DecorationInfoManager.instance().get_all() == []


@fact
def clear_store_recreates_singleton():
    """Bug 4 regression: after clear, new instance() call creates fresh manager."""
    mgr1 = _DecorationInfoManager.instance()
    _DecorationInfoManager._clear_store()
    mgr2 = _DecorationInfoManager.instance()
    assert mgr1 is not mgr2


@fact
def decoration_info_is_frozen() -> None:

    class IFoo1:
        pass

    info = _DecoInfo(
        lifetime=Lifetime.SINGLETON,
        target=IFoo1,
        interface=IFoo1,
        depends_on=(),
    )
    try:
        info.lifetime = Lifetime.TRANSIENT  # type: ignore[assignment, misc]
        assert False, 'Should not mutate a frozen dataclass'
    except AttributeError:
        pass


@fact
def decoration_info_equality_works() -> None:

    class IFoo1:
        pass

    info1 = _DecoInfo(
        lifetime=Lifetime.SINGLETON,
        target=IFoo1,
        interface=IFoo1,
        depends_on=(),
    )
    info2 = _DecoInfo(
        lifetime=Lifetime.SINGLETON,
        target=IFoo1,
        interface=IFoo1,
        depends_on=(),
    )
    assert info1 == info2


@fact
def manager_returns_singleton() -> None:
    """Multiple calls to instance() return the same object."""
    m1 = _DecorationInfoManager.instance()
    m2 = _DecorationInfoManager.instance()
    assert m1 is m2


@fact
def manager_tracks_registrations() -> None:

    class IFoo2:
        pass

    @transient(types=IFoo2)  # noqa: F811
    class TrackHelper:
        pass

    mgr = _DecorationInfoManager.instance()
    all_entries = mgr.get_all()
    assert IFoo2 in [e.interface for e in all_entries]


@fact
def singleton_class_no_parens_marks_lifecycle() -> None:

    @singleton
    class PlainClass:
        pass

    assert hasattr(PlainClass, '__hazrakah_lifecycle')
    assert getattr(PlainClass, '__hazrakah_lifecycle') is Lifetime.SINGLETON


@fact
def singleton_class_with_parens_marks_lifecycle() -> None:

    @singleton()  # type: ignore[operator]  # noqa: F811
    class PlainClass2:
        pass

    assert getattr(PlainClass2, '__hazrakah_lifecycle') is Lifetime.SINGLETON


@fact
def singleton_class_explicit_typesregisters_interface() -> None:

    class IFoo3:
        pass

    @singleton(types=IFoo3)  # noqa: F811
    class ExplicitFoo:
        pass

    all_entries = _DecorationInfoManager.instance().get_all()
    assert IFoo3 in [e.interface for e in all_entries]
    entry = next(e for e in all_entries if e.interface is IFoo3)
    assert entry.lifetime is Lifetime.SINGLETON
    assert entry.target is ExplicitFoo


@fact
def singleton_class_multiple_interfaces_registers_each() -> None:

    class IFoo4:
        pass

    class IBar4:
        pass

    @singleton(types=(IFoo4, IBar4))  # noqa: F811
    class MultiIFace:
        pass

    manager = _DecorationInfoManager.instance()
    entries = [e for e in manager.get_all() if e.target is MultiIFace]
    assert len(entries) == 2
    interfaces = {e.interface for e in entries}
    assert interfaces == {IFoo4, IBar4}


@fact
def singleton_returns_target_unmodified() -> None:

    class IFooX:
        pass

    @singleton(types=IFooX)  # noqa: F811
    class ReturnTarget:
        x = 42

    obj = ReturnTarget()
    assert obj.x == 42


@fact
def transient_class_marks_transient() -> None:

    class IFoo3:
        pass

    @transient(types=IFoo3)  # noqa: F811
    class TransClass:
        pass

    assert getattr(TransClass, '__hazrakah_lifecycle') is Lifetime.TRANSIENT


@fact
def instanced_class_marks_instance() -> None:

    class IFoo3:
        pass

    @instanced(types=IFoo3)  # noqa: F811
    class InstClass:
        pass

    assert getattr(InstClass, '__hazrakah_lifecycle') is Lifetime.INSTANCE


@fact
def singleton_then_transient_raises() -> None:

    class IFoo3:
        pass

    try:

        @singleton(types=IFoo3)  # noqa: F811
        class MixClassA:
            pass

        @transient(types=IFoo3)  # type: ignore[call-overload] # noqa: F811
        def _mix_class_b(resolver):  # type: ignore[misc] # noqa: F811
            return IFoo3()

        assert False, 'Should have raised RegistrationError'
    except RegistrationError as e:
        assert 'cannot both decorate' in str(e)


@fact
def multiple_same_lifetime_valid() -> None:

    class IFoo3:
        pass

    class IBar3:
        pass

    @singleton(types=IFoo3)  # noqa: F811
    class SameLifetime1:
        pass

    @singleton(types=IBar3)  # noqa: F811
    class SameLifetime2(SameLifetime1):
        pass

    assert getattr(SameLifetime1, '__hazrakah_lifecycle') is Lifetime.SINGLETON


@fact
def factory_with_one_param_works() -> None:

    class IFactory:
        pass

    @singleton(types=IFactory)  # type: ignore[call-overload] # noqa: F811
    def make_bar(_resolver):  # type: ignore[misc] # noqa: F811
        return IFactory()


@fact
def factory_without_positional_param_raises() -> None:

    class IFoo3:
        pass

    try:

        @singleton(types=IFoo3)  # type: ignore[call-overload] # noqa: F811
        def no_args():  # type: ignore[return, call-overload, misc] # noqa: F811
            return IFoo3()

        assert False, 'Should have raised RegistrationError'
    except RegistrationError as e:
        assert 'exactly one positional parameter' in str(e)


@fact
def factory_with_multiple_positional_params_raises() -> None:

    class IFactory2:
        pass

    try:

        @singleton(types=IFactory2)  # type: ignore[call-overload] # noqa: F811
        def too_many_args(a, b):  # type: ignore[return, call-overload, misc] # noqa: F811
            return IFactory2()

        assert False, 'Should have raised RegistrationError'
    except RegistrationError as e:
        assert 'exactly one positional parameter' in str(e)


@fact
def factory_function_without_typesraises() -> None:

    class IBar3:
        pass

    try:

        @singleton  # noqa: F811
        def bare_factory(resolver):  # type: ignore[misc] # noqa: F811
            return IBar3()

        assert False, 'Should have raised RegistrationError'
    except RegistrationError as e:
        assert 'as=' in str(e)


@fact
def decorator_accepts_depends_on() -> None:

    class IFoo3:
        pass

    class IBar3:
        pass

    @singleton(types=IFoo3, depends_on=(IBar3,))  # noqa: F811
    class DependentClass:
        pass

    manager = _DecorationInfoManager.instance()
    entries = [e for e in manager.get_all() if e.interface is IFoo3]
    entry = next(e for e in entries)
    assert IBar3 in entry.depends_on


@fact
def register_decorated_singleton_resolves() -> None:

    class IFoo1:
        pass

    @singleton(types=IFoo1)  # noqa: F811
    class RegFoo:
        def __init__(self) -> None:  # type: ignore[misc]
            self.answer = 42

    container = Container()
    container.register_decorated()
    resolved = container.resolve(IFoo1)  # type: ignore[arg-type]
    assert isinstance(resolved, RegFoo)
    assert resolved.answer == 42


@fact
def register_decorated_transient_resolves() -> None:

    class IFoo1:
        pass

    @transient(types=IFoo1)  # noqa: F811
    class RegBar:
        def __init__(self) -> None:  # type: ignore[misc]
            self.value = 'b'

    container = Container()
    container.register_decorated()
    r1 = container.resolve(IFoo1)  # type: ignore[arg-type]
    r2 = container.resolve(IFoo1)  # type: ignore[arg-type]
    assert isinstance(r1, RegBar)
    assert r1 is not r2


@fact
def register_decorated_sorts_by_depends_on() -> None:

    class IFooA:
        pass

    class IBarA:
        pass

    @singleton(types=IBarA)  # noqa: F811
    class BarService:
        pass

    @singleton(types=IFooA, depends_on=(IBarA,))  # noqa: F811
    class FooService:
        pass

    infos = _DecorationInfoManager.instance().get_all()
    sorted_infos = _sort_decoration_infos(
        [i for i in infos if i.interface in (IFooA, IBarA)]
    )
    interfaces_ordered = [e.interface for e in sorted_infos]
    assert interfaces_ordered.index(IBarA) < interfaces_ordered.index(IFooA), \
        'IBar should come before IFoo'


@fact
def register_decorated_sorted_result_order() -> None:
    """_sort_decoration_infos should produce correct order."""

    class IFooX:
        pass

    class IBarX:
        pass

    info_a = _DecoInfo(Lifetime.SINGLETON, IFooX, IBarX, ())
    info_b = _DecoInfo(Lifetime.SINGLETON, IBarX, IFooX, (IBarX,))
    sorted_list = _sort_decoration_infos([info_a, info_b])
    assert sorted_list[0].interface is IBarX
    assert sorted_list[1].interface is IFooX


@fact
def register_decorated_circular_dependency_warns() -> None:

    class IFooX:
        pass

    class IBarX:
        pass

    info_a = _DecoInfo(Lifetime.SINGLETON, IFooX, IFooX, (IBarX,))
    info_b = _DecoInfo(Lifetime.SINGLETON, IBarX, IBarX, (IFooX,))
    sorted_list = _sort_decoration_infos([info_a, info_b])
    assert len(sorted_list) == 2
    interfaces = {e.interface for e in sorted_list}
    assert interfaces == {IFooX, IBarX}


@fact
def register_decorated_on_frozen_container_raises() -> None:

    class IFooX:
        pass

    @singleton(types=IFooX)  # noqa: F811
    class FrozenTest:
        pass

    container = Container(frozen=True)
    try:
        container.register_decorated()
        assert False, 'Should have raised RegistrationError'
    except RegistrationError:
        pass


@fact
def sort_empty_list_returns_empty() -> None:
    """Sorting zero entries should return empty list."""
    result = _sort_decoration_infos([])
    assert result == []


@fact
def sort_single_entry_returns_itself() -> None:

    class IFooX:
        pass

    info = _DecoInfo(Lifetime.SINGLETON, IFooX, IFooX, ())
    result = _sort_decoration_infos([info])
    assert len(result) == 1
    assert result[0].interface is IFooX


@fact
def sort_unknown_depends_on_falls_to_end() -> None:

    class IFooX:
        pass

    class IBarX:
        pass

    info = _DecoInfo(Lifetime.SINGLETON, IFooX, IFooX, (IBarX,))  # IBarX not in batch
    result = _sort_decoration_infos([info])
    assert len(result) == 1
    assert result[0].interface is IFooX


@fact
def lifetime_enum_values_are_correct() -> None:
    """Lifetime values must match the expected IntEnum order."""
    assert Lifetime.TRANSIENT.value == 1
    assert Lifetime.SINGLETON.value == 2
    assert Lifetime.INSTANCE.value == 3


@fact
def raise_if_provides_decorated_raises_when_class_has_provides_marker() -> None:

    @provides()
    class MyClass:
        pass

    try:
        _raise_if_provides_decorated(MyClass)
    except RegistrationError as exc:
        assert 'cannot apply' in str(exc).lower()
        return
    assert False, 'expected RegistrationError'


@fact
def raise_if_provides_decorated_does_not_raise_when_no_provides_marker() -> None:

    class MyClass:
        pass

    # Should not raise for a plain class.
    _raise_if_provides_decorated(MyClass)


@fact
def singleton_incompatible_with_provides() -> None:
    """Applying @singleton on an @provides-decorated class raises at decoration time."""

    class IFoo:
        pass

    @provides()
    class MyClass:
        pass

    try:
        singleton(types=IFoo)(MyClass)  # type: ignore[arg-type]
    except RegistrationError as exc:
        assert 'cannot apply' in str(exc).lower()
        return
    assert False, 'expected RegistrationError'


@fact
def transient_incompatible_with_provides() -> None:
    """Applying @transient on an @provides-decorated class raises at decoration time."""

    class IFoo:
        pass

    @provides()
    class MyClass:
        pass

    try:
        transient(types=IFoo)(MyClass)  # type: ignore[arg-type]
    except RegistrationError as exc:
        assert 'cannot apply' in str(exc).lower()
        return
    assert False, 'expected RegistrationError'


@fact
def instanced_incompatible_with_provides() -> None:
    """Applying @instanced on an @provides-decorated class raises at decoration time."""

    class IFoo:
        pass

    @provides()
    class MyClass:
        pass

    try:
        instanced(types=IFoo)(MyClass)  # type: ignore[arg-type]
    except RegistrationError as exc:
        assert 'cannot apply' in str(exc).lower()
        return
    assert False, 'expected RegistrationError'


@fact
def namespace_pattern_none_registers_all():
    """Default (None) still registers every decorated entry."""

    class IFooNs:
        pass

    @singleton(types=IFooNs)  # noqa: F811
    class NsTarget:
        def __init__(self) -> None:  # type: ignore[misc]
            self.ok = True

    container = Container()
    container.register_decorated(namespace_pattern=None)
    resolved = container.resolve(IFooNs)  # type: ignore[arg-type]
    assert isinstance(resolved, NsTarget)
    assert resolved.ok is True


@fact
def namespace_pattern_matches_interface():
    """Pattern matches the interface's module → entry registered."""

    class IModA:
        pass

    @singleton(types=IModA)  # noqa: F811
    class TargetA:
        def __init__(self) -> None:  # type: ignore[misc]
            self.tag = 'a'

    container = Container()
    # Classes defined inside a function get the test module's dotted name as __module__
    # ('tests.lifetime_decorators_tests'); match the containing module
    container.register_decorated(namespace_pattern='lifetime_decorators')
    resolved = container.resolve(IModA)  # type: ignore[arg-type]
    assert isinstance(resolved, TargetA)


@fact
def namespace_pattern_matches_target():
    """Pattern matches the target's module → entry registered (even if interface differs)."""

    class IAny:
        pass

    @singleton(types=IAny)  # noqa: F811
    class AnyTarget:
        def __init__(self) -> None:  # type: ignore[misc]
            self.tag = 'x'

    # Both interface and target are defined inline in the same file → same module
    container = Container()
    container.register_decorated(namespace_pattern='lifetime_decorators')
    resolved = container.resolve(IAny)  # type: ignore[arg-type]
    assert isinstance(resolved, AnyTarget)


@fact
def namespace_pattern_skips_non_matching():
    """Pattern doesn't match either namespace → entry is skipped."""

    class ISkipped(Protocol):
        """Abstract protocol -- won't be auto-registered by resolve()."""
        pass

    @singleton(types=ISkipped)  # noqa: F811
    class SkippedClass:
        def __init__(self) -> None:  # type: ignore[misc]
            self.should_not_exist = True

    # Pattern matches none of our test module's namespace → entry is skipped
    container = Container()
    container.register_decorated(namespace_pattern=r'ZZZ_nonexistent_ZZZ')
    assert not container.is_registered(ISkipped)


@fact
def namespace_pattern_allows_partial_match():
    """Both interface and target are checked with re.search (partial match)."""

    class IFooSub1:
        pass

    @singleton(types=IFooSub1)  # noqa: F811
    class FooService1:
        def __init__(self) -> None:  # type: ignore[misc]
            self.svc = 1

    # 'decorators' is a substring of 'tests.lifetime_decorators_tests'
    container = Container()
    container.register_decorated(namespace_pattern='decorators')
    resolved = container.resolve(IFooSub1)  # type: ignore[arg-type]
    assert isinstance(resolved, FooService1)


@fact
def class_pattern_none_registers_all():
    """Default (None) for class_pattern still registers every decorated entry."""

    class IClassNs:
        pass

    @singleton(types=IClassNs)  # noqa: F811
    class NsTargetCls:
        def __init__(self) -> None:  # type: ignore[misc]
            self.ok = True

    container = Container()
    container.register_decorated(class_pattern=None)
    resolved = container.resolve(IClassNs)  # type: ignore[arg-type]
    assert isinstance(resolved, NsTargetCls)
    assert resolved.ok is True


@fact
def class_pattern_matches_interface_class_name():
    """Pattern matches the interface's __qualname__ → entry registered."""

    class IBar42:
        pass

    @singleton(types=IBar42)  # noqa: F811
    class BarTarget42:
        def __init__(self) -> None:  # type: ignore[misc]
            self.tag = 'bar'

    container = Container()
    container.register_decorated(class_pattern='^IBar42$')
    resolved = container.resolve(IBar42)  # type: ignore[arg-type]
    assert isinstance(resolved, BarTarget42)


@fact
def class_pattern_matches_target_class_name():
    """Pattern matches the target's __qualname__ → entry registered."""

    class IWildcard:
        pass

    @singleton(types=IWildcard)  # noqa: F811
    class FooServiceX:
        def __init__(self) -> None:  # type: ignore[misc]
            self.tag = 'foo'

    container = Container()
    # Interface is 'IWildcard', target is 'FooServiceX'; pattern matches target
    container.register_decorated(class_pattern='^FooServiceX$')
    resolved = container.resolve(IWildcard)  # type: ignore[arg-type]
    assert isinstance(resolved, FooServiceX)


@fact
def class_pattern_skips_non_matching():
    """Pattern doesn't match either class name → entry is skipped."""

    class IBar7(Protocol):
        """Abstract protocol -- won't be auto-registered by resolve()."""
        pass

    @singleton(types=IBar7)  # noqa: F811
    class SkippedClassZZ:
        def __init__(self) -> None:  # type: ignore[misc]
            self.should_not_exist = True

    container = Container()
    container.register_decorated(class_pattern=r'ZZZ_no_match_ZZZ')
    assert not container.is_registered(IBar7)


@fact
def class_and_namespace_patterns_both_must_match():
    """When both filters are provided, an info is registered only if BOTH pass."""

    class IFilterMe:
        pass

    @singleton(types=IFilterMe)  # noqa: F811
    class TargetClass1:
        def __init__(self) -> None:  # type: ignore[misc]
            self.tag = 'yes'

    container = Container()
    # Both patterns match → registered
    container.register_decorated(
        namespace_pattern='decorators',
        class_pattern='TargetClass',
    )
    resolved = container.resolve(IFilterMe)  # type: ignore[arg-type]
    assert isinstance(resolved, TargetClass1)


@fact
def class_and_namespace_patterns_disjoint_filters():
    """Namespace matches but class doesn't → entry skipped (AND logic)."""

    class IFilterNo(Protocol):
        """Abstract protocol -- won't be auto-registered."""
        pass

    @singleton(types=IFilterNo)  # noqa: F811
    class TargetClass99:
        def __init__(self) -> None:  # type: ignore[misc]
            self.should_not_exist = True

    container = Container()
    # namespace matches ('decorators') but class 'NoMatch' does not → skipped
    container.register_decorated(
        namespace_pattern='decorators',
        class_pattern=r'^NoMatch$',
    )
    assert not container.is_registered(IFilterNo)

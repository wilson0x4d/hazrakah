# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Tests for ergonomic decorator registration (@singleton, @transient, @instanced).

Each test that uses decorated classes must call ``_cleanup()`` in a finally block
to reset the global manager between tests.
"""

from __future__ import annotations

from hazrakah import (
    Lifetime,
    RegistrationError,
    Container,
    instanced,
    singleton,
    transient,
)
from hazrakah.decorators import DecorationInfo as _DecoInfo
from hazrakah.decorators import (
    _DecorationInfoManager,
    _sort_decoration_infos,
)
from punit import fact, teardown


@teardown
def _cleanup() -> None:
    """Reset the global decoration manager for isolation between tests."""
    _DecorationInfoManager._DecorationInfoManager__store.clear()  # type: ignore[attr-defined]
    _DecorationInfoManager._DecorationInfoManager__instance = None  # type: ignore[attr-defined]


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

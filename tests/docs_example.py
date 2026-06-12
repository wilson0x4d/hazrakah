# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Doc examples — unit-testable.

Each ``@fact`` function is a fully-asserted version of one README / quickstart
example snippet.  The docs strip away assertions and shared type definitions so
that each block is self-contained and readable without context.
"""

from hazrakah import Container
from hazrakah import singleton, transient, instanced, provides
from hazrakah.mocks import Mock, is_gt, contains, neg, is_in, is_type
from punit import fact
from typing import Protocol


# ── Shared placeholder types (module scope) ───────────────────────────────────

class IFoo(Protocol):
    def foo(self) -> int: ...


class IBar(Protocol):
    def bar(self) -> str: ...


class IFizz(Protocol):
    def fizz(self) -> None: ...


class IBuzz(Protocol):
    def buzz(self) -> None: ...


class IFooBar(Protocol):
    def foo_bar(self) -> int: ...


class Foo:
    def __init__(self, value: int = 1) -> None:
        self.value = value

    def foo(self) -> int:
        return self.value


class Bar:
    def __init__(self) -> None:
        pass

    def bar(self) -> str:
        return "bar"


class Fizz:
    def fizz(self) -> None:
        pass


class Buzz:
    def buzz(self) -> None:
        pass


class FooBarImpl:
    def foo_bar(self) -> int:
        return 42


class CloseableResource:
    closed = False

    def close(self) -> None:
        self.closed = True


# ── Test functions ────────────────────────────────────────────────────────────

@fact
def test_basic_lifetime_registration() -> None:
    """Core lifetimes: transient, singleton, instance."""
    container = Container()

    # TRANSIENT — a new instance for every resolve.
    container.register_transient(IFoo, Foo)
    foo1 = container.resolve(IFoo)
    foo2 = container.resolve(IFoo)
    assert foo1 is not foo2

    # SINGLETON — one shared instance across all resolves in scope.
    container.register_singleton(IFooBar, lambda c: c.resolve(FooBarImpl))
    fba = container.resolve(IFooBar)
    fbb = container.resolve(IFooBar)
    assert fba is fbb

    # INSTANCE — your exact object, returned everywhere (including child scopes).
    bar_obj = Bar()
    container.register_instance(IBar, bar_obj)
    assert container.resolve(IBar) is bar_obj


@fact
def test_hierarchical_scopes() -> None:
    """Parent-child scope isolation and shadowing."""
    parent = Container()
    child = parent.create_scope()

    # Parent registrations flow down into the child.
    parent.register_transient(IFizz, Fizz)
    assert isinstance(parent.resolve(IFizz), Fizz)
    assert isinstance(child.resolve(IFizz), Fizz)

    # Child-only registrations are invisible to parent.
    child.register_transient(IBuzz, Buzz)
    assert isinstance(child.resolve(IBuzz), Buzz)
    try:
        parent.resolve(IBuzz)
    except KeyError:
        pass  # expected


@fact
def test_context_manager_cleanup() -> None:
    """Automatic teardown of tracked resources via context manager."""
    with Container() as c:
        c.register_transient(CloseableResource)
        res = c.resolve(CloseableResource)

    assert res.closed


@fact
def test_fluent_chaining() -> None:
    """Method-chained registration DSL."""
    container = (
        Container()
        .register_transient(IFoo, Foo)
        .register_singleton(IBar, Bar)
        .register_instance(IFizz, Fizz())
    )

    assert isinstance(container.resolve(IFoo), Foo)
    assert isinstance(container.resolve(IBar), Bar)
    assert isinstance(container.resolve(IFizz), Fizz)


@fact
def test_declarative_decorators() -> None:
    """Class-level lifetime annotations + register_decorated()."""
    @singleton(types=IFoo)
    class SingletonFoo:
        def foo(self) -> int:
            return 42

    @transient(types=IBar)
    class TransientBar:
        def bar(self) -> str:
            return "bar"

    @instanced  # binds to the class itself
    class InstancedBuzz:
        def buzz(self) -> None:
            pass

    c = Container()
    c.register_decorated()

    # Singleton — same instance each resolve.
    a = c.resolve(IFoo)
    b = c.resolve(IFoo)
    assert a is b

    # Transient — new instance each resolve.
    x = c.resolve(IBar)
    y = c.resolve(IBar)
    assert x is not y

    # Instanced — the decorated class is registered with your exact class as target.
    assert isinstance(c.resolve(InstancedBuzz), InstancedBuzz)


@fact
def test_provides_multi_registration() -> None:
    """One class registered under multiple interfaces via @provides."""
    @provides(IFoo, IBar)
    class MultiImpl:
        def __init__(self) -> None:
            self.value = 99

        def foo(self) -> int:
            return self.value

        def bar(self) -> str:
            return str(self.value)

    c = Container()
    c.register_singleton(MultiImpl)   # registers under IFoo, IBar, and MultiImpl

    obj_a = c.resolve(IFoo)
    obj_b = c.resolve(IBar)
    assert isinstance(obj_a, MultiImpl)
    assert isinstance(obj_b, MultiImpl)
    assert obj_a is obj_b  # @provides caches across interfaces
    assert obj_a.foo() == 99
    assert obj_b.bar() == "99"


@fact
def test_mock_framework() -> None:
    """Built-in Mock fluent stubbing, call tracking, and matchers."""
    m = Mock()

    # Configure return values via fluent API.
    m.get_status.returns("ok")
    assert m.get_status() == "ok"

    # Side-effects as a fluent method call.
    m.add.side_effect(lambda *args: sum(args))
    assert m.add(2, 3) == 5

    # Call tracking and matchers — fluent side_effect on the child mock.
    m.compute.side_effect(lambda x: 10 if x > 5 else 20)  # type: ignore[assignment]
    assert m.compute(7) == 10
    assert m.compute(2) == 20

    # Call tracking — actual argument values.
    assert m.compute.was_called()
    assert m.compute.call_count == 2

    first_call = m.compute.calls[0]
    second_call = m.compute.calls[1]
    assert is_gt(5).__eq__(first_call.parameters[0][0])
    assert is_in(1, 2, 3).__eq__(second_call.parameters[0][0])

    # contains() — string substring or container membership.
    m.greet.returns("hello")
    assert m.greet("hi") == "hello"
    assert m.greet.was_called_with(contains("hi"))

    # neg() — negate a matcher.
    m.filter.returns(True)(neg(contains("blocked")))
    assert m.filter("allowed") is True

    # is_type() — match by runtime type.
    m.process.returns(0)(is_type(str))
    m.process("hello")  # matches → returns 0

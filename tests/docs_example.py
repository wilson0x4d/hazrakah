# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""Doc examples — unit-testable.

Each ``@fact`` function is a fully-asserted version of one README / quickstart
example snippet.  The docs strip away assertions and shared type definitions so
that each block is self-contained and readable without context.
"""

from datetime import timedelta

from hazrakah import (
    Cached,
    Container,
    ResolutionError,
    singleton,
    transient,
    instanced,
    provides,
)
from punit import fact
from typing import Protocol


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
        return 'bar'


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


# Sentinel used for Cached resolver tests.
_cached_resolver = object()


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
    except ResolutionError:
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
            return 'bar'

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
    assert obj_b.bar() == '99'


class _ConfigSource:
    """Helper class for the Caching example tests."""

    def load(self) -> str:
        return 'loaded'


@fact
def test_caching_with_cached_generic() -> None:
    """Cached[T] wraps a factory that receives a resolver with TTL-based expiry."""

    def factory(c):  # noqa: ANN201, ARG001
        return _ConfigSource()

    cache = Cached(factory, ttl=timedelta(seconds=47))

    # First access — factory called once.
    first = cache(_cached_resolver)  # type: ignore[arg-type]

    # Second access — cached value returned; factory not re-invoked.
    second = cache(_cached_resolver)  # type: ignore[arg-type]
    assert first is second  # same instance


@fact
def test_caching_container_integration() -> None:
    """Cached instance can be wired into Container registrations."""

    def factory(c):  # noqa: ANN201, ARG001
        return _ConfigSource()

    cache = Cached(factory, ttl=timedelta(seconds=47))

    c = Container()
    c.register_transient(_ConfigSource, lambda r: cache(r))  # type: ignore[arg-type]

    first = c.resolve(_ConfigSource)
    second = c.resolve(_ConfigSource)
    assert first is second


@fact
def test_cached_timeout_and_reset() -> None:
    """Zero TTL always re-invokes; reset discards cached value."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return _ConfigSource()

    cache = Cached(factory, ttl=timedelta(seconds=0))
    first = cache(_cached_resolver)  # type: ignore[arg-type]
    second = cache(_cached_resolver)  # type: ignore[arg-type]
    assert first is not second  # zero TTL — always miss
    assert call_count == 2

    # reset discards the cached value and timestamp
    cache.reset()
    _ = cache(_cached_resolver)  # type: ignore[arg-type]
    assert call_count == 3  # factory re-invoked after reset


@fact
def test_cached_ttl_property() -> None:
    """Cached exposes ttl as a timedelta property."""

    def factory(c):  # noqa: ANN201, ARG001
        return _ConfigSource()

    cache = Cached(factory, ttl=timedelta(seconds=120))
    assert cache.ttl == timedelta(seconds=120)


@fact
def test_cached_forwards_resolver_to_factory() -> None:
    """The resolver is passed from __call__ through to the factory."""
    received = []

    def factory(c):  # noqa: ANN201
        received.append(c)
        return _ConfigSource()

    cache = Cached(factory)
    my_resolver = object()
    _ = cache(my_resolver)  # type: ignore[arg-type]
    assert len(received) == 1
    assert received[0] is my_resolver


@fact
def test_cached_factory_is_called_once_within_ttl() -> None:
    """Only the first call within the TTL invokes the factory."""
    call_count = 0

    def factory(c):  # noqa: ANN201, ARG001
        nonlocal call_count
        call_count += 1
        return 'ok'

    cache = Cached(factory, ttl=timedelta(seconds=47))
    _ = cache(_cached_resolver)  # type: ignore[arg-type]
    assert call_count == 1
    _ = cache(_cached_resolver)  # type: ignore[arg-type]
    assert call_count == 1


@fact
def test_cached_float_ttl_accepted() -> None:
    """Float TTL (seconds) is accepted and converted internally."""

    def factory(c):  # noqa: ANN201, ARG001
        return _ConfigSource()

    cache = Cached(factory, ttl=90.0)  # type: ignore[arg-type]
    assert cache.ttl == timedelta(seconds=90)

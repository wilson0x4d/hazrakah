# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from hazrakah import RegistrationError
from hazrakah import Container
from punit import fact
from typing import Protocol


class IFizz(Protocol):
    def fizz(self) -> None: ...


class Fizz:
    def __init__(self) -> None:
        pass
    def fizz(self) -> None:
        pass


class IBuzz(Protocol):
    def buzz(self) -> None: ...


class Buzz:
    def __init__(self) -> None:
        pass
    def buzz(self) -> None:
        pass

class IFizzBuzz(Protocol):
    def fizz(self) -> None: ...
    def buzz(self) -> None: ...


class FizzBuzz:
    def __init__(self) -> None:
        pass
    def fizz(self) -> None:
        pass
    def buzz(self) -> None:
        pass


@fact
def basic_verification() -> None:
    container = Container()
    scoped_container = container.create_scope()

    # TRANSIENT == a new instance of `Foo` is created
    # for every resolve of `IFoo`.
    container.register_transient(IFizz, Fizz)
    #
    fizz1 = container.resolve(IFizz)
    fizz2 = container.resolve(IFizz)
    assert fizz1 is not fizz2, 'transients reg, every resolve is a new instance.'


    # SCOPED == within a given "scope" a single instance is returned
    # for every resolve of `IBuzz`. new scopes == new instances.
    container.register_scoped(IBuzz, Buzz)
    #
    buzz1 = container.resolve(IBuzz)
    buzz2 = container.resolve(IBuzz)
    buzz3 = scoped_container.resolve(IBuzz)
    assert buzz1 is buzz2, 'scoped resolves are singleton-like WITHIN a container scope.'
    assert buzz1 is not buzz3, 'scoped resolves are NOT shared between container scopes, new scope? new singleton.'

    # INSTANCE == the provided instance is returned
    # for every resolve of `FizzBuzz`.
    container.register_instance(FizzBuzz, FizzBuzz())
    #
    fizzbuzz1 = container.resolve(FizzBuzz)
    fizzbuzz2 = scoped_container.resolve(FizzBuzz)
    assert fizzbuzz1 is fizzbuzz2, 'instance resolves always yield the provided instance'
    # NOTE: "scopes" resolve hierarchically any "non-scoped" type registration,
    #       this is why `scoped_container`` resolved the same instance as `container`.
    #       if this were a scoped registration a NEW instance would have been created.
    #       this scoping logic is true for INSTANCE, SINGLETON, and TRANSIENT regs.

    # SINGLETON == a SINGLE instance will be created
    # for ALL resolves of `IFizzBuzz`.
    container.register_singleton(IFizzBuzz, lambda c: c.resolve(FizzBuzz))
    fizzbuzz3 = container.resolve(IFizzBuzz)
    fizzbuzz4 = container.resolve(IFizzBuzz)
    assert fizzbuzz3 is fizzbuzz4, 'singleton resolves always yield a single instance.'

    # for completeness, concrete types can self-regsiter without a target spec.
    container.register_transient(Fizz)
    fizz3 = container.resolve(Fizz)
    assert fizz3 is not None

    # and last, but not least, containers can be frozen,
    # making them immutable (also freezing any scopes
    # created after being frozen.)  once frozen, they
    # cannot be unfrozen.
    try:
        container.freeze()
        container.register_instance(Fizz, Fizz())
    except RegistrationError:
        pass
    else:
        assert False, 'Frozen containers should be immutable.'

    try:
        scoped_container.register_instance(Fizz, Fizz())
    except:
        assert False, 'Scopes created BEFORE freezing are NOT frozen.'

    try:
        scope2 = container.create_scope()
        scope2.register_instance(Fizz, Fizz())
    except RegistrationError:
        pass
    else:
        assert False, 'Scopes created AFETR freezing are also frozen.'

    try:
        setattr(container, '__frozen', False)
    except AttributeError:
        pass
    else:
        assert False, 'Attempts to modify Container directly will fail.'


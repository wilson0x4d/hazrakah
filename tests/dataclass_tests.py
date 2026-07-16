# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

"""A collection of regression tests specific to Python std library `@dataclass` decorated types."""


from dataclasses import dataclass, field
import hazrakah
from punit import approx, fact
from typing import Protocol


@fact
def non_dataclass_unregistered_type() -> None:
    class InlineExample:
        ex_float: float = 123.4
        ex_int: int = 1234
        ex_str: str

    container = hazrakah.Container()
    result = container.resolve(InlineExample)
    assert result is not None, 'an instance is expected'
    assert result.ex_float == approx(123.4), f'result.ex1_float should have a default of 123.4, got {result.ex_float}'
    assert result.ex_int == 1234, f'result.ex1_int should have a default of 1234, got {result.ex_int}'
    assert not hasattr(result, 'ex_str'), 'result.ex1_str has no default, so should not be defined.'


@fact
def non_dataclass_unregistered_type_has_default_params() -> None:
    class InlineExample:
        ex_float: float
        ex_int: int
        ex_str: str = 'foo'

        def __init__(self, ex_float: float = 123.4, ex_int: int = 1234) -> None:
            self.ex_float = ex_float
            self.ex_int = ex_int

    container = hazrakah.Container()
    result = container.resolve(InlineExample)
    assert result is not None, 'an instance is expected'
    assert result.ex_float == approx(123.4), f'result.ex1_float should have a default of 123.4, got {result.ex_float}'
    assert result.ex_int == 1234, f'result.ex1_int should have a default of 1234, got {result.ex_int}'
    assert result.ex_str == 'foo', f'result.ex1_str should have a default of "foo", got {result.ex_str}'


@fact
def basic_dataclass_unregistered_type() -> None:
    @dataclass(frozen=True)
    class InlineExample:
        ex_float: float = field(default=123.4)
        ex_int: int = 1234
        ex_str: str = field(default='foo')

    container = hazrakah.Container()
    result = container.resolve(InlineExample)
    assert result is not None, 'an instance is expected'
    assert result.ex_float == approx(123.4), f'result.ex1_float should have a default of 123.4, got {result.ex_float}'
    assert result.ex_int == 1234, f'result.ex1_int should have a default of 1234, got {result.ex_int}'
    assert result.ex_str == 'foo', f'result.ex1_str should have a default of "foo", got {result.ex_str}'


@fact
def complex_type_partial_registration() -> None:
    @dataclass(frozen=True)
    class InlineSubordinateExample:
        ex_float: float = field(default=123.4)
        ex_int: int = 1234

    @dataclass(frozen=True)
    class InlineExample:
        ex_subordinate: InlineSubordinateExample
        ex_str: str = field(default='foo')

    container = hazrakah.Container()
    container.register_transient(InlineSubordinateExample)
    result = container.resolve(InlineExample)
    assert result is not None, 'an instance is expected'
    assert result.ex_subordinate is not None, 'a subordinate instance is expected'
    assert result.ex_subordinate.ex_float == approx(123.4), f'result.ex_subordinate.ex1_float should have a default of 123.4, got {result.ex_subordinate.ex_float}'
    assert result.ex_subordinate.ex_int == 1234, f'result.ex_subordinate.ex1_int should have a default of 1234, got {result.ex_subordinate.ex_int}'
    assert result.ex_str == 'foo', f'result.ex1_str should have a default of "foo", got {result.ex_str}'


@fact
def protocl_base_dataclass_unregistered_type() -> None:
    class ProtoBase(Protocol):
        ex_float: float

    @dataclass(frozen=True)
    class InlineExample(ProtoBase):
        ex_float: float = field(default=123.4)
        ex_int: int = 1234
        ex_str: str = field(default='foo')

    container = hazrakah.Container()
    result = container.resolve(InlineExample)
    assert result is not None, 'an instance is expected'
    assert result.ex_float == approx(123.4), f'result.ex1_float should have a default of 123.4, got {result.ex_float}'
    assert result.ex_int == 1234, f'result.ex1_int should have a default of 1234, got {result.ex_int}'
    assert result.ex_str == 'foo', f'result.ex1_str should have a default of "foo", got {result.ex_str}'

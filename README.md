
[![hazrakah on PyPI](https://img.shields.io/pypi/v/hazrakah.svg)](https://pypi.org/project/hazrakah/) [![hazrakah on readthedocs](https://readthedocs.org/projects/hazrakah/badge/?version=latest)](https://hazrakah.readthedocs.io)

**hazrakah** (הזרקה) is a tiny but powerful DI library for Python.

This README is only a high-level introduction to **hazrakah**. For more detailed documentation, please view the official docs at [https://hazrakah.readthedocs.io](https://hazrakah.readthedocs.io).


## Features

- Supports Singleton, Transient, and Instance lifetimes.
- **Hierarchical scoping**; Isolate registrations and/or resolves. optionally use a context manager to deterministically tear down a scope and its resolved objects.
- **Protocols, ABCs, and Concretes** can be registered against **Factory Functions and Concretes**.
- **Lifetime Decorators**; (OPTIONAL) Types decorated with  `@singleton`, `@transient` or `@instanced` can be registered with a single call to `register_decorated()`, simplifying orchestration.
- **Implicit Multi-Registration**; Types decorated with `@provides` bind to all provided types (unless explicit types are specified during registration.)
- **Fluent API**; All registration methods return `self`, enabling method-chained container setup.
- **Mocking Support**: `Mock` with fluent configuration, async-aware interception, an extensible set of matchers (`is_any`, `is_gt`, `contains`, `neg`, ...), and module-level patching.

## Installation

You can install `hazrakah` from [PyPI](https://pypi.org/project/hazrakah/) through usual means, such as `pip`:

```bash
   pip install hazrakah
```


## Usage

### Core lifetimes — Transient, Singleton, Instance

`hazrakah` manages object lifecycles through three registration strategies:

```python
from hazrakah import Container

container = Container()

# TRANSIENT — a new instance for every resolve.
container.register_transient(IFoo, Foo)
assert container.resolve(IFoo) is not container.resolve(IFoo)

# SINGLETON — one shared instance across all resolves in scope.
container.register_singleton(IFooBar, lambda c: c.resolve(FooBarImpl))
assert container.resolve(IFooBar) is container.resolve(IFooBar)

# INSTANCE — your exact object, returned everywhere (including child scopes).
bar_obj = Bar()
container.register_instance(IBar, bar_obj)
assert container.resolve(IBar) is bar_obj
```

### Hierarchical scopes

Scopes provide isolation: parent registrations flow down, but child-only registrations stay local.

```python
parent = Container()
child = parent.create_scope()

parent.register_transient(IFoo, Foo)
child.resolve(IFoo)          # resolves parent's registration

child.register_transient(IBar, Bar)
child.resolve(IBar)          # works — registered in this scope
# parent.resolve(IBar)      # raises KeyError — invisible to parent
```

### Context manager cleanup

Resolve tracked resources and get deterministic teardown when the scope exits.

```python
from hazrakah import Container

class Closeable:
    def __init__(self): self.closed = False
    def close(self): self.closed = True

with Container() as c:
    c.register_transient(Closeable)
    res = c.resolve(Closeable)

assert res.closed               # teardown ran automatically on __exit__
```

### Fluent chaining

All registration methods return `self`, enabling method-chained setup.

```python
container = (
    Container()
    .register_transient(IFoo, Foo)
    .register_singleton(IBar, Bar)
    .register_instance(IFizz, Fizz())
)

assert isinstance(container.resolve(IFoo), Foo)
assert isinstance(container.resolve(IBar), Bar)
```

### Declarative lifetime decorators

Mark intent at class-definition time with `@singleton`, `@transient`, or `@instanced`, then register everything in one call.

```python
from hazrakah import Container, singleton, transient, instanced

@singleton(types=IFoo)
class FooService: ...

@transient(types=IBar)
class BarService: ...

@instanced  # binds to the class itself
class BuzzService: ...

c = Container()
c.register_decorated()            # discovers all decorated classes

assert c.resolve(IFoo) is c.resolve(IFoo)     # singleton
assert c.resolve(IBar) is not c.resolve(IBar)  # transient
```

### Implicit multi-registration with `@provides`

Declare which interfaces a class implements; registration binds to **all** of them simultaneously.

```python
from hazrakah import Container, provides

@provides(IFoo, IBar)
class MultiImpl:
    def foo(self): ...
    def bar(self): ...

c = Container()
c.register_transient(MultiImpl)    # registers under IFoo, IBar, and MultiImpl

a = c.resolve(IFoo)
b = c.resolve(IBar)
assert a is b                       # same cached singleton instance
```

#### How `@provides` works

The `@provides` decorator is a **passive marker** -- it stores metadata only, with zero registration logic at decoration time. Activation depends entirely on how the container later registers the decorated class.

**`@provides` activates** when you call `register_singleton`, `register_transient`, or `register_instance` with **no second argument** (no explicit type override):

```python
@provides(IFoo, IBar)
class MultiImpl: ...

c.register_singleton(MultiImpl)  # multi-registers under IFoo + IBar + MultiImpl
c.resolve(IFoo)                  # works -- @provides activated
c.resolve(IBar)                  # works -- @provides activated
```

**`@provides` does NOT activate** when you provide an explicit type argument to a registration method:

```python
@provides(IBar)
class MultiImpl: ...

c.register_singleton(IFoo, MultiImpl)  # only IFoo is registered
c.resolve(IFoo)                        # works -- explicit registration
c.resolve(IBar)                        # raises KeyError -- @provides was ignored
```

This is intentional. The second positional argument on any `register_*` method is the **explicit type override**. When you provide it, you are telling the container exactly which key to register against -- and `@provides` does not interfere.

| Registration call | `@provides` activates? | Registered keys |
|---|---|---|
| `register_singleton(MyClass)` | YES | MyClass + all `@provides` interfaces |
| `register_singleton(IFoo, MyClass)` | NO | Only IFoo |
| `register_transient(MyClass)` | YES | MyClass + all `@provides` interfaces |
| `register_transient(IFoo, MyClass)` | NO | Only IFoo |
| `register_instance(my_obj)` (no explicit instance) | YES | type(obj) + all `@provides` interfaces |
| `register_instance(IFoo, my_obj)` (explicit instance) | NO | Only IFoo |

### Built-in mocking framework

A lightweight `Mock` with fluent configuration, call tracking, argument matchers, and module-level `patch()`.

```python
from hazrakah.mocks import Mock, is_gt, contains, neg, is_in

m = Mock()

# Fluent stubbing.
m.get_status.returns("ok")
assert m.get_status() == "ok"

# Side-effects on the child mock (fluent call, not direct assignment).
m.compute.side_effect(lambda x: 10 if x > 5 else 20)
assert m.compute(7) == 10
assert m.compute(2) == 20

# Call tracking.
assert m.compute.was_called()
assert m.compute.call_count == 2

# Composed matchers.
m.filter.returns(True)(neg(contains("blocked")))
assert m.filter("allowed") is True

# Constructor kwargs for concise fixture creation
row = Mock(migration='alpha', status='active')
assert row.migration == 'alpha'
assert row.status == 'active'
```


## Contact

You can reach me on [Discord](https://discordapp.com/users/307684202080501761) or [open an Issue on Github](https://github.com/wilson0x4d/hazrakah/issues/new/choose).

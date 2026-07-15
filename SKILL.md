---
name: hazrakah
description: Zero-dependency dependency injection framework for Python 3.11+ — Container lifecycle, registration, resolution, scopes, decorators, teardown, Cached[T], and error handling. Use as a technical reference document for hazrakah API and concepts.
user-invocable: false
disable-model-invocation: false
type: reference
---

# hazrakah — DI Library Reference

**hazrakah** — a zero-dependency dependency injection framework for Python 3.11+.

---

## Table of Contents

1. [What is `Container`](#what-is-container)
2. [Lifetimes](#lifetimes)
3. [Registration](#registration)
4. [Resolution](#resolution)
5. [Scopes](#scopes)
6. [Decorators](#decorators)
7. [Context Manager / Teardown](#context-manager--teardown)
8. [Time-Bound Caching with `Cached[T]`](#time-bound-caching-with-cachedt)
9. [Error Handling](#error-handling)
10. [Complete Example](#complete-example)

---

## What is `Container`

A single class that combines registration, resolution, and scoping in one mixin:

```python
from hazrakah import Container

c = Container()
```

### Constructor parameters

| Param | Type | Default | Description |
|---|---|---|---|
| `outer_scope` | `Optional[Container]` | `None` | Parent container for hierarchical scoping |
| `frozen` | `bool` | `False` | Block all registrations immediately |
| `self_resolve` | `bool` | `True` | Allow a container to resolve its own DI interfaces to itself |

---

## Lifetimes

Three lifetime modes controlling how many instances exist:

| Lifetime | Behaviour |
|---|---|
| `TRANSIENT` | New instance every `resolve()` call |
| `SINGLETON` | One instance per owning container; parent singletons cascade to children |
| `INSTANCE` | One shared pre-existing object returned everywhere |

---

## Registration

All methods return `self` for fluent chaining.

### `register_transient(t: Type, target: Optional[Target] = None)`

```python
from typing import Protocol

class IFoo(Protocol): ...

# Concrete class as implementation
c.register_transient(IFoo, FooImpl)

# Factory function (receives the resolver)
c.register_transient(IFoo, lambda r: FooImpl(r.resolve(Config)))

# Self-registration (no target — container auto-wires constructor deps)
c.register_transient(FooImpl)
```

### `register_singleton(t: Type, target: Optional[Target] = None)`

```python
# With explicit interface and class
c.register_singleton(IFoo, FooImpl)

# With factory
c.register_singleton(IFoo, lambda r: FooImpl())

# Self-registration
c.register_singleton(FooImpl)
```

### `register_instance(t: Type, instance: Any = None)`

```python
# Explicit instance — exact object returned everywhere
config = MyConfig()
c.register_instance(IConfig, config)

# Inferred instance — container creates it, then returns the same object
c.register_instance(MyService)  # no explicit instance arg
```

### `freeze()`

```python
c.freeze()
c.register_transient(IFoo, Foo)  # → RegistrationError
```

### `is_registered(t: Type) -> bool`

```python
c.register_transient(IFoo, Foo)
assert c.is_registered(IFoo)  # True
c.is_registered(IBar)         # False (not registered at all)

# Inherited resolution visible even in children
child = c.create_scope()
child.is_registered(IFoo)  # True (parent's registration)
```

---

## Resolution

### `resolve(t: Type[T]) -> T`

```python
# Basic resolution
foo = c.resolve(IFoo)

# Auto-wired constructor dependencies
class Service:
    def __init__(self, db: Database, logger: ILogger) -> None: ...

svc = c.resolve(Service)  # Database & ILogger are auto-resolved if registered

# Optional resolution — returns None when unregistered
class OptService:
    def __init__(self, foo: Optional[IFoo] = None) -> None: ...

svc = c.resolve(OptService)  # .foo is None if IFoo has no registration

# Union type resolution — matches single registration
x = c.resolve(IFoo | IBar)  # IFoo and IBar resolve to the same singleton
```

Resolution walks the container hierarchy (self → parent → grandparent …).

---

## Scopes

Create hierarchical child containers:

```python
parent = Container()
child = parent.create_scope()

# Children inherit parent registrations
parent.register_singleton(IFoo, Foo)
child.resolve(IFoo)  → same instance as parent.resolve(IFoo)

# Children can shadow with their own registrations
child.register_singleton(IFoo, ChildFoo)
# child.resolve(IFoo) now resolves to ChildFoo
# parent.resolve(IFoo) still resolves to Foo
```

Scoped containers support RAII via context manager:

```python
with parent.create_scope() as scope:
    scope.register_transient(IBar, Bar)
    obj = scope.resolve(IBar)
# obj.close() called on exit if IBartype has .close()
```

---

## Decorators

Decorators are **passive** — they store metadata. Registration happens via `register_decorated()`.

### Core decorators: `@singleton`, `@transient`, `@instanced`

```python
from hazrakah import singleton, transient, instanced

@singleton(types=IFoo)
class FooImpl:
    def __init__(self, db: Database) -> None:
        self.db = db

@transient(types=ILogger)
class LoggerImpl: ...

@instanced
class BootStamp:  # self-referencing
    ...
```

#### Factory functions

```python
@singleton(types=ISession)
def make_session(r: DependencyResolver) -> Session:
    return Session(connection_string=r.resolve(str))
```

#### Usage patterns

```python
@singleton                           # class auto-ref
@singleton()                          # same
@singleton(types=IFoo)                # explicit interface
@singleton(types=(IFoo, IBar))        # multiple interfaces
@singleton(types=IFoo, depends_on=(IBar,))  # ordering hint
```

### `register_decorated()`

Registers all decorated classes/functions in the global namespace:

```python
c.register_decorated()  # registers everything decorated

# Filter by module namespace
c.register_decorated(namespace_pattern=r"myapp\.services\..*")

# Filter by class name
c.register_decorated(class_pattern="^Service$")

# Topological ordering via depends_on ensures deps registered first
@singleton(types=ILogger, depends_on=(IConfig,))
class MyLogger: ...
```

### `@provides(*interfaces)`

Multi-registration without lifecycle decorators. A single instance is registered under the class name **and** under all provided interfaces:

```python
from hazrakah import provides

@provides(IFoo, IBar)
class Impl:
    def foo_method(self): ...
    def bar_method(self): ...

c.register_singleton(Impl)

a = c.resolve(IFoo)
b = c.resolve(IBar)
assert a is b  # same instance
```

**Note**: `@provides` is bypassed when a second argument is supplied: `register_singleton(IFoo, Impl)` does NOT use `@provides`. Mutually exclusive with lifecycle decorators (`@singleton`, `@transient`, `@instanced`).

---

## Context Manager / Teardown

Containers implement RAII — tracked instances are closed automatically:

```python
from hazrakah import Container

class Closeable:
    def __init__(self) -> None: self.closed = False
    def close(self) -> None: self.closed = True

with Container() as c:
    c.register_transient(Closeable)
    obj = c.resolve(Closeable)

assert obj.closed  # True — .close() called on __exit__
```

Behaviour:
- Any object created through the container via resolution is tracked.
- Objects injected into other tracked objects are **not** tracked (only root-level resolution-created objects).
- `__del__` provides a garbage-collection fallback for `close()`.

---

## Time-Bound Caching with `Cached[T]`

Generic wrapper providing TTL-based caching around a factory:

```python
from hazrakah import Cached
from datetime import timedelta

cache = Cached(
    lambda r: ExpensiveSource(),
    ttl=timedelta(seconds=47)
)

result1 = cache(resolver)   # factory invoked
result2 = cache(resolver)   # cached value returned
assert result1 is result2

cache.reset()               # manually invalidate

# ttl=0 → factory called every time (always miss)
```

Methods:
- `cached(resolver)` → resolved value (reinvokes factory on TTL expiry)
- `cache.reset()` → invalidate cache
- `cache.ttl` → read-only `timedelta`

---

## Error Handling

```python
from hazrakah import RegistrationError, ResolutionError

# RegistrationError — raised when registration fails
try:
    frozen_container.register_transient(IFoo, Foo)
except RegistrationError:
    pass

# ResolutionError — raised when a type cannot be resolved
try:
    container.resolve(UnregisteredProtocol)
except ResolutionError:
    pass
```

| Error | Cause |
|---|---|
| `RegistrationError` | Frozen container, invalid factory signature, mixing `@provides` with lifecycle decorators, missing `types=` on factory decorator |
| `ResolutionError` | Unregistered abstract/protocol type, multiple distinct targets in a non-optional union, zero-match union |

---

## Complete Example

```python
from typing import Protocol
from hazrakah import (
    Container, provides, singleton, transient, instanced,
)

# ---- Interfaces & implementations ----

class IDatabase(Protocol):
    def exec(self, sql: str) -> list[dict]: ...

class ILogger(Protocol):
    def log(self, msg: str) -> None: ...

@singleton(types=IDatabase)
class PostgresPool:
    def exec(self, sql: str) -> list[dict]: return []

@transient(types=ILogger)
class ConsoleLogger:
    def log(self, msg: str) -> None: print(msg)

@provides(IDatabase, ILogger)
class CombinedImpl:
    def exec(self, sql: str) -> list[dict]: return []
    def log(self, msg: str) -> None: pass

# ---- Composition root ----

with (
    Container()
    .register_decorator(CombinedImpl)  # registers both IDatabase & ILogger
    .register_transient(ConsoleLogger)
    .freeze()
) as container:
    class UserService:
        def __init__(self, db: IDatabase, logger: ILogger) -> None:
            self.db = db
            self.logger = logger

    svc = container.resolve(UserService)
```

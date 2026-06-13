---
name: hazrakah
description: Dependency Injection skill for Python. MUST when the user discusses "DI", "dependency injection" or "hazrakah".
user-invocable: true
disable-model-invocation: false
---

`hazrakah` is a tiny but powerful zero-dependency DI container for Python 3.11+ with lifetime management, hierarchical scopes, decorator-based registration, and fluent chaining.

- **Install:** `python3 -m pip install hazrakah`
- **Docs:** https://hazrakah.readthedocs.io/
- **Source:** https://github.com/wilson0x4d/hazrakah

## Container Setup

All public symbols are imported directly from `hazrakah`:

```python
from hazrakah import (
    Container, provides, singleton, transient, instanced,
    Factory, Target, Lifetime, RegistrationError,
)
```

### Creating a container

The simplest setup uses fluent chaining — every `register_*` method returns `self`:

```python
container = (
    Container()
    .register_singleton(IDatabase, lambda c: DatabasePool("postgres://localhost/mydb"))
    .register_transient(Logger, ConsoleLogger)
    .register_instance(IConfig, Config.load_from_env())
)
service = container.resolve(IService)
```

### Context manager auto-teardown

Use a context manager for deterministic cleanup of resolved instances (calls `close()` on each):

```python
class Closeable:
    def __init__(self) -> None: self.closed = False
    def close(self) -> None: self.closed = True

with Container() as c:
    c.register_transient(Closeable)
    svc = c.resolve(Closeable)

assert svc.closed  # teardown ran automatically on __exit__
```

Explicit instances passed to `register_instance` are **not** tracked for cleanup. (Inferred instances — e.g., `register_instance(SomeClass)` without an explicit object — may be tracked via the resolution path.)

## Lifetimes

| Lifetime | Behavior | Best For |
| :--- | :--- | :--- |
| `SINGLETON` | One cached instance per registration, shared by any container that resolves through it | Services with state, connection pools |
| `TRANSIENT` | New instance on every `resolve()` | Stateless helpers, per-request objects |
| `INSTANCE` | Pre-bound object always returned by reference | Configuration, externally-managed resources |

```python
# SINGLETON — cached in the registration's owner
container.register_singleton(IDB, DatabasePool)
x = container.resolve(IDB)
y = container.resolve(IDB)
assert x is y  # same cached instance in this scope

# TRANSIENT — new each time
container.register_transient(ILogger, ConsoleLogger)
assert container.resolve(ILogger) is not container.resolve(ILogger)

# INSTANCE — your exact object
config = Config()
container.register_instance(IConfig, config)
assert container.resolve(IConfig) is config
```

## Scopes & Hierarchy

Scopes isolate registration: parent registrations flow down; child-only registrations stay local.

### Basic scoping

```python
parent = Container()
child = parent.create_scope()

parent.register_singleton(IRepository, SqlRepository)
child.resolve(IRepository)  # resolves parent's singleton
```

### Child overrides

```python
child.register_transient(IRepository, InMemoryRepository)
# child now gets its own implementation; parent still sees SqlRepository
```

### Nested scopes with auto-teardown

```python
root = Container()
with root.create_scope() as scope1:
    scope1.register_transient(ISession, Session)
    with scope1.create_scope() as scope2:
        session = scope2.resolve(ISession)  # found in parent scope1
# ISession.close() called for scope2, then scope1 on exit
```

### Frozen mode

Prevent further registration after composition is complete:

```python
container = Container()
(
    container
    .register_transient(FileLogger)
    .register_singleton(IDatabase, DatabasePool)
)
container.freeze()  # no more registrations allowed on this container or its descendant scopes

try:
    container.register_transient(ISomeService, SomeService)
except RegistrationError:  # blocked by frozen state
    ...
```

## Decorators

Mark intent at class-definition time; register everything in one call:

```python
from hazrakah import Container, singleton, transient, instanced

@singleton(types=ICache)
class RedisCache:
    def __init__(self, host: str = "localhost") -> None: ...

@transient(types=IEmailSender)
class SMTPSender:
    def __init__(self, cache: ICache) -> None: ...  # resolved automatically

@instanced(types=IBootStamp)
class BootTime: ...  # registered as INSTANCE (created when register_decorated() is called)

c = Container()
c.register_decorated()  # discovers all decorated classes above
```

### Multiple interfaces

Register one class under several keys — all resolve to the same instance:

```python
@singleton(types=(IFoo, IBar))
class Widget: ...

assert c.resolve(IFoo) is c.resolve(IBar)
```

### Factory functions

Lifecycle decorators work with callables too (requires `types=`):

```python
@singleton(types=ISession)
def make_session(resolver: DependencyResolver) -> Session:
    return Session(connection_string=os.environ["DB_URL"])
```

### depends_on ordering

Hint registration order so that dependencies are available first:

```python
@singleton(types=IConfig)
class ConfigService: ...

@singleton(types=ILogger, depends_on=(IConfig,))
class Logger: ...
# ConfigService is registered before Logger
```

Auto-inference of `depends_on` from constructor parameter annotations is also supported (via decorator form only).

## The @provides Marker

Declare which interfaces a class implements — registration binds to **all** of them simultaneously. Unlike lifecycle decorators, `@provides` is a pure marker (zero registration logic at decoration time):

```python
class IFoo(Protocol):
    def foo(self) -> None: ...

class IBar(Protocol):
    def bar(self) -> str: ...

@provides(IFoo, IBar)
class MultiImpl:
    def foo(self) -> None: ...
    def bar(self) -> str: return "bar"

container = Container()
container.register_singleton(MultiImpl)  # also under IFoo and IBar

a = container.resolve(IFoo)
b = container.resolve(IBar)
assert a is b  # same instance — shared cache across all provided interfaces
```

**Important:** `@provides` and lifecycle decorators (`@singleton`, `@transient`, `@instanced`) are mutually exclusive on the same class. Use one approach or the other.

## Common Patterns

### Composition root — lock down config before app startup

```python
@provides(IConfig, ILogger)
class AppConfig:
    def __init__(self) -> None: ...

container = (
    Container()
    .register_instance(AppConfig())   # auto-registers under IConfig + ILogger
    .register_transient(ISerializer, JsonSerializer)
    .register_singleton(IDatabase, DatabasePool)
    .freeze()
)
```

### Scoped request handling

```python
parent = Container()  # app-wide singletons
parent.register_singleton(IUserStore, SqlUserStore)

def handle_request():
    with parent.create_scope() as scope:
        scope.register_transient(ILogger, RequestLogger)
        store = scope.resolve(IUserStore)   # singleton from parent
        logger = scope.resolve(ILogger)      # transient within this request
        return process(store, logger)
# RequestLogger.close() called after each request; store stays alive
```

## Troubleshooting

| Problem | Cause / Fix |
| :--- | :--- |
| `KeyError` resolving a type | Unregistered type — register it with the container. |
| Singleton unexpectedly different instances | Each singleton is cached by the container that **owns its registration**. A child registering a new singleton for an interface shadows the parent's registration (different instances, each cached in its own owner). Both scopes share the same instance only when they resolve through the same registration. |
| `RegistrationError` applying lifecycle decorator to `@provides` class | The two are mutually exclusive — use one pattern per class |
| `RegistrationError` after calling `freeze()` | Freeze blocks further registration in the entire hierarchy — call it only after all registrations complete |
| Objects not cleaned up on context exit | Only objects created through resolution paths are tracked. User-owned instances passed explicitly to `register_instance` are untouched. (Inferred `register_instance(SomeClass)` may add tracking via the transient auto-registration path.) |
| Dependencies auto-resolved incorrectly | Constructor parameters must be annotated (`def __init__(self, foo: IFoo)`); unannotated params won't be wired |
| `@singleton` class resolves as transient after `register_decorated()` | Decorators store metadata only; registration happens at `register_decorated()`. If the container is not used to call it (or if the decorated class is in a different module), nothing gets registered |
| `patch` target not found (`AttributeError`) | Verify the dotted path resolves — e.g. `"myapp.database.connect"` requires `from myapp import database` already imported |

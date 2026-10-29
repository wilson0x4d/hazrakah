Lifetime Decorators
===================

.. index:: decorators; singleton; transient; instanced; provides

Overview
--------

The lifetime decorators — ``@singleton``, ``@transient``, and ``@instanced`` —
declare a type's lifetime at class-definition time. Each decorator is
**passive**: at decoration time it stores metadata in a process-wide registry
(a ``DecorationInfo`` per interface: lifetime, target, ``depends_on`` hints,
and optional ``namespace``) and marks the class. No container is involved yet.

That metadata is consumed in one of two ways:

1. **Lazily, at resolve time** (the default) — ``resolve()`` consults the
   decoration for any type that has no standing registration and registers it
   with the declared lifetime before resolving. No setup call is required.
2. **Eagerly, via ``register_decorated()``** — registers every decorated type
   at once, with optional filtering and topological ordering.

A standing registration (created any way: manual, eager, or a previous lazy
resolve) always takes precedence over decoration metadata.

Core Decorators
---------------

``@singleton``
~~~~~~~~~~~~~~

One shared instance per owning container; parent singletons cascade to children.

``@transient``
~~~~~~~~~~~~~~

A new instance on every ``resolve()``. This is also the default behavior for
undecorated concrete types, so ``@transient`` is explicit rather than necessary.

``@instanced``
~~~~~~~~~~~~~~

One pre-existing shared object, created once on first resolution (or eagerly by
``register_decorated()``), returned everywhere.

Usage Patterns
~~~~~~~~~~~~~~

.. code-block:: python

   from hazrakah import singleton, transient, instanced

   @singleton                           # self-referencing: the class is its own interface
   class Config: ...

   @singleton()                         # same, explicit call form

   @singleton(types=IFoo)               # explicit interface
   class FooService: ...

   @singleton(types=(IFoo, IBar))       # multiple interfaces

   @singleton(types=IFoo, depends_on=(IConfig,))   # ordering hint for eager registration
   class MyLogger: ...

   @singleton(namespace='v2')           # routes into the 'v2' namespace scope
   class VersionedService: ...

Factory Functions
~~~~~~~~~~~~~~~~~

Any of the three decorators can adorn a factory function. The factory must
declare exactly **one** positional parameter (which receives the resolver),
and ``types=`` is required because a function cannot infer an interface:

.. code-block:: python

   @singleton(types=ISession)
   def make_session(r: DependencyResolver) -> Session:
       return Session(connection_string=r.resolve(str))

The factory may be ``async``; the container awaits it transparently.

Lazy Resolution (Default)
-------------------------

When ``resolve()`` finds no standing registration for a type, it looks up the
type's decoration and registers it on the spot:

.. code-block:: python

   from hazrakah import Container, singleton

   @singleton
   class Service: ...

   c = Container()                       # no register_decorated() call
   assert c.resolve(Service) is c.resolve(Service)   # singleton semantics

Behavioral rules:

- **Standing registrations win.** A type already registered (manually or
  otherwise) resolves per that registration; its decoration is never inspected.
- **``types=`` works from both sides.** ``@singleton(types=IFoo) class Foo``
  makes ``resolve(IFoo)`` *and* ``resolve(Foo)`` honor the singleton lifetime,
  and both yield the *same* instance (singleton caching collapses onto the
  concrete target type).
- **Namespaced decorations.** For ``@singleton(namespace='v2') class Foo``:

  - ``c.resolve(Foo)`` (no namespace) keeps default behavior — Foo resolves as
    transient — while the v2 registration is materialized as a side effect.
  - ``c.resolve(Foo, namespace='v2')`` materializes the v2 registration on
    first touch, when the requested namespace chain includes ``'v2'``, and
    returns the shared v2 singleton.
  - Namespaces always materialize on the *root* container, so all scopes in the
    tree resolve the same namespaced instance.
- **Conflicting lifetimes on one target.** If a single class is decorated with
  two different lifetimes (e.g. ``@singleton(types=IFoo)`` *and*
  ``@transient(types=IBar)``), the target-level lookup is ignored with a logged
  warning and the type falls back to default transient behavior; each
  interface-level entry still works when resolved by its interface.
- **Frozen containers** reject lazy decoration registration with
  ``RegistrationError``, exactly as they reject manual registration.

Eager Registration: ``register_decorated()``
--------------------------------------------

``register_decorated()`` registers all decorated classes/functions found in the
global registry. It is **not required** for decorators to take effect (see lazy
resolution above) — use it for up-front validation, filtering, or ordering.

.. code-block:: python

   c.register_decorated()  # registers everything decorated

   # Filter by module namespace
   c.register_decorated(namespace_pattern=r"myapp\.services\..*")

   # Filter by class name
   c.register_decorated(class_pattern="^Service$")

- **Idempotent.** Repeated calls overwrite registrations (last-in-wins) and do
  not disturb already-created singleton instances.
- **Topological ordering.** ``depends_on=`` hints are honored: a type is
  registered only after every type it depends on (types with unresolvable
  dependencies fall to the end; cycles are logged and appended unsorted).
- **Namespace routing.** Entries decorated with ``namespace=`` are registered
  into the corresponding namespace scopes.

``@instanced`` entries are constructed immediately during ``register_decorated()``;
``@singleton``/``@transient`` entries are constructed lazily on first resolution.

Opting Out: ``disable_decorators()``
------------------------------------

A container can turn off resolve-time decoration inspection entirely:

.. code-block:: python

   c = Container().disable_decorators()   # chainable, returns self

   @singleton
   class Foo: ...

   c.resolve(Foo) is c.resolve(Foo)  # False -- plain transient fallback resumes

- The flag is per-container and **propagates to child scopes** created via
  ``create_scope()``.
- A child may override it: ``parent.create_scope(decorators=True)``, or set it
  at construction: ``Container(decorators=False)``.
- Existing registrations are unaffected — only the *inspection* of decoration
  metadata is disabled.
- Eager ``register_decorated()`` is explicit registration and still works on a
  disabled container.

``@provides``
-------------

``@provides(*types)`` is a passive multi-registration marker (it declares which
interfaces a class implements). It carries no lifetime; activation depends on
how the class is registered:

.. code-block:: python

   from hazrakah import provides, Container

   @provides(IFoo, IBar)
   class MultiImpl:
       def foo(self): ...
       def bar(self): ...

   c = Container()
   c.register_singleton(MultiImpl)   # no second arg → registers IFoo, IBar, AND MultiImpl

   assert c.resolve(IFoo) is c.resolve(IBar)   # same instance

When an explicit type is supplied (``register_singleton(IFoo, MultiImpl)``),
``@provides`` is **completely bypassed** and only the specified type is
registered.

``@provides`` is **mutually exclusive** with the lifetime decorators — stacking
them on one class raises ``RegistrationError`` at decoration time.

Rules & Error Conditions
------------------------

- **One lifetime per interface.** Decorating two targets for the same interface
  with different lifetimes raises ``RegistrationError`` at decoration time;
  the same lifetime is an overwrite (logged warning).
- **``@provides`` + lifetime decorator** on one class raises ``RegistrationError``
  at decoration time.
- **Factory signature.** A decorated factory with a number of positional
  parameters other than one raises ``RegistrationError`` at decoration time.
- **Factory without ``types=``** raises ``RegistrationError`` at decoration time.
- **Frozen container.** Lazy decoration registration raises ``RegistrationError``
  at resolve time; manual registration does so at registration time.
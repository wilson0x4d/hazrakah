Quick Start
===========
.. _quickstart:

Installation
------------

You can install ``hazrakah`` from `PyPI <https://pypi.org/project/hazrakah/>`_ through the usual means, such as ``pip``:

.. code-block:: bash

   pip install hazrakah


Usage
-----

Core lifetimes — Transient, Singleton, Instance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``hazrakah`` manages object lifecycles through three registration strategies:

.. code-block:: python

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


Hierarchical Scopes
~~~~~~~~~~~~~~~~~~~

Scopes provide isolation: parent registrations flow down, but child-only registrations stay local.

.. code-block:: python

    parent = Container()
    child = parent.create_scope()

    parent.register_transient(IFoo, Foo)
    child.resolve(IFoo)          # resolves parent's registration

    child.register_transient(IBar, Bar)
    child.resolve(IBar)          # works — registered in this scope


Context Management
~~~~~~~~~~~~~~~~~~

Resolve tracked resources and get deterministic teardown when the scope exits.

.. code-block:: python

    class Closeable:
        def __init__(self): self.closed = False
        def close(self): self.closed = True

    with Container() as c:
        c.register_transient(Closeable)
        res = c.resolve(Closeable)

    assert res.closed               # teardown ran automatically on __exit__


Fluent Chaining
~~~~~~~~~~~~~~~

All registration methods return ``self``, enabling method-chained container setup.

.. code-block:: python

    container = (
        Container()
        .register_transient(IFoo, Foo)
        .register_singleton(IBar, Bar)
        .register_instance(IFizz, Fizz())
    )

    assert isinstance(container.resolve(IFoo), Foo)
    assert isinstance(container.resolve(IBar), Bar)


Lifetime Decorators
~~~~~~~~~~~~~~~~~~~

Mark intent at class-definition time with ``@singleton``, ``@transient``, or ``@instanced``, then register everything in one call.

.. code-block:: python

    from hazrakah import Container, singleton, transient, instanced

    @singleton(types=IFoo)
    class FooService: ...

    @transient(types=IBar)
    class BarService: ...

    c = Container()
    c.register_decorated()            # discovers all decorated classes

    assert c.resolve(IFoo) is c.resolve(IFoo)     # singleton
    assert c.resolve(IBar) is not c.resolve(IBar)  # transient


Implicit multi-Registration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Declare which interfaces a class implements; registration binds to **all** of them simultaneously.

.. code-block:: python

    from hazrakah import Container, provides

    @provides(IFoo, IBar)
    class MultiImpl:
        def foo(self): ...
        def bar(self): ...

    c = Container()
    c.register_singleton(MultiImpl)    # also registers under IFoo and IBar

    a = c.resolve(IFoo)
    b = c.resolve(IBar)
    assert a is b                       # shared cache across all provided interfaces


How @provides Works
~~~~~~~~~~~~~~~~~~~

The ``@provides`` decorator is a **passive marker** -- it stores metadata only, with zero registration logic at decoration time. Activation depends entirely on how the container later registers the decorated class.

**@provides activates** when you call ``register_singleton``, ``register_transient``, or ``register_instance`` with **no second argument** (no explicit type override):

.. code-block:: python

    @provides(IFoo, IBar)
    class MultiImpl: ...

    c.register_singleton(MultiImpl)  # multi-registers under IFoo + IBar + MultiImpl
    c.resolve(IFoo)                  # works -- @provides activated
    c.resolve(IBar)                  # works -- @provides activated

**@provides does NOT activate** when you provide an explicit type argument to a registration method:

.. code-block:: python

    @provides(IBar)
    class MultiImpl: ...

    c.register_singleton(IFoo, MultiImpl)  # only IFoo is registered
    c.resolve(IFoo)                        # works -- explicit registration
    c.resolve(IBar)                        # raises KeyError -- @provides was ignored

This is intentional. The second positional argument on any ``register_*`` method is the **explicit type override**. When you provide it, you are telling the container exactly which key to register against -- and ``@provides`` does not interfere.

+-----------------------------------------------+------------------------+-------------------------------------+

Self-Resolve
~~~~~~~~~~~~

By default, hazrakah lets a :py:class:`hazrakah.Container` resolve **itself** when asked for one of its own interface types — :py:class:`~hazrakah.DependencyRegistry`, :py:class:`~hazrakah.DependencyResolver`, or :py:class:`~hazrakah.ScopedDependencyResolver` — even if nothing is explicitly registered. This makes the container conveniently available as a dependency without manual registration:

.. code-block:: python

    from hazrakah import Container, DependencyResolver

    class MyService:
        def __init__(self, resolver: DependencyResolver) -> None:
            self.resolver = resolver   # the container is injected automatically

    c = Container()
    service = c.resolve(MyService)
    assert service.resolver is c     # same container instance


You can **disable** this behaviour by passing ``self_resolve=False`` to the constructor. With self-resolve disabled, resolving for a DI interface behaves exactly like any other unregistered type — it raises :py:class:`~hazrakah.ResolutionError` unless you provide an explicit registration:

.. code-block:: python

    from hazrakah import Container, DependencyResolver, ResolutionError

    c = Container(self_resolve=False)

    # Raises ResolutionError -- no explicit registration for DependencyResolver
    try:
        c.resolve(DependencyResolver)  # type: ignore[arg-type]
    except ResolutionError:
        pass   # expected


If you need a custom ``DependencyResolver`` (or any of the other interfaces), register it explicitly — explicit registrations take precedence regardless of the ``self_resolve`` setting:

.. code-block:: python

    from hazrakah import Container, DependencyResolver

    class MyCustomResolver(DependencyRegistry):
        def resolve(self, t) -> Any: ...
        def is_registered(self, t) -> bool: ...
        def register_instance(self, t, instance): ...
        def register_singleton(self, t, target=None): ...
        def register_transient(self, t, target=None): ...

    custom = MyCustomResolver()
    c = Container(self_resolve=False)
    c.register_instance(DependencyResolver, custom)   # type: ignore[arg-type]

    resolved = c.resolve(DependencyResolver)  # type: ignore[arg-type]
    assert resolved is custom                 # explicit registration wins

Caching with ``Cached[T]``
~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``Cached[T]`` generic type wraps a factory callable so its result is produced once and re-used until the TTL window elapses.  The factory receives a resolver as its first argument, matching hazrakah's standard factory contract (see :py:data:`hazrakah.DependencyRegistry.Factory`).  It can be combined with any container lifetime to add time-bound caching on top of dependency injection.

.. code-block:: python

    from datetime import timedelta
    from hazrakah import Cached

    class ConfigSource:
        def load(self) -> str:
            return 'loaded'

    # TTL accepts float (seconds) or timedelta; default is 47.0 seconds.
    cache = Cached(lambda c: ConfigSource(), ttl=timedelta(seconds=47))

    first = cache(object())   # factory called once (TTL not yet elapsed)
    second = cache(object())  # cached value returned; factory not re-invoked
    assert first is second     # same instance


Manual expiration and zero-TTL modes are also supported:

.. code-block:: python

    always_miss = Cached(lambda c: ConfigSource(), ttl=timedelta(seconds=0))
    assert always_miss(object()) is not always_miss(object())  # factory called each time

    cache = Cached(lambda c: ConfigSource())
    cache.reset()                          # discard cached value
    fresh = cache(object())                # re-invokes factory

``ttl`` also accepts a plain float (seconds), exposed as a :py:class:`timedelta` property:

.. code-block:: python

    cache = Cached(lambda c: ConfigSource(), ttl=120.0)  # 120 seconds
    assert cache.ttl == timedelta(seconds=120)


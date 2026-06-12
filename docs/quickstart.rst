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


Built-in Mock Library
~~~~~~~~~~~~~~~~~~~~~

A lightweight ``Mock`` with fluent configuration, call tracking, argument matchers, and module-level ``patch()``.

.. code-block:: python

    from hazrakah.mocks import Mock, is_gt, is_any, contains, is_in, neg

    m = Mock()

    # Fluent stubbing.
    m.get_status.returns("ok")
    assert m.get_status() == "ok"

    # Side-effects on the child mock (fluent call, not direct assignment).
    m.compute.side_effect(lambda x: 10 if x > 5 else 20)
    assert m.compute(7) == 10
    assert m.compute(2) == 20

    # Call tracking.
    assert m.compute.was_called_with(is_gt(5), is_any())
    assert m.compute.was_called_with(is_in(1, 2, 3))
    assert m.compute.call_count == 2

    # Composed matchers.
    m.filter.returns(True)(neg(contains("blocked")))
    assert m.filter("allowed") is True

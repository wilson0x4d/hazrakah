Container Scopes
================

.. index:: scopes; hierarchy; parent; child

What Are Scopes?
----------------

A scope is a child container that inherits registrations from its parent while
allowing its own isolated registrations. Scopes form a tree — the root container
is the top of the hierarchy, and each ``create_scope()`` call extends the tree
with a new child.

The scope hierarchy enables two key patterns:

1. **Inheritance** - child scopes can resolve types registered on any ancestor.
2. **Shadowing** - child scopes can register their own implementations of a type,
   hiding the parent registration within that scope and all descendants.

Scope hierarchies are the primary mechanism for organizing DI at any granularity:
entire application, feature modules, request/transaction boundaries, or test setup.

``create_scope()``
------------------

The ``create_scope()`` method returns a new ``Container`` with the current container
as its ``outer_scope`` (parent):

.. code-block:: python

   parent = Container()
   child = parent.create_scope()
   grandchild = child.create_scope()

The parent reference is available via the ``__outer_scope`` attribute:

.. code-block:: python

   assert child.__outer_scope is parent  # True


Registration Inheritance
------------------------

Child scopes automatically inherit all registrations from their parents:

.. code-block:: python

   parent = Container()
   child = parent.create_scope()

   parent.register_transient(IDb, Postgres)

   child.resolve(IDb)  # → Postgres (inherited)

The resolution walk proceeds from the child outward: child's registrations first,
then parent, then grandparent, and so on. The first matching registration wins.


Shadowing
---------

A child can register its own implementation of a type, shadowing the parent
registration within that scope and all descendants:

.. code-block:: python

   parent = Container()
   child = parent.create_scope()

   parent.register_singleton(IFoo, FooDefault)
   child.register_singleton(IFoo, FooChild)

   parent.resolve(IFoo)  # → FooDefault
   child.resolve(IFoo)   # → FooChild

Shadowing is lifetime-aware: each lifetime mode caches separately per container.


Fluent Chaining Across Scopes
-----------------------------

Fluent-chained registrations on a parent propagate to child scopes:

.. code-block:: python

   from hazrakah import Container

   parent = (
       Container()
       .register_transient(IFoo, Foo)
       .register_singleton(IBar, Bar)
   )
   child = parent.create_scope()

   child.resolve(IFoo)   # → Foo
   child.resolve(IBar)   # → Bar (same singleton as parent)

The singleton is shared between parent and child even when the parent was
configured via a fluent chain.


Inheritance of Container Flags
------------------------------

Child scopes inherit certain container configuration from the parent.

**``frozen`` inheritance (default):**

If the parent is frozen, all newly created child scopes are automatically
frozen. You can override this by passing an explicit ``frozen`` value:

.. code-block:: python

   parent = Container(frozen=True)
   child = parent.create_scope()
   # child is also frozen

   # Override: create an unfrozen child of a frozen parent
   mutable_child = parent.create_scope(frozen=False)  # type: ignore[arg-type]

**``self_resolve`` inheritance:**

The ``self_resolve`` flag always inherits from the parent. It can be overridden:

.. code-block:: python

   parent = Container(self_resolve=False)
   child = parent.create_scope()
   # child also has self_resolve=False

   # Override: re-enable self-resolve in the child
   responsive_child = parent.create_scope(self_resolve=True)

Neither flag propagates to sibling containers — each child is only affected by
its direct parent.


One-Way Visibility
------------------

Child scopes can see their parent's registrations, but parents cannot see
child registrations:

.. code-block:: python

   parent = Container()
   child = parent.create_scope()

   child.register_transient(IBar, ChildBar)

   child.resolve(IBar)   # → ChildBar
   parent.resolve(IBar)  # → ResolutionError

Each scope only walks outward toward ancestors, never downward toward descendants.


Singleton Lifecycle Across Scopes
---------------------------------

Singletons follow strict per-container lifecycle rules:

1. A singleton registered in the parent is shared across all child scopes.
2. A singleton registered in a child is local to that child and its descendants.
3. Each container caches its own singleton instance.

.. code-block:: python

   parent = Container()
   child_a = parent.create_scope()
   child_b = parent.create_scope()

   parent.register_singleton(ISession, ParentSession)
   child_a.register_singleton(ISession, ChildASession)

   parent.resolve(ISession)    # → ParentSession
   child_a.resolve(ISession)   # → ChildASession (shadowed)
   child_b.resolve(ISession)   # → ParentSession (inherits from parent)

   # Two resolves in the same child return the same cached instance
   session1 = child_a.resolve(ISession)
   session2 = child_a.resolve(ISession)
   assert session1 is session2


Context Manager Teardown
------------------------

Containers implement RAII via context manager, providing deterministic teardown of
tracked objects when the scope exits. Objects created through ``resolve()`` are
tracked automatically:

.. code-block:: python

   class CloseableResource:
       def __init__(self) -> None:
           self.closed = False

       def close(self) -> None:
           self.closed = True

   with Container() as scope:
       scope.register_transient(CloseableResource)
       resource = scope.resolve(CloseableResource)

   assert resource.closed  # close() called on __exit__


Child Scope Teardown
--------------------

When a child scope (created via ``create_scope()``) is used as a context manager,
only its own tracked objects are destroyed:

.. code-block:: python

   with Container() as parent:
       parent.register_transient(CloseableResource)
       resource = parent.resolve(CloseableResource)

       with parent.create_scope() as child:
           child_resource = child.resolve(CloseableResource)

   # Both resources are cleaned up
   assert resource.closed
   assert child_resource.closed


Parent singletons survive child teardown:

.. code-block:: python

   with Container() as parent:
       parent.register_transient(CloseableResource)
       resource = parent.resolve(CloseableResource)

       with parent.create_scope() as child:
           # child inherits parent's CloseableResource instance
           # because it was registered in the parent and resolved as a singleton
           pass

       assert not resource.closed  # parent singleton preserved


Transitive Teardown
-------------------

All transitive dependencies created during resolution are tracked and torn down:

.. code-block:: python

   class Database:
       def __init__(self, connection: Connection) -> None: ...

   with Container() as scope:
       scope.register_transient(Connection)
       scope.register_transient(Database)
       db = scope.resolve(Database)

   # Both Database and Connection are closed


Exception Handling
------------------

Exceptions raised inside a ``with`` block propagate normally; teardown still runs:

.. code-block:: python

   with Container() as scope:
       scope.register_transient(CloseableResource)
       scope.resolve(CloseableResource)
       raise RuntimeError("oops!")  # propagates, but teardown still runs


If ``close()`` itself raises, the exception propagates from the outer scope's
``__exit__``.


Self-Resolution
---------------

By default, resolving the interfaces ``DependencyRegistry``, ``DependencyResolver``,
or ``ScopedDependencyResolver`` returns the container itself (enabling
``create_scope()`` calls). This behavior can be disabled:

.. code-block:: python

   container = Container(self_resolve=False)
   container.resolve(ScopedDependencyResolver)  # → ResolutionError

The flag is inherited by children:

.. code-block:: python

   parent = Container(self_resolve=False)
   child = parent.create_scope()

   child.resolve(ScopedDependencyResolver)  # → ResolutionError

Explicit instance registration overrides ``self_resolve=False``:

.. code-block:: python

   class MyResolver(ScopedDependencyResolver): ...

   container = Container(self_resolve=False)
   container.register_instance(ScopedDependencyResolver, MyResolver())

   result = container.resolve(ScopedDependencyResolver)  # → MyResolver instance


User-Owned Objects
------------------

Objects registered via ``register_instance()`` are user-owned and are **not**
tracked or destroyed by the context manager:

.. code-block:: python

   owned = CloseableResource()

   with Container() as scope:
       scope.register_instance(CloseableResource, owned)
       scope.resolve(CloseableResource)

   # owned is NOT closed — it belongs to the user, not the scope

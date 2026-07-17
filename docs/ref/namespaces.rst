Namespaced Registrations
=========================

.. index:: namespaces; registrations

Overview
--------

Namespaces allow multiple namespace-scoped containers within a single container tree.
A type can be registered into the main (unnamespaced) container or into one or more
named namespace scopes. Resolution with a namespace argument walks the requested
namespace scopes before falling back to the standard scope chain.

Namespaces are implemented as scope children created via ``create_scope(namespace=...)``,
with the root container maintaining a ``__namespaces`` dict mapping namespace strings
to their corresponding scoped containers.

Key Design Decisions
--------------------

**Namespaces are NOT shared between containers.** The ``__namespaces`` dict only exists
on the container that owns registrations for that namespace. A child scope with
namespace ``'v2'`` has no visibility into another container's ``'v2'`` namespaces.

**Backwards compatibility.** Existing code that does not use namespace parameters
continues to work identically. The ``namespace`` parameter has a default of ``None``
on all APIs.

**Auto-creation of namespace containers.** When registering with a namespace string
(e.g., ``register_transient(IDb, MySQL, namespace='v2')``), hazrakah automatically
creates the namespace scope container if it doesn't exist.

Basic Usage
-----------

Registering into a namespace:

.. code-block:: python

   root.register_transient(IDb, Postgres)               # → root's default container
   root.register_transient(IDb, MySQL, namespace='mysql')  # → root.__namespaces['mysql']

Resolving from a namespace:

.. code-block:: python

   root.resolve(IDb)                                         # → Postgres (default container)
   root.resolve(IDb, namespace='mysql')                      # → MySQL
   root.resolve(IDb, namespace=['mysql', None])             # → MySQL (or fallback)

Namespace priority chains resolve each scope in order:

.. code-block:: python

   root.resolve(IDb, namespace=['v2', 'v1', None])
   # Tries 'v2' first, then 'v1', then falls back to standard resolution

The ``namespace=`` argument accepts:

* **String**: ``namespace='v2'`` is equivalent to ``namespace=['v2', None]``
* **List/Tuple**: ``namespace=['v2', 'v1', None]`` tries each in order
* **Empty list**: ``namespace=[]`` treats as no fallback (strict failure)
* **None**: Default behavior, no namespace filtering

Decoupled from Scope Chain
---------------------------

**A key design rule applies:** when a namespace-scoped container resolves with a
``namespace`` argument, it only checks the explicitly requested namespace scopes
and its own registrations. It never walks the scope chain to parent defaults.

This prevents infinite resolution loops (outer → inner → outer → inner) while keeping
namespace resolution predictable:

.. code-block:: python

   root.register_transient(IDb, Postgres)  # default
   v2_scope = root.create_scope(namespace='v2')
   v2_scope.register_transient(IDb, MySQL)

   # Resolving WITH namespace → checks namespace scopes only
   root.resolve(IDb, namespace='v2')  # → MySQL

   # Resolving WITHOUT namespace on the namespace-scoped container
   # checks ONLY its own registrations, not the parent scope chain:
   v2_scope.resolve(IDb, namespace=[None])  # → ResolutionError
   # Notice: even though v2_scope.__outer_scope is root, it does NOT
   # find the Postgres registration from root's default scope.

   # To get the default (unnamespaced) registration from a namespace-scoped container,
   # resolve directly on the root container instead:
   root.resolve(IDb)  # → Postgres

Decorator Support
-----------------

Lifetime decorators accept a ``namespace`` parameter:

.. code-block:: python

   from hazrakah import singleton, transient, provides

   @singleton(namespace='v2')
   class MyService:
       pass

   @transient(namespace='mysql')
   class DBConnection:
       pass

   @provides(IFoo, IBar, namespace='v2')
   class MultiImpl:
       pass

When ``register_decorated()`` runs, it routes registrations into the specified
namespace scopes based on the decoration info.

Frozen Propagation
------------------

Calling ``container.freeze()`` also freezes all directly owned namespace containers:

.. code-block:: python

   root = Container()
   root.register_transient(IDb, MySQL, namespace='v2')
   root.freeze()

   root.__namespaces['v2'].register_transient(IDb, SQLite)
   # Raises RegistrationError

Transitive Propagation
----------------------

Namespace context flows into all constructor parameter sub-resolves:

.. code-block:: python

   class MyService:
       def __init__(self, db: IDb): ...

   root.register_transient(IDb, PostgreSQL)
   root.register_transient(IDb, MySQL, namespace='mysql')
   root.register_transient(MyService)

   root.resolve(MyService)           # → MyService(db=PostgreSQL)
   root.resolve(MyService, namespace=['mysql'])  # → MyService(db=MySQL)


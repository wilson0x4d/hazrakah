Overview
========

.. image:: https://img.shields.io/pypi/v/hazrakah.svg
   :target: https://pypi.org/project/hazrakah/
   :alt: hazrakah on PyPI

.. image:: https://readthedocs.org/projects/hazrakah/badge/?version=latest
   :target: https://hazrakah.readthedocs.io
   :alt: hazrakah on Read the Docs

**hazrakah** (הזרקה) is a tiny but powerful DI library for Python.

Features
--------

- Supports Singleton, Transient, and Instance lifetimes.
- **Hierarchical scoping**; Isolate registrations and/or resolves. optionally use a context manager to deterministically tear down a scope and its resolved objects.
- **Protocols, ABCs, and Concretes** can be registered against **Factory Functions and Concretes**.
- **Lifetime Decorators**; (OPTIONAL) Types decorated with  ``@singleton``, ``@transient`` or ``@instanced`` can be registered with a single call to ``register_decorated()``, simplifying orchestration.
- **Implicit Multi-Registration**; Types decorated with ``@provides`` bind to all provided types (unless explicit types are specified during registration.)
- **Fluent API**; All registration methods return ``self``, enabling method-chained container setup.

Contents
--------

.. toctree::
   :maxdepth: 3

   Overview <self>
   Quick Start <quickstart>
   Reference <ref/index>
   SKILL <SKILL>
   MIT License <license>
   Contact <contact>

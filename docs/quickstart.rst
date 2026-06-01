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

To use ``hazrakah`` simply create a :class:`hazrakah.Container` instance and create one or more type registrations. Afterward, the container can be used to resolve instances for the types you have registered:

.. code-block:: python

    from hazrakah import Container

    # assume you have three classes, Fizz, Buzz, and FizzBuzz,
    # and also assume you have Protocols (interfaces) for each.

    container = Container()
    scoped_container = container.create_scope()

    # TRANSIENT == a new instance of `Foo` is created
    # for every resolve of `IFoo`.
    container.register_transient(IFizz, Fizz)
    #
    fizz1 = container.resolve(IFizz)
    fizz2 = container.resolve(IFizz)
    assert fizz1 is not fizz2, 'transient reg, every resolve is a new instance.'


    # CHILD SCOPED registrations cannot be resolved
    # from PARENT SCOPE.
    scoped_container.register_transient(IBuzz, Buzz)
    buzz1 = scoped_container.resolve(IBuzz)
    assert buzz1 is not None, 'scopes should allow new registrations.'
    try:
        _ = container.resolve(IBuzz)
    except KeyError:
        pass
    else:
        raise AssertionError('parent scopes should not resolve child scope registrations.')

    # INSTANCE == the provided instance is returned
    # for every resolve of `FizzBuzz`.
    container.register_instance(FizzBuzz, FizzBuzz())
    #
    fizzbuzz1 = container.resolve(FizzBuzz)
    fizzbuzz2 = scoped_container.resolve(FizzBuzz)
    assert fizzbuzz1 is fizzbuzz2, 'instance resolves always yield the provided instance'

    # SINGLETON == a SINGLE instance will be created
    # for ALL resolves of `IFizzBuzz`.
    container.register_singleton(IFizzBuzz, lambda c: c.resolve(FizzBuzz))
    fizzbuzz3 = container.resolve(IFizzBuzz)
    fizzbuzz4 = container.resolve(IFizzBuzz)
    assert fizzbuzz3 is fizzbuzz4, 'singleton resolves always yield a single instance.'

    # for completeness, concrete types can self-regsiter without a target spec.
    container.register_transient(Fizz)
    fizz3 = container.resolve(Fizz)
    assert fizz3 is not None

    # and last, but not least, containers can be frozen,
    # making them immutable (also freezing any scopes
    # created after being frozen.)  once frozen, they
    # cannot be unfrozen.
    try:
        container.freeze()
        container.register_instance(Fizz, Fizz())
    except RegistrationError:
        pass
    else:
        assert False, 'Frozen containers should be immutable.'

    try:
        scoped_container.register_instance(Fizz, Fizz())
    except:
        assert False, 'Scopes created BEFORE freezing are NOT frozen.'

    try:
        scope2 = container.create_scope()
        scope2.register_instance(Fizz, Fizz())
    except RegistrationError:
        pass
    else:
        assert False, 'Scopes created AFETR freezing are also frozen.'

    try:
        setattr(container, '__frozen', False)
    except AttributeError:
        pass
    else:
        assert False, 'Attempts to modify Container directly will fail.'


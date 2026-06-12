# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT


class RegistrationError(RuntimeError):
    """
    Raised when a registration cannot be processed.

    Typical situations that trigger this error:

    * Attempting to create an instance from a registration that has no
      ``target`` (e.g. a ``Lifetime.INSTANCE`` registration without an
      associated object).
    * Supplying a factory that does not conform to the expected signature
      ``Callable[[Container], T]``.
    * Providing an instance to :meth:`Container.register_instance` that is
      not an instance of the registration type.
    """

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        """
        Create the exception.

        :param message: Human-readable description of the problem.
        :param cause: Optional original exception that led to this error.  It is stored as ``__cause__`` so that traceback chaining works automatically.
        """
        super().__init__(message)
        if cause is not None:
            super().__setattr__('__cause__', cause)

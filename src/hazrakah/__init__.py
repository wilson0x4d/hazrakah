# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT

from .Container import Container
from .DependencyRegistry import DependencyRegistry, Factory, Target
from .DependencyResolver import DependencyResolver, ScopedDependencyResolver
from .RegistrationError import RegistrationError
from .ResolutionError import ResolutionError
from .lifetime_decorators import Lifetime, singleton, transient, instanced
from .Cached import Cached
from .provides_decorator import provides


__version__ = '0.0.0'
__commit__ = '0abc123'
__all__ = [
    '__version__', '__commit__',
    'Cached',
    'Container',
    'DependencyRegistry',
    'DependencyResolver',
    'Factory',
    'Lifetime',
    'ResolutionError',
    'RegistrationError',
    'ScopedDependencyResolver',
    'Target',
    'provides',
    'singleton',
    'transient',
    'instanced',
]

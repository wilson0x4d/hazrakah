# SPDX-FileCopyrightText: © 2026 Shaun Wilson
# SPDX-License-Identifier: MIT


class ModuleShadowedDependentType:
    def __init__(self, t: 'ModuleShadowedType') -> None:
        pass


class ModuleShadowedType:
    def __init__(self) -> None:
        pass

"""TTRPG-owned PF2ER source and compiler input errors."""


class EngineInputError(ValueError):
    """The caller or cached source supplied an invalid compiler input."""


class EngineTransitionError(EngineInputError):
    """A compiled transition-shaped value is invalid or unsupported."""


__all__ = ["EngineInputError", "EngineTransitionError"]

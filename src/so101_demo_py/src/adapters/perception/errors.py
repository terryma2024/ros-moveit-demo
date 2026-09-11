"""Closed model boundary: only completed, invalid output is a model error."""


class DeterministicModelResultError(ValueError):
    """Computation completed, but its result violates the output contract."""


class ModelRuntimeInfrastructureError(RuntimeError, ValueError):
    """Infrastructure failure; ValueError compatibility preserves existing CLI catches."""

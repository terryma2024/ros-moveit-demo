"""Test-only controller authority port adapter.

The unified port contract is ``identity_snapshot`` plus ``close(reason, generation=None)``:
a concrete generation means "close exactly this one", ``None`` means "close the whole
attempted range" (the port knows its own range). Legacy fixtures carry
dispatch-shaped ports whose ``close`` has a different signature, so this adapter maps
that call onto the unified one and records every closure for assertions.
"""


class ControllerAuthorityAdapter:
    """Adapt a legacy dispatch port to the unified authority port contract."""

    def __init__(self, port):
        if port is None or not callable(getattr(port, "identity_snapshot", None)):
            raise TypeError("TEST_ADAPTER_PORT_INVALID")
        self._port = port
        self.closed_generations = []
        self.fencing_required = False

    def identity_snapshot(self, role):
        return self._port.identity_snapshot(role)

    def close(self, reason="CLOSED", generation=None):
        """Unified close: exact generation when given, else the whole attempted range."""

        if generation is not None and (not isinstance(generation, int) or generation <= 0):
            raise ValueError("TEST_ADAPTER_GENERATION_INVALID")
        self.closed_generations.append(generation)
        legacy = getattr(self._port, "close", None)
        if callable(legacy):
            try:
                return legacy(reason, generation=generation)
            except TypeError:
                return legacy(reason)          # legacy signature: reason only
        return True

    def close_current_generation(self, generation):
        """Compatibility shim for fixtures that still use the older member name."""

        return self.close("CLOSE_CURRENT_GENERATION", generation=generation)

    def __getattr__(self, name):
        return getattr(self._port, name)

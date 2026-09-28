"""Production controller-port contract for AuthorityTransactionRegistry.

The registry's production contract is deliberately narrow: a role-scoped
identity snapshot (read from the ACK-confirmed cache, no I/O) and an explicit
close of the current generation. It deliberately does NOT implement reserve/send:
the single production dispatch path is

    CommandBroker.claim_prepared_goal -> ControllerReservationClient.reserve_bound
    -> driver.send_prepared

so a second reservation transport through this port would be a duplicate
dispatch path.
"""


class RosControllerPort:
    """Role-aware identity + real generation closure for the registry."""

    def __init__(self, client):
        from so101_demo.adapters.act.controller_reservation_client import ControllerReservationClient

        if type(client) is not ControllerReservationClient:
            raise TypeError("ROS_CONTROLLER_PORT_CLIENT_INVALID")
        self._client = client

    def identity_snapshot(self, role):
        """ACK-confirmed identity for exactly this role (no I/O, no caller data)."""

        return self._client.identity_snapshot(role)

    def close_current_generation(self, generation):
        """Really close the controller side for this generation (not a no-op)."""

        if not isinstance(generation, int) or generation <= 0:
            raise ValueError("ROS_CONTROLLER_PORT_GENERATION_INVALID")
        return self._client.close_generation(generation) is not False

    def close(self, reason="CLOSED", generation=None):
        """Registry-facing closure.

        With an explicit generation (the composition knows the live ticket) only that
        generation is closed; otherwise the client's public close-all API is used.
        No private client state is read here.
        """

        if generation is not None:
            return self.close_current_generation(generation)
        self._client.close_all_attempted()
        return True

"""Expose the existing ROS broker's verified controller reference to the expert tap."""

from __future__ import annotations


class RosControllerReferencePort:
    def __init__(self, broker) -> None:
        self.broker = broker

    def reference_state(self, at_s: float) -> dict:
        state = self.broker.reference_state(at_s)
        return {**state, "source": "CONTROLLER_REFERENCE"}

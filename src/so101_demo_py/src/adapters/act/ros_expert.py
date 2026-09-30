"""Expose the existing ROS broker's verified controller reference to the expert tap."""

from __future__ import annotations


class RosControllerReferencePort:
    def __init__(self, broker) -> None:
        self.broker = broker

    def reference_state(self, at_s: float) -> dict:
        state = self.broker.reference_state(at_s)
        return {**state, "source": "CONTROLLER_REFERENCE"}

    def reference_frames(self, kind: str, at_s: float) -> dict:
        """The ratified A.1 frame for one kind at one instant (T3-F1).

        F1's complaint was that this path did not exist, so the expert tap could only reach the
        compatibility `reference_state`; the broker owns the frame, including its refusal when a kind
        arrived through an accepted interval rather than a publication.
        """

        return self.broker.reference_frames(kind, at_s)

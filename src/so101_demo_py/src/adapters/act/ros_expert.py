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

        # T3-F1: the broker publishes its frame with tuple-valued names and vectors; the common audit admits
        # lists, so this carrier boundary normalises the shape and preserves every value unchanged
        frame = dict(self.broker.reference_frames(kind, at_s))
        for key in ("joint_names", "published_positions", "published_velocities",
                    "evaluated_positions", "evaluated_velocities"):
            if isinstance(frame.get(key), tuple):
                frame[key] = list(frame[key])
        return frame

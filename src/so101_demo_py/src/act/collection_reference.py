"""The controller reference record of one grid instant, built from original controller publications (Phase A4c).

This was `RosBrokerDriver.collection_reference` behind the command broker's `collection_reference` RPC. The independent
Recorder reads the controller state topics itself and has no part in the Teacher's leased connection, so the RPC and its
only client are gone and the record is built here, from `recent(kind)` (identity and fresh original frames of one
controller kind), by the Recorder and by the readback tests alike.
"""

from __future__ import annotations

import copy

from .contracts import finite


def build_collection_reference(when: float, recent, *, matching=None) -> dict:
    """The `CONTROLLER_REFERENCE` record for `when`; refuses an absent, ambiguous or foreign-epoch publication.

    `matching(kind, target_ns)` may replace `recent(kind)`: it returns the same identity and only the frames within 1 us of
    the instant (what the window filter below would keep), so one read no longer copies the controller's whole window.
    """

    when = finite(when, nonnegative=True)
    target_ns = round(when * 1e9)
    frames, positions, mapping, identity = {}, [], [], None
    for kind in ("arm", "gripper"):
        if matching is None:
            current, history = recent(kind)
            found = [frame for frame in history if abs(frame["sim_stamp_ns"] - target_ns) <= 1000]
        else:
            current, found = matching(kind, target_ns)
        if identity is not None and identity != current:
            raise RuntimeError("REFERENCE_HISTORY_EPOCH_INVALID")
        identity = current
        if len(found) != 1:
            raise RuntimeError("COLLECTION_REFERENCE_EXACT_PUBLICATION_UNAVAILABLE")
        raw = found[0]
        values, velocities = list(raw["positions"]), list(raw["velocities"])
        frames[kind] = dict(
            joint_names=list(raw["joint_names"]), published_positions=values, published_velocities=velocities,
            evaluated_positions=list(values), evaluated_velocities=list(velocities),
            evaluation=dict(requested_sim_time_s=when, basis="published", goal_id=None, accepted_sim_s=None,
                            revoked_sim_s=None),
            sim_stamp_ns=raw["sim_stamp_ns"], received_monotonic_ns=raw["received_monotonic_ns"],
            observer_sequence=raw["observer_sequence"])
        if "original_message" in raw:
            frames[kind]["original_message"] = copy.deepcopy(raw["original_message"])
        positions.extend(values)
        mapping.extend([[kind, index] for index in range(len(values))])
    return dict(requested_sim_time_s=when, source="CONTROLLER_REFERENCE", positions=positions, frames=frames,
                projected_positions=list(positions), projection_map=mapping)

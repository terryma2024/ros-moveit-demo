"""Build the two APPROACH goals an inspected prefix executes.

The path screen validates these goals field by field, so the builder exists to agree with that validator rather than
to make its own choices: the same closed key set, the same joint split, the same offsets and the same
``split_positions((held,) + prefix["positions"])`` rows. A test lets the screen judge this module's output, which is
the only opinion that counts.
"""

from __future__ import annotations

from so101_demo.act.contracts import validate_action_prefix
from so101_demo.act.execution import bounded_positions, prefix_sha256, split_positions
from so101_demo.act.joints import ARM_JOINTS

#: the goals' closed key set, mirroring the screen's own `_GOAL_KEYS`; a test asserts the two are equal
APPROACH_GOAL_KEYS = frozenset({
    "joint_names", "header_stamp_s", "time_from_start_s", "positions",
    "session_id", "attempt_id", "sequence", "prefix_sha256",
})


def build_approach_goals(prefix, held_positions, *, header_stamp_s):
    """Return the (arm, gripper) goals for one validated prefix, or raise naming what is wrong.

    ``header_stamp_s`` is the goal header's stamp and must fall strictly between the prefix's observation time and its
    first target time - the screen refuses anything else, so a caller cannot pass an arbitrary stamp and hope.
    """

    checked = validate_action_prefix(prefix)
    held = bounded_positions(tuple(held_positions))
    if len(held) != len(ARM_JOINTS):
        raise ValueError("APPROACH_HELD_POSITIONS_INVALID")
    observed = checked["observation_time_s"]
    targets = tuple(checked["target_times_s"])
    if not targets or not observed < header_stamp_s < targets[0]:
        raise ValueError("APPROACH_HEADER_STAMP_INVALID")

    rows = tuple(tuple(row) for row in checked["positions"])
    arm_rows, gripper_rows = split_positions((held,) + rows)
    offsets = (0.0,) + tuple(target - header_stamp_s for target in targets)
    digest = prefix_sha256(checked)
    shared = {"header_stamp_s": header_stamp_s, "time_from_start_s": offsets,
              "session_id": checked["session_id"], "attempt_id": checked["attempt_id"],
              "sequence": checked["sequence"], "prefix_sha256": digest}
    return ({"joint_names": ARM_JOINTS[:5], "positions": arm_rows, **shared},
            {"joint_names": ARM_JOINTS[5:], "positions": gripper_rows, **shared})

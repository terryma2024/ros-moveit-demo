"""An evidence-bound transfer schedule is a source-only candidate."""

from act_identity import ACT_MODEL_SHA256
import copy
import hashlib
import json
from pathlib import Path

import pytest

from so101_demo.act.contracts import ContractError, validate_action_prefix
from so101_demo.act.execution import ActExecutionAdapter
from so101_demo.act.held_cup_transfer_profile import (
    build_held_cup_transfer_segments, load_held_cup_transfer_profile,
)
from so101_demo.act.held_cup_transfer_schedule import (
    build_held_cup_transfer_schedule, load_held_cup_transfer_schedule,
    validate_held_cup_transfer_prefix,
)
from so101_demo.act.permits import PermitAuthority


CONFIG = Path(__file__).resolve().parents[1] / "config/mujoco/act"
MODEL_SHA = ACT_MODEL_SHA256
POLICY_SHA = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"


def profile():
    return load_held_cup_transfer_schedule(
        CONFIG / "held_cup_transfer_v3.json",
        evidence_index_path=CONFIG / "held_cup_transfer_evidence_v3.json",
        expected_model_sha256=MODEL_SHA,
        expected_policy_fingerprint=POLICY_SHA,
    )


@pytest.mark.parametrize("anchor,expected_last", [
    ("default", 600), ("left", 600), ("forward", 650),
])
def test_schedule_retains_exact_parent_motion(anchor, expected_last):
    old = load_held_cup_transfer_profile(
        CONFIG / "held_cup_transfer_v2.json",
        expected_model_sha256=MODEL_SHA,
        expected_policy_fingerprint=POLICY_SHA,
    )
    new = profile()
    held = new["anchors"][anchor]["held_q_rad"]
    previous = build_held_cup_transfer_segments(old, anchor, held_q_rad=held)
    segments = build_held_cup_transfer_schedule(new, anchor, held_q_rad=held)
    assert [len(rows) for _, rows in segments] == [600] + [500] * 9 + [expected_last]
    assert [phase for phase, _ in segments] == [phase for phase, _ in previous]
    for index, ((_, rows), (_, old_rows)) in enumerate(zip(segments, previous)):
        assert rows[:500] == old_rows[:500]
        if index < 10 or anchor != "forward":
            assert rows == old_rows
    if anchor == "forward":
        assert segments[-1][1][500:] == [segments[-1][1][499]] * 150


def test_forward_prefix_is_source_only_and_tightly_bound():
    bound = profile()
    held = bound["anchors"]["forward"]["held_q_rad"]
    segments = build_held_cup_transfer_schedule(bound, "forward", held_q_rad=held)
    rows = segments[-1][1]
    # The complete checker and independent readback already covered precisely
    # these 650 target rows under the frozen source evidence index.
    assert hashlib.sha256(json.dumps(rows, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest() == (
        "46e7c77c7269afacca1e5af2bef5c9d0c5d5bd61c3071d0c15ca5a5cdf8cca76")
    prefix = {
        "session_id": "session", "attempt_id": "attempt", "sequence": 10,
        "observation_time_s": 1., "first_target_delay_s": .1,
        "target_interval_s": .002,
        "target_times_s": [1.1 + .002 * (index + 1) for index in range(650)],
        "positions": rows,
    }
    snapshot = {"phase": "FINAL", "holding_state": "HOLDING",
                "model_sha256": MODEL_SHA,
                "controller_start_positions": segments[-2][1][-1],
                "cup_in_gripper_transform": bound["anchors"]["forward"]["cup_in_gripper_transform"]}
    assert validate_held_cup_transfer_prefix(
        prefix, profile=bound, anchor="forward", segment_index=10,
        held_q_rad=held, snapshot=snapshot,
    )["positions"] == tuple(tuple(row) for row in rows)
    with pytest.raises(ContractError, match="PREFIX_SAMPLE_BUDGET"):
        validate_action_prefix(prefix)
    for key, value in (
        ("sequence", 9), ("target_times_s", prefix["target_times_s"][:-1] + [2.5]),
        ("positions", rows[:-1] + [[0.] * 6]),
    ):
        changed = copy.deepcopy(prefix)
        changed[key] = value
        with pytest.raises(ValueError, match="TRANSFER_PREFIX_BINDING_INVALID"):
            validate_held_cup_transfer_prefix(
                changed, profile=bound, anchor="forward", segment_index=10,
                held_q_rad=held, snapshot=snapshot,
            )
    for anchor, segment in (("left", 10), ("forward", 9)):
        with pytest.raises(ValueError, match="TRANSFER_PREFIX_BINDING_INVALID"):
            validate_held_cup_transfer_prefix(
                prefix, profile=bound, anchor=anchor, segment_index=segment,
                held_q_rad=held, snapshot=snapshot,
            )
    with pytest.raises(ValueError, match="TRANSFER_PREFIX_BINDING_INVALID"):
        validate_held_cup_transfer_prefix(
            prefix, profile=bound, anchor="forward", segment_index=10,
            held_q_rad=held, snapshot=dict(snapshot, holding_state="EMPTY"),
        )
    with pytest.raises(ValueError, match="TRANSFER_PREFIX_BINDING_INVALID"):
        validate_held_cup_transfer_prefix(
            prefix, profile=bound, anchor="forward", segment_index=10,
            held_q_rad=held, snapshot=dict(snapshot,
                                            controller_start_positions=held),
        )
    changed_transform = copy.deepcopy(snapshot["cup_in_gripper_transform"])
    changed_transform[0][3] += .001
    with pytest.raises(ValueError, match="TRANSFER_PREFIX_BINDING_INVALID"):
        validate_held_cup_transfer_prefix(
            prefix, profile=bound, anchor="forward", segment_index=10,
            held_q_rad=held, snapshot=dict(snapshot,
                                            cup_in_gripper_transform=changed_transform),
        )
    calls = []
    authority = PermitAuthority(
        snapshot_port=lambda: calls.append("snapshot"),
        check_port=lambda *_: calls.append("checker"),
        generation_port=lambda: calls.append("generation"),
        ttl_s=.1,
    )
    with pytest.raises(ContractError, match="PREFIX_SAMPLE_BUDGET"):
        authority.approve(prefix)
    assert calls == []

    class Port:
        def send(self, _goal):
            calls.append("controller")
            raise AssertionError("controller reached")

    class Permit:
        def require(self, _permit, _prefix):
            calls.append("permit")
            raise AssertionError("permit reached")

    adapter = ActExecutionAdapter(
        Port(), Port(), permit_port=Permit(), sim_clock=lambda: 1.,
        monotonic=lambda: 1., progress=lambda: None, submit_lead_s=.03,
        accept_timeout_s=.02, stop_timeout_s=.03,
        reference_port=lambda _time: (0.,) * 6,
    )
    adapter.begin_attempt("session", "attempt")
    with pytest.raises(ContractError, match="PREFIX_SAMPLE_BUDGET"):
        adapter.submit(prefix, {})
    assert calls == []


@pytest.mark.parametrize("anchor,segment_index", [("default", 0), ("left", 10)])
def test_other_anchor_prefixes_keep_generic_budget(anchor, segment_index):
    bound = profile()
    held = bound["anchors"][anchor]["held_q_rad"]
    segments = build_held_cup_transfer_schedule(bound, anchor, held_q_rad=held)
    phase, rows = segments[segment_index]
    prefix = {
        "session_id": "session", "attempt_id": "attempt",
        "sequence": segment_index, "observation_time_s": 1.,
        "first_target_delay_s": .1, "target_interval_s": .002,
        "target_times_s": [1.1 + .002 * (index + 1)
                           for index in range(len(rows))],
        "positions": rows,
    }
    snapshot = {
        "phase": "TRANSPORT" if phase == "TRANSPORT" else "FINAL",
        "holding_state": "HOLDING", "model_sha256": MODEL_SHA,
        "controller_start_positions": (
            held if segment_index == 0 else segments[segment_index - 1][1][-1]),
        "cup_in_gripper_transform": bound["anchors"][anchor]["cup_in_gripper_transform"],
    }
    assert validate_held_cup_transfer_prefix(
        prefix, profile=bound, anchor=anchor, segment_index=segment_index,
        held_q_rad=held, snapshot=snapshot,
    )["positions"] == tuple(tuple(row) for row in rows)
    assert len(validate_action_prefix(prefix)["positions"]) == len(rows)


def test_schedule_rejects_profile_and_evidence_mutations(tmp_path):
    bound = profile()
    index = json.loads((CONFIG / "held_cup_transfer_evidence_v3.json").read_bytes())
    forward = {entry["path"]: entry["sha256"]
               for entry in index["anchors"]["forward"]}
    assert forward[
        "experiments/exp453-forward-settling-contract/static-full-checker-v2-result.json"
    ] == "adfd52a53327e74d589fa5cf8912e9ff7bb8c2407a88ba22cde55899fcf853bc"
    assert forward[
        "experiments/exp453-forward-settling-contract/static-full-checker-result.json"
    ] == "fb95bde07a8f5aa72f5eaebae9ab9173a6aea06fb06ef23d4cf319b470060358"
    changed = copy.deepcopy(bound)
    changed["anchors"]["forward"]["final_settling_ticks"] = 49
    with pytest.raises(ValueError, match="TRANSFER_SCHEDULE_BINDING_INVALID"):
        build_held_cup_transfer_schedule(
            changed, "forward", held_q_rad=bound["anchors"]["forward"]["held_q_rad"],
        )
    evidence = (CONFIG / "held_cup_transfer_evidence_v3.json").read_bytes()
    altered = tmp_path / "evidence.json"
    altered.write_bytes(evidence + b" ")
    with pytest.raises(ValueError, match="TRANSFER_SCHEDULE_BINDING_INVALID"):
        load_held_cup_transfer_schedule(
            CONFIG / "held_cup_transfer_v3.json", evidence_index_path=altered,
            expected_model_sha256=MODEL_SHA,
            expected_policy_fingerprint=POLICY_SHA,
        )

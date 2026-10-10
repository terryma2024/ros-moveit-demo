"""Immutable source-only transfer schedule; it does not authorize execution."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .contracts import finite, identifier, integer
from .execution import bounded_positions
from .held_cup_transfer_profile import (
    build_held_cup_transfer_segments, require_held_cup_transfer_profile,
)


_RAW_SHA = "06f13cb86de4798c3eab2c9c896f0bec6b24a82d17c1d3c6e008b1fd050c4b86"
_CONTENT_SHA = "d1b6c1741ea4c039bea09344f615403697e6e2d7b273c2802e4b15a896f94730"
_PARENT_SHA = "e196a112210bc07a35bcc2a56ca37dd06166caf64226626f40132c554e6c2bba"
_EVIDENCE_SHA = "8571c5b59e1981247e0378d4b1d3c5d05a2995701f209f8285825a7e620d44e5"
_MODEL_SHA = "17c415d9541be3c13ce43d8650a0879b5b2d7f62177cca7601500fd94d3d878e"
_POLICY_SHA = "0ba8e07f16e448b16efe7b342745af7181678af47ddf45f975434919774dca11"
_ANCHORS = ("default", "left", "forward")
_PROFILE_EXTRA = frozenset({
    "source_profile_sha256", "source_evidence_index_sha256",
    "first_segment_hold_ticks", "final_stop_proof_ticks", "first_target_delay_s",
})


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def require_held_cup_transfer_schedule(value: object) -> dict:
    """Check the frozen profile and its exact v2 motion parent."""
    try:
        if not isinstance(value, dict) or _sha(_canonical(value)) != _CONTENT_SHA:
            raise ValueError("content")
        if (type(value["schema_version"]) is not int or value["schema_version"] != 2
                or value["kind"] != "HELD_CUP_TRANSFER_SCHEDULE"
                or value["eligible_for_collection"] is not False
                or value["source_profile_sha256"] != _PARENT_SHA
                or value["source_evidence_index_sha256"] != _EVIDENCE_SHA
                or type(value["first_segment_hold_ticks"]) is not int
                or value["first_segment_hold_ticks"] != 100
                or type(value["final_stop_proof_ticks"]) is not int
                or value["final_stop_proof_ticks"] != 100
                or value["first_target_delay_s"] != .1
                or set(value["anchors"]) != set(_ANCHORS)):
            raise ValueError("identity")
        parent = copy.deepcopy(value)
        for key in _PROFILE_EXTRA:
            parent.pop(key)
        parent.update(schema_version=1, kind="HELD_CUP_TRANSFER_PROFILE",
                      hold_after_first_s=.2, hold_after_last_s=.2)
        for anchor in _ANCHORS:
            entry = value["anchors"][anchor]
            if (type(entry["final_settling_ticks"]) is not int
                    or entry["final_settling_ticks"] != (50 if anchor == "forward" else 0)):
                raise ValueError("settling")
            parent["anchors"][anchor].pop("final_settling_ticks")
        require_held_cup_transfer_profile(parent)
        return value
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("TRANSFER_SCHEDULE_BINDING_INVALID") from error


def load_held_cup_transfer_schedule(
    path: Path, *, evidence_index_path: Path,
    expected_model_sha256: str, expected_policy_fingerprint: str,
) -> dict:
    """Read back the exact schedule and its frozen evidence index."""
    try:
        raw = Path(path).read_bytes()
        evidence_raw = Path(evidence_index_path).read_bytes()
        if (_sha(raw) != _RAW_SHA or _sha(evidence_raw) != _EVIDENCE_SHA
                or expected_model_sha256 != _MODEL_SHA
                or expected_policy_fingerprint != _POLICY_SHA):
            raise ValueError("bytes or activation")
        index = json.loads(evidence_raw)
        if (set(index) != {"schema_version", "kind", "evidence_root", "anchors"}
                or type(index["schema_version"]) is not int
                or index["schema_version"] != 1
                or index["kind"] != "HELD_CUP_TRANSFER_SOURCE_EVIDENCE"
                or set(index["anchors"]) != set(_ANCHORS)):
            raise ValueError("evidence schema")
        for anchor in _ANCHORS:
            for item in index["anchors"][anchor]:
                if set(item) != {"path", "sha256"}:
                    raise ValueError("evidence entry")
                relative = Path(item["path"])
                if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                    raise ValueError("evidence path")
        return require_held_cup_transfer_schedule(json.loads(raw))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("TRANSFER_SCHEDULE_BINDING_INVALID") from error


def verify_held_cup_transfer_evidence(index_path: Path) -> int:
    """Read every frozen source artifact when auditing on its evidence host."""
    try:
        raw = Path(index_path).read_bytes()
        if _sha(raw) != _EVIDENCE_SHA:
            raise ValueError("index bytes")
        index = json.loads(raw)
        root = Path(index["evidence_root"])
        count = 0
        verified = {}
        for anchor in _ANCHORS:
            for item in index["anchors"][anchor]:
                relative = Path(item["path"])
                if (relative.is_absolute() or ".." in relative.parts
                        or _sha((root / relative).read_bytes()) != item["sha256"]):
                    raise ValueError("artifact drift")
                verified[item["path"]] = item["sha256"]
                count += 1
        prefix = "experiments/exp453-forward-settling-contract/"
        result_path = prefix + "static-full-checker-v2-result.json"
        audit_path = prefix + "static-full-checker-readback.json"
        if result_path not in verified or audit_path not in verified:
            raise ValueError("corrected static proof missing")
        result = json.loads((root / result_path).read_bytes())
        audit = json.loads((root / audit_path).read_bytes())
        if (result.get("status") != "SOURCE_ONLY_STATIC_PASS"
                or result.get("full_checker_safe") is not True
                or result.get("last_segment_targets") != 650
                or audit.get("status") != "PASS"
                or audit.get("segments") != 11
                or audit.get("added_static_rows") != 50
                or audit.get("result_sha256") != verified[result_path]
                or audit.get("raw_sha256") != verified[prefix + "static-added-holds-v2.ndjson"]
                or audit.get("script_sha256") != verified[prefix + "static_full_checker.py"]
                or audit.get("manifest_sha256") != result.get("manifest_sha256")):
            raise ValueError("corrected static proof mismatch")
        def bound(name: str) -> str:
            return verified["experiments/" + name]
        manifest = json.loads((root / prefix / "candidate-manifest.json").read_bytes())
        combined = json.loads((root / prefix / "forward-combined-readback.json").read_bytes())
        failed = json.loads((root / "experiments/exp450-alternate-v2-endpoints/"
                             "forward-physical-result.json").read_bytes())
        if (failed.get("status") != "FAIL"
                or failed.get("first_failure", {}).get("reason") != "FINAL_HOLD_NOT_STOPPED"
                or manifest.get("extended_final_segment_sha256") !=
                    "46e7c77c7269afacca1e5af2bef5c9d0c5d5bd61c3071d0c15ca5a5cdf8cca76"
                or manifest["inputs"]["raw"]["sha256"] != bound(
                    "exp450-alternate-v2-endpoints/forward-physical-steps.ndjson")
                or manifest["inputs"]["state"]["sha256"] != bound(
                    "exp450-alternate-v2-endpoints/forward-final-integration-state.npy")
                or manifest["inputs"]["settling_contract"]["sha256"] != bound(
                    "exp453-forward-settling-contract/settling_prefix_contract.py")
                or manifest["inputs"]["generator"]["sha256"] != bound(
                    "exp455-transfer-v3-source/frozen-source/held_cup_transfer_profile.py")
                or manifest["inputs"]["physics"]["sha256"] != bound(
                    "exp455-transfer-v3-source/frozen-source/physics.py")
                or manifest["inputs"]["contracts"]["sha256"] != bound(
                    "exp455-transfer-v3-source/frozen-source/contracts.py")
                or combined.get("status") != "VERIFIED_SOURCE_ONLY_CANDIDATE"
                or combined.get("original_raw_sha256") != bound(
                    "exp450-alternate-v2-endpoints/forward-physical-steps.ndjson")
                or combined.get("original_state_sha256") != bound(
                    "exp450-alternate-v2-endpoints/forward-final-integration-state.npy")
                or combined.get("tail_sha256") != bound(
                    "exp453-forward-settling-contract/forward-continuation-tail.ndjson")
                or combined.get("static_readback_sha256") != verified[audit_path]
                or combined.get("manifest_sha256") != verified[prefix + "candidate-manifest.json"]):
            raise ValueError("forward source chain mismatch")
        return count
    except (OSError, TypeError, KeyError, UnicodeDecodeError,
            json.JSONDecodeError, ValueError) as error:
        raise ValueError("TRANSFER_SOURCE_EVIDENCE_INVALID") from error


def build_held_cup_transfer_schedule(
    profile: dict, anchor: str, *, held_q_rad,
) -> list[tuple[str, list[list[float]]]]:
    """Return fixed target rows without a controller or permit interface."""
    require_held_cup_transfer_schedule(profile)
    if anchor not in _ANCHORS:
        raise ValueError("TRANSFER_ANCHOR_INVALID")
    parent = copy.deepcopy(profile)
    for key in _PROFILE_EXTRA:
        parent.pop(key)
    parent.update(schema_version=1, kind="HELD_CUP_TRANSFER_PROFILE",
                  hold_after_first_s=.2, hold_after_last_s=.2)
    for entry in parent["anchors"].values():
        entry.pop("final_settling_ticks")
    segments = build_held_cup_transfer_segments(parent, anchor, held_q_rad=held_q_rad)
    settling = profile["anchors"][anchor]["final_settling_ticks"]
    if settling:
        segments[-1][1].extend([list(segments[-1][1][-1]) for _ in range(settling)])
    return segments


def validate_held_cup_transfer_prefix(
    value: object, *, profile: dict, anchor: str, segment_index: int,
    held_q_rad, snapshot: dict,
) -> dict:
    """Validate a single generated prefix for offline checking only."""
    try:
        segments = build_held_cup_transfer_schedule(
            profile, anchor, held_q_rad=held_q_rad,
        )
        if type(segment_index) is not int or not 0 <= segment_index < len(segments):
            raise ValueError("segment")
        phase = "TRANSPORT" if segments[segment_index][0] == "TRANSPORT" else "FINAL"
        if (not isinstance(snapshot, dict) or snapshot.get("phase") != phase
                or snapshot.get("holding_state") != "HOLDING"
                or snapshot.get("model_sha256") != _MODEL_SHA):
            raise ValueError("snapshot")
        expected_start = (profile["anchors"][anchor]["held_q_rad"]
                          if segment_index == 0 else segments[segment_index - 1][1][-1])
        if (bounded_positions(snapshot.get("controller_start_positions"))
                != tuple(expected_start)):
            raise ValueError("start state")
        observed_transform = snapshot.get("cup_in_gripper_transform")
        expected_transform = profile["anchors"][anchor]["cup_in_gripper_transform"]
        if (len(observed_transform) != 4
                or any(len(row) != 4 for row in observed_transform)
                or any(abs(finite(actual) - expected) > 1e-10
                       for actual_row, expected_row in zip(
                           observed_transform, expected_transform, strict=True)
                       for actual, expected in zip(
                           actual_row, expected_row, strict=True))):
            raise ValueError("attachment transform")
        keys = {"session_id", "attempt_id", "sequence", "observation_time_s",
                "first_target_delay_s", "target_interval_s", "target_times_s",
                "positions"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("fields")
        identifier(value["session_id"])
        identifier(value["attempt_id"])
        if integer(value["sequence"]) != segment_index:
            raise ValueError("sequence")
        origin = finite(value["observation_time_s"], nonnegative=True)
        if (finite(value["first_target_delay_s"]) != .1
                or finite(value["target_interval_s"]) != .002):
            raise ValueError("timing")
        expected = segments[segment_index][1]
        times, positions = value["target_times_s"], value["positions"]
        if (not isinstance(times, (list, tuple)) or len(times) != len(expected)
                or not isinstance(positions, (list, tuple))
                or len(positions) != len(expected)):
            raise ValueError("length")
        checked_times = tuple(finite(t, nonnegative=True) for t in times)
        if any(abs(t - (origin + .1 + .002 * (index + 1))) > 1e-8
               for index, t in enumerate(checked_times)):
            raise ValueError("grid")
        checked_rows = tuple(bounded_positions(row) for row in positions)
        if any(tuple(expected_row) != row for expected_row, row in
               zip(expected, checked_rows, strict=True)):
            raise ValueError("targets")
        return dict(value, target_times_s=checked_times, positions=checked_rows)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("TRANSFER_PREFIX_BINDING_INVALID") from error

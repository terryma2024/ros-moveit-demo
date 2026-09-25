"""Project one isolated, stopped ROS/MuJoCo run into a calibration sample.

The complete physics stream and command receipts stay in the run root. This
module only selects a small lossless window after validating the whole run.
It has no controller authority and never reads a candidate contact policy.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import yaml

from so101_demo.act.contact_calibration import (
    _FRAME_KEYS, _canonical, _validated_sample,
)
from so101_demo.act.contact_diagnostic import (
    prefix_matches_diagnostic, require_contact_diagnostic_sources,
)

WINDOW_LENGTHS = {
    "no_contact": 6, "bilateral_touch": 2, "over_compression": 6,
    "micro_lift_slip": 6, "stable_hold": 11, "table_only": 6,
    "post_release": 6, "left_only": 2, "right_only": 4,
}


def live_collector_sha256() -> str:
    """Bind conversion, orchestration and the runtime safety boundary together."""

    from so101_demo.act import contact_diagnostic, contact_live, contact_live_session
    from so101_demo.adapters.act import (
        broker_execution, calibration_motion, command_broker, ros_broker,
    )
    from so101_demo.cli import act_collect_contact_calibration
    from so101_demo.runtime import launch_composition

    sources = {
        "contact_live_calibration.py": Path(__file__),
        "contact_live_session.py": Path(contact_live_session.__file__),
        "contact_diagnostic.py": Path(contact_diagnostic.__file__),
        "contact_live.py": Path(contact_live.__file__),
        "broker_execution.py": Path(broker_execution.__file__),
        "calibration_motion.py": Path(calibration_motion.__file__),
        "command_broker.py": Path(command_broker.__file__),
        "ros_broker.py": Path(ros_broker.__file__),
        "launch_composition.py": Path(launch_composition.__file__),
        "act_collect_contact_calibration.py": Path(act_collect_contact_calibration.__file__),
    }
    runner = Path(contact_live_session.__file__).parent / "live_calibration_runner"
    for name in contact_live_session.RUNNER_NAMES:
        sources[f"live_calibration_runner/{name}"] = runner / name
    digests = {name: hashlib.sha256(path.read_bytes()).hexdigest()
               for name, path in sorted(sources.items())}
    return hashlib.sha256(_canonical(digests)).hexdigest()


def _force(frame: dict) -> float:
    return sum(item["normal_force_n"] for key in (
        "left_contacts", "right_contacts", "other_contacts") for item in frame[key])


def _speed(frame: dict) -> float:
    return math.sqrt(sum(value * value for value in frame["cup_velocity_m_s"]))


def _qualifies(frame: dict, regime: str) -> bool:
    left, right = bool(frame["left_contacts"]), bool(frame["right_contacts"])
    table = frame["table_supported"]
    if regime in {"no_contact", "table_only"}:
        return table and not left and not right and _speed(frame) < .0001
    if regime == "bilateral_touch":
        return left and right and table
    if regime == "over_compression":
        return left and right and not table and _force(frame) >= 2.0
    if regime == "micro_lift_slip":
        return left and right and not table and _speed(frame) >= .005
    if regime == "stable_hold":
        return left and right and not table and _speed(frame) < .0001
    if regime == "post_release":
        return frame["released"] and table and not left and not right
    if regime == "left_only":
        return left and not right
    if regime == "right_only":
        return right and not left and table
    raise ValueError("unknown live calibration regime")


def select_live_window(frames: list[dict], regime: str) -> list[dict]:
    """Choose a deterministic contiguous window using independent diagnostics."""

    if regime not in WINDOW_LENGTHS:
        raise ValueError("unknown live calibration regime")
    length = WINDOW_LENGTHS[regime]
    candidates = []
    for index in range(len(frames) - length + 1):
        window = frames[index:index + length]
        if (all(_qualifies(row, regime) for row in window) and
                all(b["physics_step"] == a["physics_step"] + 1
                    for a, b in zip(window, window[1:]))):
            candidates.append(window)
    if not candidates:
        raise ValueError(f"live regime {regime} has no qualifying physical window")
    if regime == "over_compression":
        return max(candidates, key=lambda window: min(_force(row) for row in window))
    if regime == "micro_lift_slip":
        return max(candidates, key=lambda window: max(_speed(row) for row in window))
    if regime == "stable_hold":
        return min(candidates, key=lambda window: max(_speed(row) for row in window))
    return candidates[0]


def select_session_window(frames: list[dict], regime: str, *,
                          first_motion_time: float, final_pause_step: int) -> list[dict]:
    """Keep the measured reset transient for the initial unilateral control."""

    if regime == "left_only":
        initial = frames[:WINDOW_LENGTHS[regime]]
        if (final_pause_step < WINDOW_LENGTHS[regime] or
                [row["physics_step"] for row in initial] != [1, 2] or
                not all(_qualifies(row, regime) for row in initial)):
            raise ValueError("live left-only initial reset contact is missing")
        return select_live_window(initial, regime)
    return select_live_window(
        [row for row in frames if row["simulation_time_s"] >= first_motion_time], regime)


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"live evidence file is missing or linked: {path.name}")
    return json.loads(path.read_bytes())


def _verify_execution(run: Path, manifest: dict) -> tuple[dict, int, dict, float]:
    reset = _read_json(run / "reset-result.json")
    receipt = reset["receipt"]
    if (reset.get("success") is not True or receipt["old_epoch"] != 0 or
            receipt["new_epoch"] != 1 or receipt["simulation_step"] != 0 or
            receipt["simulation_session_id"] != manifest["session_id"] or
            reset["status"][-1]["stop_confirmed"] is not True):
        raise ValueError("live reset or stop proof is invalid")
    pause = reset.get("final_pause")
    if (not isinstance(pause, dict) or pause.get("paused") is not True or
            pause.get("simulation_session_id") != manifest["session_id"] or
            pause.get("reset_epoch") != receipt["new_epoch"] or
            type(pause.get("physics_step")) is not int or pause["physics_step"] <= 0 or
            any(not isinstance(pause.get(key), (int, float)) or
                not math.isfinite(pause[key]) or pause[key] < 0.
                for key in ("simulation_time_s", "received_monotonic_s"))):
        raise ValueError("live final reset pause proof is invalid")
    result = _read_json(run / "prefix-result.json")
    if (result.get("success") is not True or result.get("final_stop") is not True or
            result.get("manifest_sha256") != manifest["manifest_sha256"] or
            result.get("session_id") != manifest["session_id"]):
        raise ValueError("live paired route did not complete and stop")
    resume_start = result.get("resume_request_monotonic_s")
    if (not isinstance(resume_start, (int, float)) or
            not math.isfinite(resume_start) or
            resume_start <= pause["received_monotonic_s"]):
        raise ValueError("live resume clock proof is invalid")
    expected_segments = math.ceil(len(manifest["target_positions"]) / manifest["segment_rows"])
    if len(result["segments"]) != expected_segments:
        raise ValueError("live route segment count mismatch")
    for sequence, segment in enumerate(result["segments"]):
        if (segment["sequence"] != sequence or
                not prefix_matches_diagnostic(segment["prefix"], manifest) or
                segment["permit"]["accepted"] is not True or
                segment["submit"]["accepted"] is not True):
            raise ValueError("live source route or permit is invalid")
        terminal = segment["goal_status"][-1]
        if (terminal["status"] != 4 or terminal["action_accepted"] is not True or
                any(item["status"] != 4 or item["result"]["error_code"] != 0
                    for item in terminal["controllers"])):
            raise ValueError("live paired controller result is invalid")
        if len(segment["stop_readbacks"]) < 3 or any(
            item["pair"]["segment_stop_confirmed"] is not True or
            item["broker"]["state"] != "RUNNING" or
            item["broker"]["stop_confirmed"] is not True or
            item["broker"]["hazard_reason"] is not None
            for item in segment["stop_readbacks"][-3:]
        ):
            raise ValueError("live segment physical stop proof is missing")
    broker = _read_json(run / "broker-post-success.json")
    if (broker["state"] != "IDLE" or broker["stop_confirmed"] is not True or
            broker["hazard_reason"] is not None):
        raise ValueError("live broker final stop proof is invalid")
    readbacks = _read_json(run / "broker-post-success-readbacks.json")
    if (not isinstance(readbacks, list) or len(readbacks) < 3 or
            any(item["state"] != "IDLE" or item["stop_confirmed"] is not True or
                item["hazard_reason"] is not None for item in readbacks[-3:])):
        raise ValueError("live broker final three-read stop proof is invalid")
    rejection_path = run / "ipc/contact-diagnostic-guard-rejections.jsonl"
    if rejection_path.is_symlink() or rejection_path.read_bytes():
        raise ValueError("live guard has a rejection")
    plugin_sha = (run / "plugin-sha256.txt").read_text().strip()
    from so101_demo.act.contact_live_session import EVIDENCE_PLUGIN_SHA256
    if plugin_sha != EVIDENCE_PLUGIN_SHA256:
        raise ValueError("live mapped evidence plugin provenance mismatch")
    if pause["simulation_time_s"] >= result["segments"][0]["clock"]["sim_time_s"]:
        raise ValueError("live final reset pause overlaps the first motion")
    return result, receipt["new_epoch"], pause, resume_start


def _read_physics(run: Path, manifest: dict, epoch: int,
                  pause: dict, resume_start: float) -> list[dict]:
    path = run / "ipc/contact-live-physics.ndjson"
    if path.is_symlink() or not path.is_file():
        raise ValueError("live physics evidence is missing or linked")
    limits = manifest["diagnostic_limits"]
    plugin = yaml.safe_load(Path(manifest["plugin_path"]).read_bytes())
    chunk_size = plugin["/**"]["ros__parameters"]["physics_step_chunk_size"]
    if type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("live physics chunk size is invalid")
    frames = []
    initial = None
    previous = None
    pause_row_seen = False
    approved_pause_gap = False
    pause_gap_first_receipt = None
    pause_gap_previous_step = None
    pause_row_receipt = None
    for line in path.open("rb"):
        row = json.loads(line)
        if ((row["simulation_session_id"], row["reset_epoch"], row["model_sha256"]) !=
                (manifest["session_id"], epoch, manifest["model_sha256"])):
            raise ValueError("live physics identity mismatch")
        if previous is None:
            if row["physics_step"] != 1:
                raise ValueError("live physics first step is missing")
            initial = row["cup_position_m"]
        else:
            if (row["physics_step"] != previous["physics_step"] + 1 or
                    row["simulation_time_s"] <= previous["simulation_time_s"] or
                    row["received_monotonic_s"] <= previous["received_monotonic_s"]):
                raise ValueError("live physics stream has a gap or stale step")
            wall_gap = row["received_monotonic_s"] - previous["received_monotonic_s"]
            if wall_gap > limits["maximum_receipt_age_s"]:
                reset_pause_gap = (
                    not approved_pause_gap and
                    previous["physics_step"] <= pause["physics_step"] and
                    # The recorder can receive the last pre-pause steps only
                    # after resume because the plugin publishes whole chunks.
                    pause["physics_step"] - previous["physics_step"] <= chunk_size and
                    previous["simulation_time_s"] <= pause["simulation_time_s"] + .002 and
                    previous["received_monotonic_s"] <= pause["received_monotonic_s"] + .02 and
                    pause["received_monotonic_s"] < resume_start <= row["received_monotonic_s"]
                )
                if not reset_pause_gap:
                    raise ValueError("live physics receipt exceeded the hard deadline")
                approved_pause_gap = True
                pause_gap_first_receipt = row["received_monotonic_s"]
                pause_gap_previous_step = previous["physics_step"]
        if (abs(row["ros_time_s"] - row["simulation_time_s"]) > limits["maximum_ros_skew_s"] or
                math.dist(row["cup_position_m"], initial) > limits["maximum_displacement_m"] or
                _force(row) > limits["maximum_force_n"]):
            raise ValueError("live physics hard limit exceeded")
        frames.append(row)
        if row["physics_step"] == pause["physics_step"]:
            if abs(row["simulation_time_s"] - pause["simulation_time_s"]) > .002:
                raise ValueError("live reset pause step has mismatched simulation time")
            pause_row_seen = True
            pause_row_receipt = row["received_monotonic_s"]
        previous = row
    if len(frames) < 51 or not pause_row_seen:
        raise ValueError("live physics stream is incomplete")
    if (approved_pause_gap and pause_gap_previous_step < pause["physics_step"] and
            not (pause_gap_first_receipt <= pause_row_receipt <= pause_gap_first_receipt + .02)):
        raise ValueError("live reset pause step was not delivered with the resumed chunk")
    return frames


def build_live_sample(
    run_root: Path, *, regime: str, seed: int, sample_id: str, metadata: dict,
) -> dict:
    """Read a complete stopped run, validate its raw stream, and select one sample."""

    run = Path(run_root)
    manifest = require_contact_diagnostic_sources(_read_json(run / "contact-manifest.json"))
    if (regime not in WINDOW_LENGTHS or type(seed) is not int or seed < 0 or
            not sample_id or manifest["regime"] != regime or manifest["seed"] != seed):
        raise ValueError("live sample identity does not match source route")
    collector_sha = live_collector_sha256()
    if (metadata["live_collector_sha256"] != collector_sha or
            manifest["model_sha256"] != metadata["model_sha256"] or
            manifest["scene_sha256"] != metadata["scene_sha256"] or
            manifest["motion_policy_sha256"] != metadata["motion_policy_sha256"] or
            manifest["diagnostic_limits"] != metadata["diagnostic_limits"]):
        raise ValueError("live collector or model provenance mismatch")
    result, epoch, pause, resume_start = _verify_execution(run, manifest)
    frames = _read_physics(run, manifest, epoch, pause, resume_start)
    first_motion_time = result["segments"][0]["clock"]["sim_time_s"]
    window = select_session_window(
        frames, regime, first_motion_time=first_motion_time,
        final_pause_step=pause["physics_step"])
    projected = [{key: row[key] for key in _FRAME_KEYS} for row in window]
    policy = yaml.safe_load(Path(manifest["motion_policy_path"]).read_bytes())
    close = -.049 if regime == "over_compression" else float(
        policy["gripper_actions"]["grasp_close_q6"])
    scenario = {
        "regime": regime, "seed": seed, "cup_start_m": manifest["cup_start_m"],
        "gripper_close_q6": close,
        "window_first_step": projected[0]["physics_step"],
        "window_last_step": projected[-1]["physics_step"],
    }
    peak_force = max(_force(row) for row in projected)
    peak_displacement = max(math.dist(row["cup_position_m"], projected[0]["cup_position_m"])
                            for row in projected)
    sample = {
        "sample_id": sample_id, "source": "live", "regime": regime,
        "simulation_session_id": manifest["session_id"], "reset_epoch": epoch,
        "scenario": scenario,
        "scenario_sha256": hashlib.sha256(_canonical(scenario)).hexdigest(),
        "frames": projected,
        "collected_monotonic_s": projected[-1]["received_monotonic_s"],
        "model_sha256": manifest["model_sha256"],
        "scene_sha256": manifest["scene_sha256"],
        "motion_policy_sha256": manifest["motion_policy_sha256"],
        "collector_sha256": collector_sha,
        "config_sha256": metadata["config_sha256"],
        "clock_origin": "ros_clock",
        "diagnostic_result": {"status": "PASS", "peak_force_n": peak_force,
                              "peak_displacement_m": peak_displacement},
    }
    _validated_sample(sample, "live", metadata["diagnostic_limits"], metadata)
    return sample

"""Live calibration window selection from retained physical evidence."""

import json
from pathlib import Path

import pytest

from so101_demo.act.contact_live_calibration import (
    build_live_sample, live_collector_sha256, select_live_window,
)


def _frame(step, *, left=False, right=False, table=False, released=False,
           force=.5, speed=0.):
    contact = lambda side: [{"robot_geom": side, "object_body": "plastic_cup",
                             "normal_force_n": force, "signed_distance_m": -.0001}]
    return {
        "physics_step": step,
        "left_contacts": contact("left_pad") if left else [],
        "right_contacts": contact("right_pad") if right else [],
        "other_contacts": contact("table_collision") if table else [],
        "table_supported": table, "released": released,
        "cup_velocity_m_s": [speed, 0., 0.],
    }


def test_live_table_bilateral_window_is_kept_even_when_cup_speed_is_high():
    frames = [_frame(1, table=True),
              _frame(2, left=True, right=True, table=True, speed=.014),
              _frame(3, left=True, right=True, table=True, speed=.015),
              _frame(4, left=True, right=True, speed=.01)]
    chosen = select_live_window(frames, "bilateral_touch")
    assert [row["physics_step"] for row in chosen] == [2, 3]


def test_live_over_compression_selects_strongest_safe_contiguous_window():
    frames = [_frame(i, left=True, right=True, force=2.1) for i in range(1, 7)]
    frames += [_frame(i, left=True, right=True, force=4.0) for i in range(7, 13)]
    chosen = select_live_window(frames, "over_compression")
    assert [row["physics_step"] for row in chosen] == list(range(7, 13))


def test_live_release_requires_recorded_release_and_table_without_fingertips():
    frames = [_frame(i, table=True, released=False) for i in range(1, 7)]
    with pytest.raises(ValueError, match="post_release"):
        select_live_window(frames, "post_release")
    frames += [_frame(i, table=True, released=True) for i in range(7, 13)]
    assert [row["physics_step"] for row in select_live_window(frames, "post_release")] == list(range(7, 13))


def test_live_window_rejects_step_gaps_and_wrong_side():
    frames = [_frame(1, left=True), _frame(3, left=True)]
    with pytest.raises(ValueError):
        select_live_window(frames, "left_only")
    frames = [_frame(1, left=True), _frame(2, left=True, right=True)]
    with pytest.raises(ValueError):
        select_live_window(frames, "left_only")


def test_live_sample_requires_completed_pair_stop_and_lossless_physics(tmp_path):
    from so101_demo.act.contact_diagnostic import build_contact_diagnostic_manifest
    from so101_demo.act.contact_live_session import EVIDENCE_PLUGIN_SHA256
    source = Path(__file__).resolve().parents[1]
    manifest = build_contact_diagnostic_manifest(
        scene_path=source / "assets/mujoco/act/scene.xml",
        motion_policy_path=source / "config/policies/light_cup_wall_pick/v1/mujoco.yaml",
        plugin_path=source / "config/mujoco/act/mujoco_plugins.yaml",
        regime="no_contact", seed=0, session_id="live-unit-a", attempt_id="live-unit-attempt",
    )
    run = tmp_path / "run"
    (run / "ipc").mkdir(parents=True)
    (run / "contact-manifest.json").write_text(json.dumps(manifest))
    (run / "reset-result.json").write_text(json.dumps({
        "success": True, "receipt": {"old_epoch": 0, "new_epoch": 1,
                                      "simulation_step": 0,
                                      "simulation_session_id": manifest["session_id"]},
        "final_pause": {"simulation_session_id": manifest["session_id"],
                        "reset_epoch": 1, "physics_step": 204,
                        "simulation_time_s": .408,
                        "received_monotonic_s": 1000.201, "paused": True},
        "status": [{"stop_confirmed": True}],
    }))
    positions = [manifest["joint_start_rad"]] + manifest["target_positions"]
    prefix = {"session_id": manifest["session_id"], "attempt_id": manifest["attempt_id"],
              "sequence": 0, "observation_time_s": .45,
              "target_times_s": [.45 + .1 * (i + 1) for i in range(len(positions))],
              "positions": positions}
    stop = {"pair": {"segment_stop_confirmed": True},
            "broker": {"state": "RUNNING", "stop_confirmed": True, "hazard_reason": None}}
    result = {"success": True, "final_stop": True,
              "manifest_sha256": manifest["manifest_sha256"],
              "session_id": manifest["session_id"],
              "resume_request_monotonic_s": 1001.5,
              "segments": [{"sequence": 0, "prefix": prefix,
                            "permit": {"accepted": True}, "submit": {"accepted": True},
                            "clock": {"sim_time_s": .45},
                            "goal_status": [{"status": 4, "action_accepted": True,
                                             "controllers": [{"status": 4, "result": {"error_code": 0}}] * 2}],
                            "stop_readbacks": [stop] * 3}]}
    (run / "prefix-result.json").write_text(json.dumps(result))
    (run / "broker-post-success.json").write_text(json.dumps(
        {"state": "IDLE", "stop_confirmed": True, "hazard_reason": None}))
    (run / "plugin-sha256.txt").write_text(EVIDENCE_PLUGIN_SHA256 + "\n")
    (run / "ipc/contact-diagnostic-guard-rejections.jsonl").write_text("")
    rows = []
    for step in range(1, 252):
        rows.append({"simulation_session_id": manifest["session_id"], "reset_epoch": 1,
                     "model_sha256": manifest["model_sha256"], "physics_step": step,
                     "simulation_time_s": step * .002, "ros_time_s": step * .002,
                     "received_monotonic_s": 1000. + step * .001 + (2. if step > 200 else 0.),
                     "left_contacts": [], "right_contacts": [],
                     "other_contacts": [{"robot_geom": "table_collision",
                                         "object_body": "plastic_cup", "normal_force_n": .1,
                                         "signed_distance_m": -.0001}],
                     "cup_position_m": manifest["cup_start_m"],
                     "cup_velocity_m_s": [0., 0., 0.],
                     "model_qpos": manifest["joint_start_rad"] + manifest["cup_start_m"],
                     "model_qvel": [0.] * 9, "table_supported": True,
                     "released": False})
    raw = run / "ipc/contact-live-physics.ndjson"
    raw.write_text("".join(json.dumps(row) + "\n" for row in rows))
    metadata = {"mujoco_version": "3.12.0", "model_sha256": manifest["model_sha256"],
                "scene_sha256": manifest["scene_sha256"],
                "motion_policy_sha256": manifest["motion_policy_sha256"],
                "collector_sha256": "a" * 64,
                "live_collector_sha256": live_collector_sha256(),
                "analyzer_sha256": "b" * 64, "config_sha256": "c" * 64,
                "evaluation": {"maximum_observation_age_s": .1,
                               "minimum_consecutive_samples": 5},
                "diagnostic_limits": manifest["diagnostic_limits"],
                "policy_id": "test", "allowed_other_contact_bodies": ["table_collision"]}
    sample = build_live_sample(
        run, regime="no_contact", seed=0, sample_id="live-no_contact-000", metadata=metadata)
    assert sample["source"] == "live" and len(sample["frames"]) == 6
    reset = json.loads((run / "reset-result.json").read_text())
    reset["final_pause"]["physics_step"] = 199
    (run / "reset-result.json").write_text(json.dumps(reset))
    with pytest.raises(ValueError, match="reset pause step|receipt exceeded"):
        build_live_sample(
            run, regime="no_contact", seed=0, sample_id="live-no_contact-000", metadata=metadata)
    reset["final_pause"]["physics_step"] = 204
    (run / "reset-result.json").write_text(json.dumps(reset))
    rows[30]["physics_step"] += 1
    raw.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="gap"):
        build_live_sample(
            run, regime="no_contact", seed=0, sample_id="live-no_contact-000", metadata=metadata)


def test_live_process_inventory_reads_only_current_user_processes(tmp_path, monkeypatch):
    import os
    from so101_demo.act import contact_live_session
    process = tmp_path / "12345"
    process.mkdir()
    (process / "environ").write_bytes(b"ROS_DOMAIN_ID=208\0")
    (process / "cmdline").write_bytes(b"python3\0worker\0")
    uid = os.getuid()
    monkeypatch.setattr(contact_live_session.os, "getuid", lambda: uid + 1)
    assert contact_live_session._task_processes(208, proc_root=tmp_path) == []
    monkeypatch.setattr(contact_live_session.os, "getuid", lambda: uid)
    assert contact_live_session._task_processes(208, proc_root=tmp_path) == [
        (12345, "python3 worker ")]


def test_live_process_inventory_skips_known_inaccessible_daemon_but_fails_on_unknown(tmp_path, monkeypatch):
    from so101_demo.act import contact_live_session
    process = tmp_path / "12345"
    process.mkdir()
    (process / "environ").write_bytes(b"")
    (process / "cmdline").write_bytes(b"/usr/lib/systemd/systemd\0--user\0")
    (process / "status").write_text("Name:\tsystemd\nState:\tS (sleeping)\n")
    original = Path.read_bytes

    def denied(path):
        if path == process / "environ":
            raise PermissionError("host denies unrelated daemon environ")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", denied)
    assert contact_live_session._task_processes(208, proc_root=tmp_path) == []
    (process / "cmdline").write_bytes(b"ros2_control_node\0")
    with pytest.raises(RuntimeError, match="PROC_ENV_UNVERIFIABLE"):
        contact_live_session._task_processes(208, proc_root=tmp_path)

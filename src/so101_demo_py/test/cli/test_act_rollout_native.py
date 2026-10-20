"""The native rollout command: preconditions, owned-root layout, environment, and the sequential run, with fakes only."""

import dataclasses
import json
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act import rollout_scenes as rs
from so101_demo.act.rollout_episode import RolloutSettings
from so101_demo.cli import act_rollout_native as native

SETTINGS = RolloutSettings(execution_deadline_s=3.0, state_unavailable_stop_s=1.0, settle_s=0.5,
                           no_motion_threshold_rad=0.005, stop_wait_s=1.0, ready_wait_s=2.0)
SUBSTITUTION = {"substituted_by": "contact_activation_receipt", "path": "receipt.json", "sha256": "a" * 64,
                "policy_fingerprint": "b" * 64, "ruling": "ruling text"}


def _scene(group, index, x=0.0):
    return {"scene_id": f"rollout-{group.removeprefix('rollout_')}-{index:03d}", "group": group, "index": index,
            "point_id": None, "xy": [x, -0.3], "cup_position_world_m": [x, -0.3, 0.165], "seed": 576010,
            "nearest_training_m": 0.004, "inside_triangle": True, "reachability": True}


def _scenes(group="rollout_validation", count=3):
    return rs.build_scene_document({group: [_scene(group, index + 1, -0.01 * index) for index in range(count)]},
                                   parameters={})


def _inputs(group="rollout_validation", count=3):
    return native.RolloutInputs(
        settings=SETTINGS, snapshot_targets={"kind": "targets"}, endpoint_policy={"policy_sha256": "c" * 64},
        timing={"submit_lead_s": 0.03}, rollout_config={"camera_topics": {}},
        observation={"cameras": ("head", "wrist"), "state_dim": 8, "source": "bundle"},
        scenes=_scenes(group, count), substitution=SUBSTITUTION,
        identity={"bundle_sha256": "1" * 64, "policy_sha256": "2" * 64, "inputs_manifest_sha256": "3" * 64,
                  "runtime_yaml_sha256": "4" * 64, "snapshot_sha256": "5" * 64, "source_commit": "abc123",
                  "gate_install": "/opt/gate-install"})


def _options(tmp_path, **changes):
    values = dict(evidence_root=tmp_path / "evidence", run_id="run-1", group="rollout_validation", scene_ids=None,
                  limit=None, max_invalid_retries=1, gpu_uuid="GPU-00000000-0000-0000-0000-000000000000",
                  install_prefix=Path("/opt/gate-install"), stack_timeout_s=60.0)
    values.update(changes)
    Path(values["evidence_root"]).mkdir(exist_ok=True)
    return SimpleNamespace(**values)


def _passing_probes(calls=None):
    calls = [] if calls is None else calls
    return {name: (lambda name=name: calls.append(name) or (True, {"checked": name})) for name in native.PRECONDITIONS}


# ---- preconditions (D5) --------------------------------------------------------------------------------------------------


def test_every_precondition_is_checked_and_recorded_in_order():
    calls = []
    evidence = native.check_preconditions(_passing_probes(calls))
    assert calls == list(native.PRECONDITIONS)
    assert [evidence[name]["ok"] for name in native.PRECONDITIONS] == [True] * 5
    assert evidence["no_gpu_process"]["detail"] == {"checked": "no_gpu_process"}


@pytest.mark.parametrize("name", native.PRECONDITIONS)
def test_a_failed_precondition_refuses_and_names_the_rule(name):
    probes = _passing_probes()
    probes[name] = lambda: (False, "something is there")
    with pytest.raises(native.PreconditionRefused, match=f"ROLLOUT_PRECONDITION_FAILED: {name}: something is there"):
        native.check_preconditions(probes)


@pytest.mark.parametrize("name", native.PRECONDITIONS)
def test_a_precondition_that_cannot_be_proven_is_a_refusal_too(name):
    probes = _passing_probes()

    def broken():
        raise OSError("permission denied on the docker socket")

    probes[name] = broken
    with pytest.raises(native.PreconditionRefused, match=f"ROLLOUT_PRECONDITION_UNPROVEN: {name}: .*docker socket"):
        native.check_preconditions(probes)


def test_a_missing_probe_is_a_refusal_not_a_skipped_rule():
    probes = _passing_probes()
    del probes["ros_graph_empty"]
    with pytest.raises(native.PreconditionRefused, match="ROLLOUT_PRECONDITION_UNPROVEN: ros_graph_empty"):
        native.check_preconditions(probes)


def test_the_gpu_probe_refuses_any_compute_process_and_the_container_probe_any_running_container():
    ran = []

    def run(argv, **kwargs):
        ran.append(argv[0])
        outputs = {"nvidia-smi": "1234, python\n", "docker": "act-shard-w00\n"}
        return SimpleNamespace(returncode=0, stdout=outputs[argv[0]], stderr="")

    assert native.gpu_probe(run=run) == (False, ["1234, python"])
    assert native.container_probe(run=run) == (False, ["act-shard-w00"])
    quiet = lambda argv, **kwargs: SimpleNamespace(returncode=0, stdout="\n", stderr="")      # noqa: E731
    assert native.gpu_probe(run=quiet) == (True, [])
    assert native.container_probe(run=quiet) == (True, [])
    failing = lambda argv, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="Cannot connect")      # noqa: E731
    with pytest.raises(RuntimeError, match="Cannot connect"):
        native.container_probe(run=failing)


def test_the_instance_process_probe_finds_the_marker_in_any_readable_environment(tmp_path):
    proc = tmp_path / "proc"
    for pid, environ in (("100", b"PATH=/bin\x00"), ("200", b"X=1\x00SO101_ACT_INSTANCE_ROOT=/old/root\x00"),
                         ("300", b"SO101_ACT_INSTANCE_ROOT=/mine\x00")):
        (proc / pid).mkdir(parents=True)
        (proc / pid / "environ").write_bytes(environ)
        (proc / pid / "stat").write_text(f"{pid} (x) S 1 1 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 0\n")
    (proc / "self").mkdir()
    ok, found = native.instance_process_probe(proc=proc, own_pid=300)
    assert ok is False and found == [{"pid": 200, "root": "/old/root"}]
    (proc / "200" / "environ").write_bytes(b"X=1\x00")
    assert native.instance_process_probe(proc=proc, own_pid=300) == (True, [])


def test_the_unified_store_probe_needs_an_idle_store_without_leases(tmp_path):
    import sqlite3

    root = tmp_path / "unified"
    root.mkdir()
    database = root / "intents.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        "CREATE TABLE global_state (singleton INTEGER PRIMARY KEY, state TEXT NOT NULL);"
        "CREATE TABLE gpu_workload_leases (lease_id TEXT);"
        "CREATE TABLE act_worker_slots (campaign_id TEXT, active INTEGER);"
        "INSERT INTO global_state VALUES (1, 'IDLE');")
    connection.commit()
    assert native.unified_store_probe(root) == (True, {"state": "IDLE", "gpu_leases": 0, "active_slots": 0})
    connection.execute("INSERT INTO gpu_workload_leases VALUES ('lease-1')")
    connection.commit()
    assert native.unified_store_probe(root)[0] is False
    connection.execute("DELETE FROM gpu_workload_leases")
    connection.execute("UPDATE global_state SET state = 'TASK_ACTIVE'")
    connection.commit()
    ok, detail = native.unified_store_probe(root)
    assert ok is False and detail["state"] == "TASK_ACTIVE"
    connection.close()
    with pytest.raises(RuntimeError, match="UNIFIED_STORE_UNAVAILABLE"):
        native.unified_store_probe(tmp_path / "absent")


# ---- layout and environment ----------------------------------------------------------------------------------------------


def test_the_owned_root_layout_is_private_and_never_reused(tmp_path):
    (tmp_path / "evidence").mkdir()
    layout = native.prepare_layout(tmp_path / "evidence", "run-1")
    assert layout.owned_root == tmp_path / "evidence" / "owned" / "run-1"
    for name in ("output_root", "control_root", "stack_root", "tmp_root", "ros_log_root"):
        directory = getattr(layout, name)
        assert directory.is_dir() and directory.is_relative_to(layout.owned_root)
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert layout.output_root == layout.owned_root / "output" and layout.stack_root == layout.owned_root / "stack"
    with pytest.raises(ValueError, match="ROLLOUT_OWNED_ROOT_EXISTS"):
        native.prepare_layout(tmp_path / "evidence", "run-1")
    for evidence_root, run_id in (("relative", "run-2"), (tmp_path / "evidence", "bad/id"), (tmp_path / "absent", "run-3")):
        with pytest.raises(ValueError, match="ROLLOUT_LAYOUT_INVALID"):
            native.prepare_layout(evidence_root, run_id)


def test_the_environment_is_the_fixed_instance_identity_of_the_owned_root(tmp_path):
    (tmp_path / "evidence").mkdir()
    layout = native.prepare_layout(tmp_path / "evidence", "run-1")
    base = {"PATH": "/usr/bin", "DISPLAY": ":0", "ROS_DOMAIN_ID": "7", "ROS_NAMESPACE": "/x", "CUDA_VISIBLE_DEVICES": "0"}
    environment = native.native_environment(base, layout=layout, session_id="sim-1", gpu_uuid="GPU-1",
                                            install_prefix="/opt/gate-install")
    assert environment["ROS_DOMAIN_ID"] == "181" and environment["MUJOCO_GL"] == "egl"
    assert "DISPLAY" not in environment and "ROS_NAMESPACE" not in environment
    assert environment["SO101_ACT_INSTANCE_ROOT"] == str(layout.owned_root)
    assert environment["SO101_ACT_INSTANCE_OUTPUT"] == str(layout.owned_root / "output")
    assert environment["SO101_MUJOCO_SESSION_ID"] == "sim-1" and environment["CUDA_VISIBLE_DEVICES"] == "GPU-1"
    target = {"DISPLAY": ":0", "PATH": "/usr/bin", "ROS_NAMESPACE": "/x"}
    native.apply_environment(target, environment)
    assert target == environment                                      # removed names are removed, set names are set


# ---- the run -------------------------------------------------------------------------------------------------------------


class FakeComposition:
    def __init__(self, tmp_path, *, start_error=None, stop_confirmed=True):
        self.log, self.start_error, self.stop_confirmed = [], start_error, stop_confirmed
        self.closed = 0

    def start(self):
        self.log.append("start")
        if self.start_error:
            raise self.start_error

    def new_ports(self, scene, attempt_id, episode_dir):
        self.log.append(f"ports:{attempt_id}")
        return SimpleNamespace(scene=scene, attempt_id=attempt_id)

    def stop(self):
        self.log.append("stop")
        return {"confirmed": self.stop_confirmed, "graph_clear": self.stop_confirmed, "marker_survivors": []}

    def close(self):
        self.closed += 1
        self.log.append("close")


def _result(scene, attempt_id, verdict="DONE", reason=None):
    done = verdict == "DONE"
    return {"scene_id": scene["scene_id"], "group": scene["group"], "attempt_id": attempt_id, "verdict": verdict,
            "done": done, "reason": reason, "status": "COMPLETED", "phases": ["reset"], "counts": {"applied": 3},
            "motion": {"max_arm_displacement_rad": 0.1}, "stop": {"confirmed": True}, "timing": {"wall_s": 12.5},
            "receipt": {"reset_epoch": 1}, "gate": {"ok": True}, "recorder": {"ready": True},
            "substitutions": {"start_target": "commanded_reset_pose"},
            "endpoint": None if verdict == "INVALID" else {"result": "PASS" if done else "FAIL", "reasons": [],
                                                           "measured": {"final_xy_error_m": 0.01},
                                                           "end_observation": {"position": [0, 0, 0]}},
            "targets": {"start_target": {}, "end_target": {}}, "retire_errors": []}


def _runner(script, log):
    def run(*, scene, attempt_id, ports, settings, snapshot_targets, endpoint_policy, sink=None, execution=None):
        run.executions.append(execution)
        log.append((scene["scene_id"], attempt_id))
        verdict, reason = script.get(attempt_id, ("DONE", None))
        sink.step({"sequence": 0, "applied": True})
        sink.world({"observation_sim_s": 1.0})
        return _result(scene, attempt_id, verdict, reason)
    run.executions = []
    return run


def _run(tmp_path, *, script=None, composition=None, probes=None, inputs=None, environ=None, **option_changes):
    composition = composition or FakeComposition(tmp_path)
    runs = []
    options = _options(tmp_path, **option_changes)
    summary = native.run_rollout(
        options=options, inputs=inputs or _inputs(), probes=probes or _passing_probes(),
        composition_factory=lambda **kwargs: composition, episode_runner=_runner(script or {}, runs),
        environ={} if environ is None else environ)
    return summary, composition, runs, options


def test_a_refused_precondition_creates_nothing_and_starts_nothing(tmp_path):
    probes = _passing_probes()
    probes["no_gpu_process"] = lambda: (False, ["1234, python"])
    composition = FakeComposition(tmp_path)
    created = []
    with pytest.raises(native.PreconditionRefused, match="no_gpu_process"):
        native.run_rollout(options=_options(tmp_path), inputs=_inputs(), probes=probes,
                           composition_factory=lambda **kwargs: created.append(1) or composition,
                           episode_runner=_runner({}, []), environ={})
    assert created == [] and composition.log == []
    assert list((tmp_path / "evidence").iterdir()) == []


def test_episodes_run_one_at_a_time_in_scene_order_and_each_writes_its_evidence(tmp_path):
    summary, composition, runs, options = _run(tmp_path)
    assert summary["exit_code"] == 0 and summary["done"] == 3 and summary["invalid_exhausted"] == []
    assert [scene for scene, _attempt in runs] == ["rollout-validation-001", "rollout-validation-002", "rollout-validation-003"]
    assert composition.log[0] == "start" and composition.log[-2:] == ["stop", "close"]
    group_root = options.evidence_root / "rollout_validation"
    rows = [json.loads(line) for line in (group_root / "act-runs.jsonl").read_text().splitlines()]
    assert [row["scene_id"] for row in rows] == [scene for scene, _attempt in runs]
    assert all(set(row) == {"search_locked", "done", "interventions", "elapsed_wall_s", "scene_id", "evidence"}
               for row in rows)
    assert rows[0]["search_locked"] is True and rows[0]["interventions"] == 0 and rows[0]["elapsed_wall_s"] == 12.5
    episode = group_root / rows[0]["evidence"][0].rsplit("/", 1)[0]
    for name in ("episode.json", "endpoint.json", "steps.jsonl", "world.jsonl", "stop-proof.json"):
        assert (episode / name).is_file()
    document = json.loads((episode / "episode.json").read_text())
    assert document["scene"]["scene_id"] == "rollout-validation-001" and document["group"] == "rollout_validation"
    assert document["calibration"] == SUBSTITUTION                       # the substitution is in every episode record
    assert document["identity"]["bundle_sha256"] == "1" * 64 and document["identity"]["policy_sha256"] == "2" * 64
    assert document["observation"]["cameras"] == ["head", "wrist"] and document["observation"]["state_dim"] == 8
    assert document["verdict"] == "DONE" and document["result"]["counts"] == {"applied": 3}
    assert document["preconditions"]["no_container"]["ok"] is True
    endpoint = json.loads((episode / "endpoint.json").read_text())
    assert endpoint["endpoint"]["result"] == "PASS" and endpoint["stop_receipt"] == {"confirmed": True}
    assert (options.evidence_root / "rollout_validation" / "run.json").is_file()
    stop = json.loads((options.evidence_root / "owned" / "run-1" / "stack-stop-proof.json").read_text())
    assert stop["confirmed"] is True


def test_the_effective_execution_mode_is_passed_to_every_episode_and_recorded_in_run_and_episode_json(tmp_path):
    from so101_demo.act.rollout_execution import resolve_execution

    mode = resolve_execution({"chunk_size": 10, "execution_prefix": 1}, prefix=5)
    inputs = dataclasses.replace(_inputs(), execution=mode)
    composition, runs = FakeComposition(tmp_path), []
    options = _options(tmp_path)
    runner = _runner({}, runs)
    native.run_rollout(options=options, inputs=inputs, probes=_passing_probes(),
                       composition_factory=lambda **kwargs: composition, episode_runner=runner, environ={})
    assert runner.executions == [mode] * 3
    group_root = options.evidence_root / "rollout_validation"
    run = json.loads((group_root / "run.json").read_text())
    assert run["execution"] == mode.document()
    episode = json.loads(next((group_root / "episodes").iterdir()).joinpath("episode.json").read_text())
    assert episode["execution"] == mode.document() and episode["execution"]["execution_prefix"] == 5


def test_the_clamp_tolerance_is_recorded_in_run_and_episode_json_and_clamped_steps_are_summed(tmp_path):
    settings = dataclasses.replace(SETTINGS, joint_limit_clamp_tolerance_rad=0.01)
    inputs = dataclasses.replace(_inputs(), settings=settings)
    composition, runs = FakeComposition(tmp_path), []
    options = _options(tmp_path)
    base = _runner({}, runs)

    def runner(**kwargs):
        result = base(**kwargs)
        result["counts"] = {"applied": 3, "clamped_steps": 2}
        return result

    runner.executions = base.executions
    summary = native.run_rollout(options=options, inputs=inputs, probes=_passing_probes(),
                                 composition_factory=lambda **kw: composition, episode_runner=runner, environ={})
    assert summary["clamped_steps"] == 6                                   # 3 episodes x 2
    group_root = options.evidence_root / "rollout_validation"
    run = json.loads((group_root / "run.json").read_text())
    assert run["joint_limit_clamp_tolerance_rad"] == 0.01
    episode = json.loads(next((group_root / "episodes").iterdir()).joinpath("episode.json").read_text())
    assert episode["joint_limit_clamp_tolerance_rad"] == 0.01


def test_without_a_clamp_tolerance_run_and_episode_record_none_and_the_summary_counts_zero(tmp_path):
    summary, _composition, _runs, options = _run(tmp_path)
    assert summary["clamped_steps"] == 0
    group_root = options.evidence_root / "rollout_validation"
    assert json.loads((group_root / "run.json").read_text())["joint_limit_clamp_tolerance_rad"] is None
    episode = json.loads(next((group_root / "episodes").iterdir()).joinpath("episode.json").read_text())
    assert episode["joint_limit_clamp_tolerance_rad"] is None


def test_an_episode_without_a_resolved_mode_records_what_the_episode_reports(tmp_path):
    summary, _composition, _runs, options = _run(tmp_path)
    assert summary["exit_code"] == 0
    run = json.loads((options.evidence_root / "rollout_validation" / "run.json").read_text())
    assert run["execution"] is None


def test_the_environment_is_applied_before_anything_is_composed(tmp_path):
    seen = {}
    composition = FakeComposition(tmp_path)

    def factory(**kwargs):
        seen.update(kwargs["environment"])
        return composition

    environ = {"DISPLAY": ":0"}
    native.run_rollout(options=_options(tmp_path), inputs=_inputs(), probes=_passing_probes(),
                       composition_factory=factory, episode_runner=_runner({}, []), environ=environ)
    assert environ["ROS_DOMAIN_ID"] == "181" and "DISPLAY" not in environ and seen == environ


def test_an_invalid_episode_is_rerun_and_reported_separately(tmp_path):
    summary, _composition, runs, options = _run(tmp_path, script={"rollout-validation-002-a1": ("INVALID", "GATE_FAILED: x")})
    assert [attempt for _scene, attempt in runs] == [
        "rollout-validation-001-a1", "rollout-validation-002-a1", "rollout-validation-002-a2", "rollout-validation-003-a1"]
    assert summary["exit_code"] == 0 and summary["done"] == 3 and summary["invalid_attempts"] == 1
    group_root = options.evidence_root / "rollout_validation"
    invalid = [json.loads(line) for line in (group_root / "invalid-runs.jsonl").read_text().splitlines()]
    assert len(invalid) == 1 and invalid[0]["scene_id"] == "rollout-validation-002" and invalid[0]["reason"] == "GATE_FAILED: x"
    rows = [json.loads(line) for line in (group_root / "act-runs.jsonl").read_text().splitlines()]
    assert len(rows) == 3                                                  # the invalid attempt is not a run row


def test_a_scene_that_stays_invalid_ends_the_run_and_is_not_counted(tmp_path):
    script = {f"rollout-validation-002-a{n}": ("INVALID", "STOP_UNCONFIRMED") for n in (1, 2)}
    summary, composition, runs, options = _run(tmp_path, script=script)
    assert summary["exit_code"] == 1 and summary["invalid_exhausted"] == ["rollout-validation-002"]
    assert [scene for scene, _attempt in runs].count("rollout-validation-003") == 0       # the run stops: the stack is suspect
    rows = (options.evidence_root / "rollout_validation" / "act-runs.jsonl").read_text().splitlines()
    assert len(rows) == 1
    assert composition.log[-2:] == ["stop", "close"]


def test_a_failing_or_no_motion_policy_is_a_run_row_not_an_invalid_attempt(tmp_path):
    script = {"rollout-validation-001-a1": ("FAILED", "FINAL_XY_OUT_OF_TOLERANCE"),
              "rollout-validation-002-a1": ("NO_MOTION", "NO_MOTION")}
    summary, _composition, runs, options = _run(tmp_path, script=script)
    assert len(runs) == 3 and summary["done"] == 1 and summary["verdicts"] == {"DONE": 1, "FAILED": 1, "NO_MOTION": 1}
    rows = [json.loads(line) for line in (options.evidence_root / "rollout_validation" / "act-runs.jsonl").read_text().splitlines()]
    assert [row["done"] for row in rows] == [False, False, True]


def test_an_unproven_stack_stop_fails_the_run_even_when_every_episode_passed(tmp_path):
    summary, composition, _runs, _options_ = _run(tmp_path, composition=FakeComposition(tmp_path, stop_confirmed=False))
    assert summary["exit_code"] == 3 and summary["stack_stop_confirmed"] is False and composition.closed == 1


def test_a_stack_that_does_not_start_runs_no_episode_and_is_still_stopped(tmp_path):
    composition = FakeComposition(tmp_path, start_error=RuntimeError("ACT_STACK_READINESS_UNPROVED"))
    summary, composition, runs, _options_ = _run(tmp_path, composition=composition)
    assert runs == [] and summary["exit_code"] == 4 and "ACT_STACK_READINESS_UNPROVED" in summary["fault"]
    assert composition.log == ["start", "stop", "close"]


def test_scene_selection_by_id_and_limit(tmp_path):
    summary, _composition, runs, _options_ = _run(tmp_path, scene_ids=["rollout-validation-003"])
    assert [scene for scene, _attempt in runs] == ["rollout-validation-003"]
    with pytest.raises(ValueError, match="ROLLOUT_SCENE_UNKNOWN: nope"):
        _run(tmp_path, scene_ids=["nope"], run_id="run-2")
    summary, _composition, runs, _options_ = _run(tmp_path, limit=2, run_id="run-3", evidence_root=tmp_path / "e3")
    assert len(runs) == 2
    with pytest.raises(ValueError, match="ROLLOUT_GROUP_UNKNOWN"):
        _run(tmp_path, group="rollout_test", run_id="run-4", evidence_root=tmp_path / "e4")


def test_the_held_out_test_group_is_opened_once_per_policy(tmp_path):
    inputs = _inputs("rollout_test", 1)
    _run(tmp_path, inputs=inputs, group="rollout_test", run_id="run-1")
    marker = tmp_path / "evidence" / "rollout_test" / ("opened-" + "2" * 12 + ".json")
    assert marker.is_file() and json.loads(marker.read_text())["policy_sha256"] == "2" * 64
    with pytest.raises(ValueError, match="ROLLOUT_TEST_ALREADY_OPENED"):
        _run(tmp_path, inputs=inputs, group="rollout_test", run_id="run-2")


def test_a_second_run_cannot_overwrite_the_run_rows_of_a_group(tmp_path):
    _run(tmp_path)
    with pytest.raises(ValueError, match="ROLLOUT_GROUP_ROOT_EXISTS"):
        _run(tmp_path, run_id="run-2")


def test_the_import_preflight_refuses_when_a_module_is_missing_or_cuda_is_absent():
    seen = []
    modules = {"rclpy": object(), "torch": SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True)),
               "lerobot": object()}

    def importer(name):
        seen.append(name)
        if name not in modules:
            raise ImportError(name)
        return modules[name]

    native.import_preflight(importer=importer)
    assert seen == ["rclpy", "torch", "lerobot"]
    del modules["lerobot"]
    with pytest.raises(RuntimeError, match="ROLLOUT_IMPORT_PREFLIGHT_FAILED: lerobot"):
        native.import_preflight(importer=importer)
    modules["lerobot"] = object()
    modules["torch"] = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    with pytest.raises(RuntimeError, match="ROLLOUT_IMPORT_PREFLIGHT_FAILED: torch.cuda"):
        native.import_preflight(importer=importer)

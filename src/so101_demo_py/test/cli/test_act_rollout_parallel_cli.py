"""The parallel rollout command end to end over doubles: refusals, preconditions, the real policy-service subprocess protocol,
the real owner and coordinator over fake container shards, and the files it leaves.

Real: argument checks, preconditions, run directory and campaign layout, the admitted context, `PolicyServiceOwner` against a child
process that behaves like the service, `RolloutCampaignOwner`, `RolloutCoordinator`, task journals, the receipt, `summary.json` and
`table.md`. Controlled doubles: the frozen inputs loader, the container shards and their task control, and (for one assertion) the
launch registry's independent re-inspection. No Docker, container, ROS, model or GPU is involved.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.act.rollout_shared import RolloutInputs
from so101_demo.cli import act_rollout_parallel as cli
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.act_rollout.owner import EXIT_INVALID, EXIT_OK, EXIT_START_FAILED

from test_act_rollout_owner import Clock, Instance, Launcher, Registry, World
from test_act_rollout_policy_service_owner import BUNDLE, FAKE_SERVICE, POLICY, PYTHONPATH
from test_config_identity import campaign_fixture, write_config
from test_act_rollout_targets import SNAPSHOT_TARGETS
from test_act_rollout_episode import SETTINGS, _endpoint_policy

from paths import PACKAGE_ROOT

GPU = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
SCENES = {"groups": {"rollout_standard": [{"scene_id": "task_start"}, {"scene_id": "forward_5cm"}],
                     "rollout_test": [{"scene_id": "held_out"}]}, "manifest_sha256": "2" * 64}


VARIANT_RECORD = {"name": "dark", "variant": {"name": "dark", "set": {"key_light.diffuse": [0.35, 0.35, 0.35]}},
                  "variant_sha256": "1" * 64, "applied": {"key_light.diffuse": {"nominal": [0.7] * 3, "value": [0.35] * 3}},
                  "realized_sha256": "2" * 64, "physics_fingerprint": "3" * 64, "nominal_physics_fingerprint": "3" * 64}


class CliWorld(World):
    """The owner test's doubles without its run directory (the command makes its own)."""

    def __init__(self):
        self.clock = Clock()
        self.registry = Registry()
        self.script, self.documents, self.launches, self.closed = {}, {}, [], []
        self.running = self.max_running = 0
        self.start_error = self.policy_error = None
        self.close_ok = True
        self.instances = {}
        self.run = None

    def launcher_factory(self, **arguments):
        self.run = arguments["run"]
        self.launcher_arguments = arguments
        return Launcher(self)

    def control_factory(self, shard):
        return self.instances.setdefault(shard.launch.launch_id, Instance(self, shard))


class Setup:
    def __init__(self, tmp_path, monkeypatch, mode="ok"):
        self.tmp = tmp_path
        self.evidence = tmp_path / "evidence"
        self.evidence.mkdir()
        files = tmp_path / "inputs"
        files.mkdir()
        (files / "manifest.json").write_text("{}")
        (files / "scenes.json").write_text("{}")
        (files / "runtime.yaml").write_text("inference: {}\n")
        (files / "rollout.yaml").write_text("undeclared_bundle_cameras: [head, wrist]\n")
        bundle = files / "bundle"
        bundle.mkdir()
        (bundle / "bundle.json").write_text("{}")
        self.files, self.bundle = files, bundle
        campaign = campaign_fixture(tmp_path)
        campaign["gpu_uuid"] = GPU
        self.campaign = write_config(tmp_path, campaign)
        from so101_demo.runtime.container_campaign.mount_build import mount_from_config
        self.mount = mount_from_config(campaign)          # every run starts from a mount tree
        self.parallel = tmp_path / "parallel.yaml"
        self.parallel.write_bytes((PACKAGE_ROOT / "config/mujoco/parallel_batch_act_offline.yaml").read_bytes())
        (tmp_path / "unified").mkdir()
        service = tmp_path / "fake_service.py"
        service.write_text(FAKE_SERVICE)
        self.world = CliWorld()
        self.probe_calls = []
        self.gpu = (True, [])
        self.docker_calls = []
        monkeypatch.setattr(ContainerLaunchRegistry, "all_terminated", lambda self, *a, **k: True)
        self.edges = cli.Edges(
            probes={name: (lambda name=name: (self.probe_calls.append(name), (True, []))[1]) for name in cli.PRECONDITIONS},
            gpu_probe=lambda: self.gpu, docker_runner=lambda argv: self.docker_calls.append(argv),
            inputs_loader=self.inputs, launcher_factory=self.world.launcher_factory,
            control_factory=self.world.control_factory, policy_command=[sys.executable, str(service), "--mode", mode],
            health_probe=lambda: True,                       # the fake service answers no health query; a test names the probe
            clock=self.world.clock, sleep=self.world.clock.sleep, monitor_interval_s=0.005)

    def inputs(self, arguments):
        self.loaded_with = arguments
        identity = {"bundle_sha256": BUNDLE, "policy_sha256": POLICY, "scenes_sha256": "2" * 64,
                    "inputs_manifest_sha256": "3" * 64, "gate_install": str(arguments.install_prefix)}
        variant = None
        if getattr(arguments, "scene_variant", None) is not None:
            variant = dict(VARIANT_RECORD, file={"path": str(arguments.scene_variant), "sha256": "5" * 64})
            identity["scene_variant"] = {key: variant[key] for key in ("name", "variant_sha256", "realized_sha256", "physics_fingerprint")}
        return RolloutInputs(scene_variant=variant, identity=identity,
            settings=SETTINGS, snapshot_targets=SNAPSHOT_TARGETS, endpoint_policy=_endpoint_policy(), timing={}, rollout_config={},
            observation={"cameras": ("head", "wrist"), "state_dim": 8, "image_shape": [4, 6, 3], "source": "bundle"},
            substitution={}, scenes=SCENES, runtime_config={"inference": {"request_timeout_s": 0.5}},
            )

    def argv(self, *extra, run_id="run-1", group="rollout_standard"):
        return ["--evidence-root", str(self.evidence), "--run-id", run_id, "--campaign-config", str(self.campaign),
                "--parallel-runtime-config", str(self.parallel), "--group", group, "--scenes", str(self.files / "scenes.json"),
                "--bundle-dir", str(self.bundle), "--inputs-manifest", str(self.files / "manifest.json"),
                "--runtime-config", str(self.files / "runtime.yaml"), "--rollout-config", str(self.files / "rollout.yaml"),
                "--unified-state-root", str(self.tmp / "unified"), "--policy-python", sys.executable,
                "--policy-pythonpath", str(PYTHONPATH), "--policy-start-timeout-s", "30", "--policy-stop-timeout-s", "10",
                "--shards", "2", "--trials", "2", *extra]

    def run(self, *extra, **changes):
        return cli.main(self.argv(*extra, **changes), edges=self.edges)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    return Setup(tmp_path, monkeypatch)


def read(setup, *parts):
    return json.loads((setup.evidence / "run-1" / Path(*parts)).read_text())


def test_a_run_makes_the_files_and_the_exit_code_of_a_clean_parallel_rollout(setup, capsys):
    assert setup.run() == EXIT_OK
    run = setup.evidence / "run-1"
    assert (run / "run.json").is_file() and (run / "summary.json").is_file() and (run / "table.md").is_file()
    summary = read(setup, "summary.json")
    assert summary["totals"] == {"done": 4, "valid": 4, "invalid_attempts": 0, "invalid_exhausted": 0, "retry_not_run": 0,
                                 "not_run": 0, "units": 4}
    assert summary["runtime"]["shards"] == 2 and summary["runtime"]["trials"] == 2 and summary["policy_service"]["stop_confirmed"]
    assert summary["cleanup_terminated"] is True and summary["fault"] is None and summary["exit_code"] == 0
    document = read(setup, "run.json")
    assert document["kind"] == "ACT_ROLLOUT_PARALLEL_RUN" and document["group"] == "rollout_standard"
    assert document["units"] == ["task_start-t1-a1", "forward_5cm-t1-a1", "task_start-t2-a1", "forward_5cm-t2-a1"]
    assert document["preconditions"] == {name: {"ok": True, "detail": []} for name in cli.PRECONDITIONS}
    assert document["rig_profile_sha256"] and len(document["run_identity_sha256"]) == 64
    assert document["runtime_settings"]["gc_freeze"] is True and document["runtime_settings"]["stall_monitor"] is True
    assert document["runtime_settings"]["gc_freeze_points"] == ["the shard's first task", "each episode reset, before the physics resume"]
    assert read(setup, "services/policy/host-stop.json")["confirmed"] is True
    assert read(setup, "services/policy/host-start.json")["ready"]["bundle_sha256"] == BUNDLE
    checks = read(setup, "host/gpu-checks.json")
    assert [item["only_the_policy_service"] for item in checks] == [True, True]       # after the start, and before the one wave
    assert (run / "host" / "containers-receipt-01-rollout.json").is_file()
    assert json.loads(capsys.readouterr().out.strip().splitlines()[-1])["exit_code"] == 0
    assert setup.probe_calls == list(cli.PRECONDITIONS)
    assert setup.loaded_with.install_prefix == setup.mount.package_prefix       # the mounted install, never an image path


def test_the_launcher_is_given_the_run_identity_the_rig_and_the_inputs_the_shards_may_read(setup):
    setup.run()
    arguments = setup.world.launcher_arguments
    assert arguments["rollout_identity"]["policy_sha256"] == POLICY and arguments["rollout_identity"]["bundle_sha256"] == BUNDLE
    assert arguments["rollout_identity"]["scenes_sha256"] == "2" * 64 and len(arguments["rollout_identity"]["run_identity_sha256"]) == 64
    assert len(arguments["rig_profile_sha256"]) == 64 and arguments["context"].workload_kind == "act_rollout_start"
    context = arguments["context"]
    assert context.manifest_sha256 == "2" * 64 and context.contact_policy_fingerprint == POLICY
    assert context.collection_config_sha256 == arguments["rollout_identity"]["run_identity_sha256"]
    assert context.registered_evidence_root == str(setup.evidence) and context.physical_gpu_uuid == GPU
    approved = {str(path) for path in arguments["approved_inputs"]}
    assert str(setup.files) in approved or {str(setup.files / "scenes.json"), str(setup.bundle)} <= approved
    assert str(setup.parallel) in approved and str(setup.tmp / "controlled.json") in approved


def test_the_task_documents_carry_the_runtime_values_and_the_shared_run_identity(setup):
    setup.run("--execution-prefix", "5", "--task-timeout-s", "900")
    document = next(iter(setup.world.documents.values()))
    assert document["execution"] == {"execution_prefix": 5, "temporal_ensembling": None}
    assert document["policy"]["service_generation"] == "run-1-policy" and document["policy"]["bundle_sha256"] == BUNDLE
    assert document["inputs"]["install_prefix"] == str(setup.mount.package_prefix)
    assert document["inputs"]["scenes"]["sha256"] and document["inputs"]["bundle_dir"] == str(setup.bundle)
    assert len({item["run_identity_sha256"] for item in setup.world.documents.values()}) == 1


def test_a_scene_variant_is_bound_into_the_run_the_tasks_the_launcher_and_the_mounts(setup):
    variant = setup.files / "variant.json"
    variant.write_text("{}")
    assert setup.run("--scene-variant", str(variant)) == EXIT_OK
    assert str(setup.loaded_with.scene_variant) == str(variant)
    document = read(setup, "run.json")
    assert document["scene_variant"]["name"] == "dark" and document["scene_variant"]["realized_sha256"] == "2" * 64
    assert document["identity"]["scene_variant"]["physics_fingerprint"] == "3" * 64
    task = next(iter(setup.world.documents.values()))
    assert task["inputs"]["scene_variant"]["path"] == str(variant) and len(task["inputs"]["scene_variant"]["sha256"]) == 64
    entry = setup.world.launcher_arguments["scene_variant"]
    assert entry["file"]["path"] == str(variant) and entry["realized_sha256"] == "2" * 64 and entry["physics_fingerprint"] == "3" * 64
    assert str(variant) in {str(path) for path in setup.world.launcher_arguments["approved_inputs"]} or \
        str(setup.files) in {str(path) for path in setup.world.launcher_arguments["approved_inputs"]}
    assert len({item["run_identity_sha256"] for item in setup.world.documents.values()}) == 1


def test_a_scene_variant_that_is_not_an_absolute_regular_file_refuses_before_anything_exists(setup, capsys):
    for path in ("variant.json", str(setup.files / "missing.json"), str(setup.files)):
        assert setup.run("--scene-variant", path) == 2
        assert "ROLLOUT_SCENE_VARIANT_INVALID" in capsys.readouterr().err
        assert not (setup.evidence / "run-1").exists()


def test_a_run_without_a_scene_variant_has_none_of_it_anywhere(setup):
    assert setup.run() == EXIT_OK
    assert setup.loaded_with.scene_variant is None
    assert "scene_variant" not in read(setup, "run.json") or read(setup, "run.json")["scene_variant"] is None
    assert "scene_variant" not in next(iter(setup.world.documents.values()))["inputs"]
    assert setup.world.launcher_arguments.get("scene_variant") is None


def test_an_invalid_attempt_is_run_again(setup):
    setup.world.script["task_start-t1-a1"] = {"verdict": "INVALID", "reason": "goal response timeout"}
    assert setup.run("--max-invalid-retries", "1") == EXIT_OK
    assert read(setup, "summary.json")["totals"]["invalid_attempts"] == 1


def test_a_cell_that_never_gives_a_result_is_exit_one(tmp_path, monkeypatch):
    run = Setup(tmp_path, monkeypatch)
    run.world.script["task_start-t1-a1"] = {"verdict": "INVALID", "reason": "A"}
    run.world.script["task_start-t1-a2"] = {"verdict": "INVALID", "reason": "B"}
    assert run.run("--max-invalid-retries", "1") == EXIT_INVALID
    assert json.loads((run.evidence / "run-1" / "summary.json").read_text())["totals"]["invalid_exhausted"] == 1


def test_a_precondition_that_fails_refuses_before_anything_exists(setup, capsys):
    for name in cli.PRECONDITIONS:
        original = setup.edges.probes[name]
        setup.edges.probes[name] = lambda: (False, "something is there")
        assert setup.run() == 2
        assert f"ROLLOUT_PRECONDITION_FAILED: {name}: something is there" in capsys.readouterr().err
        assert not (setup.evidence / "run-1").exists()
        setup.edges.probes[name] = original
    setup.edges.probes["no_container"] = lambda: (_ for _ in ()).throw(RuntimeError("docker socket unreadable"))
    assert setup.run() == 2 and "ROLLOUT_PRECONDITION_UNPROVEN: no_container" in capsys.readouterr().err
    del setup.edges.probes["no_gpu_process"]
    assert setup.run() == 2 and not (setup.evidence / "run-1").exists()


def test_another_compute_process_on_the_gpu_after_the_service_starts_stops_the_run_and_the_service(setup):
    setup.gpu = (False, ["999999, python"])
    setup.edges.probes["no_gpu_process"] = lambda: (True, [])           # the precondition before the start held
    assert setup.run() == EXIT_START_FAILED
    summary = read(setup, "summary.json")
    assert "another compute process" in summary["fault"] and summary["policy_service"]["stop_confirmed"] is True
    assert setup.world.launches == []
    assert read(setup, "host/gpu-checks.json")[-1]["only_the_policy_service"] is False


def test_the_gpu_check_after_the_start_accepts_the_service_itself():
    assert cli.only_own_gpu_process(lambda: (False, ["1234, python", "1234, python"]), 1234) == (True, ["1234, python", "1234, python"])
    assert cli.only_own_gpu_process(lambda: (False, ["1234, python", "55, python3"]), 1234)[0] is False
    assert cli.only_own_gpu_process(lambda: (True, []), 1234)[0] is True


@pytest.mark.parametrize("extra", [["--shards", "0"], ["--trials", "0"], ["--max-invalid-retries", "-1"],
                                   ["--max-concurrent-episodes", "0"], ["--min-assignment-gap-s", "-1"],
                                   ["--task-timeout-s", "0"], ["--campaign-timeout-s", "inf"], ["--policy-queue-timeout-s", "0"]])
def test_counts_and_timings_are_checked_before_anything_is_created(setup, extra):
    assert setup.run(*extra) == 2 and not (setup.evidence / "run-1").exists()


def test_a_bad_run_id_a_relative_path_or_a_missing_evidence_root_is_refused(setup):
    assert setup.run(run_id="bad id") == 2
    argv = setup.argv()
    argv[argv.index("--scenes") + 1] = "scenes.json"
    assert cli.main(argv, edges=setup.edges) == 2
    argv = setup.argv()
    argv[argv.index("--evidence-root") + 1] = str(setup.tmp / "nowhere")
    assert cli.main(argv, edges=setup.edges) == 2


def test_an_input_the_native_loader_refuses_is_a_refusal(setup, capsys):
    def refuse(arguments):
        raise ValueError("ROLLOUT_ENDPOINT_POLICY_MISMATCH")
    setup.edges.inputs_loader = refuse
    assert setup.run() == 2 and "ROLLOUT_INPUTS_REFUSED: ROLLOUT_ENDPOINT_POLICY_MISMATCH" in capsys.readouterr().err
    assert not (setup.evidence / "run-1").exists()


def test_the_held_out_group_is_opened_once_per_policy(setup, capsys):
    assert setup.run("--trials", "1", group="rollout_test") == EXIT_OK
    marker = setup.evidence / "rollout-test-opened" / f"{POLICY[:12]}.json"
    assert json.loads(marker.read_text())["run_id"] == "run-1"
    setup.world.documents.clear()
    assert setup.run("--trials", "1", group="rollout_test", run_id="run-2") == 2
    assert "ROLLOUT_TEST_ALREADY_OPENED" in capsys.readouterr().err and not (setup.evidence / "run-2").exists()


def test_scene_selection_and_the_limit_reach_the_queue(setup):
    setup.run("--scene-id", "forward_5cm", "--trials", "1")
    assert read(setup, "run.json")["units"] == ["forward_5cm-t1-a1"]


def test_approved_inputs_leave_out_what_the_mounted_build_already_shows_and_collapse_nested_paths(tmp_path):
    root = tmp_path / "build" / ("a" * 12)
    (root / "source" / "config").mkdir(parents=True)
    inside = root / "source" / "config" / "runtime.yaml"
    inside.write_text("x")
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    manifest = frozen / "manifest.json"
    manifest.write_text("{}")
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    controlled = tmp_path / "controlled.json"
    controlled.write_text("{}")
    parallel = tmp_path / "parallel.yaml"
    parallel.write_text("{}")
    scenes = frozen / "scenes.json"                  # inside the frozen inputs directory: already mounted with it
    scenes.write_text("{}")
    args = SimpleNamespace(inputs_manifest=manifest, bundle_dir=bundle, scenes=scenes, runtime_config=inside, rollout_config=inside,
                           contact_activation_receipt=None, contact_proposal=None)
    from so101_demo.runtime.container_campaign.mount_build import MountBuild
    kept = cli.approved_inputs(args, {"controlled_runtime": {"path": str(controlled)}}, MountBuild("a" * 40, root), parallel)
    assert set(kept) == {frozen, bundle, controlled, parallel}


def test_the_held_out_group_is_not_used_up_by_a_run_that_never_assigned_a_task(tmp_path, monkeypatch):
    run = Setup(tmp_path, monkeypatch, mode="exit_early")
    assert run.run("--trials", "1", group="rollout_test") == EXIT_START_FAILED
    assert not (run.evidence / "rollout-test-opened").exists() and run.world.documents == {}


def test_the_held_out_group_is_marked_after_the_first_task_is_sent_and_not_before(setup):
    states = []
    marker = setup.evidence / "rollout-test-opened" / f"{POLICY[:12]}.json"
    setup.world.on_assign = lambda: states.append(marker.exists())
    assert setup.run("--trials", "1", group="rollout_test") == EXIT_OK
    assert states == [False] and marker.is_file()


def test_the_policy_pythonpath_defaults_to_the_mounted_install_and_a_missing_interpreter_is_refused_before_anything_is_created(setup):
    argv = setup.argv("--trials", "1", group="rollout_test")
    index = argv.index("--policy-pythonpath")
    del argv[index:index + 2]
    *_, pythonpath = cli.prepare(cli.build_parser().parse_args(argv), setup.edges)
    assert pythonpath == setup.mount.package_prefix / "lib/python3.12/site-packages"
    assert not (setup.evidence / "run-1").exists() and not (setup.evidence / "rollout-test-opened").exists()
    argv = setup.argv()
    argv[argv.index("--policy-python") + 1] = str(setup.tmp / "no-such-python")
    assert cli.main(argv, edges=setup.edges) == 2 and not (setup.evidence / "run-1").exists()


def test_a_failure_after_the_run_directory_exists_is_not_a_refusal(setup, capsys):
    def broken(**_):
        raise RuntimeError("cannot build the launcher")
    setup.edges.launcher_factory = broken
    assert setup.run() == cli.EXIT_RUN_FAULT
    assert "ROLLOUT_RUN_FAULT: RuntimeError: cannot build the launcher" in capsys.readouterr().err
    assert (setup.evidence / "run-1").is_dir()


def test_a_faulted_service_ends_the_run_with_the_policy_fault_code_and_no_new_assignment(tmp_path, monkeypatch):
    run = Setup(tmp_path, monkeypatch)
    run.edges.health_probe = lambda: True if not run.world.documents else "POLICY_SERVICE_FAULT: POLICY_MODEL_FAILED: RuntimeError"
    assert run.run("--shards", "1") == 5
    summary = json.loads((run.evidence / "run-1" / "summary.json").read_text())
    assert summary["exit_code"] == 5 and summary["policy_fault"].startswith("ROLLOUT_POLICY_SERVICE_UNHEALTHY: POLICY_SERVICE_FAULT")
    assert len(run.world.documents) == 1 and summary["totals"]["invalid_attempts"] == 0
    assert summary["policy_service"]["stop_confirmed"] is True


def test_without_an_explicit_probe_the_run_asks_the_service_itself_and_an_unanswering_service_is_a_policy_fault(tmp_path, monkeypatch):
    run = Setup(tmp_path, monkeypatch)
    run.edges.health_probe = None                    # the production probe: a policy_health_query over the socket
    assert run.run("--shards", "1") == 5             # the fake service holds no socket: three unanswered queries in a row
    assert "HEALTH_QUERY_UNANSWERED" in json.loads((run.evidence / "run-1" / "summary.json").read_text())["policy_fault"]


def test_the_gpu_check_looks_only_at_the_configured_device():
    def smi(*rows, code=0):
        return lambda argv, **_: SimpleNamespace(returncode=code, stdout="\n".join(rows) + "\n", stderr="boom")
    uuid = "GPU-28221cec-9d21-7753-fd5a-da645740df19"
    other = "GPU-11111111-2222-3333-4444-555555555555"
    free, rows = cli.gpu_processes(uuid, run=smi(f"{other}, 4242, python", f"{other}, 99, trainer"))
    assert free is True and rows == []                                  # a job on the other GPU is not this run's business
    free, rows = cli.gpu_processes(uuid, run=smi(f"{uuid}, 4242, python", f"{other}, 99, trainer", f"{uuid.lower()}, 7, x"))
    assert free is False and rows == ["4242, python", "7, x"]
    assert cli.gpu_processes(uuid, run=smi())[0] is True
    with pytest.raises(RuntimeError, match="nvidia-smi failed"):
        cli.gpu_processes(uuid, run=smi(code=9))
    with pytest.raises(RuntimeError, match="without a device"):
        cli.gpu_processes(uuid, run=smi("4242"))


def test_the_policy_consecutive_error_bound_is_a_runtime_parameter_checked_before_anything_exists(setup):
    assert setup.run("--policy-max-consecutive-errors", "0") == 2 and not (setup.evidence / "run-1").exists()


def test_a_campaign_config_without_a_mount_build_is_refused_and_no_run_root_is_made(setup, capsys):
    document = json.loads(setup.campaign.read_text())
    del document["mount_build"]
    setup.campaign.write_text(json.dumps(document))
    assert setup.run() == 2
    assert "MOUNT_BUILD_REQUIRED" in capsys.readouterr().err
    assert not (setup.evidence / "run-1").exists() and setup.docker_calls == []

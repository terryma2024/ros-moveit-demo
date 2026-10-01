"""The stack-free exclusive-ownership gate Task 14 Step 1 must pass before any qualifier starts.

Every fixture is synthetic: a fake `/proc` tree, fake command runners and fake observation documents. No
test in this file starts a stack, loads a detector, touches the GPU or reads the live process table
(except the one that asserts the real reader returns a document without raising).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_ownership import (
    EXCLUSIVE_OWNERSHIP_OK,
    EXCLUSIVE_OWNERSHIP_REFUSED,
    RECEIPT_NAME,
    ResourceObservation,
    check_exclusive_ownership,
    classify_owner_command,
    default_observers,
    observe_evidence_root,
    observe_gpu_processes,
    observe_planned_run_root,
    observe_process_table,
    observe_ros_graph,
    observe_tmux_panes,
    parse_gpu_compute_apps,
    parse_ros_nodes,
    parse_tmux_panes,
    read_runtime_identity,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

VALUE_NAMES = (
    "center_deadband_px",
    "coarse_step_rad",
    "horizontal_fov_rad",
    "lock_valid_neck_rad",
    "max_age_s",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_skew_s",
    "min_area_px2",
    "min_bbox_aspect",
    "min_confidence",
    "search_timeout_s",
    "stop_latency_s",
    "stop_velocity_rad_s",
    "submit_lead_s",
    "tracking_iou",
    "vertical_bounds_px",
)


def _write_proc_entry(
    proc_root: Path, pid: int, argv: list[str], *, ppid: int = 1, starttime: int = 1000
) -> None:
    entry = proc_root / str(pid)
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "cmdline").write_bytes(b"".join(item.encode() + b"\0" for item in argv))
    after = [
        "S",
        str(ppid),
        str(ppid),
        str(ppid),
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "20",
        "0",
        "1",
        "0",
        str(starttime),
    ]
    (entry / "stat").write_text(f"{pid} ({Path(argv[0]).name}) " + " ".join(after) + "\n")


def _observation(name: str, **overrides) -> ResourceObservation:
    fields = {"command": (), "rc": 0, "rows": (), "value": None, "note": ""}
    fields.update(overrides)
    return ResourceObservation(name=name, **fields)


def _clean_observers(**extra) -> dict:
    observers = {
        "process_table": lambda: _observation("process_table"),
        "ros_graph": lambda: _observation("ros_graph", value="clean"),
        "gpu_processes": lambda: _observation("gpu_processes"),
        "tmux_panes": lambda: _observation("tmux_panes"),
        "evidence_root": lambda: _observation("evidence_root", value="usable"),
        "planned_run_root": lambda: _observation("planned_run_root", value="absent"),
        "ament_prefix": lambda: _observation("ament_prefix", value="/frozen/so101_demo_py"),
    }
    observers.update(extra)
    return observers


def _runtime(**overrides) -> dict:
    runtime = {
        "final_run": "/frozen",
        "source_commit": "9" * 40,
        "setup_bash_present": True,
        "production_config": "/frozen/config.json",
        "production_config_sha256": "a" * 64,
        "values_count": 17,
        "values_sha256": "b" * 64,
        "allow_cpu_fallback": False,
        "cuda_device": "cuda:0",
        "weight_path": "/frozen/best.pt",
        "weight_sha256_declared": "c" * 64,
        "weight_sha256_observed": "c" * 64,
    }
    runtime.update(overrides)
    return runtime


# --- pure readers -----------------------------------------------------------------------------------


def test_a_token_is_classified_by_the_owner_it_names() -> None:
    assert classify_owner_command(["mujoco_ros2_control", "--ros-args"]) == "stack"
    assert classify_owner_command(["/usr/bin/move_group"]) == "stack"
    assert classify_owner_command(["python3", "/x/so101_unified_web_server.py"]) == "stack"
    assert classify_owner_command(["/x/so101_head_search_calibration", "qualify"]) == "detector"
    assert (
        classify_owner_command(["python3", "so101_demo.cli.head_search_calibration"]) == "detector"
    )
    assert (
        classify_owner_command(["python3", "-m", "so101_demo.application.qualification"]) == "stack"
    )
    # a test file that merely mentions the calibration is not a running campaign
    assert (
        classify_owner_command(
            ["pytest", "src/so101_demo_py/test/test_act_head_search_calibration.py"]
        )
        is None
    )
    assert classify_owner_command(["bash", "-c", "ls"]) is None


def test_the_process_table_reports_only_owner_processes(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_proc_entry(proc, 111, ["mujoco_ros2_control", "--ros-args"], starttime=11)
    _write_proc_entry(proc, 222, ["bash", "-c", "sleep 1"], starttime=22)
    _write_proc_entry(proc, 333, ["/frozen/so101_head_search_calibration", "qualify"], starttime=33)
    observation = observe_process_table(proc_root=proc)
    assert observation.rc == 0
    assert [(row["pid"], row["kind"]) for row in observation.rows] == [
        (111, "stack"),
        (333, "detector"),
    ]
    assert observation.rows[0]["command"].endswith("mujoco_ros2_control --ros-args")
    assert observation.rows[0]["started_ticks"] == 11


def test_the_gate_never_reports_itself_or_its_own_launcher(tmp_path: Path) -> None:
    proc = tmp_path / "proc"
    _write_proc_entry(proc, 111, ["/frozen/so101_head_search_calibration", "check-ownership"])
    _write_proc_entry(proc, 112, ["bash", "-c", "so101_head_search_calibration check-ownership"])
    _write_proc_entry(proc, 113, ["pytest", "src/so101_demo_py/test"], starttime=5)
    observation = observe_process_table(proc_root=proc, excluded_pids=(111, 112))
    assert observation.rows == ()


def test_gpu_compute_apps_are_parsed_with_their_pids_and_memory() -> None:
    text = "1234, python3, 512 MiB\n4321, /usr/bin/mujoco, 2048 MiB\n"
    rows = parse_gpu_compute_apps(text)
    assert [row["pid"] for row in rows] == [1234, 4321]
    assert rows[0]["process_name"] == "python3"
    assert rows[0]["used_memory_mib"] == 512
    assert parse_gpu_compute_apps("") == []


def test_ros_nodes_and_tmux_panes_are_parsed_from_the_command_output() -> None:
    assert parse_ros_nodes("/move_group\n/robot_state_publisher\n") == [
        "/move_group",
        "/robot_state_publisher",
    ]
    assert parse_ros_nodes("\n") == []
    panes = parse_tmux_panes("dst\t1174838\tnode\nso101\t42\tros2\n")
    assert panes[0] == {"session": "dst", "pane_pid": 1174838, "command": "node"}
    assert panes[1]["command"] == "ros2"


def test_a_failing_probe_is_never_read_as_clean() -> None:
    def failing_runner(argv, *, timeout):
        return 127, "", f"{argv[0]}: command not found"

    observation = observe_gpu_processes(runner=failing_runner)
    assert observation.rc == 127
    assert observation.note.startswith("PROBE_FAILED")


def test_a_missing_tmux_server_is_clean_and_a_missing_tmux_binary_is_not() -> None:
    def no_server(argv, *, timeout):
        return 1, "", "no server running on /tmp/tmux-1000/default\n"

    def no_binary(argv, *, timeout):
        return 127, "", "tmux: command not found"

    clean = observe_tmux_panes(runner=no_server)
    assert clean.rc == 0 and clean.rows == ()
    failed = observe_tmux_panes(runner=no_binary)
    assert failed.note.startswith("PROBE_FAILED")


def test_the_ros_graph_observation_lists_every_visible_node() -> None:
    def runner(argv, *, timeout):
        return 0, "/move_group\n/robot_state_publisher\n", ""

    observation = observe_ros_graph(runner=runner)
    assert observation.value == "not-empty"
    assert [row["node"] for row in observation.rows] == ["/move_group", "/robot_state_publisher"]


def test_the_evidence_root_must_be_writable_and_inside_the_platform_root(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert observe_evidence_root(outside, within=tmp_path / "so101-evidence").value == "unusable"
    usable = tmp_path / "so101-evidence" / "campaign"
    usable.mkdir(parents=True)
    observation = observe_evidence_root(usable, within=tmp_path / "so101-evidence")
    assert observation.value == "usable"
    assert observation.note == str(usable.resolve())
    missing = observe_evidence_root(tmp_path / "so101-evidence" / "nope", within=tmp_path)
    assert missing.value == "unusable"
    assert missing.note.startswith("MISSING")


def test_the_planned_qualification_root_must_not_exist(tmp_path: Path) -> None:
    assert observe_planned_run_root(tmp_path / "new").value == "absent"
    existing = tmp_path / "existing"
    existing.mkdir()
    assert observe_planned_run_root(existing).value == "exists"


def test_the_real_process_table_reader_returns_a_document() -> None:
    observation = observe_process_table()
    assert observation.rc == 0
    assert observation.name == "process_table"


# --- the runtime of record --------------------------------------------------------------------------


def _frozen_root(tmp_path: Path, *, commit: str = "9" * 40) -> tuple[Path, Path]:
    root = tmp_path / "head-toolchain"
    config_dir = root / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act"
    config_dir.mkdir(parents=True)
    (root / "install/setup.bash").write_text("# frozen overlay\n", encoding="utf-8")
    (root / "source-commit.txt").write_text(commit + "\n", encoding="utf-8")
    weights = root / "weights/best.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    weights.write_bytes(b"frozen weights\n")
    config = config_dir / "head_search_v2.json"
    config.write_text(
        json.dumps(
            {
                "values": {name: 1.0 for name in VALUE_NAMES},
                "allow_cpu_fallback": False,
                "cuda_device": "cuda:0",
                "weight_path": str(weights),
                "weight_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return root, config


def test_the_runtime_identity_is_read_from_the_frozen_root(tmp_path: Path) -> None:
    root, config = _frozen_root(tmp_path)
    identity = read_runtime_identity(root)
    assert identity["source_commit"] == "9" * 40
    assert identity["setup_bash_present"] is True
    assert identity["production_config"] == str(config)
    assert identity["production_config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    assert identity["values_count"] == 17
    assert identity["values_sha256"] == canonical_sha256({name: 1.0 for name in VALUE_NAMES})
    assert identity["allow_cpu_fallback"] is False
    assert identity["cuda_device"] == "cuda:0"
    assert identity["weight_sha256_observed"] == identity["weight_sha256_declared"]


def test_an_unreadable_frozen_root_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="RUNTIME_IDENTITY_UNREADABLE"):
        read_runtime_identity(tmp_path / "missing")


# --- the gate ---------------------------------------------------------------------------------------


def _gate(tmp_path: Path, *, observers=None, runtime=None, expected=None, **overrides):
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    arguments = {
        "run_root": overrides.pop("run_root", tmp_path / "gate"),
        "evidence_root": evidence,
        "runtime": _runtime() if runtime is None else runtime,
        "expected_runtime": expected,
        "observers": _clean_observers() if observers is None else observers,
    }
    arguments.update(overrides)
    return check_exclusive_ownership(**arguments)


def test_clean_resources_publish_ok_and_bind_the_run_root(tmp_path: Path) -> None:
    document = _gate(tmp_path)
    assert document["status"] == EXCLUSIVE_OWNERSHIP_OK
    assert document["refusals"] == []
    assert document["operation"] == "QUALIFICATION_OWNERSHIP_CHECK"
    assert document["runtime"]["source_commit"] == "9" * 40
    assert document["owner"]["pid"] > 0
    receipt = json.loads((tmp_path / "gate" / RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt == document
    assert receipt["observations"]["process_table"]["rc"] == 0


def test_a_second_stack_owner_refuses_the_gate(tmp_path: Path) -> None:
    observers = _clean_observers(
        process_table=lambda: _observation(
            "process_table",
            rows=({"pid": 7, "kind": "stack", "command": "mujoco_ros2_control"},),
        )
    )
    document = _gate(tmp_path, observers=observers)
    assert document["status"] == EXCLUSIVE_OWNERSHIP_REFUSED
    assert [item["code"] for item in document["refusals"]] == ["STACK_OWNER_ACTIVE"]


def test_a_second_detector_owner_refuses_the_gate(tmp_path: Path) -> None:
    observers = _clean_observers(
        process_table=lambda: _observation(
            "process_table", rows=({"pid": 8, "kind": "detector", "command": "yolo"},)
        )
    )
    document = _gate(tmp_path, observers=observers)
    assert [item["code"] for item in document["refusals"]] == ["DETECTOR_OWNER_ACTIVE"]


@pytest.mark.parametrize(
    ("observer_name", "observation", "code"),
    (
        (
            "gpu_processes",
            {"rows": ({"pid": 9, "process_name": "python3"},)},
            "GPU_COMPUTE_APP_ACTIVE",
        ),
        (
            "ros_graph",
            {"rows": ({"node": "/move_group"},), "value": "not-empty"},
            "ROS_GRAPH_NOT_EMPTY",
        ),
        (
            "tmux_panes",
            {"rows": ({"session": "so101", "pane_pid": 42, "kind": "stack"},)},
            "TMUX_OWNER_ACTIVE",
        ),
        ("ament_prefix", {"value": "/somewhere/else"}, "PACKAGE_PREFIX_MISMATCH"),
        ("planned_run_root", {"value": "exists"}, "PLANNED_RUN_ROOT_ALREADY_EXISTS"),
        ("evidence_root", {"value": "unusable", "note": "MISSING"}, "EVIDENCE_ROOT_UNUSABLE"),
    ),
)
def test_each_contended_resource_is_refused_by_its_own_code(
    tmp_path: Path, observer_name: str, observation: dict, code: str
) -> None:
    observers = _clean_observers(
        **{observer_name: lambda: _observation(observer_name, **observation)}
    )
    document = _gate(tmp_path, observers=observers, expected_package_prefix="/frozen/so101_demo_py")
    assert document["status"] == EXCLUSIVE_OWNERSHIP_REFUSED
    assert code in [item["code"] for item in document["refusals"]]


def test_a_failed_probe_refuses_rather_than_passes(tmp_path: Path) -> None:
    observers = _clean_observers(
        gpu_processes=lambda: _observation(
            "gpu_processes", rc=127, note="PROBE_FAILED: no nvidia-smi"
        )
    )
    document = _gate(tmp_path, observers=observers)
    assert [item["code"] for item in document["refusals"]] == ["OWNERSHIP_PROBE_FAILED"]


def test_the_runtime_of_record_is_compared_field_by_field(tmp_path: Path) -> None:
    document = _gate(
        tmp_path,
        expected={
            "source_commit": "9" * 40,
            "production_config_sha256": "a" * 64,
            "values_sha256": "b" * 64,
            "weight_sha256_declared": "c" * 64,
        },
    )
    assert document["status"] == EXCLUSIVE_OWNERSHIP_OK
    mismatch = _gate(
        tmp_path / "two",
        expected={"source_commit": "0" * 40},
    )
    assert mismatch["status"] == EXCLUSIVE_OWNERSHIP_REFUSED
    refusals = {item["code"]: item for item in mismatch["refusals"]}
    assert "RUNTIME_OF_RECORD_MISMATCH" in refusals
    assert "source_commit" in refusals["RUNTIME_OF_RECORD_MISMATCH"]["detail"]


def test_a_cpu_fallback_runtime_is_refused_before_anything_starts(tmp_path: Path) -> None:
    document = _gate(tmp_path, runtime=_runtime(allow_cpu_fallback=True))
    assert [item["code"] for item in document["refusals"]] == ["RUNTIME_CUDA_REQUIRED"]


def test_an_incomplete_value_set_is_refused(tmp_path: Path) -> None:
    document = _gate(tmp_path, runtime=_runtime(values_count=16, values_sha256="d" * 64))
    assert "RUNTIME_VALUES_INCOMPLETE" in [item["code"] for item in document["refusals"]]


def test_a_weight_digest_that_does_not_match_its_declaration_is_refused(tmp_path: Path) -> None:
    document = _gate(tmp_path, runtime=_runtime(weight_sha256_observed="e" * 64))
    assert "RUNTIME_WEIGHTS_MISMATCH" in [item["code"] for item in document["refusals"]]


def test_an_existing_gate_root_is_never_reused(tmp_path: Path) -> None:
    existing = tmp_path / "gate"
    existing.mkdir()
    with pytest.raises(ValueError, match="RUN_ROOT_ALREADY_EXISTS"):
        _gate(tmp_path, run_root=existing)


def test_the_default_observers_are_the_five_resources_the_plan_names(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    observers = default_observers(evidence_root=evidence, within=tmp_path)
    assert set(observers) == {
        "process_table",
        "ros_graph",
        "gpu_processes",
        "tmux_panes",
        "evidence_root",
        "planned_run_root",
        "ament_prefix",
    }
    for name, observer in observers.items():
        if name in {"gpu_processes", "ros_graph", "ament_prefix"}:
            continue  # these need the live machine and are covered above with fake runners
        observation = observer()
        assert isinstance(observation, ResourceObservation)

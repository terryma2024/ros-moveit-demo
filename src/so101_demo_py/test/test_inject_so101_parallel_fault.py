"""Safety contract for the explicit Task 12 process-group fault injector."""

import importlib.util
import json
import os
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/inject_so101_parallel_fault.py"
TASK_ROOT = Path("/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1")


@pytest.fixture
def module():
    spec = importlib.util.spec_from_file_location("inject_so101_parallel_fault", SCRIPT)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def worker_command(root, worker_id="worker-01"):
    path = root / "workers" / worker_id / "worker-spec.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "batch_id": "batch-1",
                "resources": {"worker_id": worker_id, "generation": 1},
            }
        ),
        encoding="utf-8",
    )
    return (
        "/usr/bin/python3",
        "-m",
        "so101_demo.cli.mujoco_parallel_batch",
        "--internal-worker",
        str(path),
    )


def write_manifest(root, entries, *, batch_id="batch-1", extra=None):
    root.mkdir(parents=True, exist_ok=True)
    current = root
    while current != TASK_ROOT / "scratch":
        current.chmod(0o700)
        current = current.parent
    document = {
        "schema_version": 1,
        "batch_id": batch_id,
        "processes": entries,
    }
    if extra:
        document.update(extra)
    path = root / "owned-processes.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o600)


def evidence_root(tmp_path, suffix):
    """Keep script fixtures inside this pytest run's registered NVMe scratch."""
    run_id = Path(os.environ["TMPDIR"]).parent.name
    return TASK_ROOT / "scratch" / run_id / "fault-injector" / tmp_path.name / suffix


def entry(root, target="worker-01", **changes):
    role = "broker" if target == "broker" else "worker"
    if role == "broker":
        broker_spec = root / "ipc" / "broker" / "broker-spec.json"
        broker_spec.parent.mkdir(parents=True, exist_ok=True)
        broker_spec.write_text(
            json.dumps({
                "schema_version": 1,
                "kind": "so101_parallel_broker_runtime",
                "batch_id": "batch-1",
                "broker_generation": 1,
            }),
            encoding="utf-8",
        )
    command = (
        (
            "docker",
            "run",
            "--volume",
            f"{root / 'ipc/broker'}:/runtime:rw",
            "sha256:" + "a" * 64,
        )
        if role == "broker"
        else worker_command(root, target)
    )
    value = {
        "batch_id": "batch-1",
        "role": role,
        "pid": 41001,
        "pgid": 41001,
        "cmdline": list(command),
        "start_time": 123456,
    }
    value.update(changes)
    return value


def proc(value):
    return {
        "pid": value["pid"],
        "pgid": value["pgid"],
        "cmdline": tuple(value["cmdline"]),
        "start_time": value["start_time"],
        "session_id": value["pgid"],
        "uid": os.getuid(),
    }


@pytest.mark.parametrize("target", ["worker-01", "worker-02", "worker-03", "broker"])
def test_exact_owned_identity_is_rechecked_before_term(module, tmp_path, target):
    root = evidence_root(tmp_path, target)
    value = entry(root, target)
    write_manifest(root, [value])
    sent = []

    result = module.inject_fault(
        [str(root), target, "TERM"],
        proc_reader=lambda _pid: proc(value),
        signal_group=lambda pgid, signal_number: sent.append((pgid, signal_number)),
    )

    assert result["batch_id"] == "batch-1"
    assert result["target"] == target
    assert result["pid"] == value["pid"]
    assert result["pgid"] == value["pgid"]
    assert sent == [(value["pgid"], module.signal.SIGTERM)]


def test_default_signal_port_is_monkeypatched_and_never_targets_an_unrelated_group(
    module, tmp_path, monkeypatch
):
    root = evidence_root(tmp_path, "default-signal")
    value = entry(root)
    write_manifest(root, [value])
    sent = []
    monkeypatch.setattr(module.os, "killpg", lambda *args: sent.append(args))

    module.inject_fault(
        [str(root), "worker-01", "TERM"],
        proc_reader=lambda _pid: proc(value),
    )

    assert sent == [(value["pgid"], module.signal.SIGTERM)]


@pytest.mark.parametrize(
    "argv",
    [
        ["relative", "worker-01", "TERM"],
        [str(TASK_ROOT.parent / "other"), "worker-01", "TERM"],
        [str(TASK_ROOT), "worker-04", "TERM"],
        [str(TASK_ROOT), "worker-01", "KILL"],
    ],
)
def test_rejects_out_of_scope_paths_targets_and_signals(module, argv):
    with pytest.raises(ValueError):
        module.inject_fault(argv, proc_reader=lambda _pid: None, signal_group=lambda *_: None)


@pytest.mark.parametrize("argv", [[], [str(TASK_ROOT)], [str(TASK_ROOT), "broker"]])
def test_rejects_partial_argument_vectors_without_parser_exit(module, argv):
    with pytest.raises(ValueError, match="ARGUMENT"):
        module.inject_fault(argv, proc_reader=lambda _pid: None, signal_group=lambda *_: None)


@pytest.mark.parametrize(
    "mutation,error",
    [
        (lambda root, value: [], "TARGET_COUNT"),
        (lambda root, value: [value, dict(value, pid=41002, pgid=41002)], "TARGET_COUNT"),
        (lambda root, value: [dict(value, batch_id="other")], "BATCH_MISMATCH"),
        (lambda root, value: [dict(value, role="broker")], "ROLE_MISMATCH"),
        (lambda root, value: [dict(value, pgid=41002)], "UNOWNED_PGID"),
        (lambda root, value: [dict(value, cmdline=[])], "MANIFEST"),
    ],
)
def test_rejects_missing_duplicate_malformed_or_mismatched_target(
    module, tmp_path, mutation, error
):
    root = evidence_root(tmp_path, error)
    value = entry(root)
    write_manifest(root, mutation(root, value))
    with pytest.raises(ValueError, match=error):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


@pytest.mark.parametrize(
    "field,replacement,error",
    [
        ("pid", 41002, "PID"),
        ("pgid", 41002, "PGID"),
        ("cmdline", ("different",), "CMDLINE"),
        ("start_time", 123457, "START_TIME"),
        ("session_id", 41002, "UNOWNED_PGID"),
        ("uid", 1 + os.getuid(), "UID"),
    ],
)
def test_rejects_fresh_proc_identity_drift_without_signalling(
    module, tmp_path, field, replacement, error
):
    root = evidence_root(tmp_path, field)
    value = entry(root)
    write_manifest(root, [value])
    observed = proc(value)
    observed[field] = replacement
    sent = []
    with pytest.raises(ValueError, match=error):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: observed,
            signal_group=lambda *args: sent.append(args),
        )
    assert sent == []


def test_rejects_identity_drift_between_readback_and_signal(module, tmp_path):
    root = evidence_root(tmp_path, "race")
    value = entry(root)
    write_manifest(root, [value])
    observations = [proc(value), proc(value) | {"start_time": 999999}]
    sent = []

    with pytest.raises(ValueError, match="IDENTITY_DRIFT"):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: observations.pop(0),
            signal_group=lambda *args: sent.append(args),
        )
    assert sent == []


def test_rejects_manifest_drift_between_proc_readback_and_signal(module, tmp_path):
    root = evidence_root(tmp_path, "manifest-race")
    value = entry(root)
    write_manifest(root, [value])
    reads = 0
    sent = []

    def read(_pid):
        nonlocal reads
        reads += 1
        if reads == 1:
            write_manifest(root, [dict(value, start_time=value["start_time"] + 1)])
        return proc(value)

    with pytest.raises(ValueError, match="MANIFEST_DRIFT"):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=read,
            signal_group=lambda *args: sent.append(args),
        )
    assert sent == []


def test_rejects_symlinked_root_manifest_and_worker_spec(module, tmp_path):
    real = evidence_root(tmp_path, "real")
    value = entry(real)
    write_manifest(real, [value])
    linked_root = evidence_root(tmp_path, "linked")
    linked_root.parent.mkdir(parents=True, exist_ok=True)
    linked_root.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="SYMLINK"):
        module.inject_fault(
            [str(linked_root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )

    worker_root = evidence_root(tmp_path, "worker-spec-link")
    worker_value = entry(worker_root)
    write_manifest(worker_root, [worker_value])
    worker_spec = worker_root / "workers/worker-01/worker-spec.json"
    worker_saved = worker_spec.with_name("worker-spec-real.json")
    worker_spec.rename(worker_saved)
    worker_spec.symlink_to(worker_saved)
    with pytest.raises(ValueError, match="TARGET_COUNT"):
        module.inject_fault(
            [str(worker_root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(worker_value),
            signal_group=lambda *_: None,
        )

    manifest = real / "owned-processes.json"
    saved = real / "manifest-real.json"
    manifest.rename(saved)
    manifest.symlink_to(saved)
    with pytest.raises(ValueError, match="SYMLINK"):
        module.inject_fault(
            [str(real), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


def test_rejects_broker_spec_batch_mismatch(module, tmp_path):
    root = evidence_root(tmp_path, "broker-batch")
    value = entry(root, "broker")
    write_manifest(root, [value])
    spec = root / "ipc/broker/broker-spec.json"
    document = json.loads(spec.read_text(encoding="utf-8"))
    document["batch_id"] = "other-batch"
    spec.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="BATCH_MISMATCH"):
        module.inject_fault(
            [str(root), "broker", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


def test_rejects_broker_cmdline_bound_to_a_different_ipc_mount(module, tmp_path):
    root = evidence_root(tmp_path, "broker-mount")
    value = entry(root, "broker")
    value["cmdline"][3] = f"{root / 'ipc/not-broker'}:/runtime:rw"
    write_manifest(root, [value])

    with pytest.raises(ValueError, match="TARGET_COUNT"):
        module.inject_fault(
            [str(root), "broker", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


def test_rejects_worker_cmdline_that_does_not_bind_exact_target(module, tmp_path):
    root = evidence_root(tmp_path, "wrong-worker")
    value = entry(root, "worker-02")
    write_manifest(root, [value])
    with pytest.raises(ValueError, match="TARGET_COUNT"):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


def test_manifest_schema_is_closed_and_rejects_partial_or_duplicate_json(module, tmp_path):
    root = evidence_root(tmp_path, "schema")
    value = entry(root)
    write_manifest(root, [value], extra={"unexpected": True})
    with pytest.raises(ValueError, match="MANIFEST"):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )

    (root / "owned-processes.json").write_text(
        '{"schema_version":1,"batch_id":"batch-1","batch_id":"batch-2","processes":[]}',
        encoding="utf-8",
    )
    (root / "owned-processes.json").chmod(0o600)
    with pytest.raises(ValueError, match="MANIFEST"):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


@pytest.mark.parametrize("target", ["root", "manifest"])
def test_rejects_group_or_world_access_before_deriving_signal_authority(
        module, tmp_path, target):
    root = evidence_root(tmp_path, f"permissions-{target}")
    value = entry(root)
    write_manifest(root, [value])
    if target == "root":
        root.chmod(0o750)
    else:
        (root / "owned-processes.json").chmod(0o640)

    with pytest.raises(ValueError, match="(EVIDENCE_ROOT|MANIFEST)"):
        module.inject_fault(
            [str(root), "worker-01", "TERM"],
            proc_reader=lambda _pid: proc(value),
            signal_group=lambda *_: None,
        )


def test_proc_stat_parser_handles_process_names_with_spaces(module):
    fields = ["S", *[str(value) for value in range(4, 23)]]
    raw = "41001 (worker process name) " + " ".join(fields)
    assert module._proc_start_time(raw) == 22

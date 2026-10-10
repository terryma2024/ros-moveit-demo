"""Task 14 Step 1: prove exclusive ownership before a qualifier starts its own stack.

The gate reads the five resources the plan names - the fresh process table, the ROS graph, the GPU
compute processes, tmux ownership and the evidence root - plus the frozen runtime identity, and refuses
when any of them is already held by another detector, MuJoCo instance, controller owner or campaign. It
starts nothing: every probe is read-only, it never creates a ROS node beyond the short-lived
``ros2 node list --no-daemon`` discovery process, and the only file it writes is its own receipt inside
a brand-new run root. The qualification phases own every start and teardown after this gate passes.

The gate fails closed. A probe that cannot run is a refusal (``OWNERSHIP_PROBE_FAILED``), never a silent
pass, because "could not look" is not "nothing is there".
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from so101_demo.act.head_search_qualification import (
    _require_new_root,
    process_start_ticks,
    write_exclusive,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

EXCLUSIVE_OWNERSHIP_OK = "EXCLUSIVE_OWNERSHIP_OK"
EXCLUSIVE_OWNERSHIP_REFUSED = "EXCLUSIVE_OWNERSHIP_REFUSED"
RECEIPT_NAME = "exclusive-ownership.json"
OPERATION = "QUALIFICATION_OWNERSHIP_CHECK"

#: durable evidence on this host lives under this platform root (repository rule)
EVIDENCE_ROOT_PLATFORM = Path("/data/work/so101-evidence")

#: the approved bundle promotes exactly this many values, and Task 14 reads all of them back effective
APPROVED_VALUE_COUNT = 17

#: argv basenames that mean a ROS/MuJoCo/controller owner already exists; matched exactly or as a
#: dotted module suffix, so a *test file* named after one of them is never mistaken for a running owner
STACK_OWNERS = (
    "move_group",
    "ros2_control_node",
    "mujoco_ros2_control",
    "robot_state_publisher",
    "rviz2",
    "gzserver",
    "gzclient",
    "gazebo",
    "spawner",
    "qualification_stack",
    "qualification",
    "ros2_control",
)

#: argv basenames that mean another detector or campaign process exists
DETECTOR_OWNERS = (
    "so101_head_search_calibration",
    "so101_head_search_smoke",
    "head_search_calibration",
    "head_search_smoke",
    "run_qualification",
    "generate_yolo_seg_dataset",
    "train_yolo_seg",
    "evaluate_head_search_yolo_candidates",
)

#: fragments that name an owner wherever they sit, including inside a ``.py`` path
OWNER_FRAGMENTS = {
    "stack": ("so101_unified_web_server", "mujoco_ros2_control"),
    "detector": ("ultralytics", "yolo11"),
}

CommandRunner = Callable[..., "tuple[int, str, str]"]
ObservationFactory = Callable[[], "ResourceObservation"]


@dataclass(frozen=True)
class ResourceObservation:
    """One read-only probe: the command it ran, its exit code, its rows and its verdict."""

    name: str
    command: tuple[str, ...] = ()
    rc: int = 0
    rows: tuple[Mapping[str, object], ...] = ()
    value: str | None = None
    note: str = ""

    def document(self) -> dict:
        return {
            "name": self.name,
            "command": list(self.command),
            "rc": self.rc,
            "rows": [dict(row) for row in self.rows],
            "value": self.value,
            "note": self.note,
        }


def run_command(argv: Sequence[str], *, timeout: float = 20.0) -> tuple[int, str, str]:
    """Run one read-only probe; a missing binary or a timeout is a failure code, not an exception."""

    try:
        completed = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as error:
        return 127, "", f"{argv[0]}: {error}"
    except subprocess.TimeoutExpired:
        return 124, "", f"{argv[0]}: timed out after {timeout}s"
    return completed.returncode, completed.stdout, completed.stderr


def _probe_failed(name: str, argv: Sequence[str], rc: int, detail: str) -> ResourceObservation:
    return ResourceObservation(
        name=name,
        command=tuple(str(item) for item in argv),
        rc=rc,
        note=f"PROBE_FAILED: {detail.strip() or f'rc={rc}'}",
    )


# --- pure readers (synthetic fixtures are the only input in tests) ------------------------------------


def classify_owner_command(argv: Sequence[str]) -> str | None:
    """Name the owner kind a command line belongs to, or None when it owns none of these resources."""

    for token in argv:
        basename = Path(str(token)).name
        if not basename:
            continue
        for kind, owners in (("stack", STACK_OWNERS), ("detector", DETECTOR_OWNERS)):
            for owner in owners:
                if basename == owner or basename.endswith("." + owner):
                    return kind
        for kind, fragments in OWNER_FRAGMENTS.items():
            if any(fragment in basename for fragment in fragments):
                return kind
    return None


def parse_gpu_compute_apps(text: str) -> list[dict]:
    """The `nvidia-smi --query-compute-apps` CSV rows, with unnamed values kept honest as None."""

    rows: list[dict] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("pid"):
            continue
        parts = [part.strip() for part in stripped.split(",")]
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        memory = None
        if len(parts) > 2:
            match = re.match(r"(\d+)", parts[2])
            memory = int(match.group(1)) if match else None
        rows.append({"pid": int(parts[0]), "process_name": parts[1], "used_memory_mib": memory})
    return rows


def parse_ros_nodes(text: str) -> list[str]:
    """The node names `ros2 node list` printed, in order, ignoring blank lines."""

    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_tmux_panes(text: str) -> list[dict]:
    """The `session<TAB>pane_pid<TAB>current_command` rows of `tmux list-panes -a`."""

    panes: list[dict] = []
    for line in text.splitlines():
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 3:
            continue
        panes.append(
            {
                "session": parts[0],
                "pane_pid": int(parts[1]) if parts[1].strip().isdigit() else None,
                "command": parts[2],
            }
        )
    return panes


def _read_argv(proc_root: Path, pid: int) -> list[str]:
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return []
    return [item.decode("utf-8", "replace") for item in raw.split(b"\0") if item]


def _read_stat(proc_root: Path, pid: int) -> tuple[int, int]:
    """(ppid, starttime) for one process, or (0, 0) when the kernel will not say."""

    try:
        text = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return 0, 0
    fields = text.rsplit(")", 1)[-1].split()
    if len(fields) < 20:
        return 0, 0
    return int(fields[1]), int(fields[19])


def _child_pids(proc_root: Path, pid: int) -> list[int]:
    try:
        text = (proc_root / str(pid) / "task" / str(pid) / "children").read_text(encoding="utf-8")
    except OSError:
        return []
    return [int(item) for item in text.split() if item.isdigit()]


def process_ancestry(pid: int | None = None, *, proc_root: Path = Path("/proc")) -> tuple[int, ...]:
    """This process and every ancestor, so the gate never reports its own launcher as an owner."""

    current = os.getpid() if pid is None else pid
    chain = [current]
    for _ in range(64):
        parent, _start = _read_stat(proc_root, current)
        if parent <= 1 or parent in chain:
            break
        chain.append(parent)
        current = parent
    return tuple(chain)


# --- the five resources -------------------------------------------------------------------------------


def observe_process_table(
    *, proc_root: Path = Path("/proc"), excluded_pids: Sequence[int] = ()
) -> ResourceObservation:
    """Every live process whose command line belongs to a stack, controller or detector owner."""

    excluded = {int(pid) for pid in excluded_pids}
    rows: list[dict] = []
    try:
        entries = sorted(
            proc_root.iterdir(), key=lambda item: int(item.name) if item.name.isdigit() else 0
        )
    except OSError as error:  # pragma: no cover - a host without /proc cannot pass this gate
        return _probe_failed("process_table", (), 1, str(error))
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid in excluded:
            continue
        argv = _read_argv(proc_root, pid)
        if not argv:
            continue
        kind = classify_owner_command(argv)
        if kind is None:
            continue
        ppid, started = _read_stat(proc_root, pid)
        rows.append(
            {
                "pid": pid,
                "ppid": ppid,
                "kind": kind,
                "command": " ".join(argv),
                "started_ticks": started,
            }
        )
    return ResourceObservation("process_table", rc=0, rows=tuple(rows))


def observe_ros_graph(
    *, runner: CommandRunner = run_command, spin_time: float = 2.0
) -> ResourceObservation:
    """Every node discoverable on this domain, asked without spawning or reusing a daemon."""

    argv = ("ros2", "node", "list", "--no-daemon", "--spin-time", str(spin_time))
    rc, stdout, stderr = runner(argv, timeout=max(20.0, spin_time + 10.0))
    if rc != 0:
        return _probe_failed("ros_graph", argv, rc, stderr)
    nodes = parse_ros_nodes(stdout)
    return ResourceObservation(
        "ros_graph",
        command=tuple(argv),
        rc=0,
        rows=tuple({"node": node} for node in nodes),
        value="clean" if not nodes else "not-empty",
    )


def observe_gpu_processes(*, runner: CommandRunner = run_command) -> ResourceObservation:
    """Every compute application the driver reports, because one CUDA detector is the whole budget."""

    argv = (
        "nvidia-smi",
        "--query-compute-apps=pid,process_name,used_memory",
        "--format=csv,noheader",
    )
    rc, stdout, stderr = runner(argv, timeout=20.0)
    if rc != 0:
        return _probe_failed("gpu_processes", argv, rc, stderr)
    return ResourceObservation(
        "gpu_processes", command=tuple(argv), rc=0, rows=tuple(parse_gpu_compute_apps(stdout))
    )


def observe_tmux_panes(
    *,
    runner: CommandRunner = run_command,
    proc_root: Path = Path("/proc"),
    excluded_pids: Sequence[int] = (),
) -> ResourceObservation:
    """Every tmux pane whose process tree runs an owner, so a pane is not used to hide a second stack."""

    argv = (
        "tmux",
        "list-panes",
        "-a",
        "-F",
        "#{session_name}\t#{pane_pid}\t#{pane_current_command}",
    )
    rc, stdout, stderr = runner(argv, timeout=20.0)
    if rc != 0:
        # a host with no tmux server simply owns no panes; a missing tmux binary is a failed probe
        if "no server running" in stderr or "error connecting to" in stderr:
            return ResourceObservation(
                "tmux_panes", command=tuple(argv), rc=0, note="no tmux server"
            )
        return _probe_failed("tmux_panes", argv, rc, stderr)
    excluded = {int(pid) for pid in excluded_pids}
    rows: list[dict] = []
    for pane in parse_tmux_panes(stdout):
        pane_pid = pane["pane_pid"]
        if pane_pid is not None and pane_pid in excluded:
            continue
        tokens: list[str] = [str(pane["command"])]
        if pane_pid is not None:
            tokens.extend(_read_argv(proc_root, pane_pid))
            for child in _child_pids(proc_root, pane_pid):
                tokens.extend(_read_argv(proc_root, child))
        kind = classify_owner_command(tokens)
        if kind is None:
            continue
        rows.append({**pane, "kind": kind, "command_line": " ".join(tokens).strip()})
    return ResourceObservation("tmux_panes", command=tuple(argv), rc=0, rows=tuple(rows))


def observe_evidence_root(
    root: Path, *, within: Path | None = EVIDENCE_ROOT_PLATFORM
) -> ResourceObservation:
    """The registered campaign root must exist, be writable and live under the platform root."""

    path = Path(root)
    argv = ("stat", str(path))
    if not path.exists():
        return ResourceObservation(
            "evidence_root", command=argv, rc=0, value="unusable", note=f"MISSING: {path}"
        )
    if not path.is_dir():
        return ResourceObservation(
            "evidence_root", command=argv, rc=0, value="unusable", note=f"NOT_A_DIRECTORY: {path}"
        )
    resolved = path.resolve()
    if within is not None:
        platform = Path(within).resolve()
        if resolved != platform and platform not in resolved.parents:
            return ResourceObservation(
                "evidence_root",
                command=argv,
                rc=0,
                value="unusable",
                note=f"OUTSIDE_PLATFORM_ROOT: {resolved} is not under {platform}",
            )
    if not os.access(resolved, os.W_OK):
        return ResourceObservation(
            "evidence_root", command=argv, rc=0, value="unusable", note=f"NOT_WRITABLE: {resolved}"
        )
    return ResourceObservation(
        "evidence_root", command=argv, rc=0, value="usable", note=str(resolved)
    )


def observe_planned_run_root(root: Path | None) -> ResourceObservation:
    """The qualifier's future run root must not exist: the gate never pre-creates or resumes one."""

    if root is None:
        return ResourceObservation("planned_run_root", rc=0, value="absent", note="none declared")
    path = Path(root)
    return ResourceObservation(
        "planned_run_root",
        command=("test", "-e", str(path)),
        rc=0,
        value="exists" if path.exists() else "absent",
        note=str(path),
    )


def observe_ament_prefix(
    *, runner: CommandRunner = run_command, package: str = "so101_demo_py"
) -> ResourceObservation:
    """Which install prefix the environment resolves the package to; no ROS graph is involved."""

    argv = ("ros2", "pkg", "prefix", package)
    rc, stdout, stderr = runner(argv, timeout=20.0)
    if rc != 0:
        return _probe_failed("ament_prefix", argv, rc, stderr)
    return ResourceObservation(
        "ament_prefix", command=tuple(argv), rc=0, value=stdout.strip() or None
    )


def default_observers(
    *,
    evidence_root: Path,
    planned_run_root: Path | None = None,
    excluded_pids: Sequence[int] | None = None,
    proc_root: Path = Path("/proc"),
    runner: CommandRunner = run_command,
    within: Path | None = EVIDENCE_ROOT_PLATFORM,
    package: str = "so101_demo_py",
) -> dict[str, ObservationFactory]:
    """The five plan-named resources plus the planned root and the resolved package prefix."""

    excluded = tuple(
        process_ancestry(proc_root=proc_root) if excluded_pids is None else excluded_pids
    )
    return {
        "process_table": lambda: observe_process_table(proc_root=proc_root, excluded_pids=excluded),
        "ros_graph": lambda: observe_ros_graph(runner=runner),
        "gpu_processes": lambda: observe_gpu_processes(runner=runner),
        "tmux_panes": lambda: observe_tmux_panes(
            runner=runner, proc_root=proc_root, excluded_pids=excluded
        ),
        "evidence_root": lambda: observe_evidence_root(evidence_root, within=within),
        "planned_run_root": lambda: observe_planned_run_root(planned_run_root),
        "ament_prefix": lambda: observe_ament_prefix(runner=runner, package=package),
    }


# --- the runtime of record ----------------------------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def default_production_config(final_run: Path) -> Path:
    """The installed promoted config inside the frozen root; the repo copy is not the runtime's."""

    return (
        Path(final_run)
        / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_runtime.json"
    )


def read_runtime_identity(final_run: Path, *, production_config: Path | None = None) -> dict:
    """Read the frozen runtime's own identity off disk, or refuse by name when it cannot be read."""

    root = Path(final_run)
    if not root.is_dir():
        raise ValueError(f"RUNTIME_IDENTITY_UNREADABLE: {root} is not a directory")
    commit_path = root / "source-commit.txt"
    if not commit_path.is_file():
        raise ValueError(f"RUNTIME_IDENTITY_UNREADABLE: {commit_path} is missing")
    config_path = (
        Path(production_config)
        if production_config is not None
        else default_production_config(root)
    )
    if not config_path.is_file():
        raise ValueError(f"RUNTIME_IDENTITY_UNREADABLE: {config_path} is missing")
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"RUNTIME_IDENTITY_UNREADABLE: {config_path}: {error}") from error
    if not isinstance(document, Mapping):
        raise ValueError(f"RUNTIME_IDENTITY_UNREADABLE: {config_path} is not a mapping")
    values = document.get("values")
    if not isinstance(values, Mapping):
        raise ValueError(f"RUNTIME_IDENTITY_UNREADABLE: {config_path} declares no values block")
    weight_path = str(document.get("weight_path", ""))
    observed = None
    if weight_path and Path(weight_path).is_file():
        observed = _digest(Path(weight_path))
    return {
        "final_run": str(root),
        "source_commit": commit_path.read_text(encoding="utf-8").strip(),
        "setup_bash_present": (root / "install/setup.bash").is_file(),
        "production_config": str(config_path),
        "production_config_sha256": _digest(config_path),
        "values_count": len(values),
        "values_sha256": canonical_sha256(dict(values)),
        "allow_cpu_fallback": document.get("allow_cpu_fallback"),
        "cuda_device": str(document.get("cuda_device", "")),
        "weight_path": weight_path,
        "weight_sha256_declared": str(document.get("weight_sha256", "")),
        "weight_sha256_observed": observed,
    }


# --- the gate -----------------------------------------------------------------------------------------


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def check_exclusive_ownership(
    *,
    run_root: Path,
    evidence_root: Path,
    runtime: Mapping[str, object] | None = None,
    expected_runtime: Mapping[str, object] | None = None,
    expected_package_prefix: str | None = None,
    planned_run_root: Path | None = None,
    observers: Mapping[str, ObservationFactory] | None = None,
    excluded_pids: Sequence[int] | None = None,
    now: Callable[[], str] | None = None,
) -> dict:
    """Claim a brand-new gate root, read every resource, and write the receipt whatever the verdict.

    The receipt is evidence, so it is written for a refusal too: the refusal codes, the observations
    and the runtime identity are what a later reviewer reads back.
    """

    root = _require_new_root(Path(run_root))
    excluded = tuple(process_ancestry() if excluded_pids is None else excluded_pids)
    if observers is None:
        observers = default_observers(
            evidence_root=Path(evidence_root),
            planned_run_root=planned_run_root,
            excluded_pids=excluded,
        )

    observations: dict[str, dict] = {}
    for name in sorted(observers):
        try:
            observation = observers[name]()
        except Exception as error:  # noqa: BLE001 - a probe that raises must fail closed, not pass
            observation = ResourceObservation(
                name=name, rc=1, note=f"PROBE_FAILED: {type(error).__name__}: {error}"
            )
        observations[str(name)] = observation.document()

    refusals: list[dict] = []

    def refuse(code: str, resource: str, detail: str) -> None:
        refusals.append({"code": code, "resource": resource, "detail": detail})

    for name, observation in observations.items():
        if observation["rc"] != 0 or str(observation["note"]).startswith("PROBE_FAILED"):
            refuse(
                "OWNERSHIP_PROBE_FAILED",
                name,
                str(observation["note"]) or f"rc={observation['rc']}",
            )
    for row in observations.get("process_table", {}).get("rows", ()):
        kind = str(row.get("kind"))
        if kind == "stack":
            refuse(
                "STACK_OWNER_ACTIVE", "process_table", f"pid {row.get('pid')}: {row.get('command')}"
            )
        elif kind == "detector":
            refuse(
                "DETECTOR_OWNER_ACTIVE",
                "process_table",
                f"pid {row.get('pid')}: {row.get('command')}",
            )
    for row in observations.get("ros_graph", {}).get("rows", ()):
        refuse("ROS_GRAPH_NOT_EMPTY", "ros_graph", f"node {row.get('node')} is already visible")
    for row in observations.get("gpu_processes", {}).get("rows", ()):
        refuse(
            "GPU_COMPUTE_APP_ACTIVE",
            "gpu_processes",
            f"pid {row.get('pid')} ({row.get('process_name')}) holds the GPU",
        )
    for row in observations.get("tmux_panes", {}).get("rows", ()):
        refuse(
            "TMUX_OWNER_ACTIVE",
            "tmux_panes",
            f"session {row.get('session')} pid {row.get('pane_pid')} runs {row.get('kind')}",
        )
    if expected_package_prefix is not None:
        observed_prefix = observations.get("ament_prefix", {}).get("value")
        if observed_prefix != expected_package_prefix:
            refuse(
                "PACKAGE_PREFIX_MISMATCH",
                "ament_prefix",
                f"expected {expected_package_prefix!r}, observed {observed_prefix!r}",
            )
    planned = observations.get("planned_run_root", {})
    if planned.get("value") == "exists":
        refuse("PLANNED_RUN_ROOT_ALREADY_EXISTS", "planned_run_root", str(planned.get("note")))
    evidence = observations.get("evidence_root", {})
    if evidence.get("value") != "usable":
        refuse("EVIDENCE_ROOT_UNUSABLE", "evidence_root", str(evidence.get("note")))

    if runtime is not None:
        if runtime.get("allow_cpu_fallback") is not False:
            refuse(
                "RUNTIME_CUDA_REQUIRED",
                "runtime",
                f"allow_cpu_fallback={runtime.get('allow_cpu_fallback')!r} must be False",
            )
        if int(runtime.get("values_count", 0)) != APPROVED_VALUE_COUNT:
            refuse(
                "RUNTIME_VALUES_INCOMPLETE",
                "runtime",
                f"{runtime.get('values_count')} values, {APPROVED_VALUE_COUNT} approved",
            )
        declared = runtime.get("weight_sha256_declared")
        observed_weight = runtime.get("weight_sha256_observed")
        if not observed_weight or observed_weight != declared:
            refuse(
                "RUNTIME_WEIGHTS_MISMATCH",
                "runtime",
                f"declared {declared!r}, observed {observed_weight!r}",
            )
        if runtime.get("setup_bash_present") is not True:
            refuse("RUNTIME_OF_RECORD_MISMATCH", "runtime", "install/setup.bash is missing")
        for key, expected in sorted((expected_runtime or {}).items()):
            observed_value = runtime.get(key)
            if observed_value != expected:
                refuse(
                    "RUNTIME_OF_RECORD_MISMATCH",
                    "runtime",
                    f"{key}: expected {expected!r}, observed {observed_value!r}",
                )
    elif expected_runtime:
        refuse("RUNTIME_OF_RECORD_MISMATCH", "runtime", "no runtime identity was read")

    document = {
        "schema_version": 1,
        "operation": OPERATION,
        "status": EXCLUSIVE_OWNERSHIP_OK if not refusals else EXCLUSIVE_OWNERSHIP_REFUSED,
        "checked_at_utc": (now or _utc_now)(),
        "run_root": str(root),
        "evidence_root": str(evidence_root),
        "planned_run_root": str(planned_run_root) if planned_run_root is not None else None,
        "owner": {
            "pid": os.getpid(),
            "started_ticks": process_start_ticks(),
            "argv_sha256": hashlib.sha256(" ".join(sys.argv).encode("utf-8")).hexdigest(),
            "excluded_pids": list(excluded),
        },
        "runtime": dict(runtime) if runtime is not None else None,
        "expected_runtime": dict(expected_runtime) if expected_runtime else None,
        "expected_package_prefix": expected_package_prefix,
        "observations": observations,
        "refusals": refusals,
    }
    write_exclusive(root, RECEIPT_NAME, document)
    return document

"""The full task station control run and the fixed dylib farm run."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from so101_demo.cli.macos_station.contracts import (
    _CLI_DEFAULT_TIMEOUT_S,
    CONTROLLER_RELATIVE_PATH,
    FARM_CONTRACT_RECEIPT_SCHEMA_VERSION,
    PLUGIN_BASENAME,
    READINESS_RELATIVE_PATH,
    VENDOR_BASENAME,
    StationDiagnosticError,
    StationMode,
)
from so101_demo.cli.macos_station.diagnostic_run import (
    _atomic_write_json,
    _bounded_cleanup,
    _command_executable,
    _controller_process,
    _descendants,
    _first_bad_phase,
    _phase_markers,
    _process_rows,
    _readiness_argv,
    _socket_residue,
)
from so101_demo.cli.macos_station.farm_contract import (
    FixedDylibFarmContract,
    FixedFarmRuntimePaths,
    _farm_round_binding,
    _owner_ancestry,
    _write_farm_report,
    load_fixed_dylib_farm_contract,
)
from so101_demo.cli.macos_station.observation import full_task_station_argv


def run_full_task_station_control(
    *, manifest_path: Path, binding_path: Path, control: str
) -> dict[str, object]:
    """Launch, attest, stop, and classify one manifest-bound full-station control."""

    from so101_demo.runtime.macos_dlopen_gate.control import (
        GateAControlObservation,
        GateARunBinding,
    )
    from so101_demo.runtime.macos_dlopen_gate.farm import verify_filtered_ros_dylib_farm
    from so101_demo.runtime.macos_dlopen_gate.semantics import _closure_dylib_basenames
    from so101_demo.runtime.macos_dlopen_probe import load_binding, load_manifest, write_json
    from so101_demo.runtime.runtime_closure.attestation import build_runtime_process_attestation
    from so101_demo.runtime.runtime_closure.build import (
        default_loaded_image_probe,
        read_process_birth_identity,
        verify_runtime_closure,
    )
    from so101_demo.runtime.runtime_closure.identities import (
        ControllerRuntimeOwnerBinding,
        RuntimeClosureError,
    )

    manifest = load_manifest(manifest_path)
    binding = load_binding(binding_path)
    if control != binding.control:
        raise StationDiagnosticError("STATION_CONTROL_MISMATCH", control)
    expected = GateARunBinding.create(
        run_root=binding.run_root,
        session_id=binding.session_id,
        ros_domain_id=binding.ros_domain_id,
        control=control,
        manifest=manifest,
    )
    if (
        expected.expanded_argv != binding.expanded_argv
        or dict(expected.expanded_environment)
        != dict(binding.expanded_environment)
        or expected.normalized_semantic_sha256
        != binding.normalized_semantic_sha256
    ):
        raise StationDiagnosticError("STATION_SEMANTIC_DRIFT")
    expected_argv = full_task_station_argv(
        session_id=binding.session_id,
        task_evidence_root=binding.task_evidence_root,
        scene=manifest.scene_path,
        readiness_timeout_s=90.0,
        python_executable=manifest.semantic.python_executable,
        ros2_script=manifest.semantic.ros2_script,
    )
    if binding.expanded_argv != expected_argv:
        raise StationDiagnosticError("STATION_SEMANTIC_DRIFT", "argv")
    verify_filtered_ros_dylib_farm(
        manifest.ros_dylib_farm,
        excluded_basenames=_closure_dylib_basenames(manifest.closure),
    )
    verify_runtime_closure(
        manifest.closure,
        install_root=manifest.install_root,
        source_commit=manifest.closure.source_commit,
        mujoco_ros2_control_commit=manifest.closure.mujoco_ros2_control_commit,
        environment=manifest.semantic.environment,
    )
    intent_path = binding.run_root / "controller-runtime-spawn-intent.json"
    write_json(
        intent_path,
        {
            "role": "controller_runtime",
            "ancestor_role": "full_task_station_launcher",
            "executable_pattern": "mujoco_ros2_control/ros2_control_node",
            "manifest_sha256": manifest.sha256,
        },
    )
    stdout_path = binding.run_root / "station.stdout.log"
    stderr_path = binding.run_root / "station.stderr.log"
    identities: dict[int, int] = {}
    controller_attestation = None
    controller_identity: dict[str, object] | None = None
    collector_healthy = True
    invalid_reasons: list[str] = []
    timed_out = False
    readiness_document: dict[str, object] = {}
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        launch = subprocess.Popen(
            list(binding.expanded_argv),
            env=dict(binding.expanded_environment),
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        launch_birth = read_process_birth_identity(int(launch.pid))
        identities[int(launch.pid)] = launch_birth
        try:
            controller_pid, controller_command, descendants = _controller_process(
                int(launch.pid), deadline=time.monotonic() + 30.0
            )
            for pid, _parent, _command in descendants:
                try:
                    identities[pid] = read_process_birth_identity(pid)
                except RuntimeClosureError:
                    continue
            controller_birth_before = read_process_birth_identity(controller_pid)
            identities[controller_pid] = controller_birth_before
            controller_executable = _command_executable(controller_command)
            readiness = subprocess.run(
                _readiness_argv(manifest),
                check=False,
                capture_output=True,
                text=True,
                env=dict(binding.expanded_environment),
                timeout=100.0,
            )
            for line in reversed(readiness.stdout.splitlines()):
                if line.startswith("{"):
                    readiness_document = json.loads(line)
                    break
            ready = bool(readiness.returncode == 0 and readiness_document.get("ready"))
            loaded_images = default_loaded_image_probe(controller_pid)
            controller_birth_after = read_process_birth_identity(controller_pid)
            controller_identity = {
                "role": "controller_runtime",
                "pid": controller_pid,
                "birth_identity_before": controller_birth_before,
                "birth_identity_after": controller_birth_after,
                "executable": str(controller_executable),
                "command": controller_command,
            }
            try:
                controller_attestation = build_runtime_process_attestation(
                    closure=manifest.closure,
                    install_root=manifest.install_root,
                    role="controller_runtime",
                    pid=controller_pid,
                    birth_identity_before=controller_birth_before,
                    birth_identity_after=controller_birth_after,
                    executable=controller_executable,
                    loaded_images=loaded_images,
                    required_relative_paths=(
                        manifest.plugin_relative_path,
                        manifest.vendor_relative_path,
                    ),
                    owner_binding=ControllerRuntimeOwnerBinding(
                        owner_root_role="full_task_station_launcher",
                        owner_root_pid=int(launch.pid),
                        owner_root_birth_identity=launch_birth,
                        spawn_role="controller_runtime",
                        # The historical N/P/F route keeps its own observation: it pins the
                        # relative path it actually read back, while the A2 farm route pins
                        # the frozen CONTROLLER_RELATIVE_PATH constant.
                        expected_executable_relative_path=(
                            controller_executable.relative_to(manifest.install_root).as_posix()
                        ),
                        ancestry=_owner_ancestry(
                            descendants,
                            root_pid=int(launch.pid),
                            root_role="full_task_station_launcher",
                            root_birth_identity=launch_birth,
                            root_executable=str(controller_executable),
                            target_pid=controller_pid,
                            target_birth_identity=controller_birth_before,
                            target_executable=str(controller_executable),
                        ),
                        manifest_sha256=manifest.sha256,
                        closure_prefixes=(str(manifest.install_root),),
                        dylib_farm_root=str(manifest.install_root),
                    ),
                    plugin_relative_path=manifest.plugin_relative_path,
                    vendor_relative_path=manifest.vendor_relative_path,
                )
            except RuntimeClosureError as error:
                if ready:
                    invalid_reasons.append(error.code)
        except subprocess.TimeoutExpired:
            timed_out = True
            ready = False
            invalid_reasons.append("READINESS_SUBPROCESS_TIMEOUT")
        except RuntimeClosureError as error:
            ready = False
            invalid_reasons.append(error.code)
        except StationDiagnosticError as error:
            ready = False
            collector_healthy = error.code != "STATION_PROCESS_COLLECTOR_FAILED"
            invalid_reasons.append(error.code)
        finally:
            stdout.flush()
            stderr.flush()
            try:
                rows = _process_rows()
                for pid, _parent, _command in _descendants(int(launch.pid), rows):
                    try:
                        identities.setdefault(pid, read_process_birth_identity(pid))
                    except RuntimeClosureError:
                        continue
            except StationDiagnosticError:
                collector_healthy = False
                invalid_reasons.append("STATION_PROCESS_COLLECTOR_FAILED")
            cleanup = _bounded_cleanup(launch, identities)
    log_text = stdout_path.read_text(encoding="utf-8", errors="replace") + "\n" + stderr_path.read_text(
        encoding="utf-8", errors="replace"
    )
    markers = _phase_markers(log_text, ready=ready)
    dlopen_path = binding.run_root / "dlopen.json"
    if not dlopen_path.is_file():
        invalid_reasons.append("DLOPEN_OBSERVATION_MISSING")
        dlopen_document: dict[str, object] = {}
    else:
        dlopen_document = json.loads(dlopen_path.read_text(encoding="utf-8"))
    marker_list = dlopen_document.get("markers", [])
    dlopen_marker = marker_list[-1] if marker_list else None
    loader_error = dlopen_document.get("dlerror")
    vendor_token = "@rpath/libmujoco.3.4.0.dylib"
    exact_vendor_missing = bool(
        dlopen_marker == "DLOPEN_FAILED"
        and isinstance(loader_error, str)
        and vendor_token in loader_error
        and vendor_token in log_text
    )
    cleanup_complete = bool(cleanup["complete"])
    sockets = _socket_residue(binding.run_root)
    if sockets:
        cleanup_complete = False
        invalid_reasons.append("IPC_RESIDUE")
    plugin_attested = False
    vendor_attested = False
    if controller_attestation is not None:
        attested_paths = {
            item.relative_path for item in controller_attestation.loaded_images
        }
        plugin_attested = manifest.plugin_relative_path in attested_paths
        vendor_attested = manifest.vendor_relative_path in attested_paths
    process_stable = bool(
        controller_identity
        and controller_identity["birth_identity_before"]
        == controller_identity["birth_identity_after"]
    )
    executable_attested = bool(
        controller_identity
        and Path(str(controller_identity["executable"])).is_relative_to(
            manifest.install_root
        )
    )
    first_bad = None if ready else _first_bad_phase(markers)
    observation = GateAControlObservation(
        invariants_valid=not invalid_reasons,
        collector_healthy=collector_healthy,
        process_identity_stable=process_stable,
        controller_role_attested=controller_identity is not None,
        controller_executable_attested=executable_attested,
        dlopen_marker=dlopen_marker,
        loader_error=(None if loader_error is None else str(loader_error)),
        exact_vendor_missing=exact_vendor_missing,
        plugin_image_attested=plugin_attested,
        vendor_image_attested=vendor_attested,
        ros_instance_markers=markers,
        ready=ready,
        first_bad_phase=first_bad,
        timed_out=timed_out,
        cleanup_complete=cleanup_complete,
        invalid_reasons=tuple(sorted(set(invalid_reasons))),
    )
    report = {
        "schema_version": 1,
        "control": control,
        "manifest_sha256": manifest.sha256,
        "binding": binding.as_document(),
        "spawn_intent": str(intent_path),
        "controller_identity": controller_identity,
        "runtime_process_attestation": (
            None
            if controller_attestation is None
            else controller_attestation.as_document()
        ),
        "readiness": readiness_document,
        "phase_markers": list(markers),
        "cleanup": cleanup,
        "ipc_residue": list(sockets),
        "control_observation": observation.as_document(),
        "observation_class": observation.observation_class.value,
    }
    write_json(binding.report_path, report)
    write_json(binding.run_root / "control-observation.json", observation.as_document())
    return report


def run_fixed_dylib_farm_full_task_station(
    *,
    farm_contract_receipt: Path,
    run_binding_path: Path,
    output_path: Path,
    timeout_s: float = _CLI_DEFAULT_TIMEOUT_S,
    paths: FixedFarmRuntimePaths | None = None,
    spawn: Callable[..., object] | None = None,
    process_rows: Callable[[], tuple[tuple[int, int, str], ...]] | None = None,
    loaded_image_probe: Callable[[int], tuple[Path, ...]] | None = None,
    birth_identity: Callable[[int], int] | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    cleanup_owner_tree: Callable[..., dict[str, object]] | None = None,
) -> int:
    """Own one fixed-dylib-farm round: intent, spawn, readiness, attestation, shutdown.

    Exactly one station owner tree is created per invocation, the report is renamed into
    ``--output`` before returning, and the owner-bound bounded cleanup runs on both the PASS
    and the FAIL path. A receipt, run binding or farm identity that drifts is refused with
    ``spawned=false`` and no signal at all.
    """

    from so101_demo.runtime.runtime_closure.attestation import build_runtime_process_attestation
    from so101_demo.runtime.runtime_closure.build import (
        default_loaded_image_probe,
        read_process_birth_identity,
    )
    from so101_demo.runtime.runtime_closure.identities import (
        ControllerRuntimeOwnerBinding,
        ProcessIdentity,
        RuntimeClosureError,
    )

    runtime_paths = paths or FixedFarmRuntimePaths.production()
    spawn_process = spawn or subprocess.Popen
    rows_reader = process_rows or _process_rows
    image_probe = loaded_image_probe or default_loaded_image_probe
    read_birth = birth_identity or read_process_birth_identity

    report: dict[str, object] = {
        "schema_version": FARM_CONTRACT_RECEIPT_SCHEMA_VERSION,
        "mode": StationMode.FIXED_DYLIB_FARM_FULL_TASK_STATION.value,
        "spawned": False,
        "observation_class": "INVALID",
        "invalid_reasons": [],
    }
    try:
        contract = load_fixed_dylib_farm_contract(Path(farm_contract_receipt))
        binding = _farm_round_binding(contract, Path(run_binding_path))
    except StationDiagnosticError as error:
        report["invalid_reasons"] = [error.code]
        report["detail"] = error.detail
        report["report_sha256"] = _write_farm_report(Path(output_path), report)
        return 1

    report["farm"] = contract.as_document()
    report["round_id"] = binding["round_id"]
    report["session_id"] = binding["session_id"]
    report["ros_domain_id"] = int(binding["ros_domain_id"])  # type: ignore[arg-type]
    evidence_root = Path(str(binding["task_evidence_root"]))
    scene_path = Path(str(binding["scene_path"]))
    if not evidence_root.is_absolute() or not scene_path.is_absolute():
        report["invalid_reasons"] = ["FARM_RUN_BINDING_INVALID"]
        report["report_sha256"] = _write_farm_report(Path(output_path), report)
        return 1

    # The runner sources the four validated setups before this mode starts, so the station keeps
    # those prefixes; the fixed contract keys are then written over whatever the shell had. Passing
    # only the 12-key baseline replaced the sourced ROS environment outright, which is why the
    # station died with `PackageNotFoundError: ros2cli`.
    environment = {
        key: value for key, value in os.environ.items() if isinstance(value, str)
    }
    environment.update(runtime_paths.environment(int(binding["ros_domain_id"])))  # type: ignore[arg-type]
    if str(runtime_paths.project_install.resolve()) != str(contract.project_install):
        report["invalid_reasons"] = ["FARM_PROJECT_INSTALL_DRIFT"]
        report["report_sha256"] = _write_farm_report(Path(output_path), report)
        return 1
    # Both installed layouts carry the same relative path: merged at the prefix, isolated under a
    # package directory. Resolving only the merged one refused the readiness entry on this host.
    readiness_executable = next(
        (
            candidate
            for candidate in (
                runtime_paths.project_install / READINESS_RELATIVE_PATH,
                runtime_paths.project_install / "so101_demo_py" / READINESS_RELATIVE_PATH,
            )
            if candidate.is_file()
        ),
        runtime_paths.project_install / READINESS_RELATIVE_PATH,
    )
    if not readiness_executable.is_file():
        report["invalid_reasons"] = ["FARM_READINESS_EXECUTABLE_MISSING"]
        report["report_sha256"] = _write_farm_report(Path(output_path), report)
        return 1

    # The spawn intent is atomic and lands before the station exists; the role is bound here
    # and is never inferred from a loaded-image list afterwards. This diagnostic process is
    # the round's owner root; a binding that names a different owner is refused before spawn.
    owner_root_pid = os.getpid()
    owner_root_birth = read_birth(owner_root_pid)
    declared_pid = binding.get("owner_root_pid")
    declared_birth = binding.get("owner_root_birth_identity")
    declared_pid_drift = declared_pid is not None and int(declared_pid) != owner_root_pid
    declared_birth_drift = (
        declared_birth is not None and int(declared_birth) != owner_root_birth
    )
    if declared_pid_drift or declared_birth_drift:
        report["invalid_reasons"] = ["FARM_OWNER_ROOT_MISMATCH"]
        report["report_sha256"] = _write_farm_report(Path(output_path), report)
        return 1
    intent_path = Path(output_path).parent / "farm-station-spawn-intent.json"
    argv = full_task_station_argv(
        session_id=str(binding["session_id"]),
        task_evidence_root=evidence_root,
        scene=scene_path,
        readiness_timeout_s=float(timeout_s),
        python_executable=runtime_paths.python,
        ros2_script=runtime_paths.ros2_script,
    )
    intent = {
        "role": "controller_runtime",
        "ancestor_role": "fixed_dylib_farm_full_task_station",
        "owner_root_pid": owner_root_pid,
        "owner_root_birth_identity": owner_root_birth,
        "expected_executable_relative_path": CONTROLLER_RELATIVE_PATH,
        "argv": list(argv),
        "farm_contract_sha256": contract.receipt_sha256,
    }
    intent_sha256 = _atomic_write_json(intent_path, intent)
    report["spawned"] = True
    report["spawn_intent"] = {
        "path": str(intent_path),
        "sha256": intent_sha256,
        "spawned": True,
        "role": "controller_runtime",
    }

    evidence_root.mkdir(parents=True, exist_ok=True)
    identities: dict[int, int] = {}
    anchors: list[ProcessIdentity] = []
    controller_document: dict[str, object] = {}
    invalid_reasons: list[str] = list(report["invalid_reasons"])  # type: ignore[arg-type]
    readiness_document: dict[str, object] = {}
    ready = False
    attestation_error: dict[str, object] | None = None
    attestation_document: dict[str, object] | None = None
    controller_attestation = None
    with (evidence_root / "station.stdout.log").open("w", encoding="utf-8") as stdout, (
        evidence_root / "station.stderr.log"
    ).open("w", encoding="utf-8") as stderr:
        launch = spawn_process(
            list(argv),
            env=dict(environment),
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        station_pid = int(launch.pid)  # type: ignore[attr-defined]
        station_birth = read_birth(station_pid)
        identities[station_pid] = station_birth
        anchors.append(
            ProcessIdentity(
                role="fixed_dylib_farm_full_task_station",
                pid=owner_root_pid,
                parent_pid=os.getppid(),
                birth_identity=owner_root_birth,
                executable=sys.executable,
            )
        )
        anchors.append(
            ProcessIdentity(
                role="task_station_launcher",
                pid=station_pid,
                parent_pid=owner_root_pid,
                birth_identity=station_birth,
                executable=str(runtime_paths.python),
            )
        )
        try:
            controller_pid, controller_command, descendants = _controller_process(
                station_pid, deadline=clock() + min(30.0, max(1.0, float(timeout_s) / 3.0)),
                rows_reader=rows_reader, sleep=sleep, clock=clock)
            for pid, _parent, _command in descendants:
                try:
                    identities[pid] = read_birth(pid)
                except RuntimeClosureError:
                    continue
            controller_birth_before = read_birth(controller_pid)
            identities[controller_pid] = controller_birth_before
            controller_executable = _command_executable(controller_command)
            completed = subprocess.run(
                [str(readiness_executable)],
                check=False,
                capture_output=True,
                text=True,
                env=dict(environment),
                timeout=max(1.0, float(timeout_s)),
            )
            for line in reversed(completed.stdout.splitlines()):
                if line.startswith("{"):
                    readiness_document = json.loads(line)
                    break
            ready = bool(completed.returncode == 0 and readiness_document.get("ready"))
            loaded_images = image_probe(controller_pid)
            controller_birth_after = read_birth(controller_pid)
            anchors.append(
                ProcessIdentity(
                    role="controller_runtime",
                    pid=controller_pid,
                    parent_pid=station_pid,
                    birth_identity=controller_birth_before,
                    executable=str(controller_executable),
                )
            )
            plugin_path, plugin_relative = _farm_image(
                loaded_images, contract, PLUGIN_BASENAME, runtime_paths)
            vendor_path, vendor_relative = _farm_image(
                loaded_images, contract, VENDOR_BASENAME, runtime_paths)
            owner_binding = ControllerRuntimeOwnerBinding(
                owner_root_role="fixed_dylib_farm_full_task_station",
                owner_root_pid=owner_root_pid,
                owner_root_birth_identity=owner_root_birth,
                spawn_role="controller_runtime",
                expected_executable_relative_path=CONTROLLER_RELATIVE_PATH,
                ancestry=tuple(anchors),
                manifest_sha256=contract.dylib_farm_manifest_sha256,
                closure_prefixes=contract.closure_prefixes,
                dylib_farm_root=contract.dylib_farm_root,
            )
            try:
                controller_attestation = build_runtime_process_attestation(
                    closure=None,  # type: ignore[arg-type]
                    install_root=runtime_paths.project_install,
                    role="controller_runtime",
                    pid=controller_pid,
                    birth_identity_before=controller_birth_before,
                    birth_identity_after=controller_birth_after,
                    executable=controller_executable,
                    loaded_images=loaded_images,
                    required_relative_paths=(plugin_relative, vendor_relative),
                    owner_binding=owner_binding,
                    plugin_relative_path=plugin_relative,
                    vendor_relative_path=vendor_relative,
                )
                attestation_document = controller_attestation.as_document()
            except RuntimeClosureError as error:
                attestation_error = {"code": error.code, "detail": error.detail}
                if ready:
                    invalid_reasons.append(error.code)
            controller_document = {
                "pid": controller_pid,
                "birth_identity": controller_birth_before,
                "executable": str(controller_executable),
                "command": controller_command,
                "plugin_path": str(plugin_path),
                "plugin_sha256": (
                    attestation_document.get("plugin_sha256") if attestation_document else None
                ),
                "vendor_path": str(vendor_path),
                "vendor_sha256": (
                    attestation_document.get("vendor_sha256") if attestation_document else None
                ),
            }
        except subprocess.TimeoutExpired:
            invalid_reasons.append("READINESS_SUBPROCESS_TIMEOUT")
        except RuntimeClosureError as error:
            attestation_error = {"code": error.code, "detail": error.detail}
            invalid_reasons.append(error.code)
        except StationDiagnosticError as error:
            invalid_reasons.append(error.code)
        finally:
            try:
                for pid, _parent, _command in _descendants(station_pid, rows_reader()):
                    try:
                        identities.setdefault(pid, read_birth(pid))
                    except RuntimeClosureError:
                        continue
            except StationDiagnosticError:
                invalid_reasons.append("STATION_PROCESS_COLLECTOR_FAILED")
            cleanup = (cleanup_owner_tree or _bounded_cleanup)(launch, identities)
    report["owner_tree"] = {
        "root_pid": owner_root_pid,
        "root_birth_identity": owner_root_birth,
        "identities": [
            {"pid": pid, "birth_identity": birth} for pid, birth in sorted(identities.items())
        ],
        "ancestry": [identity.as_document() for identity in anchors],
    }
    report["controller"] = controller_document
    report["readiness"] = {"ready": ready, "document": readiness_document}
    report["attestation"] = attestation_document
    report["attestation_error"] = attestation_error
    report["cleanup"] = cleanup
    report["invalid_reasons"] = invalid_reasons
    residue = cleanup.get("residue_pids") if isinstance(cleanup, dict) else None
    complete = bool(isinstance(cleanup, dict) and cleanup.get("complete"))
    if not ready:
        invalid_reasons.append("STATION_NOT_READY")
    if attestation_document is None:
        invalid_reasons.append("PROCESS_ATTESTATION_MISSING")
    if not complete or residue:
        invalid_reasons.append("CLEANUP_RESIDUE")
    report["observation_class"] = "PASS" if not invalid_reasons else "INVALID"
    report["report_sha256"] = _write_farm_report(Path(output_path), report)
    return 0 if report["observation_class"] == "PASS" else 1


def _farm_image(
    loaded_images: Sequence[Path],
    contract: FixedDylibFarmContract,
    basename: str,
    paths: FixedFarmRuntimePaths,
) -> tuple[Path, str]:
    """Find one loaded image by basename inside a sanctioned prefix."""

    prefixes = tuple(Path(prefix).resolve() for prefix in contract.closure_prefixes)
    for raw_path in loaded_images:
        candidate = Path(raw_path)
        if candidate.name != basename:
            continue
        resolved = candidate.resolve()
        for prefix in prefixes:
            if resolved.is_relative_to(prefix):
                return resolved, resolved.relative_to(prefix).as_posix()
    raise StationDiagnosticError("FARM_IMAGE_MISSING", basename)

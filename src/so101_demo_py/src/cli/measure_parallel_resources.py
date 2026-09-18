"""Candidate-only resource measurement CLI.

It validates a sealed operator authorization, the closed v2 runtime config and the
local measurement capabilities, then binds an owned measurement context. It never
reads an approved budget profile and never writes promotion state. The runner it
composes spawns the frozen copied-install batch entry with the same sealed
authorization bytes, inside the owned cgroup, under the real sampler and deadline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import os
import sys
import time
from pathlib import Path

from so101_demo.parallel_batch.contracts import ContractError, load_parallel_runtime_config_v2
from so101_demo.parallel_batch.measurement_control import ProcessIdentity
from so101_demo.parallel_batch.owned_resources import (
    MeasurementSession, NvmlDevicePort, OwnedCgroupV2, own_cgroup_path)
from so101_demo.parallel_batch.resource_measurement import (
    MeasurementAuthorization,
    build_candidate_plan,
    compose_measurement_admission,
    measurement_child_environment,
    run_candidate_batch,
    verify_measurement_arguments,
)


class MeasurementCliError(RuntimeError):
    """The candidate entry refused to start a measurement."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _local_identity() -> ProcessIdentity:
    fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
    return ProcessIdentity(os.getpid(), int(fields[19]), os.getuid(), os.getpgrp())


def require_measurement_capabilities(
    *, cgroup_parent: Path | None = None, device_index: int = 0, observation_source=None,
) -> dict[str, object]:
    """Verify the real capabilities; a missing one fails closed, never with sudo."""

    parent = Path(cgroup_parent) if cgroup_parent else own_cgroup_path()
    probe = OwnedCgroupV2.create(
        parent=parent, name=f"so101-measurement-preflight-{os.getpid()}")
    try:
        probe.require_delegated()
        controllers = sorted(set((probe.path / "cgroup.controllers").read_text().split()))
    finally:
        probe.remove()
    device = NvmlDevicePort(device_index=device_index)
    device.refresh()
    if observation_source is not None:
        observation = observation_source()
    else:
        from so101_demo.parallel_batch.resource_budget import LiveObservationSource

        observation = LiveObservationSource(gpu_device_index=device_index)()
    if not observation.attribution_complete:
        raise MeasurementCliError("MEASUREMENT_CAPABILITY_MISSING: attribution")
    return {
        "cgroup_parent": str(parent),
        "controllers": controllers,
        "gpu": device.name,
        "gpu_total_bytes": device.total_bytes,
        "cpu_core_equivalent": observation.capacity["cpu_core_equivalent"],
    }


def _installed_package_prefix() -> Path:
    import so101_demo

    return Path(so101_demo.__file__).resolve().parents[1]


def _installed_module_root() -> Path:
    return _installed_package_prefix().parent


def _installed_launcher_module() -> Path:
    from so101_demo.cli import mujoco_parallel_batch

    return Path(mujoco_parallel_batch.__file__).resolve()


def _installed_entry_points() -> Path:
    """The metadata file of the installed distribution, wherever this interpreter finds it."""

    from importlib.metadata import PackageNotFoundError, distribution

    try:
        candidate = Path(distribution("so101-demo-py").locate_file("entry_points.txt"))
    except (PackageNotFoundError, FileNotFoundError):
        candidate = None
    if candidate is not None and candidate.is_file():
        return candidate
    # A source-tree import has no distribution metadata; the file that declares the same
    # console entries there is the package's own setup.py.
    fallback = Path(_installed_package_prefix()) / "setup.py"
    if fallback.is_file():
        return fallback
    raise MeasurementCliError("MEASUREMENT_OVERLAY_INPUT_MISSING: entry_points")


def measurement_source_commit() -> str:
    """The source commit as a debug observation: environment first, never a runtime Git call."""

    from so101_demo.runtime.provenance import observed_source_commit

    observed = observed_source_commit(Path.cwd()) or ""
    return str(observed or os.environ.get("SO101_MEASUREMENT_SOURCE_COMMIT", ""))


def launcher_module_for_install(site_packages: Path) -> Path:
    """The launcher module inside the install, or this interpreter's when it has none."""

    candidate = Path(site_packages) / "so101_demo/cli/mujoco_parallel_batch.py"
    return candidate if candidate.is_file() else _installed_launcher_module()


def child_environment_for_launcher(environment, console_dir, site_packages=None,
                                   prefixes=None) -> dict[str, str]:
    """The child environment: no inherited authority, and the install's own console.

    A copied install ships its console beside the module it runs
    (``<prefix>/so101_demo_py/lib/so101_demo_py/so101_parallel_batch``) and no ``bin`` entry,
    so the launcher's provenance check cannot find it on the inherited PATH.
    """

    values = measurement_child_environment(dict(environment))
    inherited = values.get("PATH", "")
    values["PATH"] = os.pathsep.join(
        part for part in (str(console_dir), inherited) if part)
    if site_packages is not None:
        # The prefixes arrive as a mapping of package name to prefix; iterating the
        # mapping itself would put bare names on the path and let the launcher's AMENT
        # re-query fall through to an inherited prefix.
        entries = list(prefixes.values()) if isinstance(prefixes, dict) else list(prefixes or ())
        inherited_ament = values.get("AMENT_PREFIX_PATH", "")
        values["AMENT_PREFIX_PATH"] = os.pathsep.join(
            [str(path) for path in entries] + ([inherited_ament] if inherited_ament else []))
        inherited_path = values.get("PYTHONPATH", "")
        values["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(site_packages), inherited_path) if part)
    return values


def verify_broker_image(*, tag: str, digest: str, inspector=None) -> str:
    """Return the tag once it is proven to still carry the sealed image digest.

    The sealed runtime binding is content-addressed (an image digest) because that is what
    the authorization can commit to, while the launcher only knows the local tag. The tag
    is therefore resolved here and refused if it now points at a different image.
    """

    run = inspector or _default_image_inspector
    try:
        observed = str(run(tag)).strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise MeasurementCliError("MEASUREMENT_BROKER_IMAGE_UNAVAILABLE") from error
    if observed != digest:
        raise MeasurementCliError("MEASUREMENT_BROKER_IMAGE_MISMATCH")
    return tag


def _default_image_inspector(tag: str) -> str:
    completed = subprocess.run(
        ["docker", "image", "inspect", tag, "--format", "{{.Id}}"],
        capture_output=True, text=True, timeout=30, check=True)
    return completed.stdout


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install_prefix_entry_points(install_prefix: Path) -> Path:
    """The distribution metadata inside the sealed install, not this interpreter's."""

    root = Path(install_prefix) / "so101_demo_py/lib"
    for pattern in ("python*/site-packages/*.egg-info/entry_points.txt",
                    "python*/site-packages/*.dist-info/entry_points.txt"):
        matches = sorted(root.glob(pattern))
        if len(matches) == 1:
            return matches[0]
    raise MeasurementCliError("MEASUREMENT_OVERLAY_INPUT_MISSING: entry_points")


def entry_points_for_install(install_prefix: Path) -> Path:
    """The metadata file of the sealed install, or this interpreter's when it has none."""

    try:
        return install_prefix_entry_points(install_prefix)
    except MeasurementCliError:
        return _installed_entry_points()


def overlay_package_prefixes(install_root: Path) -> dict[str, Path]:
    """The two prefixes the launcher requires, and they must sit inside its install root."""

    prefixes: dict[str, Path] = {}
    for name in ("so101_demo_py", "so101_mujoco_support"):
        prefix = Path(install_root) / name
        if not prefix.is_dir() or prefix.is_symlink():
            raise MeasurementCliError(f"MEASUREMENT_OVERLAY_INPUT_MISSING: {name}")
        prefixes[name] = prefix
    return prefixes


def _ament_package_prefixes() -> dict[str, Path]:
    """The prefixes the launcher's overlay check compares against AMENT, not import paths."""

    from ament_index_python.packages import get_package_prefix

    prefixes: dict[str, Path] = {}
    for name in ("so101_demo_py", "so101_mujoco_support"):
        try:
            prefixes[name] = Path(get_package_prefix(name)).resolve()
        except Exception:  # noqa: BLE001 - an unavailable package is simply not declared
            continue
    if "so101_demo_py" not in prefixes:
        raise MeasurementCliError("MEASUREMENT_OVERLAY_INPUT_MISSING: package_prefix")
    return prefixes


def ensure_private_batch_root(batch_root) -> Path:
    """Create the sealed batch root private; the launcher refuses anything looser.

    Writing the overlay binding first would create the root as an intermediate directory
    with the umask default, which the launcher then rejects as
    MEASUREMENT_EVIDENCE_ROOT_INVALID.
    """

    root = Path(batch_root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    return root


def write_overlay_provenance_binding(
    *, target: Path, source_root: Path, build_root: Path, install_root: Path,
    package_prefix: Path, console: Path, module: Path, entry_points: Path,
    package_prefixes=None,
    parallel_config: Path, point_catalog: Path, source_commit: str,
) -> Path:
    """Write the external overlay binding the launcher verifies before creating a root.

    The launcher reads its ``--provenance-binding`` as an *overlay* document (schema 1) that
    names the trees and the artifact hashes it should compare, which is a different document
    from the sealed authorization's provenance binding, so it gets its own file.
    """

    inputs = {
        "coordinator_console": Path(console), "coordinator_module": Path(module),
        "entry_points": Path(entry_points), "parallel_config": Path(parallel_config),
        "point_catalog": Path(point_catalog),
    }
    for name, path in inputs.items():
        if not path.is_file():
            raise MeasurementCliError(f"MEASUREMENT_OVERLAY_INPUT_MISSING: {name}")
    for name, path in (("source_root", source_root), ("build_root", build_root),
                       ("install_root", install_root), ("package_prefix", package_prefix)):
        if not Path(path).is_dir():
            raise MeasurementCliError(f"MEASUREMENT_OVERLAY_INPUT_MISSING: {name}")
    document = {
        "schema_version": 1,
        "source_root": str(Path(source_root).resolve()),
        "source_commit": str(source_commit),
        "build_root": str(Path(build_root).resolve()),
        "install_root": str(Path(install_root).resolve()),
        "package_prefixes": (
            {name: str(Path(prefix).resolve())
             for name, prefix in dict(package_prefixes).items()}
            if package_prefixes else
            {"so101_demo_py": str(Path(package_prefix).resolve())}),
        "artifacts": {
            name: {"path": str(path.resolve()), "sha256": _file_sha256(path)}
            for name, path in inputs.items()
        },
    }
    target = Path(target)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    target.chmod(0o600)
    return target


def production_runner_factory(plan, *, child_runner=None, image_inspector=None):
    """Real composition runner: the frozen copied install's fixed batch entry."""

    binding = json.loads(Path(plan.bindings.provenance_binding_path).read_bytes())
    install_prefix = Path(str(binding.get("install_prefix", "")))
    if not install_prefix.is_absolute() or not install_prefix.is_dir():
        raise MeasurementCliError("MEASUREMENT_RUNTIME_UNAVAILABLE: install_prefix")
    launcher = install_prefix / "so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    if not launcher.is_file():
        raise MeasurementCliError("MEASUREMENT_RUNTIME_UNAVAILABLE: launcher")
    site_packages = install_prefix / "so101_demo_py/lib/python3.12/site-packages"
    environment = child_environment_for_launcher(
        dict(os.environ), launcher.parent, site_packages=site_packages,
        prefixes=overlay_package_prefixes(install_prefix))
    from so101_demo.cli.mujoco_parallel_batch import _BROKER_IMAGE

    tag = verify_broker_image(tag=_BROKER_IMAGE, digest=plan.bindings.broker_image_id,
                              inspector=image_inspector)
    overlay = write_overlay_provenance_binding(
        target=ensure_private_batch_root(plan.batch_root) / "raw/overlay-provenance-binding.json",
        source_root=Path(str(binding.get("source_root", "")) or Path.cwd()),
        build_root=install_prefix, install_root=install_prefix,
        package_prefix=overlay_package_prefixes(install_prefix)["so101_demo_py"],
        package_prefixes=overlay_package_prefixes(install_prefix),
        console=launcher,
        module=launcher_module_for_install(site_packages),
        entry_points=entry_points_for_install(install_prefix),
        parallel_config=Path(plan.config_path),
        point_catalog=Path(plan.bindings.points_path),
        source_commit=measurement_source_commit())
    argv = (str(launcher),
            *plan.runner_argv(broker_image=tag, provenance_binding=overlay))

    def runner(candidate_plan, session):
        if child_runner is not None:
            child = child_runner(session=session, argv=argv, cwd=candidate_plan.batch_root,
                                 environment=environment)
        else:
            child = session.spawn(argv=argv, cwd=candidate_plan.batch_root,
                                  environment=environment)
        code = session.supervise(child)
        if int(code) != 0:
            # A failed workload batch is not a measurement: refuse and seal nothing.
            raise ContractError(f"MEASUREMENT_WORKLOAD_FAILED: launcher_exit {int(code)}")
        return {
            "raw_files": session.raw_files(),
            "coverage_events": session.events_path,
            "result": {"launcher_exit": int(code), "launcher": str(launcher)},
        }

    return runner


def main(argv=None, *, runner_factory=None, capability_probe=None, session_factory=None,
         image_inspector=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-sha256", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--intent", choices=("CALIBRATION_ONLY", "QUALIFICATION"), required=True)
    parser.add_argument("--cgroup-parent", type=Path)
    parser.add_argument("--device-index", type=int, default=0)
    options = parser.parse_args(argv)
    try:
        authorization = MeasurementAuthorization.load(
            options.authorization, expected_sha256=options.authorization_sha256)
        if authorization.intent != options.intent:
            raise MeasurementCliError("AUTHORIZATION_INTENT_MISMATCH")
        if authorization.is_expired(now_ns=time.time_ns()):
            raise MeasurementCliError("AUTHORIZATION_EXPIRED")
        evidence_root = options.evidence_root.resolve()
        if not evidence_root.is_dir():
            raise MeasurementCliError("EVIDENCE_ROOT_UNAVAILABLE")
        if not authorization.batch_root.is_relative_to(evidence_root):
            raise MeasurementCliError("BATCH_ROOT_OUTSIDE_EVIDENCE_ROOT")
        config = load_parallel_runtime_config_v2(options.config)
        if config.deployment.approved_profile_path is not None:
            raise MeasurementCliError("CANDIDATE_CONFIG_MUST_HAVE_NULL_DEPLOYMENT")
        if capability_probe is not None:
            capability = capability_probe()
        else:
            # The capability probe must verify the same cgroup/device selection the
            # session will own; validating a different object would not prove the
            # delegated capability the measurement actually relies on.
            capability = require_measurement_capabilities(
                cgroup_parent=options.cgroup_parent, device_index=options.device_index)
        # The composition is determined by the sealed authorization alone: an inherited
        # production authority is refused inside the composer, not accepted as a grant.
        authorization, gate = compose_measurement_admission(
            authorization_path=options.authorization,
            authorization_sha256=options.authorization_sha256,
            config_path=options.config)
        plan = build_candidate_plan(
            authorization=authorization, authorization_path=options.authorization,
            config_path=options.config, evidence_root=evidence_root,
            batch_id=options.batch_id)
        verify_measurement_arguments(
            authorization=authorization, batch_id=plan.batch_id,
            worker_count=plan.worker_count, evidence_root=plan.batch_root,
            points_path=Path(plan.bindings.points_path),
            points_sha256=plan.bindings.points_sha256,
            yolo_weights_path=Path(plan.bindings.yolo_weights_path),
            yolo_weights_sha256=plan.bindings.yolo_weights_sha256,
            grounded_root=Path(plan.bindings.grounded_root),
            grounded_manifest_sha256=plan.bindings.grounded_manifest_sha256,
            broker_image=plan.bindings.broker_image_id, config_path=plan.config_path)
        # One admission for this batch, taken through the measurement context before
        # the owned cgroup is created; the session then caps the run itself.
        from so101_demo.parallel_batch.resource_budget import FixedAdmissionRequest

        decision = gate.admit(FixedAdmissionRequest(
            worker_count=plan.worker_count, batch_id=plan.batch_id, epoch=1,
            execution_identity_sha256=plan.execution_identity_sha256,
            request_kind=gate.request_kind))
        if not decision.admitted:
            raise MeasurementCliError(decision.reason_codes[0])
        session = (session_factory or _session)(
            authorization=authorization, batch_root=plan.batch_root,
            batch_id=plan.batch_id, sampling=config.measurement.sampling,
            safety=config.measurement.safety, owner=_local_identity(),
            cgroup_parent=options.cgroup_parent, device_index=options.device_index)
        factory = runner_factory or (
            lambda plan: production_runner_factory(plan, image_inspector=image_inspector))
        summary = run_candidate_batch(plan=plan, runner=factory(plan), session=session)
        summary["capability"] = capability
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (ContractError, MeasurementCliError, OSError, ValueError) as error:
        code = getattr(error, "code", None) or str(error) or type(error).__name__
        print(json.dumps({"status": "REFUSED", "code": code}, sort_keys=True),
              file=sys.stderr)
        return 1


def _session(**kwargs) -> MeasurementSession:
    return MeasurementSession(**kwargs)


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic macOS Gate A control set, direct loader probe and reducer."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from so101_demo.runtime.macos_dlopen_gate.control import (
    DirectDlopenObservation,
    GateAControlObservation,
    GateAControlSetManifest,
    GateARunBinding,
    build_control_set_manifest,
    reduce_gate_a_controls,
    run_direct_dlopen,
)
from so101_demo.runtime.macos_dlopen_gate.farm import (
    GateAControlError,
    verify_filtered_ros_dylib_farm,
)
from so101_demo.runtime.macos_dlopen_gate.semantics import _closure_dylib_basenames
from so101_demo.runtime.runtime_closure.build import verify_runtime_closure


def write_json(path: Path, document: Mapping[str, object]) -> None:
    target = Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise GateAControlError("CONTROL_OUTPUT_INVALID", str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(8)}.tmp")
    payload = json.dumps(document, sort_keys=True, indent=2) + "\n"
    with temporary.open("x", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    directory = os.open(target.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def load_manifest(path: Path) -> GateAControlSetManifest:
    return GateAControlSetManifest.from_document(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def load_binding(path: Path) -> GateARunBinding:
    return GateARunBinding.from_document(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _next_domain(run_root: Path, session_id: str) -> int:
    used: set[int] = set()
    for path in run_root.parent.rglob("run-binding.json"):
        try:
            used.add(int(json.loads(path.read_text(encoding="utf-8"))["ros_domain_id"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    start = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16) % 233
    for offset in range(233):
        candidate = (start + offset) % 233
        if candidate not in used:
            return candidate
    raise GateAControlError("CONTROL_BINDING_INVALID", "no free ROS domain")


def _prepare_run_root(run_root: Path) -> Path:
    root = Path(run_root)
    if root.is_symlink():
        raise GateAControlError("CONTROL_BINDING_INVALID", str(root))
    try:
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        if root.is_symlink() or not root.is_dir():
            raise GateAControlError("CONTROL_BINDING_INVALID", str(root))
        try:
            next(root.iterdir())
        except StopIteration:
            pass
        else:
            raise GateAControlError("CONTROL_BINDING_INVALID", f"nonempty: {root}")
    return root


def _execute_probe_child(
    manifest: GateAControlSetManifest, binding: GateARunBinding
) -> DirectDlopenObservation:
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
    command = (
        sys.executable,
        "-m",
        "so101_demo.runtime.macos_dlopen_probe",
        "--child-dlopen",
        "--plugin",
        str(manifest.plugin_path),
        "--vendor",
        str(manifest.vendor_path),
    )
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=dict(binding.expanded_environment),
        timeout=30.0,
    )
    candidates = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    if not candidates:
        raise GateAControlError(
            "DLOPEN_CHILD_INVALID",
            f"rc={completed.returncode} stderr={completed.stderr.strip()}",
        )
    observation = DirectDlopenObservation.from_document(json.loads(candidates[-1]))
    if completed.returncode not in {0, 1}:
        raise GateAControlError("DLOPEN_CHILD_INVALID", str(completed.returncode))
    return observation


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="macos_dlopen_probe")
    parser.add_argument("--create-manifest", action="store_true")
    parser.add_argument("--create-run-binding", action="store_true")
    parser.add_argument("--child-dlopen", action="store_true")
    parser.add_argument("--reduce-controls", action="store_true")
    parser.add_argument("--manifest")
    parser.add_argument("--run-binding")
    parser.add_argument("--control", choices=("N", "P", "F"))
    parser.add_argument("--run-root")
    parser.add_argument("--session-id")
    parser.add_argument("--ros-domain-id", type=int)
    parser.add_argument("--install-root")
    parser.add_argument("--gate-a-run-root")
    parser.add_argument("--ros-dylib-farm")
    parser.add_argument("--source-commit")
    parser.add_argument("--submodule-commit")
    parser.add_argument("--plugin")
    parser.add_argument("--vendor")
    parser.add_argument("--negative")
    parser.add_argument("--positive")
    parser.add_argument("--output")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> int:
    options = parse_arguments(argv)
    if options.child_dlopen:
        if not options.plugin:
            raise GateAControlError("DLOPEN_CHILD_INVALID", "plugin")
        observation = run_direct_dlopen(
            Path(options.plugin), None if not options.vendor else Path(options.vendor)
        )
        print(json.dumps(observation.as_document(), sort_keys=True), flush=True)
        return 0 if observation.succeeded else 1
    if options.create_manifest:
        required = (
            options.gate_a_run_root,
            options.install_root,
            options.source_commit,
            options.submodule_commit,
            options.ros_dylib_farm,
            options.output,
        )
        if not all(required):
            raise GateAControlError("CONTROL_MANIFEST_INVALID", "arguments")
        manifest = build_control_set_manifest(
            gate_a_run_root=Path(options.gate_a_run_root),
            install_root=Path(options.install_root),
            source_commit=options.source_commit,
            submodule_commit=options.submodule_commit,
            environment=os.environ,
            ros_dylib_farm=Path(options.ros_dylib_farm),
        )
        write_json(Path(options.output), manifest.as_document())
        return 0
    if options.create_run_binding:
        if not all((options.manifest, options.control, options.run_root, options.session_id, options.output)):
            raise GateAControlError("CONTROL_BINDING_INVALID", "arguments")
        manifest = load_manifest(Path(options.manifest))
        run_root = _prepare_run_root(Path(options.run_root))
        domain = (
            options.ros_domain_id
            if options.ros_domain_id is not None
            else _next_domain(run_root, options.session_id)
        )
        binding = GateARunBinding.create(
            run_root=run_root,
            session_id=options.session_id,
            ros_domain_id=domain,
            control=options.control,
            manifest=manifest,
        )
        write_json(Path(options.output), binding.as_document())
        return 0
    if options.reduce_controls:
        if not all((options.negative, options.positive, options.output)):
            raise GateAControlError("CONTROL_REDUCER_INVALID", "arguments")
        negative = GateAControlObservation.from_document(
            json.loads(Path(options.negative).read_text(encoding="utf-8"))
        )
        positive = GateAControlObservation.from_document(
            json.loads(Path(options.positive).read_text(encoding="utf-8"))
        )
        write_json(
            Path(options.output), reduce_gate_a_controls(negative, positive).as_document()
        )
        return 0
    if not all((options.manifest, options.run_binding, options.control, options.output)):
        raise GateAControlError("DLOPEN_CONTROL_INVALID", "arguments")
    manifest = load_manifest(Path(options.manifest))
    binding = load_binding(Path(options.run_binding))
    if binding.control != options.control:
        raise GateAControlError("DLOPEN_CONTROL_INVALID", "binding control mismatch")
    observation = _execute_probe_child(manifest, binding)
    write_json(Path(options.output), observation.as_document())
    return 0 if observation.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())

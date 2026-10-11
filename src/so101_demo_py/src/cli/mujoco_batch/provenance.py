"""Provenance verification of the installed overlay, the external binding and the broker image."""

from __future__ import annotations

import configparser
import json
from pathlib import Path
import shutil
import subprocess
from typing import Callable, Mapping

import yaml

from so101_demo.cli.mujoco_batch.common import CliError, _absolute, _sha256

_CATALOG_SHA256 = "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"


_BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"


# The provenance describes the command module itself (``cli/mujoco_parallel_batch.py``), not this helper.
_ENTRY_MODULE_PATH = Path(__file__).resolve().parent.parent / "mujoco_parallel_batch.py"

_CURRENT_PROVENANCE_FILES = {
    "source_tree_sha256": "source_tree_sha256.json",
    "install_tree_sha256": "install_tree_sha256.json",
    "runtime_config_sha256": "runtime_config.json",
    "policy_sha256": "policy_sha256.json",
    "scene_sha256": "scene_sha256.json",
    "models_sha256": "models_sha256.json",
    "container_sha256": "container_sha256.json",
    "catalog_sha256": "catalog_sha256.json",
}


_DYNAMIC_MUJOCO_POLICY = Path(
    "config/policies/dynamic_cup_pick/mujoco.yaml"
)


def _runtime_package_root(
    *,
    module_path: Path | None = None,
    share_directory_provider: Callable[[str], str] | None = None,
) -> Path:
    """Locate packaged policy data in either a source tree or a copied install."""

    module = (module_path or _ENTRY_MODULE_PATH).resolve()
    source_root = module.parents[2]
    source_policy = source_root / _DYNAMIC_MUJOCO_POLICY
    if source_policy.is_file() and not source_policy.is_symlink():
        return source_root
    if share_directory_provider is None:
        from ament_index_python.packages import get_package_share_directory

        share_directory_provider = get_package_share_directory
    share_root = Path(share_directory_provider("so101_demo_py"))
    share_policy = share_root / _DYNAMIC_MUJOCO_POLICY
    if (
        not share_root.is_absolute()
        or not share_root.is_dir()
        or share_root.is_symlink()
        or not share_policy.is_file()
        or share_policy.is_symlink()
    ):
        raise CliError("RUNTIME_POLICY_ROOT_INVALID")
    return share_root


def _external_binding_source_root(binding_path: Path) -> Path:
    """Read only the candidate source root needed to locate Git authority."""

    binding_path = Path(binding_path)
    if (
        not binding_path.is_absolute()
        or binding_path.is_symlink()
        or not binding_path.is_file()
    ):
        raise CliError("PROVENANCE_EXTERNAL_BINDING_PATH")
    try:
        if binding_path.stat().st_size > 1024 * 1024:
            raise CliError("PROVENANCE_EXTERNAL_BINDING_DOCUMENT")
        document = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliError("PROVENANCE_EXTERNAL_BINDING_DOCUMENT") from error
    value = document.get("source_root") if type(document) is dict else None
    source_root = Path(value) if isinstance(value, str) else Path()
    if (
        not isinstance(value, str)
        or not source_root.is_absolute()
        or source_root.is_symlink()
        or not source_root.is_dir()
    ):
        raise CliError("PROVENANCE_EXTERNAL_SOURCE_ROOT")
    return source_root.resolve()


def _catalog(path: Path) -> tuple[dict[str, Mapping[str, object]], str]:
    path = path.resolve()
    digest = _sha256(path)
    if digest != _CATALOG_SHA256:
        raise CliError("POINT_CATALOG_HASH_MISMATCH")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise CliError("POINT_CATALOG_INVALID") from error
    if type(document) is not dict or set(document) != {"schema_version", "points"}:
        raise CliError("POINT_CATALOG_SCHEMA")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise CliError("POINT_CATALOG_SCHEMA")
    points = document["points"]
    if not isinstance(points, list) or len(points) != 20:
        raise CliError("POINT_CATALOG_SCHEMA")
    catalog = {}
    for point in points:
        if type(point) is not dict or set(point) != {"id", "label", "cup_position_world_m"}:
            raise CliError("POINT_CATALOG_SCHEMA")
        point_id = point["id"]
        if not isinstance(point_id, str) or not point_id or point_id in catalog:
            raise CliError("POINT_CATALOG_DUPLICATE")
        catalog[point_id] = point
    return catalog, digest


def _observed_source_dirty(source_root: Path) -> bool | None:
    """DEBUG observation only; a no-Git tree records None and never refuses."""

    try:
        completed = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain", "--untracked-files=no"],
            check=True, capture_output=True, text=True, timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return bool(completed.stdout.strip())


def verify_provenance(spec: Mapping[str, object]) -> Mapping[str, object]:
    """Verify exact local model and image inputs before creating the batch root."""

    yolo = _absolute("yolo_weights", Path(spec["yolo_weights"]))
    grounded = _absolute("grounded_root", Path(spec["grounded_root"]))
    if not yolo.is_file() or yolo.is_symlink():
        raise CliError("PROVENANCE_YOLO_PATH")
    if not grounded.is_dir() or grounded.is_symlink():
        raise CliError("PROVENANCE_GROUNDED_PATH")
    manifest = grounded / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise CliError("PROVENANCE_GROUNDED_MANIFEST")
    if _sha256(yolo) != spec["yolo_weights_sha256"]:
        raise CliError("PROVENANCE_YOLO_HASH")
    if _sha256(manifest) != spec["grounded_manifest_sha256"]:
        raise CliError("PROVENANCE_GROUNDED_HASH")
    image = spec["broker_image"]
    if image != _BROKER_IMAGE:
        raise CliError("PROVENANCE_BROKER_IMAGE")
    module_import_path = _ENTRY_MODULE_PATH.absolute()
    module_path = module_import_path.resolve()
    external_binding = spec.get("provenance_binding")
    # The source commit is an optional DEBUG observation only: this deployment may be
    # a pure copied install with no Git checkout, and no commit value can refuse a run.
    from so101_demo.runtime.provenance import observed_source_commit
    if external_binding is not None:
        repository_root = _external_binding_source_root(Path(external_binding))
    else:
        candidate = module_path.parents[3]
        # A copied install has no source checkout next to its modules. The source root only
        # feeds a debug observation, so a missing one records "unknown" instead of refusing
        # the run -- this was the gate that killed the coordinator of the live campaign
        # (PROVENANCE_SOURCE_ROOT) and it is exactly the runtime admission the lightweight
        # start guard removed.
        repository_root = candidate if (candidate / "src/so101_demo_py").is_dir() else None
    source_commit = (
        observed_source_commit(Path(repository_root).resolve())
        if repository_root is not None else None
    )
    source_dirty = _observed_source_dirty(repository_root)
    # The patch that made the source root optional left this path unconditional, which turned
    # "no checkout" into a TypeError and therefore into PROVENANCE_VERIFICATION_FAILED. The
    # package root is debug/overlay evidence; without a checkout it simply does not exist.
    package_root = (repository_root if repository_root is not None
                    else module_path.parents[3]) / "src/so101_demo_py"
    console = shutil.which("so101_parallel_batch")
    if console is None:
        raise CliError("PROVENANCE_CONSOLE_MISSING")
    console_path = Path(console).resolve()
    config_path = Path(spec["config"]).absolute()
    points_path = Path(spec["points"]).absolute()
    if repository_root is None and external_binding is None:
        # A pure copied install has neither a checkout to compare against nor an external
        # overlay binding, so the cross-checkout identity question cannot be asked. This is
        # deployment provenance, not admission: the functional checks above (model files and
        # hashes, broker image) have already run, and the copied bytes are read back by the
        # deployment gates. Recording "not bound" is the honest answer.
        overlay_identity: Mapping[str, object] = {
            "external_overlay_bound": False,
            "package_prefixes": {},
            "overlay_kind": "COPIED_INSTALL",
        }
    else:
        overlay_identity = _validate_provenance_overlay(
            repository_root if repository_root is not None else module_path.parents[3],
            module_path,
            console_path,
            config_path,
            points_path,
            module_import_path=module_import_path,
            external_binding=external_binding,
        )
    if overlay_identity["external_overlay_bound"]:
        try:
            from ament_index_python.packages import get_package_prefix

            for package, expected_prefix in overlay_identity["package_prefixes"].items():
                if Path(get_package_prefix(package)).resolve() != Path(expected_prefix):
                    raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX")
        except CliError:
            raise
        except Exception as error:
            raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX") from error
    if repository_root is None:
        # A copied install keeps these inputs in its share directory, not in a source tree.
        # They are functional files the run really reads, so this is a real requirement --
        # only the place they are looked for changes. Discovery is attempted first, with a
        # layout-derived fallback because this code also runs inside a spawned coordinator
        # whose environment may not carry the ament index.
        installed_root = None
        try:
            from ament_index_python.packages import get_package_share_directory

            candidate = Path(get_package_share_directory("so101_demo_py")).resolve()
            if candidate.is_dir():
                installed_root = candidate
        except Exception:
            installed_root = None
        if installed_root is None:
            for parent in module_path.parents:
                candidate = parent / "share/so101_demo_py"
                if candidate.is_dir():
                    installed_root = candidate
                    break
        if installed_root is None:
            raise CliError("PROVENANCE_INSTALLED_SHARE_MISSING")
    else:
        installed_root = package_root
    policy_path = installed_root / "config/mujoco/headless_execution.yaml"
    scene_config = installed_root / "config/mujoco/task_scene.yaml"
    scene_model = installed_root / "assets/mujoco/scene.xml"
    if any(not value.is_file() or value.is_symlink() for value in (
        console_path, module_path, config_path, points_path,
        policy_path, scene_config, scene_model,
    )):
        raise CliError("PROVENANCE_INSTALLED_INPUT_MISSING")
    from so101_demo.cli.parallel_perception_broker import source_hash
    if overlay_identity["external_overlay_bound"]:
        source_tree = source_hash(package_root / "src")
        build_tree_path = Path(overlay_identity["installed_module_tree_path"])
        build_tree = source_hash(build_tree_path.resolve())
        if build_tree != source_tree:
            raise CliError("PROVENANCE_INSTALLED_BYTES")
        installed_identity = {
            **overlay_identity,
            "source_module_tree_sha256": source_tree,
            "installed_module_tree_sha256": build_tree,
        }
    elif repository_root is None:
        # A pure copied install has no source module tree to compare against; the identity is
        # the installed one. This branch exists because `_installed_overlay_identity` starts
        # with `Path(repository_root)` and would raise on None -- the TypeError that surfaced as
        # the generic PROVENANCE_VERIFICATION_FAILED in the coordinator log.
        installed_identity = {
            **overlay_identity,
            "source_module_tree_sha256": None,
            "installed_module_tree_sha256": source_hash(module_path.parent),
        }
    else:
        installed_identity = _installed_overlay_identity(
            repository_root, module_import_path, console_path, source_hash=source_hash
        )
    try:
        from so101_demo.cli.parallel_perception_broker import image_record

        immutable_image = image_record(image)
    except Exception as error:
        raise CliError("PROVENANCE_BROKER_IMAGE_READBACK") from error
    return {
        "source_commit": source_commit,
        "source_commit_authority": "DEBUG_METADATA_ONLY",
        "source_dirty": source_dirty,
        "source_tree_sha256": source_hash(package_root),
        "installed_console_path": str(console_path),
        "installed_console_sha256": _sha256(console_path),
        "installed_module_path": str(module_path),
        "installed_module_sha256": _sha256(module_path),
        **installed_identity,
        "runtime_config_sha256": _sha256(config_path),
        "dynamic_policy_sha256": _sha256(policy_path),
        "task_scene_sha256": _sha256(scene_config),
        "scene_model_sha256": _sha256(scene_model),
        "catalog_sha256": spec["catalog_sha256"],
        "yolo_weights_sha256": spec["yolo_weights_sha256"],
        "grounded_manifest_sha256": spec["grounded_manifest_sha256"],
        "broker_image": image,
        **immutable_image,
    }


def _validate_provenance_overlay(
    repository_root: Path,
    module_path: Path,
    console_path: Path,
    config_path: Path,
    points_path: Path,
    *,
    module_import_path: Path | None = None,
    external_binding: Path | str | None = None,
) -> Mapping[str, object]:
    """Reject a source/import/console/config selection spanning checkouts."""

    repository_root = Path(repository_root).resolve()
    package_root = repository_root / "src/so101_demo_py"
    expected_module = (
        package_root / "src/cli/mujoco_parallel_batch.py"
    ).resolve()
    expected_console_root = (
        repository_root / "install/so101_demo_py/lib/so101_demo_py"
    ).resolve()
    local_overlay = (
        Path(module_path).resolve() != expected_module
        or Path(console_path).resolve()
        != (expected_console_root / "so101_parallel_batch").resolve()
    )
    try:
        Path(config_path).resolve().relative_to(package_root.resolve())
        Path(points_path).resolve().relative_to(package_root.resolve())
    except ValueError:
        local_overlay = True
    if not local_overlay:
        return {"external_overlay_bound": False}
    if external_binding is None:
        raise CliError("PROVENANCE_MIXED_OVERLAY")
    if module_import_path is None:
        raise CliError("PROVENANCE_EXTERNAL_BINDING_CONTEXT")
    return _validate_external_overlay_binding(
        Path(external_binding),
        repository_root=repository_root,
        module_path=Path(module_path),
        module_import_path=Path(module_import_path),
        console_path=Path(console_path),
        config_path=Path(config_path),
        points_path=Path(points_path),
    )


def _validate_external_overlay_binding(
    binding_path: Path,
    *,
    repository_root: Path,
    module_path: Path,
    module_import_path: Path,
    console_path: Path,
    config_path: Path,
    points_path: Path,
) -> Mapping[str, object]:
    """Validate a closed, content-bound external build/install overlay."""

    binding_path = Path(binding_path)
    if not binding_path.is_absolute() or binding_path.is_symlink() or not binding_path.is_file():
        raise CliError("PROVENANCE_EXTERNAL_BINDING_PATH")
    try:
        document = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CliError("PROVENANCE_EXTERNAL_BINDING_DOCUMENT") from error
    expected_keys = {
        "schema_version",
        "source_root",
        "source_commit",
        "build_root",
        "install_root",
        "package_prefixes",
        "artifacts",
    }
    if type(document) is not dict or set(document) != expected_keys or document["schema_version"] != 1:
        raise CliError("PROVENANCE_EXTERNAL_BINDING_SCHEMA")

    def absolute_directory(name: str) -> Path:
        value = document.get(name)
        if not isinstance(value, str):
            raise CliError("PROVENANCE_EXTERNAL_BINDING_SCHEMA")
        path = Path(value)
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise CliError("PROVENANCE_EXTERNAL_BINDING_PATH")
        return path.resolve()

    source_root = absolute_directory("source_root")
    build_root = absolute_directory("build_root")
    install_root = absolute_directory("install_root")
    if source_root != repository_root.resolve():
        raise CliError("PROVENANCE_EXTERNAL_SOURCE_ROOT")
    # The binding's declared commit is compatibility metadata; the overlay is bound by
    # its roots, prefixes and byte artifacts below, never by a commit equality.
    if document["source_commit"] is not None and not isinstance(document["source_commit"], str):
        raise CliError("PROVENANCE_EXTERNAL_BINDING_SCHEMA")
    expected_source_module = (
        source_root / "src/so101_demo_py/src/cli/mujoco_parallel_batch.py"
    ).resolve()
    if (
        not expected_source_module.is_file()
        or expected_source_module.is_symlink()
        or module_path.resolve() != module_import_path.resolve()
    ):
        raise CliError("PROVENANCE_EXTERNAL_SOURCE_ROOT")

    package_prefixes = document["package_prefixes"]
    if type(package_prefixes) is not dict or set(package_prefixes) != {
        "so101_demo_py",
        "so101_mujoco_support",
    }:
        raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX")
    prefixes: dict[str, Path] = {}
    for package, value in package_prefixes.items():
        if not isinstance(value, str):
            raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX")
        prefix = Path(value)
        if not prefix.is_absolute() or prefix.is_symlink() or not prefix.is_dir():
            raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX")
        prefix = prefix.resolve()
        try:
            prefix.relative_to(install_root)
        except ValueError as error:
            raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX") from error
        prefixes[package] = prefix

    demo_prefix = prefixes["so101_demo_py"]
    expected_console = demo_prefix / "lib/so101_demo_py/so101_parallel_batch"
    expected_config = demo_prefix / "share/so101_demo_py/config/mujoco/parallel_batch_linux_cuda.yaml"
    expected_points = (
        demo_prefix
        / "share/so101_demo_py/config/mujoco/moveit_expert_validation_points.yaml"
    )
    if (
        console_path.absolute() != expected_console.absolute()
        or config_path.absolute() != expected_config.absolute()
        or points_path.absolute() != expected_points.absolute()
    ):
        raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX")
    try:
        module_import_path.absolute().relative_to(demo_prefix)
    except ValueError as error:
        raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX") from error

    artifacts = document["artifacts"]
    artifact_paths = {
        "coordinator_console": console_path.absolute(),
        "coordinator_module": module_import_path.absolute(),
        "parallel_config": config_path.absolute(),
        "point_catalog": points_path.absolute(),
    }
    if type(artifacts) is not dict or set(artifacts) != {
        *artifact_paths,
        "entry_points",
    }:
        raise CliError("PROVENANCE_EXTERNAL_BINDING_SCHEMA")
    verified_artifacts: dict[str, str] = {}
    for name, expected_path in artifact_paths.items():
        entry = artifacts[name]
        if type(entry) is not dict or set(entry) != {"path", "sha256"}:
            raise CliError("PROVENANCE_EXTERNAL_BINDING_SCHEMA")
        path = Path(entry["path"])
        if (
            not path.is_absolute()
            or path.absolute() != expected_path
            or path.is_symlink()
            or not path.is_file()
            or entry["sha256"] != _sha256(path)
        ):
            raise CliError("PROVENANCE_EXTERNAL_ARTIFACT_IDENTITY")
        verified_artifacts[name] = str(path)

    entry_points_entry = artifacts["entry_points"]
    if type(entry_points_entry) is not dict or set(entry_points_entry) != {"path", "sha256"}:
        raise CliError("PROVENANCE_EXTERNAL_BINDING_SCHEMA")
    entry_points = Path(entry_points_entry["path"])
    try:
        entry_points.absolute().relative_to(build_root)
    except ValueError as error:
        raise CliError("PROVENANCE_EXTERNAL_PACKAGE_PREFIX") from error
    if (
        not entry_points.is_absolute()
        or entry_points.is_symlink()
        or not entry_points.is_file()
        or entry_points_entry["sha256"] != _sha256(entry_points)
    ):
        raise CliError("PROVENANCE_EXTERNAL_ARTIFACT_IDENTITY")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(entry_points.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, configparser.Error) as error:
        raise CliError("PROVENANCE_EXTERNAL_ARTIFACT_IDENTITY") from error
    if (
        "console_scripts" not in parser
        or parser["console_scripts"].get("so101_parallel_batch")
        != "so101_demo.cli.mujoco_parallel_batch:main"
        or console_path.read_bytes() not in {
            _expected_console_wrapper(),
            _expected_console_wrapper().replace(
                b"so101-demo-py'", b"so101-demo-py==0.1.0'"
            ),
        }
    ):
        raise CliError("PROVENANCE_EXTERNAL_ARTIFACT_IDENTITY")
    module_tree = module_import_path.absolute().parents[1]
    return {
        "external_overlay_bound": True,
        "external_overlay_binding_path": str(binding_path),
        "external_overlay_binding_sha256": _sha256(binding_path),
        "package_prefixes": {
            package: str(prefix) for package, prefix in sorted(prefixes.items())
        },
        "module_import_path": str(module_import_path.absolute()),
        "module_import_sha256": _sha256(module_import_path),
        "installed_module_tree_path": str(module_tree),
        "installed_egg_link_path": None,
        "installed_egg_link_sha256": None,
        "installed_entry_points_path": str(entry_points),
        "installed_entry_points_sha256": _sha256(entry_points),
    }


def _installed_overlay_identity(
    repository_root: Path,
    module_import_path: Path,
    console_path: Path,
    *,
    source_hash,
) -> Mapping[str, object]:
    """Bind editable build/install artifacts to this exact source checkout."""

    repository_root = Path(repository_root).resolve()
    source_package = (repository_root / "src/so101_demo_py/src").resolve()
    build_package = repository_root / "build/so101_demo_py/so101_demo"
    expected_module = build_package / "cli/mujoco_parallel_batch.py"
    expected_console = (
        repository_root
        / "install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    )
    egg_links = tuple(
        (repository_root / "install/so101_demo_py/lib").glob(
            "python*/site-packages/so101-demo-py.egg-link"
        )
    )
    if (
        Path(module_import_path).absolute() != expected_module.absolute()
        or Path(console_path).absolute() != expected_console.absolute()
        or not build_package.is_symlink()
        or build_package.resolve() != source_package
        or len(egg_links) != 1
    ):
        raise CliError("PROVENANCE_INSTALLED_OVERLAY")
    egg_link = egg_links[0]
    try:
        target_line = egg_link.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeError, IndexError) as error:
        raise CliError("PROVENANCE_INSTALLED_OVERLAY") from error
    target = Path(target_line)
    if not target.is_absolute():
        target = egg_link.parent / target
    expected_build_root = (repository_root / "build/so101_demo_py").resolve()
    if target.resolve() != expected_build_root:
        raise CliError("PROVENANCE_INSTALLED_OVERLAY")
    entry_points = expected_build_root / "so101_demo_py.egg-info/entry_points.txt"
    if (
        not entry_points.is_file()
        or entry_points.is_symlink()
        or not console_path.is_file()
        or console_path.is_symlink()
    ):
        raise CliError("PROVENANCE_CONSOLE_METADATA")
    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(entry_points.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, configparser.Error) as error:
        raise CliError("PROVENANCE_CONSOLE_METADATA") from error
    entry_point = "so101_demo.cli.mujoco_parallel_batch:main"
    if (
        "console_scripts" not in parser
        or parser["console_scripts"].get("so101_parallel_batch") != entry_point
    ):
        raise CliError("PROVENANCE_CONSOLE_METADATA")
    expected_wrapper = _expected_console_wrapper()
    try:
        console_bytes = console_path.read_bytes()
    except OSError as error:
        raise CliError("PROVENANCE_CONSOLE_CONTENT") from error
    if console_bytes != expected_wrapper:
        raise CliError("PROVENANCE_CONSOLE_CONTENT")
    source_tree = source_hash(source_package)
    build_tree = source_hash(build_package.resolve())
    if build_tree != source_tree:
        raise CliError("PROVENANCE_INSTALLED_BYTES")
    return {
        "module_import_path": str(expected_module),
        "module_import_sha256": _sha256(expected_module),
        "source_module_tree_sha256": source_tree,
        "installed_module_tree_path": str(build_package),
        "installed_module_tree_sha256": build_tree,
        "installed_egg_link_path": str(egg_link),
        "installed_egg_link_sha256": _sha256(egg_link),
        "installed_entry_points_path": str(entry_points),
        "installed_entry_points_sha256": _sha256(entry_points),
    }


def _expected_console_wrapper() -> bytes:
    """Return the frozen setuptools wrapper for the reviewed entry point."""

    return b"""#!/usr/bin/python3
# EASY-INSTALL-ENTRY-SCRIPT: 'so101-demo-py','console_scripts','so101_parallel_batch'
import re
import sys

# for compatibility with easy_install; see #2198
__requires__ = 'so101-demo-py'

try:
    from importlib.metadata import distribution
except ImportError:
    try:
        from importlib_metadata import distribution
    except ImportError:
        from pkg_resources import load_entry_point


def importlib_load_entry_point(spec, group, name):
    dist_name, _, _ = spec.partition('==')
    matches = (
        entry_point
        for entry_point in distribution(dist_name).entry_points
        if entry_point.group == group and entry_point.name == name
    )
    return next(matches).load()


globals().setdefault('load_entry_point', importlib_load_entry_point)


if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\\.pyw?|\\.exe)?$', '', sys.argv[0])
    sys.exit(load_entry_point('so101-demo-py', 'console_scripts', 'so101_parallel_batch')())
"""

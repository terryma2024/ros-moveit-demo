"""Source, overlay and installed provenance checks of the parallel batch command."""

from __future__ import annotations

import json

from parallel_batch_cli_support import (
    _canonical_console_wrapper,
    _external_overlay_fixture,
    local_start_guard,  # noqa: F401  (pytest fixtures)
)
import pytest


def test_provenance_rejects_mixed_source_install_overlay_before_snapshot(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.provenance import _validate_provenance_overlay

    repository = tmp_path / "checkout"
    module = repository / "src/so101_demo_py/src/cli/mujoco_parallel_batch.py"
    console = repository / "install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    config = repository / "src/so101_demo_py/config/mujoco/parallel_batch_linux_cuda.yaml"
    points = repository / "src/so101_demo_py/config/mujoco/moveit_expert_validation_points.yaml"
    for path in (module, console, config, points):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("approved", encoding="utf-8")
    _validate_provenance_overlay(repository, module, console, config, points)

    foreign = tmp_path / "other/install/so101_parallel_batch"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("mixed", encoding="utf-8")
    with pytest.raises(CliError, match="MIXED_OVERLAY"):
        _validate_provenance_overlay(repository, module, foreign, config, points)


def test_explicit_external_overlay_binding_accepts_exact_candidate(tmp_path):
    from so101_demo.cli.mujoco_batch.provenance import _validate_provenance_overlay

    fixture = _external_overlay_fixture(tmp_path)
    identity = _validate_provenance_overlay(
        fixture["repository"],
        fixture["module_import"],
        fixture["console"],
        fixture["config"],
        fixture["points"],
        module_import_path=fixture["module_import"],
        external_binding=fixture["binding"],
    )

    assert identity["external_overlay_bound"] is True
    assert identity["package_prefixes"]["so101_demo_py"] == str(
        fixture["package_prefix"].resolve()
    )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ("package_prefix", "PACKAGE_PREFIX"),
        ("console", "ARTIFACT_IDENTITY"),
        ("config", "ARTIFACT_IDENTITY"),
    ],
)
def test_external_overlay_binding_rejects_identity_mismatch(tmp_path, mutation, error):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.provenance import _validate_provenance_overlay

    fixture = _external_overlay_fixture(tmp_path)
    document = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    if mutation == "package_prefix":
        document["package_prefixes"]["so101_demo_py"] = str(
            (tmp_path / "foreign-prefix").resolve()
        )
    elif mutation == "console":
        document["artifacts"]["coordinator_console"]["sha256"] = "0" * 64
    else:
        document["artifacts"]["parallel_config"]["sha256"] = "0" * 64
    fixture["binding"].write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CliError, match=error):
        _validate_provenance_overlay(
            fixture["repository"],
            fixture["module_import"],
            fixture["console"],
            fixture["config"],
            fixture["points"],
            module_import_path=fixture["module_import"],
            external_binding=fixture["binding"],
        )


def test_external_overlay_binding_accepts_any_debug_commit_value(tmp_path):
    """The binding's commit is compatibility metadata; byte artifacts still bind it."""

    from so101_demo.cli.mujoco_batch.provenance import _validate_provenance_overlay

    fixture = _external_overlay_fixture(tmp_path)
    document = json.loads(fixture["binding"].read_text(encoding="utf-8"))
    for value in ("b" * 40, "UNRECORDED_SOURCE", None):
        document["source_commit"] = value
        fixture["binding"].write_text(json.dumps(document), encoding="utf-8")
        identity = _validate_provenance_overlay(
            fixture["repository"],
            fixture["module_import"],
            fixture["console"],
            fixture["config"],
            fixture["points"],
            module_import_path=fixture["module_import"],
            external_binding=fixture["binding"],
        )
        assert identity["external_overlay_bound"] is True


def test_external_overlay_remains_rejected_when_not_explicitly_bound(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.provenance import _validate_provenance_overlay

    fixture = _external_overlay_fixture(tmp_path)
    with pytest.raises(CliError, match="MIXED_OVERLAY"):
        _validate_provenance_overlay(
            fixture["repository"],
            fixture["module_source"],
            fixture["console"],
            fixture["config"],
            fixture["points"],
            module_import_path=fixture["module_import"],
        )


def test_installed_provenance_binds_exact_editable_tree_and_rejects_stale_target(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.provenance import _installed_overlay_identity
    from so101_demo.cli.parallel_perception_broker import source_hash

    repository = tmp_path / "checkout"
    source = repository / "src/so101_demo_py/src"
    module = source / "cli/mujoco_parallel_batch.py"
    module.parent.mkdir(parents=True)
    module.write_text("approved = True\n", encoding="utf-8")
    build = repository / "build/so101_demo_py"
    build.mkdir(parents=True)
    (build / "so101_demo").symlink_to(source, target_is_directory=True)
    console = repository / "install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    console.parent.mkdir(parents=True)
    console.write_text("#!/bin/sh\n", encoding="utf-8")
    egg = repository / "install/so101_demo_py/lib/python3.12/site-packages/so101-demo-py.egg-link"
    egg.parent.mkdir(parents=True)
    egg.write_text(str(build) + "\n.\n", encoding="utf-8")
    import_path = build / "so101_demo/cli/mujoco_parallel_batch.py"

    metadata = build / "so101_demo_py.egg-info/entry_points.txt"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "[console_scripts]\n"
        "so101_parallel_batch = so101_demo.cli.mujoco_parallel_batch:main\n",
        encoding="utf-8",
    )

    with pytest.raises(CliError, match="CONSOLE"):
        _installed_overlay_identity(
            repository, import_path, console, source_hash=source_hash
        )

    console.write_text(_canonical_console_wrapper(), encoding="utf-8")
    identity = _installed_overlay_identity(
        repository, import_path, console, source_hash=source_hash
    )
    assert identity["installed_module_tree_sha256"] == source_hash(source)

    stale = repository / "stale/so101_demo"
    stale.mkdir(parents=True)
    (stale / "old.py").write_text("old = True\n", encoding="utf-8")
    (build / "so101_demo").unlink()
    (build / "so101_demo").symlink_to(stale, target_is_directory=True)
    with pytest.raises(CliError, match="INSTALLED_OVERLAY|INSTALLED_BYTES"):
        _installed_overlay_identity(
            repository, import_path, console, source_hash=source_hash
        )

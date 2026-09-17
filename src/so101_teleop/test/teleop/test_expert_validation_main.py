import sys
from types import SimpleNamespace
import json

import pytest

from so101_teleop.expert_validation.main import configured_evidence_root


def test_evidence_root_is_required_absolute_and_not_symlink(tmp_path):
    with pytest.raises(RuntimeError, match="SO101_VALIDATION_EVIDENCE_ROOT_REQUIRED"):
        configured_evidence_root({})
    with pytest.raises(RuntimeError, match="EVIDENCE_ROOT_ABSOLUTE"):
        configured_evidence_root({"SO101_VALIDATION_EVIDENCE_ROOT": "relative"})
    root = (tmp_path / "evidence").resolve()
    root.mkdir()
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(RuntimeError, match="EVIDENCE_ROOT_SYMLINK"):
        configured_evidence_root({"SO101_VALIDATION_EVIDENCE_ROOT": str(link.absolute())})
    assert configured_evidence_root(
        {"SO101_VALIDATION_EVIDENCE_ROOT": str(root)}
    ) == root


def test_validation_main_module_does_not_import_rclpy():
    import so101_teleop.expert_validation.main as validation_main

    assert "rclpy" not in validation_main.__dict__


def test_production_default_broker_image_matches_fixed_coordinator_contract():
    from so101_demo.cli.mujoco_parallel_batch import _BROKER_IMAGE as coordinator_image
    from so101_teleop.expert_validation.production import _BROKER_IMAGE as production_image

    assert production_image == coordinator_image


def test_source_identity_uses_binding_for_copied_installed_module(tmp_path):
    from so101_teleop.expert_validation.production import _source_identity

    source_root = (tmp_path / "checkout").resolve()
    source_root.mkdir()
    installed_module = (
        tmp_path
        / "install/so101_demo_py/lib/python3.12/site-packages/so101_demo/__init__.py"
    )
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("", encoding="utf-8")
    binding = (tmp_path / "binding.json").resolve()
    binding.write_text(
        json.dumps({
            "schema_version": 1,
            "source_root": str(source_root),
            "source_commit": "a" * 40,
        }),
        encoding="utf-8",
    )

    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        if command[-2:] == ["rev-parse", "--show-toplevel"]:
            return SimpleNamespace(stdout=f"{source_root}\n")
        if command[-2:] == ["rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="a" * 40 + "\n")
        if command[-1] == "--untracked-files=no":
            return SimpleNamespace(stdout="")
        raise AssertionError(command)

    assert _source_identity(
        module_path=installed_module,
        provenance_binding=binding,
        subprocess_runner=run,
    ) == (source_root, "a" * 40)
    assert all(str(installed_module.parent) not in command for command in calls)


def test_installed_entry_point_uses_production_factory_and_closes(monkeypatch, tmp_path):
    import so101_teleop.expert_validation.main as validation_main

    root = (tmp_path / "evidence").resolve()
    root.mkdir()
    service = SimpleNamespace(close=lambda: closed.append(True))
    closed = []
    calls = []
    monkeypatch.setenv("SO101_VALIDATION_EVIDENCE_ROOT", str(root))
    monkeypatch.setattr(
        validation_main,
        "create_production_service",
        lambda configured_root: calls.append(configured_root) or service,
    )
    monkeypatch.setattr(
        validation_main,
        "create_expert_validation_app",
        lambda configured_service, _static_dir, *, bind_address: (
            configured_service,
            bind_address,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(run=lambda app, **kwargs: calls.append((app, kwargs))),
    )

    validation_main.main()

    assert calls[0] == root
    assert calls[1][0] == (service, "127.0.0.1")
    assert calls[1][1] == {"host": "127.0.0.1", "port": 8010}
    assert closed == [True]


def test_production_factory_wires_durable_authorities_and_releases_lock(
    monkeypatch, tmp_path
):
    from so101_teleop.expert_validation.production import (
        ProductionRuntimeLayout,
        create_production_service,
    )
    from so101_teleop.expert_validation.store import SupervisorStore

    runtime = tmp_path / "runtime"
    runtime.mkdir()

    def file(name, content="approved\n"):
        path = runtime / name
        path.write_text(content, encoding="utf-8")
        path.chmod(0o700)
        return path.resolve()

    demo_prefix = runtime / "install/so101_demo_py"
    demo_prefix.mkdir(parents=True)
    layout = ProductionRuntimeLayout(
        source_root=tmp_path.resolve(),
        source_commit="a" * 40,
        demo_prefix=demo_prefix.resolve(),
        points_path=file("points.yaml"),
        parallel_config_path=file("parallel.yaml"),
        adaptive_config_path=file("adaptive.yaml"),
        coordinator_executable=file("so101_parallel_batch"),
        cleanup_executable=file("so101_parallel_batch_cleanup"),
        adaptive_wrapper=file("run_so101_adaptive_batch.zsh"),
        provenance_binding=None,
        yolo_weights_path=None,
        grounded_root=None,
        yolo_weights_sha256="0" * 64,
        grounded_manifest_sha256="0" * 64,
        broker_image_id="sha256:" + "b" * 64,
        parallel_acceptance=None,
        adaptive_acceptance=None,
        adaptive_fault_injection=None,
        adaptive_performance_tiers=(),
    )
    monkeypatch.setattr(
        ProductionRuntimeLayout,
        "discover",
        classmethod(lambda _cls, _environment: layout),
    )
    evidence = (tmp_path / "evidence").resolve()
    evidence.mkdir()

    service = create_production_service(evidence, environment={})
    assert service.health() == {"ok": True, "service": "expert-validation"}
    assert service.store is service.supervisor.store
    assert service.supervisor.process_owner._store is service.store
    assert service.lease_service.store is service.store
    assert service.artifacts is not None
    assert service.registry.require("moveit_expert", "validate_pick_place")
    service.close()

    reopened = SupervisorStore.open(evidence / "validation-service")
    reopened.close()

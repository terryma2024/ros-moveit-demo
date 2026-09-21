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


OWNER_TREE_ENV_KEYS = (
    "SO101_OWNER_TOKEN",
    "SO101_OWNER_PARENT_TOKEN",
    "SO101_OWNER_TREE_ROOT",
    "SO101_OWNER_CAMPAIGN_ID",
    "SO101_OWNER_BATCH_ID",
    "SO101_OWNER_GENERATION",
)


def _approved_layout(tmp_path, monkeypatch):
    """The resolved production layout the installed entry point would discover."""

    from so101_teleop.expert_validation.production import ProductionRuntimeLayout

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
    return layout


def _wait_for_file(path, timeout=5.0):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {path}")


def _bind_batch(store, tmp_path, *, campaign_id, batch_id, coordinator_epoch):
    """The real campaign/batch binding a spawn intent's foreign key requires."""

    from so101_teleop.expert_validation.models import (
        BatchBinding,
        CampaignBinding,
        PreflightReceipt,
    )

    store.record_manifest(
        "manifest-wire", {"schema_version": 1}, source_config_sha256="a" * 64, created_at_ns=1
    )
    store.record_preflight_receipt(
        PreflightReceipt(
            receipt_id="receipt-wire",
            campaign_id=campaign_id,
            manifest_id="manifest-wire",
            canonical_start_request_sha256="b" * 64,
            receipt={"admitted": True},
            expires_at_monotonic_ns=10_000,
        )
    )
    store.consume_preflight_and_bind_campaign_batch(
        "receipt-wire",
        "b" * 64,
        CampaignBinding(
            campaign_id=campaign_id,
            manifest_id="manifest-wire",
            executor_id="operator",
            operation_id="operation-wire",
            executor_config_sha256="c" * 64,
            execution_mode="SEQUENTIAL",
            execution_config={"worker_count": 1, "max_points_per_worker": 1},
            preflight_receipt_id="receipt-wire",
        ),
        BatchBinding(
            batch_id=batch_id,
            campaign_id=campaign_id,
            batch_kind="FIRST_PASS",
            point_id=None,
            journal_root=(tmp_path / "journal" / batch_id).resolve(),
            coordinator_epoch=coordinator_epoch,
        ),
        now_monotonic_ns=1,
    )


def test_production_factory_wires_the_owner_tree_record_path(monkeypatch, tmp_path):
    from so101_teleop.expert_validation.coordinator import CoordinatorStartRequest
    from so101_teleop.expert_validation.production import create_production_service

    _approved_layout(tmp_path, monkeypatch)
    evidence = (tmp_path / "evidence").resolve()
    evidence.mkdir()
    tree_root = (evidence / "owner-tree").resolve()
    output = (tmp_path / "child-env.json").resolve()
    script = (
        "import json,os,pathlib,sys,time;"
        "pathlib.Path(sys.argv[1]).write_text("
        "json.dumps({key: os.environ.get(key) for key in sys.argv[2:]}));"
        "time.sleep(60)"
    )
    batch_root = (tmp_path / "batch-root").resolve()
    start = CoordinatorStartRequest(
        campaign_id="campaign-wire",
        batch_id="b001",
        execution_mode="SEQUENTIAL",
        worker_count=1,
        max_points_per_worker=1,
        argv=(sys.executable, "-c", script, str(output), *OWNER_TREE_ENV_KEYS),
        environment={},
        batch_root=batch_root,
        control_socket=batch_root / "control.sock",
        control_token_sha256="a" * 64,
        coordinator_epoch=2,
    )

    service = create_production_service(evidence, environment={})
    running = None
    try:
        owner = service.supervisor.process_owner
        assert owner.owner_tree_root == tree_root
        # The wiring must not require the directory to exist before the first spawn.
        assert tree_root.exists() is False
        _bind_batch(
            service.store, tmp_path, campaign_id="campaign-wire", batch_id="b001",
            coordinator_epoch=2,
        )

        running = owner.spawn(start)
        _wait_for_file(output)
        environment = json.loads(output.read_text(encoding="utf-8"))
        token = environment["SO101_OWNER_TOKEN"]
        directory = tree_root / "campaign-wire" / "b001"
        intent_path = directory / f"{token}.intent.json"
        confirmation_path = directory / f"{token}.confirmed.json"

        assert intent_path.is_file(), "the ADAPTER intent must be durable under the evidence root"
        assert confirmation_path.is_file()
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        assert intent["schema"] == "so101.owner-intent/1"
        assert intent["role"] == "ADAPTER"
        assert intent["parent_spawn_token"] is None
        assert intent["campaign_id"] == "campaign-wire"
        assert intent["batch_id"] == "b001"
        assert intent["generation"] == 2
        confirmation = json.loads(confirmation_path.read_text(encoding="utf-8"))
        assert confirmation["schema"] == "so101.owner-confirmation/1"
        assert confirmation["spawn_token"] == token
        assert confirmation["pid"] == running.pid
        assert confirmation["started_ticks"] == running.started_ticks
        assert confirmation["command_sha256"] == running.argv_sha256

        assert environment == {
            "SO101_OWNER_TOKEN": token,
            "SO101_OWNER_PARENT_TOKEN": "",
            "SO101_OWNER_TREE_ROOT": str(tree_root),
            "SO101_OWNER_CAMPAIGN_ID": "campaign-wire",
            "SO101_OWNER_BATCH_ID": "b001",
            "SO101_OWNER_GENERATION": "2",
        }
        # The service's own store indexes the same durable record, so a recovery reads one tree.
        records = service.store.owner_tree("campaign-wire", "b001")
        assert [(record.intent.spawn_token, record.confirmed.pid) for record in records] == [
            (token, running.pid)
        ]
    finally:
        if running is not None:
            # The production owner has no test cleanup gate, so clear its group directly.
            from so101_teleop.owned_group import terminate_group

            terminate_group(pgid=running.pgid, leader_pid=running.pid, timeout_s=1.0)
        service.close()

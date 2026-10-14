"""A stored PARALLEL or ADAPTIVE campaign is fenced to operator recovery after a restart, never relaunched.

Native multi-worker execution is gone. A campaign of those modes that was still running (or whose
cleanup was never confirmed) when the service stopped cannot be adopted by a single-worker service, so
the restore records a durable recovery fence: the page projects ``NEEDS_OPERATOR_RECOVERY`` and no new
campaign or retry starts until an operator resolves it. The store here is built by the test itself.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_teleop.expert_validation.catalog import CatalogPoint, PointSelection
from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    PreflightReceipt,
)
from so101_teleop.expert_validation.production import ProductionExpertValidationService
from so101_teleop.expert_validation.store import SupervisorStore

SHA = "a" * 64


def _selection():
    points = tuple(
        CatalogPoint(
            id=f"point_{index}", label=f"Point {index}", source="generated", stratum="near/center",
            position_world_m=(float(index), 0.0, 0.0), display_id=f"P{index:02d}",
        )
        for index in range(1, 5)
    )
    return PointSelection("catalog", 1, SHA, points, tuple(p.id for p in points), SHA)


def _store_with_campaign(tmp_path, *, campaign_id, mode, config):
    """One durable campaign row of ``mode``, written the way the supervisor writes it."""

    store = SupervisorStore.open((tmp_path / "store").resolve())
    if store.manifest("manifest-1", current_source_config_sha256=SHA) is None:
        store.record_manifest(
            "manifest-1",
            {"catalog_sha256": SHA, "selection_sha256": SHA,
             "point_ids": ["point_1", "point_2", "point_3", "point_4"]},
            source_config_sha256=SHA, created_at_ns=1,
        )
    receipt_id = f"receipt-{campaign_id}"
    store.record_preflight_receipt(
        PreflightReceipt(
            receipt_id=receipt_id, campaign_id=campaign_id, manifest_id="manifest-1",
            canonical_start_request_sha256=SHA, receipt={"admitted": True},
            expires_at_monotonic_ns=10_000_000_000,
        )
    )
    store.consume_preflight_and_bind_campaign_batch(
        receipt_id, SHA,
        CampaignBinding(
            campaign_id=campaign_id, manifest_id="manifest-1", executor_id="expert-validation-web",
            operation_id="first-pass", executor_config_sha256=SHA, execution_mode=mode,
            execution_config=config, preflight_receipt_id=receipt_id,
        ),
        BatchBinding(
            batch_id="b001", campaign_id=campaign_id, batch_kind="FIRST_PASS", point_id=None,
            journal_root=(tmp_path / "store/campaigns" / campaign_id / "b001").resolve(),
            coordinator_epoch=1,
        ),
        now_monotonic_ns=1,
    )
    return store


def _service(tmp_path, store):
    install = tmp_path / "install"
    install.mkdir(parents=True, exist_ok=True)
    for name in ("so101_parallel_batch", "cleanup", "run_adaptive.zsh"):
        (install / name).write_text("binary\n", encoding="utf-8")
    (tmp_path / "points.yaml").write_text("points: []\n", encoding="utf-8")
    (tmp_path / "adaptive.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (tmp_path / "parallel.yaml").write_text("schema_version: 3\n", encoding="utf-8")
    launched = []

    class NoLaunch:
        _requests = {}

        def __getattr__(self, name):  # any launch or cancel path would land here
            launched.append(name)
            raise AssertionError(f"restore must not call the supervisor: {name}")

    supervisor = NoLaunch()
    service = object.__new__(ProductionExpertValidationService)
    service.store = store
    service.supervisor = supervisor
    service._campaigns = {}
    service._campaign_requests = {}
    service.layout = SimpleNamespace(
        demo_prefix=install.resolve(),
        points_path=(tmp_path / "points.yaml").resolve(),
        parallel_config_path=(tmp_path / "parallel.yaml").resolve(),
        adaptive_config_path=(tmp_path / "adaptive.yaml").resolve(),
        coordinator_executable=(install / "so101_parallel_batch").resolve(),
        cleanup_executable=(install / "cleanup").resolve(),
        adaptive_wrapper=(install / "run_adaptive.zsh").resolve(),
        yolo_weights_path=None, yolo_weights_sha256=SHA, grounded_root=None,
        grounded_manifest_sha256=SHA, broker_image_id="sha256:" + SHA, provenance_binding=None,
        source_commit="1" * 40,
    )
    service._selection = lambda manifest_id: _selection()
    return service, launched


MULTI_WORKER_ROWS = [
    ("PARALLEL", {"worker_count": 4}),
    ("ADAPTIVE", {
        "preferred_worker_count": 8, "fallback_worker_counts": [6, 4, 2, 1],
        "initial_points_per_worker": 3, "worker_start_timeout_s": 120.0,
        "max_infra_attempts_per_point": 5, "yolo_executor_count": 2,
    }),
]


@pytest.mark.parametrize("mode,config", MULTI_WORKER_ROWS)
def test_a_non_terminal_multi_worker_campaign_is_fenced_and_never_relaunched(tmp_path, mode, config):
    store = _store_with_campaign(tmp_path, campaign_id="campaign-1", mode=mode, config=config)
    try:
        service, launched = _service(tmp_path, store)
        assert store.recovery_fence("campaign-1") is None
        service._restore_campaigns()

        projection = service._campaigns["campaign-1"]
        assert projection["status"] == "NEEDS_OPERATOR_RECOVERY"
        assert projection["execution_mode"] == mode
        fence = store.recovery_fence("campaign-1")
        assert fence is not None and fence["reason"] == "NATIVE_MULTI_WORKER_REMOVED"
        assert fence["batch_id"] == "b001"
        # The fence blocks every new start and retry until an operator resolves it.
        assert store.has_recovery_fence() is True
        # Restoring twice is idempotent and still launches nothing.
        service._restore_campaigns()
        assert service._campaigns["campaign-1"]["status"] == "NEEDS_OPERATOR_RECOVERY"
        assert launched == []
    finally:
        store.close()


def test_a_sequential_campaign_is_not_fenced_by_the_restore(tmp_path):
    store = _store_with_campaign(
        tmp_path, campaign_id="campaign-2", mode="SEQUENTIAL", config={"worker_count": 1}
    )
    try:
        service, launched = _service(tmp_path, store)
        service._restore_campaigns()
        assert service._campaigns["campaign-2"]["status"] == "STARTED"
        assert store.recovery_fence("campaign-2") is None
        assert store.has_recovery_fence() is False
        assert launched == []
    finally:
        store.close()

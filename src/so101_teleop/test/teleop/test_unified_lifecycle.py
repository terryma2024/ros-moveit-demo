"""Lifecycle, composition and no-ROS import tests for the unified service."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from so101_teleop.unified.app import create_unified_app, schema_services
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.compose import compose_domain_services
from so101_teleop.unified.contracts import MutationError, QualificationView
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.lifecycle import UnifiedLifecycle
from so101_teleop.unified.ports import UnknownBudgetSource, UnifiedServices
from retry_fixture import build_environment


class FakeBridge:
    def __init__(self, *, error: str | None = None) -> None:
        self.started = False
        self.stopped = False
        self.error = error

    async def start(self):
        self.started = True
        if self.error:
            raise RuntimeError(self.error)
        return "owner-key"

    async def stop_owned(self) -> None:
        self.stopped = True


class FakeTeleop:
    async def health(self):
        return {"ok": True}


class FakeValidation:
    def __init__(self, *, maintenance_error: str | None = None) -> None:
        self.maintenance_error = maintenance_error
        self.maintenance_started = False

    def start_maintenance(self) -> None:
        self.maintenance_started = True
        if self.maintenance_error:
            raise RuntimeError(self.maintenance_error)


def services(**overrides) -> UnifiedServices:
    base = dict(teleop=None, tasks=None, validation=None, arbiter=None, instances=None)
    base.update(overrides)
    return UnifiedServices(**base)


def test_startup_marks_teleop_unavailable_when_the_bridge_fails():
    async def run():
        bridge = FakeBridge(error="IPC_CONNECT_FAILED")
        composition = services(teleop=FakeTeleop(), bridge=bridge)
        lifecycle = UnifiedLifecycle(composition)
        await lifecycle.startup()
        assert bridge.started
        assert composition.teleop is None, "a broken bridge must lower Teleop readiness"
        assert lifecycle.teleop_error and "IPC_CONNECT_FAILED" in lifecycle.teleop_error
        assert lifecycle.started and lifecycle.accepting_mutations
        assert lifecycle.teleop_ready() is False
        await lifecycle.shutdown()
        assert bridge.stopped

    asyncio.run(run())


def test_startup_refuses_to_serve_over_a_blocked_arbiter(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        try:
            arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
            arbiter.block("OWNER_UNKNOWN")
            lifecycle = UnifiedLifecycle(services(arbiter=arbiter))
            with pytest.raises(MutationError, match="BLOCKED"):
                await lifecycle.startup()
            assert lifecycle.started is False
            assert lifecycle.accepting_mutations is False
        finally:
            store.close()

    asyncio.run(run())


def test_validation_maintenance_failure_is_recorded_without_hiding_history():
    async def run():
        validation = FakeValidation(maintenance_error="LEASE_STORE_UNREADABLE")
        lifecycle = UnifiedLifecycle(services(validation=validation))
        await lifecycle.startup()
        assert validation.maintenance_started
        assert lifecycle.validation_error and "LEASE_STORE_UNREADABLE" in lifecycle.validation_error
        assert lifecycle.started is True, "a blocked domain must not stop the web process"
        assert lifecycle.accepting_mutations is True
        await lifecycle.shutdown()

    asyncio.run(run())


def test_shutdown_stops_accepting_mutations_before_closing_the_bridge():
    async def run():
        bridge = FakeBridge()
        lifecycle = UnifiedLifecycle(services(bridge=bridge))
        await lifecycle.startup()
        assert lifecycle.accepting_mutations is True
        await lifecycle.shutdown()
        assert lifecycle.accepting_mutations is False
        assert bridge.stopped is True
        assert lifecycle.started is False

    asyncio.run(run())


def test_composition_builds_a_readable_app_without_ros(tmp_path, monkeypatch):
    """A valid validation domain remains available without a ROS worker."""

    monkeypatch.delenv("SO101_UNIFIED_ROS_PYTHON", raising=False)
    monkeypatch.delenv("SO101_UNIFIED_INSTALL_PREFIX", raising=False)
    environment = build_environment(tmp_path)
    environment["SO101_UNIFIED_RUNTIME_ID"] = "R-test"
    composition = compose_domain_services(
        environment=environment,
        evidence_root=tmp_path / "evidence",
        worker=None,
        bridge_owner=None,
    )
    try:
        assert composition.teleop is None
        assert composition.arbiter is not None and composition.instances is not None
        assert composition.safety is not None
        assert composition.teleop is None and composition.bridge is None
        assert isinstance(composition.budget_source, UnknownBudgetSource)
        assert composition.validation_error is None
        assert composition.validation is not None
        app = create_unified_app(composition, bind_address="127.0.0.1")
        with TestClient(app) as client:
            live = client.get("/health/live")
            assert live.status_code == 200
            assert client.get("/health/ready").status_code in (200, 503)
            assert client.get("/snapshot").json()["code"] == "TELEOP_UNAVAILABLE"
            assert client.get("/tasks/runs").json()["code"] == "TASKS_UNAVAILABLE"
    finally:
        composition.store.close()


def test_composition_reports_missing_validation_points_without_hiding_the_app(tmp_path):
    environment = build_environment(tmp_path)
    environment["SO101_VALIDATION_POINTS"] = str(tmp_path / "missing-points.yaml")
    composition = compose_domain_services(
        environment=environment,
        evidence_root=tmp_path / "evidence",
        worker=None,
        bridge_owner=None,
    )
    try:
        assert "SO101_VALIDATION_POINTS_INVALID" in composition.validation_error
        assert composition.validation is None
        with TestClient(create_unified_app(composition, bind_address="127.0.0.1")) as client:
            assert client.get("/health/live").status_code == 200
    finally:
        composition.store.close()


def test_budget_view_fields_match_the_task_ten_contract():
    view = UnknownBudgetSource().decision(5, "R")
    assert isinstance(view, QualificationView)
    assert set(QualificationView.__dataclass_fields__) == {
        "selected_n",
        "status",
        "reasons",
        "runtime_identity",
        "contract_version",
        "profile_sha256",
        "approval_sha256",
    }
    assert view.status == "UNKNOWN" and view.reasons == ("BUDGET_PROVIDER_NOT_READY",)
    assert view.selected_n == 5 and view.contract_version == 2
    assert view.profile_sha256 is None and view.approval_sha256 is None


def test_web_entry_point_has_no_helper_or_driver_flags():
    from so101_teleop.unified.main import build_parser

    parser = build_parser()
    options = {action.dest for action in parser._actions}
    assert options == {"help", "host", "port", "static_dir", "capture_dir", "check"}, options
    for forbidden in ("driver", "helper", "execution_port", "budget_source"):
        assert forbidden not in options


def test_unified_app_import_probe_never_loads_ros(tmp_path):
    """The web import chain must stay ROS-free, source and installed alike."""
    program = textwrap.dedent(
        """
        import importlib.abc, runpy, sys
        class NoRos(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split('.')[0] in {'rclpy','moveit_msgs','sensor_msgs','trajectory_msgs'}:
                    raise ImportError('ROS_IMPORT_IN_WEB: ' + fullname)
        sys.meta_path.insert(0, NoRos())
        import so101_teleop.unified.app, so101_teleop.openapi_export
        runpy.run_module('so101_teleop.unified.main', run_name='import_probe')
        assert 'rclpy' not in sys.modules
        print('UNIFIED_WEB_IMPORT_ROS_FREE')
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert "UNIFIED_WEB_IMPORT_ROS_FREE" in completed.stdout

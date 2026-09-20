"""The migrated Teleop surface must exist on the unified app.

This test replaces the legacy/unified parity comparison that lived here while
`so101_teleop/api.py` still carried its own route table (implementation ledger CP-69). That table is
deleted, so the guard now asserts the thing that still matters: every route the legacy per-domain tests
were migrated onto is actually served by the unified app, and the unified-only additions are present
too.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from so101_teleop.unified.app import create_unified_app, schema_services


def _route_pairs(app) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path is None:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            pairs.add((method, path))
    return pairs


def test_the_migrated_teleop_surface_is_served_by_the_unified_app():
    unified = _route_pairs(create_unified_app(schema_services(), bind_address="127.0.0.1"))
    for pair in [
        ("POST", "/plans/{plan_id}/execute"),
        ("POST", "/plan/joints"),
        ("POST", "/plan/tcp"),
        ("POST", "/gripper/execute"),
        ("POST", "/execution/cancel"),
        ("POST", "/scene/repair"),
        ("POST", "/robot/home"),
        ("POST", "/simulation/reset"),
        ("POST", "/gazebo/screenshot"),
        ("POST", "/gazebo/camera/presets/{preset}"),
        ("POST", "/parameters/{operation}"),
        ("POST", "/workflow/{operation}"),
        ("GET", "/health"),
        ("GET", "/snapshot"),
        ("GET", "/capabilities"),
        ("GET", "/gazebo/camera/presets"),
        ("GET", "/tasks/presets"),
        ("POST", "/tasks/runs"),
        ("GET", "/tasks/runs"),
        ("GET", "/tasks/artifacts/{artifact_id}"),
        ("GET", "/expert-validation/capabilities"),
        ("POST", "/expert-validation/campaigns"),
    ]:
        assert pair in unified, pair


def test_the_unified_app_keeps_its_additions():
    unified = _route_pairs(create_unified_app(schema_services(), bind_address="127.0.0.1"))
    assert {
        ("POST", "/plans/{plan_id}/execute-all"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("POST", "/control/instances"),
        ("POST", "/control/instances/handoff"),
    } <= unified


def test_there_is_exactly_one_route_table_in_the_package():
    """`api.create_app` and its duplicate closures are gone (CP-83)."""
    import so101_teleop.api as compat

    assert not hasattr(compat, "create_app")
    assert callable(compat.validate_bind_address)

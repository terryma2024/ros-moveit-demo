"""Drift guard for the legacy factory while it still owns its own route closures.

CP-67 recorded that `so101_teleop/api.py:create_app` keeps a second, hand-maintained route table that
the plan wants removed. Until that refactor lands, this test makes the duplication *detected*: every
path and method the legacy factory serves must also exist in the unified app, so a route added to the
old factory alone fails here instead of silently shipping only on the legacy surface.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from so101_teleop.api import create_app as create_legacy_app
from so101_teleop.unified.app import create_unified_app, schema_services


class _LegacyStubService:
    """The route table is what matters here; nothing is dispatched by this test."""

    async def camera_presets(self):
        return {"presets": []}


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


def test_every_legacy_route_also_exists_in_the_unified_app():
    legacy = _route_pairs(create_legacy_app(_LegacyStubService()))
    unified = _route_pairs(
        create_unified_app(schema_services(), bind_address="127.0.0.1")
    )
    legacy_only = sorted(legacy - unified)
    assert legacy_only == [], (
        "these routes exist only on the legacy factory and would ship nowhere else: "
        f"{legacy_only}"
    )


def test_the_unified_app_adds_rather_than_replaces_surfaces():
    legacy = _route_pairs(create_legacy_app(_LegacyStubService()))
    unified = _route_pairs(
        create_unified_app(schema_services(), bind_address="127.0.0.1")
    )
    assert {("POST", "/plans/{plan_id}/execute-all")} <= unified
    assert {("GET", "/health/live"), ("GET", "/health/ready")} <= unified
    assert {("POST", "/control/instances"), ("POST", "/control/instances/handoff")} <= unified
    # And the legacy surface is still a real subset, not an empty one.
    assert {("POST", "/gripper/execute"), ("GET", "/snapshot")} <= legacy


def test_legacy_factory_still_answers_its_own_routes():
    with TestClient(create_legacy_app(_LegacyStubService())) as client:
        assert client.get("/gazebo/camera/presets").status_code == 200

"""Unified API factory tests: one route table, no deny shim, real schemas."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from so101_teleop.unified.app import (
    API_NAMESPACES,
    create_unified_app,
    schema_services,
)


AUTHORITY_HEADERS = {
    "X-SO101-Instance-ID": "i1",
    "X-SO101-Instance-Proof": "p1",
    "X-SO101-Channel-Revision": "1",
    "X-SO101-Execution-Generation": "1",
}


@pytest.fixture()
def app():
    return create_unified_app(
        schema_services(), static_dir=None, capture_dir=None, bind_address="127.0.0.1"
    )


def test_single_factory_has_real_tasks_and_validation_without_deny(app):
    registered_routes = [
        route
        for included in app.routes
        for route in getattr(getattr(included, "original_router", None), "routes", (included,))
    ]
    routes = [
        route
        for route in registered_routes
        if getattr(route, "path", None) == "/tasks/runs" and "POST" in getattr(route, "methods", set())
    ]
    assert len(routes) == 1
    assert not any(getattr(route, "name", "") == "disabled_tasks" for route in registered_routes)
    schema = app.openapi()
    assert "/expert-validation/campaigns" in schema["paths"]
    assert "/plans/{plan_id}/execute-all" in schema["paths"]
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.post(
            "/gripper/execute",
            json={
                "command_id": "old",
                "lease_id": "l",
                "session_id": "s",
                "target_position_rad": 0.0,
            },
        )
        assert response.json()["code"] == "CONTROLLER_INSTANCE_REQUIRED"


def test_no_duplicate_operation_ids_in_the_unified_schema(app):
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids)), "operation ids must be unique"
    for path in ("/health", "/health/live", "/health/ready", "/tasks/runs", "/expert-validation/campaigns"):
        assert path in schema["paths"], path


def test_legacy_mutation_without_authority_is_refused_with_a_structured_code(app):
    with TestClient(app) as client:
        for path, body in (
            ("/gripper/execute", {"command_id": "c1"}),
            ("/plan/joints", {"command_id": "c2"}),
            ("/robot/home", {"command_id": "c3"}),
            ("/execution/cancel", {"command_id": "c4"}),
            ("/tasks/runs", {"command_id": "c5"}),
            ("/expert-validation/campaigns", {"contract_version": 3}),
        ):
            response = client.post(path, json=body)
            assert response.status_code == 409, path
            assert response.json()["code"] == "CONTROLLER_INSTANCE_REQUIRED", path

        response = client.put("/expert-validation/lease/l1", json={"service_session_id": "s", "generation": 1})
        assert response.json()["code"] == "CONTROLLER_INSTANCE_REQUIRED"
        response = client.request(
            "DELETE",
            "/expert-validation/lease/l1",
            json={"service_session_id": "s", "generation": 1},
        )
        assert response.json()["code"] == "CONTROLLER_INSTANCE_REQUIRED"


def test_authority_headers_without_a_registry_fail_closed(app):
    with TestClient(app) as client:
        response = client.post(
            "/gripper/execute", json={"command_id": "c1"}, headers=AUTHORITY_HEADERS
        )
        assert response.status_code == 503
        assert response.json()["code"] == "SERVICE_NOT_COMPOSED"


def test_read_only_routes_stay_reachable_when_a_domain_is_unavailable(app):
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["schema_only"] is True
        assert client.get("/health").json()["domains"]["validation"] == "ready"
        assert client.get("/tasks/runs").json() == []
        capabilities = client.get("/expert-validation/capabilities").json()
        assert capabilities["available"] is True
        assert [item["selected_n"] for item in capabilities["worker_qualifications"]] == list(range(2, 9))
        assert all(item["status"] == "UNKNOWN" for item in capabilities["worker_qualifications"])


def test_unknown_api_paths_never_return_the_spa_fallback(tmp_path):
    static = tmp_path / "dist"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>shell</html>")
    (static / "assets" / "app.js").write_text("console.log('ok')")
    app = create_unified_app(
        schema_services(), static_dir=static, capture_dir=None, bind_address="127.0.0.1"
    )
    with TestClient(app) as client:
        assert client.get("/assets/app.js").text == "console.log('ok')"
        for page in ("/", "/tasks", "/expert-validation"):
            assert "shell" in client.get(page).text, page
        for namespace in API_NAMESPACES:
            response = client.get(f"/{namespace}/definitely-unknown")
            assert response.status_code == 404, namespace
            assert response.headers["content-type"].startswith("application/json"), namespace
        deep_link = client.get("/expert-validation/campaigns/unknown-id")
        assert deep_link.status_code == 409 or deep_link.status_code == 404


def test_legacy_execution_contract_is_rejected_before_body_validation(app):
    with TestClient(app) as client:
        response = client.post(
            "/expert-validation/campaigns",
            json={
                "contract_version": 3,
                "max_points_per_worker": 4,
                "service_session_id": "s",
                "lease_id": "l",
                "lease_generation": 1,
                "manifest_id": "m",
            },
            headers=AUTHORITY_HEADERS,
        )
        assert response.status_code in (409, 422)
        assert response.json()["code"].startswith("LEGACY_")


def test_bind_address_policy_is_enforced():
    with pytest.raises(ValueError, match="BIND_ADDRESS_UNSAFE"):
        create_unified_app(
            schema_services(), static_dir=None, capture_dir=None, bind_address="0.0.0.0"
        )
    app = create_unified_app(
        schema_services(), static_dir=None, capture_dir=None, bind_address="100.101.102.103"
    )
    assert app is not None


def test_instance_registration_route_requires_a_composed_registry(app):
    with TestClient(app) as client:
        response = client.post("/control/instances", json={"domain": "teleop"})
        assert response.status_code == 503
        assert response.json()["code"] == "SERVICE_NOT_COMPOSED"


def test_authority_headers_are_part_of_the_generated_contract(app):
    """The plan requires the authority headers to be generated into the single OpenAPI document,
    not just read off the raw request."""
    schema = app.openapi()
    for path in ("/gripper/execute", "/plan/joints", "/robot/home", "/tasks/runs"):
        operation = schema["paths"][path]["post"]
        names = {parameter["name"] for parameter in operation.get("parameters", [])}
        assert names >= {
            "X-SO101-Instance-ID",
            "X-SO101-Instance-Proof",
            "X-SO101-Channel-Revision",
            "X-SO101-Execution-Generation",
        }, (path, names)
    for name in ("InstanceProofResponse", "QualificationViewResponse"):
        assert name in schema["components"]["schemas"], name

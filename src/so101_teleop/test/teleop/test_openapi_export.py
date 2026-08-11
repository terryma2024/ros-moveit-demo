import json

from so101_teleop.openapi_export import export_openapi


def test_openapi_export_is_byte_deterministic_and_contains_control_routes(tmp_path):
    """Nondeterministic or incomplete schema output would silently stale generated clients."""
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    export_openapi(first)
    export_openapi(second)

    assert first.read_bytes() == second.read_bytes()
    schema = json.loads(first.read_text())
    assert schema["info"]["title"] == "SO-101 Teleop"
    assert "/plan/tcp" in schema["paths"]
    assert "/workflow/{operation}" in schema["paths"]
    assert "/gazebo/camera/presets" in schema["paths"]
    assert "/gazebo/camera/presets/{preset}" in schema["paths"]


def test_openapi_contains_physical_outcome_evidence_schema(tmp_path):
    output = tmp_path / "openapi.json"
    export_openapi(output)

    schema = json.loads(output.read_text())
    assert "PhysicalOutcomeEvidence" in schema["components"]["schemas"]
    snapshot = schema["components"]["schemas"]["TelemetrySnapshot"]
    assert "physical_outcome" in snapshot["properties"]


def test_capabilities_route_exports_a_typed_backend_contract(tmp_path):
    output = tmp_path / "openapi.json"
    export_openapi(output)

    schema = json.loads(output.read_text())
    response = schema["paths"]["/capabilities"]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/BackendCapabilitiesResponse"
    }
    capabilities = schema["components"]["schemas"]["BackendCapabilityMap"]
    assert set(capabilities["required"]) == {
        "backend_probe", "workflow_execute", "workflow_start", "workflow_run",
        "workflow_resume", "reset_world", "scene_operations",
        "physical_observation", "manual_joint_execute", "manual_tcp_execute",
        "camera_presets",
    }

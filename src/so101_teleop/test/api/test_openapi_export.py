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
        "workflow_resume", "workflow_stop", "reset_world", "scene_operations",
        "physical_observation", "manual_joint_execute", "manual_tcp_execute",
        "camera_presets",
        "task_batch", "task_reachability", "sensor_capture",
        "task_environment_shutdown",
    }


def test_openapi_exports_separate_task_station_contract(tmp_path):
    output = tmp_path / "openapi.json"
    export_openapi(output)
    schema = json.loads(output.read_text())
    assert {
        "/tasks/presets", "/tasks/reachability", "/tasks/runs",
        "/tasks/runs/{run_id}", "/tasks/runs/{run_id}/cancel",
        "/tasks/runs/{run_id}/recovery", "/tasks/captures",
        "/tasks/captures/{capture_id}/rendered-image",
        "/tasks/artifacts/{artifact_id}", "/tasks/environment/shutdown",
    } <= set(schema["paths"])
    assert "TaskRunRequest" in schema["components"]["schemas"]


def test_unified_export_is_one_schema_and_the_views_are_projections(tmp_path):
    import json

    from so101_teleop.openapi_export import (
        export_openapi,
        export_unified_openapi,
    )

    unified_path = export_unified_openapi(tmp_path / "unified.json")
    teleop_path = export_openapi(tmp_path / "teleop.json")
    unified = json.loads(unified_path.read_text())
    teleop = json.loads(teleop_path.read_text())

    assert unified["info"]["title"] == "SO-101 Unified"
    assert "/tasks/runs" in unified["paths"]
    assert not any(path.startswith("/expert-validation") for path in unified["paths"])
    assert "/plans/{plan_id}/execute-all" in unified["paths"]

    for view in (teleop,):
        assert set(view["paths"]) <= set(unified["paths"])
        for path, item in view["paths"].items():
            assert item == unified["paths"][path], path
    assert "/plan/tcp" in teleop["paths"]

    operation_ids = [
        operation["operationId"]
        for path in unified["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))

    again = export_unified_openapi(tmp_path / "unified-again.json")
    assert unified_path.read_bytes() == again.read_bytes()


def test_archive_contract_is_complete_offline_and_absent_from_compatibility(tmp_path):
    from so101_teleop.openapi_export import unified_schema
    schema=unified_schema()
    archive={p:item for p,item in schema['paths'].items() if p.startswith('/api/archives')}
    assert sum(len(item) for item in archive.values())==12
    download=archive['/api/archives/packages/{package_id}/episodes/{scene_id}/files/{file_id}/download']['get']
    assert download['responses']['200']['content']['image/png']['schema']['format']=='binary'
    assert {'EpisodeDetail','EpisodeSeries','FileView','VerifyProgress'} <= set(schema['components']['schemas'])
    compat=json.loads(export_openapi(tmp_path/'compat.json').read_text())
    assert not any(p.startswith('/api/archives') for p in compat['paths'])

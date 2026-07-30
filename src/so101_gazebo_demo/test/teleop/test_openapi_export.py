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

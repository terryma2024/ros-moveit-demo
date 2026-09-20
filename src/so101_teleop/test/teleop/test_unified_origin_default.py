"""The service origin must default to the address it actually serves on.

The registry rejects a channel handshake whose origin is not the service origin, and the default
used to be `http://127.0.0.1:8000` regardless of the port the server was told to bind. A page served
on any other port therefore had every handshake rejected with ORIGIN_REJECTED, which left the runtime
with no authority and made every mutation impossible - a silent, total failure of the authority model
caused by one default value.
"""

from __future__ import annotations

from so101_teleop.unified.main import build_app, build_parser


def _app(port: int, tmp_path, extra: dict[str, str] | None = None):
    args = build_parser().parse_args(["--host", "127.0.0.1", "--port", str(port)])
    environment = {
        "SO101_UNIFIED_EVIDENCE_ROOT": str(tmp_path / "evidence"),
        "SO101_UNIFIED_IPC_SOCKET_BASE": str(tmp_path / "ipc"),
    }
    environment.update(extra or {})
    return build_app(args, environment)


def test_origin_defaults_to_the_served_address(tmp_path):
    app = _app(8801, tmp_path)
    assert app.state.services.instances.origin == "http://127.0.0.1:8801"


def test_explicit_origin_still_wins(tmp_path):
    app = _app(8801, tmp_path, {"SO101_UNIFIED_ORIGIN": "http://127.0.0.1:9999"})
    assert app.state.services.instances.origin == "http://127.0.0.1:9999"

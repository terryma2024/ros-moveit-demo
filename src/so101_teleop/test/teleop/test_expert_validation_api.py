import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from so101_teleop.expert_validation.api import create_expert_validation_app
from so101_teleop.expert_validation.lease import ValidationLeaseService
from so101_teleop.expert_validation.store import SupervisorStore
import pytest


def test_idle_event_socket_disconnect_unsubscribes_without_waiting_for_an_event():
    """A disconnected idle page must not keep an ASGI task alive at shutdown."""
    async def run():
        queue = asyncio.Queue()
        subscriptions = set()
        incoming = asyncio.Queue()
        accepted = asyncio.Event()

        def subscribe():
            subscriptions.add(queue)
            return queue

        app = create_expert_validation_app(SimpleNamespace(
            subscribe=subscribe, unsubscribe=subscriptions.remove,
        ))

        async def send(message):
            if message["type"] == "websocket.accept":
                accepted.set()

        await incoming.put({"type": "websocket.connect"})
        task = asyncio.create_task(app({
            "type": "websocket", "asgi": {"version": "3.0"},
            "scheme": "ws", "path": "/expert-validation/events",
            "raw_path": b"/expert-validation/events", "query_string": b"",
            "headers": [], "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8010), "subprotocols": [],
        }, incoming.get, send))
        try:
            await asyncio.wait_for(accepted.wait(), timeout=2)
            assert subscriptions == {queue}
            await incoming.put({"type": "websocket.disconnect", "code": 1000})
            await asyncio.wait_for(asyncio.shield(task), timeout=2)
            assert subscriptions == set()
            assert queue.empty()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    asyncio.run(run())


class Artifacts:
    def resolve_opaque_id(self, artifact_id):
        assert artifact_id == "artifact-1"
        path = self.root / "artifact.json"
        path.write_text("{}")
        return type(
            "Artifact",
            (),
            {"path": path, "media_type": "application/json"},
        )()


class Service:
    def __init__(self, root):
        self.receipts = {}
        self.artifacts = Artifacts()
        self.artifacts.root = root

    def health(self):
        return {"ok": True, "service": "expert-validation"}

    def capabilities(self):
        return {
            "available": True,
            "execution_modes": ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
        }

    def acquire_lease(self, body):
        return {
            "lease_id": "lease-a",
            "service_session_id": body["service_session_id"],
            "generation": 1,
            "expires_monotonic_ns": 1000,
        }

    def renew_lease(self, lease_id, body):
        return {"lease_id": lease_id, **body, "expires_monotonic_ns": 2000}

    def release_lease(self, lease_id, body):
        return {"lease_id": lease_id, "released": True}

    def create_manifest_from_count(self, total_points):
        return {
            "manifest_id": f"manifest-{total_points}",
            "point_count": total_points,
            "points": [
                {
                    "id": f"anchor-{index}",
                    "display_id": f"A{index}",
                    "label": f"Anchor {index}",
                    "source": "anchor",
                    "stratum": "anchor",
                    "position_world_m": [float(index), 0.0, 0.0],
                }
                for index in range(total_points)
            ],
        }

    def get_manifest(self, manifest_id):
        return {"manifest_id": manifest_id, "stale": False}

    def preflight_api(self, body):
        receipt_id = "receipt-1"
        self.receipts[receipt_id] = dict(body)
        return {
            "receipt_id": receipt_id,
            "admitted": True,
            "manifest_id": body["manifest_id"],
            "execution_mode": body["execution_mode"],
            "execution_config": {
                key: value
                for key, value in body.items()
                if key not in {"service_session_id", "lease_id", "lease_generation", "manifest_id"}
            },
        }

    def start_campaign_api(self, body):
        expected = self.receipts[body["preflight_receipt_id"]]
        comparable = {key: body.get(key) for key in expected}
        if comparable != expected:
            raise ValueError("PREFLIGHT_REQUEST_MISMATCH")
        return {"campaign_id": "campaign-1", "sequence": 1}

    def list_campaigns(self):
        return []

    def get_campaign(self, campaign_id):
        return {"campaign_id": campaign_id, "sequence": 8}

    def cancel_campaign(self, campaign_id, body):
        return {"campaign_id": campaign_id, "status": "CANCELLING"}

    def retry_campaign(self, campaign_id, body):
        return {"campaign_id": campaign_id, "status": "RETRYING"}


def _client(tmp_path):
    return TestClient(create_expert_validation_app(Service(tmp_path.resolve())))


def test_dedicated_root_redirects_and_tasks_are_disabled(tmp_path):
    client = _client(tmp_path)
    assert client.get("/", follow_redirects=False).headers["location"] == "/expert-validation"
    response = client.post("/tasks/runs", json={})
    assert response.status_code == 503
    assert response.json()["code"] == "VALIDATION_TASKS_DISABLED"


def test_validation_page_serves_vite_absolute_asset_urls(tmp_path):
    """The shared Vite build uses /assets, not a validation-only base URL."""
    web_root = tmp_path / "web"
    assets = web_root / "assets"
    assets.mkdir(parents=True)
    (web_root / "index.html").write_text(
        '<script type="module" src="/assets/app.js"></script>'
        '<link rel="stylesheet" href="/assets/app.css">'
    )
    (assets / "app.js").write_text("window.validationPageLoaded = true;")
    (assets / "app.css").write_text("body { color: white; }")
    client = TestClient(create_expert_validation_app(Service(tmp_path), web_root))
    assert client.get("/expert-validation").status_code == 200
    for name, expected in (
        ("app.js", "window.validationPageLoaded = true;"),
        ("app.css", "body { color: white; }"),
    ):
        response = client.get(f"/assets/{name}")
        assert response.status_code == 200
        assert response.text == expected
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/tasks/runs").status_code == 503


def test_server_lifespan_expires_lease_without_browser_traffic_and_stops_monitor(tmp_path):
    """Disconnect leaves authority until expiry, which must run independently of HTTP."""
    async def run():
        store = SupervisorStore.open((tmp_path / "store").resolve())
        clock = [1_000]
        cancellations = []
        cancelled = asyncio.Event()

        def cancel(reason):
            cancellations.append(reason)
            cancelled.set()

        supervisor = SimpleNamespace(
            cancel_for_reason=cancel, has_unresolved_campaign=lambda: True
        )
        lease_service = ValidationLeaseService(
            store, supervisor, clock_ns=lambda: clock[0], duration_ns=100
        )
        app = create_expert_validation_app(SimpleNamespace(lease_service=lease_service))
        try:
            async with app.router.lifespan_context(app):
                first = lease_service.acquire("browser-a")
                await asyncio.sleep(0)
                assert lease_service.current() == first
                assert cancellations == []
                clock[0] = first.expires_monotonic_ns
                await asyncio.wait_for(cancelled.wait(), timeout=2)
                assert lease_service.current() is None
                assert cancellations == ["LEASE_EXPIRED"]
            replacement = lease_service.acquire("browser-b")
            clock[0] = replacement.expires_monotonic_ns
            await asyncio.sleep(0.3)
            assert lease_service.current() == replacement
            assert cancellations == ["LEASE_EXPIRED"]
        finally:
            store.close()

    asyncio.run(run())


def test_failed_lease_maintenance_fails_closed_and_requests_owner_cancel():
    import httpx

    async def run():
        cancellations = []

        def broken_tick():
            raise RuntimeError("STORE_UNAVAILABLE")

        service = SimpleNamespace(
            lease_service=SimpleNamespace(expire_due=broken_tick),
            supervisor=SimpleNamespace(cancel_for_reason=cancellations.append),
        )
        app = create_expert_validation_app(service)
        async with app.router.lifespan_context(app):
            await asyncio.sleep(0)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/expert-validation/campaigns",
                    json={
                        "service_session_id": "browser-a", "lease_id": "lease-a",
                        "lease_generation": 1, "manifest_id": "manifest-a",
                        "execution_mode": "SEQUENTIAL", "worker_count": 1,
                        "max_points_per_worker": 4, "command_id": "start-a",
                        "preflight_receipt_id": "receipt-a",
                    },
                )
            assert response.status_code == 503
            assert response.json()["code"] == "LEASE_MAINTENANCE_FAILED"
            assert cancellations == ["LEASE_MAINTENANCE_FAILED"]

    asyncio.run(run())


def test_retry_requires_lease_command_and_confirmation(tmp_path):
    response = _client(tmp_path).post(
        "/expert-validation/campaigns/c1/full-restart-retries",
        json={
            "service_session_id": "browser-a",
            "lease_id": "lease-a",
            "lease_generation": 1,
            "command_id": "retry-1",
            "point_ids": ["sample_05_near_center"],
            "confirmation": "wrong",
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "CONFIRMATION_REQUIRED"


def test_parallel_start_requires_matching_preflight_and_capacity(tmp_path):
    client = _client(tmp_path)
    body = {
        "contract_version": 3,
        "service_session_id": "browser-a",
        "lease_id": "lease-a",
        "lease_generation": 1,
        "manifest_id": "manifest-20",
        "execution_mode": "PARALLEL",
        "worker_count": 2,
    }
    receipt = client.post("/expert-validation/campaigns/preflight", json=body).json()
    # Version two has no lifetime quota, so the mismatching variable is the exact N.
    response = client.post(
        "/expert-validation/campaigns",
        json={
            **body,
            "command_id": "start-1",
            "worker_count": 3,
            "preflight_receipt_id": receipt["receipt_id"],
        },
    )
    assert response.status_code == 409
    assert response.json()["code"] == "PREFLIGHT_REQUEST_MISMATCH"


def test_adaptive_start_rejects_k_and_freezes_ladder(tmp_path):
    response = _client(tmp_path).post(
        "/expert-validation/campaigns/preflight",
        json={
            "service_session_id": "browser-a",
            "lease_id": "lease-a",
            "lease_generation": 1,
            "manifest_id": "manifest-20",
            "execution_mode": "ADAPTIVE",
            "preferred_worker_count": 8,
            "fallback_worker_counts": [6, 4, 2, 1],
            "initial_points_per_worker": 3,
            "yolo_executor_count": 2,
            "max_points_per_worker": 10,
        },
    )
    assert response.status_code == 422


def test_all_fourteen_routes_and_artifact_download_exist(tmp_path):
    client = _client(tmp_path)
    paths = create_expert_validation_app(Service(tmp_path.resolve())).openapi()["paths"]
    operations = sum(
        len(methods)
        for path, methods in paths.items()
        if path.startswith("/expert-validation/")
    )
    assert operations == 13  # Plus the WebSocket event route gives 14 endpoints.
    response = client.get("/expert-validation/artifacts/artifact-1")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


def test_health_and_capabilities_are_available(tmp_path):
    client = _client(tmp_path)
    assert client.get("/health").json()["ok"] is True
    assert client.get("/expert-validation/capabilities").json()["available"] is True


def test_manifest_response_exposes_declared_point_source(tmp_path):
    response = _client(tmp_path).post(
        "/expert-validation/manifests",
        json={"total_points": 4},
    )

    assert response.status_code == 200
    assert [point["source"] for point in response.json()["points"]] == [
        "anchor",
        "anchor",
        "anchor",
        "anchor",
    ]


def test_fixed_capability_range_and_api_boundaries(tmp_path):
    client = _client(tmp_path)
    assert client.get("/expert-validation/capabilities").json()["fixed_worker_counts"] == [1, 2, 3, 4, 5, 6, 7, 8]
    base = dict(contract_version=3, service_session_id="s", lease_id="l",
                lease_generation=1, manifest_id="m")
    for mode, workers, expected in (("SEQUENTIAL", 1, 200), ("SEQUENTIAL", 2, 422),
                                     ("PARALLEL", 1, 422), ("PARALLEL", 2, 200),
                                     ("PARALLEL", 8, 200), ("PARALLEL", 9, 422)):
        response = client.post("/expert-validation/campaigns/preflight",
                               json={**base, "execution_mode": mode, "worker_count": workers})
        assert response.status_code == expected, response.text
        if expected == 200:
            assert response.json()["execution_config"]["worker_count"] == workers


def test_installed_asset_symlink_chain_is_served_without_shadowing_artifacts(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "app.js").write_text("window.validationLoaded = true;")
    web = tmp_path / "installed"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text('<script src="/assets/app.js"></script>')
    (web / "assets/app.js").symlink_to(source / "app.js")
    service = Service(tmp_path)
    def missing_artifact(artifact_id):
        raise KeyError(artifact_id)
    service.artifacts = SimpleNamespace(resolve_opaque_id=missing_artifact)
    client = TestClient(create_expert_validation_app(service, web))
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/app.js").text == "window.validationLoaded = true;"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/expert-validation/artifacts/missing").status_code == 404
    assert client.get("/expert-validation/results").text == (web / "index.html").read_text()


@pytest.mark.parametrize('legacy_value', [1, 20, None])
def test_new_request_rejects_legacy_key(tmp_path, legacy_value):
    """The lifetime quota is refused by presence, before any service call."""

    client = _client(tmp_path)
    body = {
        'contract_version': 3, 'service_session_id': 'browser-a',
        'lease_id': 'lease-a', 'lease_generation': 1, 'manifest_id': 'manifest-20',
        'execution_mode': 'PARALLEL', 'worker_count': 2, 'command_id': 'start-a',
        'preflight_receipt_id': 'receipt-a',
        'max_points_per_worker': legacy_value,
    }
    response = client.post('/expert-validation/campaigns', json=body)
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED'


@pytest.mark.parametrize('version', [None, 1, 2])
def test_new_request_requires_the_active_contract_version(tmp_path, version):
    client = _client(tmp_path)
    body = {
        'service_session_id': 'browser-a', 'lease_id': 'lease-a', 'lease_generation': 1,
        'manifest_id': 'manifest-20', 'execution_mode': 'SEQUENTIAL', 'worker_count': 1,
        'command_id': 'start-a', 'preflight_receipt_id': 'receipt-a',
    }
    if version is not None:
        body['contract_version'] = version
    response = client.post('/expert-validation/campaigns', json=body)
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION'


def test_capabilities_expose_exact_n_availability_without_quota(tmp_path):
    client = _client(tmp_path)
    capabilities = client.get('/expert-validation/capabilities').json()
    assert 'fixed_max_points_per_worker' not in capabilities
    availability = capabilities['worker_count_availability']
    assert [item['worker_count'] for item in availability] == [2, 3, 4, 5, 6, 7, 8]
    for item in availability:
        # The static DTO default is unknown, never a budget rejection; the real service
        # reports CONFIGURED counts (see test_expert_validation_start_guard.py).
        assert item['selectable'] is False
        assert item['reason_codes'] == ['CAPABILITIES_NOT_LOADED']
        assert item['status'] == 'UNKNOWN'
        assert item['profile_sha256'] is None and item['qualification_sha256'] is None


# --------------------------------------------------------------------------------------
# The macOS W1/W2 support matrix on the API surface
#
# The request carries the routing key `(execution_profile, batch_kind)`; the API refuses a
# claim that contradicts its own mode/worker count before any service call, and the
# capability document can express a W1 (one-worker) entry, which the schema-v3 DTO could not.
# --------------------------------------------------------------------------------------


def test_the_api_accepts_a_closed_profile_claim():
    from so101_teleop.expert_validation.api import CampaignConfiguration

    claim = CampaignConfiguration(
        contract_version=3, service_session_id="s", lease_id="l", lease_generation=1,
        manifest_id="m", execution_mode="SEQUENTIAL", worker_count=1,
        execution_profile="MPS_W1_FIRST_PASS", batch_kind="FIRST_PASS",
    )
    assert claim.execution_profile == "MPS_W1_FIRST_PASS"
    assert claim.batch_kind == "FIRST_PASS"

    w2 = CampaignConfiguration(
        contract_version=3, service_session_id="s", lease_id="l", lease_generation=1,
        manifest_id="m", execution_mode="PARALLEL", worker_count=2,
        execution_profile="MPS_W2_FIRST_PASS", batch_kind="FIRST_PASS",
    )
    assert w2.execution_profile == "MPS_W2_FIRST_PASS"

    retry = CampaignConfiguration(
        contract_version=3, service_session_id="s", lease_id="l", lease_generation=1,
        manifest_id="m", execution_mode="SEQUENTIAL", worker_count=1,
        execution_profile="MPS_W1_FULL_RESTART_RETRY", batch_kind="FULL_RESTART_RETRY",
    )
    assert retry.batch_kind == "FULL_RESTART_RETRY"


def test_the_api_refuses_a_claim_that_contradicts_its_mode_or_worker_count():
    from pydantic import ValidationError

    from so101_teleop.expert_validation.api import CampaignConfiguration

    base = dict(contract_version=3, service_session_id="s", lease_id="l", lease_generation=1,
                manifest_id="m")
    # A W2 profile cannot be claimed while asking for the W1 mode.
    with pytest.raises(ValidationError, match="EXECUTION_PROFILE_MODE"):
        CampaignConfiguration(**base, execution_mode="SEQUENTIAL", worker_count=1,
                              execution_profile="MPS_W2_FIRST_PASS", batch_kind="FIRST_PASS")
    # W1 first-pass and W1 retry are different rows of the matrix, not one profile.
    with pytest.raises(ValidationError, match="EXECUTION_PROFILE_CLAIM"):
        CampaignConfiguration(**base, execution_mode="SEQUENTIAL", worker_count=1,
                              execution_profile="MPS_W1_FIRST_PASS",
                              batch_kind="FULL_RESTART_RETRY")
    with pytest.raises(ValidationError, match="EXECUTION_PROFILE_CLAIM"):
        CampaignConfiguration(**base, execution_mode="SEQUENTIAL", worker_count=1,
                              execution_profile="MPS_W1_FIRST_PASS")
    with pytest.raises(ValidationError, match="EXECUTION_PROFILE_CLAIM"):
        CampaignConfiguration(**base, execution_mode="SEQUENTIAL", worker_count=1,
                              batch_kind="FIRST_PASS")
    with pytest.raises(ValidationError):
        CampaignConfiguration(**base, execution_mode="SEQUENTIAL", worker_count=1,
                              execution_profile="MPS_W8_FIRST_PASS", batch_kind="FIRST_PASS")
    # N>2 is a platform-support refusal, not a shape error: the API carries it to preflight,
    # which refuses it with the stable UNSUPPORTED_ON_MACOS reason.
    oversized = CampaignConfiguration(
        **base, execution_mode="PARALLEL", worker_count=8,
        execution_profile="MPS_W2_FIRST_PASS", batch_kind="FIRST_PASS")
    assert oversized.worker_count == 8


def test_the_preflight_route_refuses_a_cross_profile_claim(tmp_path):
    response = _client(tmp_path).post(
        "/expert-validation/campaigns/preflight",
        json={
            "contract_version": 3, "service_session_id": "s", "lease_id": "l",
            "lease_generation": 1, "manifest_id": "m", "execution_mode": "SEQUENTIAL",
            "worker_count": 1, "execution_profile": "MPS_W2_FIRST_PASS",
            "batch_kind": "FIRST_PASS",
        },
    )
    assert response.status_code == 422, response.text


def test_the_preflight_route_forwards_a_closed_profile_claim(tmp_path):
    response = _client(tmp_path).post(
        "/expert-validation/campaigns/preflight",
        json={
            "contract_version": 3, "service_session_id": "s", "lease_id": "l",
            "lease_generation": 1, "manifest_id": "m", "execution_mode": "SEQUENTIAL",
            "worker_count": 1, "execution_profile": "MPS_W1_FIRST_PASS",
            "batch_kind": "FIRST_PASS",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["admitted"] is True
    assert payload["execution_config"]["worker_count"] == 1


def test_the_capability_document_models_w1_w2_and_the_no_qualification_note():
    from so101_teleop.expert_validation.api import (
        CapabilitiesResponse,
        ExecutionProfileResponse,
        START_GUARD_NOT_A_QUALIFICATION,
        WorkerCountAvailability,
    )

    payload = CapabilitiesResponse(
        available=True,
        execution_modes=("SEQUENTIAL", "PARALLEL"),
        platform="macos",
        execution_profile="MPS_W2_FIRST_PASS",
        execution_schema_version=4,
        execution_config_sha256="a" * 64,
        support_matrix=(
            ExecutionProfileResponse(
                profile="MPS_W2_FIRST_PASS", schema_version=4, execution_mode="PARALLEL",
                worker_count=2, batch_kind="FIRST_PASS"),
            ExecutionProfileResponse(
                profile="MPS_W1_FULL_RESTART_RETRY", schema_version=5,
                execution_mode="SEQUENTIAL", worker_count=1,
                batch_kind="FULL_RESTART_RETRY"),
            ExecutionProfileResponse(
                profile="MPS_W1_FIRST_PASS", schema_version=6, execution_mode="SEQUENTIAL",
                worker_count=1, batch_kind="FIRST_PASS"),
        ),
        worker_count_availability=(
            WorkerCountAvailability(worker_count=1, selectable=True, status="SUPPORTED"),
            WorkerCountAvailability(worker_count=2, selectable=True, status="SUPPORTED"),
            WorkerCountAvailability(
                worker_count=3, selectable=False, status="UNSUPPORTED_ON_MACOS",
                reason_codes=("UNSUPPORTED_ON_MACOS",)),
        ),
        start_guard_note=START_GUARD_NOT_A_QUALIFICATION,
    )

    document = payload.model_dump()
    assert document["platform"] == "macos"
    assert document["worker_count_availability"][0]["worker_count"] == 1
    assert document["worker_count_availability"][2]["status"] == "UNSUPPORTED_ON_MACOS"
    rows = {row["profile"]: row for row in document["support_matrix"]}
    assert set(rows) == {
        "MPS_W2_FIRST_PASS", "MPS_W1_FULL_RESTART_RETRY", "MPS_W1_FIRST_PASS"}
    assert (rows["MPS_W2_FIRST_PASS"]["schema_version"],
            rows["MPS_W2_FIRST_PASS"]["worker_count"],
            rows["MPS_W2_FIRST_PASS"]["batch_kind"]) == (4, 2, "FIRST_PASS")
    assert "not a resource qualification proof" in document["start_guard_note"]
    assert list(document["worker_qualifications"]) == []

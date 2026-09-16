from pathlib import Path

from fastapi.testclient import TestClient

from so101_teleop.expert_validation.api import create_expert_validation_app


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
        return {"manifest_id": f"manifest-{total_points}", "point_count": total_points}

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
        "service_session_id": "browser-a",
        "lease_id": "lease-a",
        "lease_generation": 1,
        "manifest_id": "manifest-20",
        "execution_mode": "PARALLEL",
        "worker_count": 2,
        "max_points_per_worker": 10,
    }
    receipt = client.post("/expert-validation/campaigns/preflight", json=body).json()
    response = client.post(
        "/expert-validation/campaigns",
        json={
            **body,
            "command_id": "start-1",
            "max_points_per_worker": 9,
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

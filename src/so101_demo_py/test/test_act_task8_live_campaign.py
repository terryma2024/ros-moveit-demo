"""Task 8 case ordering is readable, but full-stack lifecycle is not yet owned."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import hashlib
import time

import pytest

from so101_demo.act.task8 import Task8Runner
from so101_demo.act.pick_place_validation_manifest import build_pick_place_validation_manifest, write_new_manifest
from so101_demo.act.pick_place_validation_campaign import PickPlaceValidationCampaign, PickPlaceValidationError


ANCHORS = {
    "default": {"cup_start_m": [0.02, -0.28, 0.165], "neck_start_rad": 0.1},
    "left": {"cup_start_m": [-0.08, -0.28, 0.165], "neck_start_rad": 0.0},
    "forward": {"cup_start_m": [0.02, -0.36, 0.165], "neck_start_rad": 0.0},
}


@dataclass(frozen=True)
class Context:
    campaign_id: str
    manifest_sha256: str
    source_sha256: str
    runtime_config_sha256: str
    collection_config_sha256: str
    contact_policy_fingerprint: str
    worker_count: int = 1


class Worker:
    def __init__(self, context):
        self.context = context
        self.launch = type("Launch", (), {"mujoco_session_id": "session-247"})()
        self.requests = []

    async def task8(self, request):
        self.requests.append(request)
        raise AssertionError("no case may reach a reused child")


def prepared(tmp_path):
    document = build_pick_place_validation_manifest(
        ANCHORS, source_sha256="a" * 64, runtime_config_sha256="b" * 64,
        collection_config_sha256="c" * 64, contact_policy_fingerprint="d" * 64,
        calibration_report_path="calibration-report.json",
        calibration_report_sha256="e" * 64,
    )
    path = tmp_path / "manifest.json"
    write_new_manifest(path, document)
    context = Context("campaign-247", hashlib.sha256(path.read_bytes()).hexdigest(),
                      "a" * 64, "b" * 64, "c" * 64, "d" * 64)
    return path, context


def test_closed_manifest_previews_exact_nine_prefix_and_five_full_cases(tmp_path):
    manifest_path, context = prepared(tmp_path)
    worker = Worker(context)
    campaign = PickPlaceValidationCampaign(manifest_path, context, worker, tmp_path / "cases.jsonl")
    cases = campaign.planned_cases(deadline_ns=time.monotonic_ns() + 60_000_000_000)
    assert [case["stop_after"] for case in cases[:9]] == list(Task8Runner.PHASES)
    assert [case["anchor"] for case in cases[9:]] == [
        "default", "left", "forward", "default", "left",
    ]
    assert all(case["lifecycle"] == "FULL_RESTART" for case in cases)
    assert worker.requests == []


def test_full_restart_cannot_be_claimed_without_the_production_composition(
        tmp_path, monkeypatch):
    """The static proof is the installed composition; remove it and nothing is admitted."""

    manifest_path, context = prepared(tmp_path)
    worker = Worker(context)
    journal = tmp_path / "case-results.jsonl"
    monkeypatch.setattr(PickPlaceValidationCampaign, "trusted_full_restart_composition",
                        staticmethod(lambda: None))
    with pytest.raises(PickPlaceValidationError, match="FULL_RESTART_PROOF_UNAVAILABLE"):
        asyncio.run(PickPlaceValidationCampaign(manifest_path, context, worker, journal).run(
            deadline_ns=time.monotonic_ns() + 60_000_000_000))
    assert worker.requests == [] and not journal.exists()


def test_manifest_hash_drift_refuses_even_read_only_preview(tmp_path):
    manifest_path, context = prepared(tmp_path)
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    campaign = PickPlaceValidationCampaign(manifest_path, context, Worker(context), tmp_path / "cases.jsonl")
    with pytest.raises(PickPlaceValidationError, match="TASK8_MANIFEST_BINDING_INVALID"):
        campaign.planned_cases(deadline_ns=time.monotonic_ns() + 60_000_000_000)


def test_policy_binding_drift_refuses_even_read_only_preview(tmp_path):
    manifest_path, context = prepared(tmp_path)
    wrong = replace(context, contact_policy_fingerprint="e" * 64)
    campaign = PickPlaceValidationCampaign(manifest_path, wrong, Worker(wrong), tmp_path / "cases.jsonl")
    with pytest.raises(PickPlaceValidationError, match="TASK8_MANIFEST_BINDING_INVALID"):
        campaign.planned_cases(deadline_ns=time.monotonic_ns() + 60_000_000_000)

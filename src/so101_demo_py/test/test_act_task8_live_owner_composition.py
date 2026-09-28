"""Contract for the production full-restart owner composition.

The admission proof is static: only the installed production composition satisfies it, and
no caller-supplied object can claim it. Each case gets a freshly constructed owner with both
retirement receipts, and an unavailable composition admits nothing.
"""

import asyncio
import json
from pathlib import Path

import pytest

from test_act_task8_live_cli import Lifecycle, Worker, prepared


class _Launch:
    """The bridge launch surface the per-case factory reads."""

    def __init__(self, root):
        self.environment = {"SO101_UNIFIED_EVIDENCE_ROOT": str(root)}
        self.install_prefix = root


class _ChildOwner:
    def __init__(self, root):
        self.base_launch = _Launch(root)
        self.arbiter = "arbiter"
        self.safety = "safety"


class StubLifecycle:
    """The ActCampaignLifecycle surface the production factory consumes."""

    def __init__(self, root):
        self.workload_service = "workload"
        self.child_owner = _ChildOwner(root)
        self.starts = self.finishes = 0

    async def start(self, spec):
        self.starts += 1
        return None, ()

    async def finish(self, context):
        self.finishes += 1

def _records(monkeypatch):
    """Patch the production composition entry points and record their calls."""

    from so101_teleop.unified import pick_place_case_execution, pick_place_full_restart_campaign

    calls = {"campaign": [], "case": [], "owners": [], "specs": []}

    async def fake_campaign(manifest_path, journal_root, make_case, *, execute_case=None):
        manifest = json.loads(Path(manifest_path).read_text())
        cases = (*manifest["prefix_cases"], *manifest["full_cases"])
        calls["campaign"].append((Path(manifest_path), Path(journal_root)))
        for case in cases:
            case_id = case["case_id"]
            journal_file = Path(journal_root) / f"{case_id}.json"
            spec, owner = make_case(dict(case), journal_file)
            calls["owners"].append(owner)
            calls["specs"].append(spec)
            await pick_place_case_execution.run_pick_place_case(spec, case_id, owner, journal_file)
        return {"status": "PASSED"}

    async def fake_case(spec, case_id, owner, journal_path):
        calls["case"].append(case_id)
        return {"case_id": case_id, "full_restart_retired": True}

    monkeypatch.setattr(pick_place_full_restart_campaign, "run_full_restart_campaign", fake_campaign)
    monkeypatch.setattr(pick_place_case_execution, "run_pick_place_case", fake_case)
    return calls


def test_gate_accepts_no_caller_supplied_proof():
    """(a) A lambda cannot claim the proof: the gate takes no proof argument at all."""

    from so101_demo.act import pick_place_validation_campaign as campaign

    gate = campaign.PickPlaceValidationCampaign.require_full_restart_lifecycle
    with pytest.raises(TypeError):
        gate(owner_factory=lambda case_id: object())
    composition = campaign.PickPlaceValidationCampaign.trusted_full_restart_composition()
    assert composition is not None and asyncio.iscoroutinefunction(composition)
    assert composition.__module__ == "so101_teleop.unified.pick_place_full_restart_campaign"


def test_admitted_campaign_routes_through_the_production_composition(tmp_path, monkeypatch):
    """(b) The frozen cases must route through the production campaign and case entries."""

    from so101_demo.cli import act_run_pick_place_validation as cli

    spec, context = prepared(tmp_path)
    calls = _records(monkeypatch)
    journal = tmp_path / "task8-live" / "cases.jsonl"
    journal.parent.mkdir()
    asyncio.run(cli.run_admitted_campaign(spec, StubLifecycle(tmp_path), journal))
    assert calls["campaign"], "the production full-restart campaign entry was never called"
    assert calls["case"], "no case was routed through the production per-case entry"
    assert calls["campaign"][0][1] == journal.parent


def test_each_case_gets_a_fresh_owner_bound_to_the_admitted_spec(tmp_path, monkeypatch):
    """(c) One fresh owner per case, bound to the admitted spec.

    The retirement boundary itself (both receipts, the final clear and the released
    admission) is asserted by the production owner suite, not by this routing test.
    """

    from so101_demo.cli import act_run_pick_place_validation as cli
    from so101_teleop.unified.pick_place_case_owner import PickPlaceCaseOwner

    spec, context = prepared(tmp_path)
    calls = _records(monkeypatch)
    journal = tmp_path / "task8-live" / "cases.jsonl"
    journal.parent.mkdir()
    asyncio.run(cli.run_admitted_campaign(spec, StubLifecycle(tmp_path), journal))
    owners = calls["owners"]
    assert owners, "no owner was constructed by the production composition"
    assert all(isinstance(owner, PickPlaceCaseOwner) for owner in owners)
    assert len({id(owner) for owner in owners}) == len(owners), "owners must be fresh per case"
    assert all(item is spec for item in calls["specs"]), "the admitted spec binds every case"


def test_unavailable_composition_still_admits_nothing(tmp_path, monkeypatch):
    """(d) With no trusted composition, zero admission and zero journal must remain."""

    from so101_demo.cli import act_run_pick_place_validation as cli

    spec, context = prepared(tmp_path)
    worker = Worker(context)
    lifecycle = Lifecycle(context, worker)
    journal = tmp_path / "task8-live" / "cases.jsonl"
    journal.parent.mkdir()
    monkeypatch.setattr(cli, "trusted_full_restart_composition", lambda: None)
    with pytest.raises(ValueError, match="FULL_RESTART_PROOF_UNAVAILABLE"):
        asyncio.run(cli.run_admitted_campaign(spec, lifecycle, journal))
    assert worker.requests == []
    assert lifecycle.starts == lifecycle.finishes == 0
    assert not journal.exists()

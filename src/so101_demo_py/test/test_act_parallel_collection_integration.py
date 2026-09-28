"""Task 11A CLI and composition: every refusal happens before a service exists."""

import json
from pathlib import Path

import pytest

from so101_demo.cli.act_collect_parallel import main


def _inputs(tmp_path, *, kind="W8", scenes=3, revoked=False, worker_count=4, declared=4):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"kind": kind,
                                    "scenarios": [{"scene_id": f"act-{index}", "split": "train"}
                                                  for index in range(scenes)],
                                    "qualification_contract": {"revoked": revoked, "scenes": 40}}))
    files = {}
    for name in ("calibration", "policy", "receipt", "collection", "runtime"):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps({"worker_count": declared} if name == "runtime" else {}))
        files[name] = path
    return manifest, files


def _context(tmp_path, *, source=None, children=()):
    from types import SimpleNamespace

    source_path = source or (tmp_path / "source.json")
    if not source_path.is_file():
        source_path.write_text("{}")
    proposal = tmp_path / "proposal.json"
    if not proposal.is_file():
        proposal.write_text("{}")
    return SimpleNamespace(campaign_id="campaign-1", source_path=source_path,
                           contact_policy_fingerprint="f" * 64, proposal_path=proposal,
                           service_epoch=7, resource_binding_id="binding-1",
                           children=list(children))


def _live_contract(tmp_path, *, scenes=40, revoked=False):
    path = tmp_path / "w8-qualification-contract.json"
    path.write_text(json.dumps({"schema_version": 1, "kind": "W8", "revoked": revoked,
                                "scenes": scenes}))
    return path


def _argv(manifest, files, tmp_path, *, worker_count=4, extra=(), contract=None):
    return ["--manifest", str(manifest), "--calibration", str(files["calibration"]),
            "--policy", str(files["policy"]), "--activation-receipt", str(files["receipt"]),
            "--collection-config", str(files["collection"]),
            "--runtime-config", str(files["runtime"]), "--root", str(tmp_path),
            "--worker-count", str(worker_count),
            *([] if contract is None else ["--qualification-contract", str(contract)]), *extra]


class _Service:
    def __init__(self):
        self.calls = []

    def start(self, spec, request):
        self.calls.append(request)
        return {"status": "PASSED"}


def test_formal_run_needs_exact_w8_under_a_live_contract(tmp_path):
    built = []
    manifest, files = _inputs(tmp_path)
    contract = _live_contract(tmp_path)
    service = _Service()
    assert main(_argv(manifest, files, tmp_path, contract=contract),
                service_factory=lambda spec: built.append(spec) or service,
                context_factory=lambda: _context(tmp_path)) == 0
    from so101_teleop.unified.admission import _ACT_PAYLOAD_KEYS

    assert built[0]["kind"] == "act_collection_start"                 # what admission recognises
    assert set(built[0]["payload"]) == set(_ACT_PAYLOAD_KEYS)         # imported, so it cannot drift
    assert built[0]["payload"]["worker_count"] == 4
    assert built[0]["payload"]["qualification_mode"] is False
    assert service.calls[0]["plane"] == "formal"

    built.clear()
    for bad_kind in ("W1", "train"):
        (tmp_path / bad_kind).mkdir(exist_ok=True)      # the fixture writes into this directory
        bad_manifest, files = _inputs(tmp_path / bad_kind, kind=bad_kind)
        bad_contract = _live_contract(tmp_path / bad_kind)
        with pytest.raises(ValueError, match="FORMAL_MANIFEST_NOT_EXACT_W8"):
            main(_argv(bad_manifest, files, tmp_path / bad_kind, contract=bad_contract),
                 service_factory=lambda spec: built.append(spec) or service,
                 context_factory=lambda: _context(tmp_path))
    # a W8 manifest without a live 40-scene contract is refused as well
    for kwargs, expected in (({"revoked": True}, "FORMAL_QUALIFICATION_CONTRACT_MISSING_OR_REVOKED"),
                             ({"scenes": 8}, "FORMAL_QUALIFICATION_SCENE_COUNT_INVALID")):
        dead = _live_contract(tmp_path / "dead", **kwargs) if (tmp_path / "dead").mkdir(
            exist_ok=True) is None else None
        with pytest.raises(ValueError, match=expected):
            main(_argv(manifest, files, tmp_path, contract=dead),
                 service_factory=lambda spec: built.append(spec) or service,
                 context_factory=lambda: _context(tmp_path))
    assert built == []                                   # nothing was ever built or started


def test_qualification_run_creates_the_contract_atomically_before_the_service(tmp_path):
    manifest, files = _inputs(tmp_path, kind="W2")
    contract = tmp_path / "qualification-contract.json"
    built = []
    assert main(_argv(manifest, files, tmp_path,
                      extra=["--qualification", "--qualification-contract", str(contract)]),
                service_factory=lambda spec: built.append(spec) or _Service(),
                context_factory=lambda: _context(tmp_path)) == 0
    assert contract.is_file()
    assert built[0]["payload"]["qualification_mode"] is True
    assert not (tmp_path / "qualification-contract.json.partial").exists()
    # a second run must not inherit the first run's qualification evidence
    with pytest.raises(ValueError, match="QUALIFICATION_CONTRACT_EXISTS"):
        main(_argv(manifest, files, tmp_path,
                   extra=["--qualification", "--qualification-contract", str(contract)]),
             service_factory=lambda spec: built.append(spec) or _Service(),
             context_factory=lambda: _context(tmp_path))
    with pytest.raises(ValueError, match="QUALIFICATION_CONTRACT_PATH_REQUIRED"):
        main(_argv(manifest, files, tmp_path, extra=["--qualification"]),
             service_factory=lambda spec: built.append(spec) or _Service(),
             context_factory=lambda: _context(tmp_path))


def test_worker_count_must_be_explicit_and_match_the_runtime_config(tmp_path):
    manifest, files = _inputs(tmp_path, declared=4)
    contract = _live_contract(tmp_path)
    for bad in (0, -2):
        with pytest.raises(ValueError, match="FIXED_COLLECTION_WORKER_COUNT_INVALID"):
            main(_argv(manifest, files, tmp_path, worker_count=bad, contract=contract),
                 service_factory=lambda spec: _Service(),
             context_factory=lambda: _context(tmp_path))
    with pytest.raises(ValueError, match="FIXED_COLLECTION_WORKER_COUNT_MISMATCH"):
        main(_argv(manifest, files, tmp_path, worker_count=8, contract=contract),
             service_factory=lambda spec: _Service(),
             context_factory=lambda: _context(tmp_path))


def test_resume_requires_the_campaign_index_that_a_previous_run_published(tmp_path):
    manifest, files = _inputs(tmp_path)
    contract = _live_contract(tmp_path)
    with pytest.raises(ValueError, match="FIXED_COLLECTION_RESUME_INDEX_MISSING"):
        main(_argv(manifest, files, tmp_path, contract=contract, extra=["--resume"]),
             service_factory=lambda spec: _Service(),
             context_factory=lambda: _context(tmp_path))
    index = tmp_path / "campaign-index.json"
    index.write_text(json.dumps({"schema_version": 1, "kind": "act_collection_campaign_index",
                                 "qualification": False, "waves": [], "scene_count": 0}))
    built = []
    assert main(_argv(manifest, files, tmp_path, contract=contract, extra=["--resume"]),
                service_factory=lambda spec: built.append(spec) or _Service(),
                context_factory=lambda: _context(tmp_path)) == 0
    assert built[0]["kind"] == "act_collection_resume"                # resume is the operation itself
    assert built[0]["payload"]["evidence_root"] == str(tmp_path)

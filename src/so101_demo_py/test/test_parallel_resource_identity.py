"""Acyclic identity: normalization, semantic config, inventories and byte audits."""

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

PACKAGE = Path(__file__).resolve().parents[1]
V2_CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v2.yaml"


def candidate_document():
    return yaml.safe_load(V2_CONFIG_PATH.read_text(encoding="utf-8"))


def deployed_document():
    document = candidate_document()
    document["deployment"] = {
        "approved_profile_path": "/sealed/profile.json",
        "approved_profile_sha256": "a" * 64,
        "promotion_record_path": "/sealed/promotion.json",
    }
    return document


def inventory(**files):
    from so101_demo.parallel_batch.resource_identity import build_inventory
    return build_inventory({name: content for name, content in files.items()})


def identity(document, source_files, installed_files, facts=None, semantic=None):
    from so101_demo.parallel_batch.resource_identity import build_runtime_fingerprint
    return build_runtime_fingerprint(
        config=document,
        source_inventory=source_files,
        installed_inventory=installed_files,
        runtime_facts=facts or {"gpu_uuid": "GPU-1", "threads": 8},
        semantic_config_sha256=semantic,
    )


def test_first_promotion_changes_audit_not_semantic_identity():
    from so101_demo.parallel_batch.resource_identity import (
        canonical_sha256, semantic_config_sha256)
    candidate = candidate_document()
    deployed = deployed_document()
    assert semantic_config_sha256(candidate) == semantic_config_sha256(deployed)
    assert canonical_sha256(candidate) != canonical_sha256(deployed)


def test_frozen_execution_rules_cannot_drift_and_free_rules_change_identity():
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_identity import semantic_config_sha256
    base = candidate_document()
    baseline = semantic_config_sha256(base)
    for section, key, value in (
        ("execution", "heartbeat_timeout_s", 6.0),
        ("execution", "batch_hard_timeout_s", 5401.0),
        ("execution", "max_frame_age_s", 6.0),
        ("execution", "yolo_model_id", "other-model"),
        ("execution", "requested_device", "cpu"),
        ("safety", "capacity_fraction", 0.81),
        ("safety", "abort_on_swap_activity", False),
        ("coverage", "required_normal_runs", 6),
        ("coverage", "cells", ["COLD_START"]),
        ("clock", "pace_source", "WALL_CLOCK"),
    ):
        mutated = deepcopy(base)
        target = mutated["execution"] if section == "execution" else mutated["execution"][section]
        target[key] = value
        with pytest.raises(ContractError):
            semantic_config_sha256(mutated)
    for section, key, value in (
        ("sampling", "resource_sample_interval_s", 0.06),
        ("sampling", "baseline_minimum_s", 30.0),
        ("clock", "window_s", 2.0),
        ("clock", "minimum_consecutive_steady_windows", 6),
    ):
        mutated = deepcopy(base)
        target = mutated["execution"] if section == "execution" else mutated["execution"][section]
        target[key] = value
        assert semantic_config_sha256(mutated) != baseline, (section, key)
    assert semantic_config_sha256(base) == baseline


def test_unknown_deployment_key_is_rejected():
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_identity import semantic_config_sha256
    document = deployed_document()
    document["deployment"]["promotion_record_sha256"] = "b" * 64
    with pytest.raises(ContractError) as error:
        semantic_config_sha256(document)
    assert error.value.code.startswith("UNKNOWN_DEPLOYMENT_FIELD")


def test_canonical_sha256_rejects_nonfinite_and_unsorted_input():
    from so101_demo.parallel_batch.contracts import ContractError
    from so101_demo.parallel_batch.resource_identity import canonical_sha256
    assert canonical_sha256({"b": 1, "a": 2}) == canonical_sha256({"a": 2, "b": 1})
    with pytest.raises(ContractError):
        canonical_sha256({"a": float("nan")})
    with pytest.raises(ContractError):
        canonical_sha256({"a": float("inf")})


def test_carrier_uses_semantic_digest_while_other_files_keep_raw_bytes():
    from so101_demo.parallel_batch.resource_identity import (
        CARRIER_LOGICAL_PATH, build_inventory, inventory_sha256)
    files = {
        CARRIER_LOGICAL_PATH: b"schema_version: 2\n",
        "lib/so101_demo/cli.py": b"print('v1')\n",
    }
    entries = build_inventory(files, semantic_carriers={CARRIER_LOGICAL_PATH: "c" * 64})
    carrier = next(item for item in entries if item.logical_path == CARRIER_LOGICAL_PATH)
    other = next(item for item in entries if item.logical_path != CARRIER_LOGICAL_PATH)
    assert carrier.semantic_sha256 == "c" * 64
    assert other.semantic_sha256 is None
    changed = build_inventory({**files, "lib/so101_demo/cli.py": b"print('v2')\n"},
                              semantic_carriers={CARRIER_LOGICAL_PATH: "c" * 64})
    assert inventory_sha256(entries) != inventory_sha256(changed)
    promoted = build_inventory({**files, CARRIER_LOGICAL_PATH: b"deployment: filled\n"},
                               semantic_carriers={CARRIER_LOGICAL_PATH: "c" * 64})
    assert inventory_sha256(entries) == inventory_sha256(promoted)


def test_executable_byte_change_changes_installed_identity():
    from so101_demo.parallel_batch.resource_identity import CARRIER_LOGICAL_PATH
    document = candidate_document()
    source = inventory(**{CARRIER_LOGICAL_PATH: b"execution: {}\n", "bin/run": b"#!/bin/sh\n"})
    installed = inventory(**{CARRIER_LOGICAL_PATH: b"execution: {}\n", "bin/run": b"#!/bin/sh\n"})
    drifted = inventory(**{CARRIER_LOGICAL_PATH: b"execution: {}\n", "bin/run": b"#!/bin/sh -e\n"})
    first = identity(document, source, installed)
    second = identity(document, source, installed)
    third = identity(document, source, drifted)
    assert first.sha256 == second.sha256
    assert first.sha256 != third.sha256
    assert first.installed_inventory_sha256 != third.installed_inventory_sha256


def test_equivalence_allows_only_carrier_and_location_changes():
    from so101_demo.parallel_batch.resource_identity import (
        CARRIER_LOGICAL_PATH, build_inventory, verify_deployment_equivalence)
    document = candidate_document()
    measured_files = {CARRIER_LOGICAL_PATH: b"deployment: null\n", "bin/run": b"#!/bin/sh\n"}
    deployed_files = {CARRIER_LOGICAL_PATH: b"deployment: filled\n", "bin/run": b"#!/bin/sh\n"}
    semantic = "d" * 64
    measured_inventory = build_inventory(
        measured_files, semantic_carriers={CARRIER_LOGICAL_PATH: semantic})
    deployed_inventory = build_inventory(
        deployed_files, semantic_carriers={CARRIER_LOGICAL_PATH: semantic})
    measured_identity = identity(document, measured_inventory, measured_inventory)
    measured_audit = build_audit("/data/work/ws_moveit/install/so101_demo_py", measured_inventory)
    deployed_audit = build_audit("/data/work/so101-worktrees/uq/install/so101_demo_py",
                                 deployed_inventory)
    verify_deployment_equivalence(
        measured=measured_audit, deployed=deployed_audit,
        measured_identity=measured_identity, deployed_identity=measured_identity)
    from so101_demo.parallel_batch.contracts import ContractError
    drifted_inventory = build_inventory(
        {CARRIER_LOGICAL_PATH: b"deployment: filled\n", "bin/run": b"#!/bin/sh -e\n"},
        semantic_carriers={CARRIER_LOGICAL_PATH: semantic})
    with pytest.raises(ContractError) as error:
        verify_deployment_equivalence(
            measured=measured_audit,
            deployed=build_audit("/data/elsewhere", drifted_inventory),
            measured_identity=measured_identity, deployed_identity=measured_identity)
    assert error.value.code.startswith("UNALLOWED_BYTE_DRIFT")
    with pytest.raises(ContractError) as error:
        verify_deployment_equivalence(
            measured=measured_audit, deployed=deployed_audit,
            measured_identity=measured_identity,
            deployed_identity=identity(document, measured_inventory,
                                      measured_inventory, facts={"gpu_uuid": "GPU-2"}))
    assert error.value.code.startswith("RUNTIME_FACT_DRIFT")


def build_audit(prefix, entries):
    from so101_demo.parallel_batch.resource_identity import FullByteAudit
    return FullByteAudit(
        schema_version=2, source_commit="e" * 40, source_clean=True, prefix=prefix,
        files=tuple(entries), origins={"so101_demo_py": prefix})


def test_audit_records_raw_config_bytes_and_prefix():
    import hashlib
    from so101_demo.parallel_batch.resource_identity import CARRIER_LOGICAL_PATH
    raw = V2_CONFIG_PATH.read_bytes()
    entries = inventory(**{CARRIER_LOGICAL_PATH: raw})
    audit = build_audit("/data/work/ws_moveit/install/so101_demo_py", entries)
    carrier = audit.files[0]
    assert carrier.raw_sha256 == hashlib.sha256(raw).hexdigest()
    document = audit.as_document()
    assert document["prefix"] == "/data/work/ws_moveit/install/so101_demo_py"
    assert document["files"][0]["raw_sha256"] == carrier.raw_sha256
    assert json.loads(json.dumps(document)) == document

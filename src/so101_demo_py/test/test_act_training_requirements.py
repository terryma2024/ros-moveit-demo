"""Task 12: a training run may not start against an unpinned dependency set."""

from pathlib import Path

import pytest
import yaml

from so101_demo.act.training_requirements import (
    load_training_requirements, require_resolved_requirements,
)

PACKAGE = Path(__file__).resolve().parents[1]
LOCK = PACKAGE / "config/act/requirements.lock"


def _resolved(tmp_path, **overrides):
    document = {"schema_version": 1, "kind": "act_training_requirements", "status": "RESOLVED",
                "resolver": {"python": "3.12.3", "resolved_at": "2026-09-24T00:00:00Z",
                             "index_sha256": "a" * 64},
                "packages": [{"name": "torch", "version": "2.7.0", "sha256": "b" * 64},
                             {"name": "lerobot", "version": "0.4.0", "sha256": "c" * 64}]}
    for dotted, value in overrides.items():
        head, dot, leaf = dotted.partition(".")
        if not dot:                      # a top-level field such as `status`
            document[head] = value
        else:
            document[head][leaf] = value
    path = tmp_path / "requirements.lock"
    path.write_text(yaml.safe_dump(document))
    return path


def test_the_shipped_lock_is_resolved_and_pins_every_package_by_source_hash():
    """The shipped lock was UNRESOLVED while no interpreter had resolved it; now that one has, it must
    present a complete pin set rather than a partial one. A half-resolved lock is still refused, which the
    synthetic cases below cover."""

    document = require_resolved_requirements(LOCK)
    assert document["status"] == "RESOLVED" and document["packages"]
    assert document["resolver"]["python"] and document["resolver"]["index_sha256"]
    names = [package["name"] for package in document["packages"]]
    assert len(set(names)) == len(names)
    for package in document["packages"]:
        assert len(package["sha256"]) == 64 and package["version"]
    assert {"torch", "lerobot"} <= set(names)


def test_a_lock_that_claims_to_be_unresolved_but_carries_packages_is_refused(tmp_path):
    path = tmp_path / "requirements.lock"
    path.write_text(yaml.safe_dump({"schema_version": 1, "kind": "act_training_requirements",
                                    "status": "UNRESOLVED", "resolver": None,
                                    "packages": [{"name": "torch", "version": "2.11.0", "sha256": "a" * 64}]},
                                   sort_keys=False))
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_INVALID"):
        load_training_requirements(path)


def test_a_resolved_lock_pins_every_package_by_version_and_source_hash(tmp_path):
    path = _resolved(tmp_path)
    document = require_resolved_requirements(path)
    assert [package["name"] for package in document["packages"]] == ["torch", "lerobot"]
    # a version without its source hash is not a pin
    for packages in ([{"name": "torch", "version": "2.7.0"}],
                     [{"name": "torch", "version": "", "sha256": "b" * 64}],
                     [{"name": "torch", "version": "2.7.0", "sha256": "short"}],
                     [{"name": "torch", "version": "2.7.0", "sha256": "b" * 64},
                      {"name": "torch", "version": "2.7.1", "sha256": "c" * 64}]):
        with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_(UNPINNED|INVALID)"):
            load_training_requirements(_resolved(tmp_path, packages=packages))
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_EMPTY"):
        load_training_requirements(_resolved(tmp_path, packages=[]))


def test_the_lock_document_is_closed_and_cannot_be_half_resolved(tmp_path):
    half = tmp_path / "half.lock"
    half.write_text(yaml.safe_dump({"schema_version": 1, "kind": "act_training_requirements",
                                    "status": "UNRESOLVED", "resolver": {"python": "3.12.3"},
                                    "packages": []}))
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_INVALID"):
        load_training_requirements(half)
    for overrides in ({"status": "MAYBE"}, {"resolver.index_sha256": "short"},
                      {"resolver.python": ""}, {"resolver.resolved_at": ""}):
        with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_INVALID"):
            load_training_requirements(_resolved(tmp_path, **overrides))
    extra = _resolved(tmp_path)
    document = yaml.safe_load(extra.read_text())
    document["extra"] = 1
    extra.write_text(yaml.safe_dump(document))
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_INVALID"):
        load_training_requirements(extra)
    with pytest.raises(ValueError, match="TRAINING_REQUIREMENTS_MISSING"):
        load_training_requirements(tmp_path / "absent.lock")

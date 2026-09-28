"""The resolver that turns a uv install report into the closed Task 12 training lock.

The lock is only meaningful if every package carries the SHA of the artifact that was actually resolved and
the resolver records which interpreter and which indexes produced it. Anything less fails closed, because a
version without its source hash is not a pin.
"""

import json

import pytest
import yaml

from so101_demo.act.training_requirements import load_training_requirements, require_resolved_requirements


def _report(*, hashes=True, names=(("torch", "2.9.0", "a" * 64), ("lerobot", "0.6.1", "b" * 64))):
    install = []
    for name, version, digest in names:
        entry = {"metadata": {"name": name, "version": version},
                 "download_info": {"url": f"https://example.invalid/{name}-{version}.whl"}}
        if hashes:
            entry["download_info"]["archive_info"] = {"hash": f"sha256={digest}"}
        install.append(entry)
    return {"version": "1", "environment": {"python_version": "3.12.3"}, "install": install}


def test_resolver_writes_a_lock_that_validates_as_resolved(tmp_path):
    from so101_demo.cli.act_resolve_training_requirements import build_lock_document

    document = build_lock_document(_report(), python="3.12.3", resolved_at="2026-09-29T00:00:00Z",
                                   index_sha256="c" * 64)
    path = tmp_path / "requirements.lock"
    path.write_text(yaml.safe_dump(document, sort_keys=False))
    resolved = require_resolved_requirements(path)
    assert resolved["status"] == "RESOLVED"
    assert [package["name"] for package in resolved["packages"]] == ["lerobot", "torch"]
    assert resolved["packages"][1]["sha256"] == "a" * 64            # the report's own artifact hash


def test_resolver_refuses_a_report_without_artifact_hashes(tmp_path):
    from so101_demo.cli.act_resolve_training_requirements import build_lock_document

    with pytest.raises(ValueError, match="TRAINING_REPORT_UNHASHED"):
        build_lock_document(_report(hashes=False), python="3.12.3", resolved_at="2026-09-29T00:00:00Z",
                            index_sha256="c" * 64)


def test_resolver_refuses_an_unknown_report_shape():
    from so101_demo.cli.act_resolve_training_requirements import build_lock_document

    # the fourth case has a name, a version and no download_info at all: unhashable, not merely unusual
    for broken in ({}, {"install": []}, {"install": [{"metadata": {"name": "x"}}]},
                   {"install": [{"metadata": {"name": "x", "version": "1"}}]},
                   {"install": [{"metadata": {"name": "x", "version": "1"},
                                 "download_info": {"archive_info": {"hash": "sha256=nothex"}}}]}):
        with pytest.raises(ValueError):
            build_lock_document(broken, python="3.12.3", resolved_at="2026-09-29T00:00:00Z",
                                index_sha256="c" * 64)


def test_resolver_records_the_interpreter_and_the_indexes(tmp_path):
    from so101_demo.cli.act_resolve_training_requirements import build_lock_document

    document = build_lock_document(_report(), python="3.12.3", resolved_at="2026-09-29T00:00:00Z",
                                   index_sha256="c" * 64)
    assert document["resolver"]["python"] == "3.12.3"
    assert document["resolver"]["resolved_at"] == "2026-09-29T00:00:00Z"
    assert document["resolver"]["index_sha256"] == "c" * 64
    assert set(document) == {"schema_version", "kind", "status", "resolver", "packages"}


def test_the_cli_writes_a_lock_the_loader_accepts(tmp_path):
    from so101_demo.cli.act_resolve_training_requirements import main

    report = tmp_path / "report.json"
    report.write_text(json.dumps(_report()))
    lock = tmp_path / "requirements.lock"
    code = main(["--report", str(report), "--lock", str(lock), "--python", "3.12.3",
                 "--index", "https://pypi.tuna.tsinghua.edu.cn/simple",
                 "--index", "https://download.pytorch.org/whl/cu128"])
    assert code == 0
    resolved = require_resolved_requirements(lock)
    assert len(resolved["packages"]) == 2
    assert load_training_requirements(lock)["status"] == "RESOLVED"

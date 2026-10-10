"""the deterministic offline aggregator.

One v2 sealed batch with exactly three anchors renders four canonical documents whose `sample_path` values are
serialised against a single caller-supplied absolute `publication_root`. Rendering is pure and byte-deterministic;
publishing writes exactly those bytes. A batch that is not one sealed, indexed, three-anchor CLOSED batch is
refused rather than partially aggregated.
"""

import hashlib
import json
from pathlib import Path

import pytest

DOCUMENTS = ("head-search-qualification.json", "task8-ready-support.json", "task8-ready-calibration.json",
             "aggregation-receipt.json")


def _render():
    from so101_demo.act.pick_place_calibration_aggregator import render_pick_place_calibration, publish_pick_place_calibration

    return render_pick_place_calibration, publish_pick_place_calibration


def _contract():
    from so101_demo.act.pick_place_calibration_measurement_schema import load_contract

    return load_contract()


def _sealed_batch(root, *, anchors=("default", "left", "forward"), measurements=None, status="CLOSED",
                  identity=None, extra_files=None):
    """Build a minimal v2 sealed batch: one raw record per anchor, every file registered in the index."""
    root = Path(root)
    (root / "raw").mkdir(parents=True, exist_ok=True)
    files = {}
    entries = []
    for ordinal, anchor in enumerate(anchors):
        record = {"measurements": dict(measurements or {"min_confidence": [0.6]}),
                  "configured": {"min_confidence": 0.5},
                  "anchor": anchor, "reset_epoch": ordinal + 1, "physics_step": ordinal}
        payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
        relative = f"raw/{anchor}.json"
        (root / relative).write_bytes(payload)
        files[relative] = hashlib.sha256(payload).hexdigest()
        entries.append({"anchor": anchor, "identity": {"session_id": f"s-{ordinal}", "reset_epoch": ordinal + 1,
                                                       "attempt_id": f"a-{ordinal}"}})
    for name, payload in (extra_files or {}).items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(payload)
    batch = {"schema_version": 2, "kind": "task8_calibration_batch", "status": status,
             "identity": identity or {"source_commit": "a" * 40, "config_sha256": "b" * 64,
                                      "source_provenance_sha256": "c" * 64,
                                      "measurement_plan_sha256": "d" * 64},
             "anchors": entries, "files": files}
    if status == "INVALID":
        batch["error_code"] = "STACK_LAUNCH_FAILED"
    (root / "batch.json").write_bytes(json.dumps(batch, sort_keys=True, separators=(",", ":")).encode())
    return root


def test_rendering_is_byte_deterministic_and_emits_exactly_the_four_documents(tmp_path):
    render, _ = _render()
    root = _sealed_batch(tmp_path / "batch")
    publication = tmp_path / "published"
    first = render(root, _contract(), publication)
    second = render(root, _contract(), publication)
    assert set(first) == set(DOCUMENTS)
    assert first == second, "the same immutable fixture must render identical bytes"
    assert all(isinstance(payload, bytes) for payload in first.values())


def test_publishing_writes_those_bytes_and_every_sample_path_is_absolute_and_present(tmp_path):
    render, publish = _render()
    root = _sealed_batch(tmp_path / "batch")
    publication = tmp_path / "published"
    rendered = render(root, _contract(), publication)
    publish(rendered, publication)
    for name, payload in rendered.items():
        assert (publication / name).read_bytes() == payload
    receipt = json.loads((publication / "aggregation-receipt.json").read_bytes())
    for field, entry in receipt["fields"].items():
        path = Path(entry["sample_path"])
        assert path.is_absolute(), field
        assert path.is_file(), field
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sample_sha256"], field


@pytest.mark.parametrize("case", [
    {"status": "INVALID"},                      # a sealed INVALID batch is never aggregated
    {"anchors": ("default", "left")},           # a missing anchor
    {"identity": {"source_commit": "a" * 40}},  # malformed identity
])
def test_a_batch_that_is_not_one_three_anchor_closed_batch_is_refused(tmp_path, case):
    render, _ = _render()
    root = _sealed_batch(tmp_path / "batch", **case)
    with pytest.raises(ValueError):
        render(root, _contract(), tmp_path / "published")


def test_an_unindexed_file_is_never_read(tmp_path):
    render, _ = _render()
    root = _sealed_batch(tmp_path / "batch")
    (root / "raw" / "extra.json").write_bytes(b'{"measurements":{"min_confidence":[0.9]}}')
    # the extra file is not in the index, so it must not influence the rendered values
    rendered = render(root, _contract(), tmp_path / "published")
    receipt = json.loads(rendered["aggregation-receipt.json"])
    assert "extra.json" not in json.dumps(receipt)


def test_mutating_a_raw_label_does_not_change_the_rendering_but_mutating_a_number_does(tmp_path):
    render, _ = _render()
    baseline = render(_sealed_batch(tmp_path / "a"), _contract(), tmp_path / "published")
    labelled = render(_sealed_batch(tmp_path / "b", extra_files={"raw/label.json": b'{"qualified":true}'}),
                      _contract(), tmp_path / "published")
    assert labelled["head-search-qualification.json"] == baseline["head-search-qualification.json"]
    mutated = render(_sealed_batch(tmp_path / "c", measurements={"min_confidence": [0.1]}),
                     _contract(), tmp_path / "published")
    assert mutated["head-search-qualification.json"] != baseline["head-search-qualification.json"]


def test_a_time_reversed_batch_is_refused(tmp_path):
    render, _ = _render()
    root = _sealed_batch(tmp_path / "batch")
    batch = json.loads((root / "batch.json").read_bytes())
    batch["anchors"] = list(reversed(batch["anchors"]))
    (root / "batch.json").write_bytes(json.dumps(batch, sort_keys=True, separators=(",", ":")).encode())
    with pytest.raises(ValueError, match="ANCHOR_ORDER"):
        render(root, _contract(), tmp_path / "published")

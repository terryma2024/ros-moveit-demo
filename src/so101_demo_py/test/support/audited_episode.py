"""Seal an ``EpisodeRecorder`` episode against an audit built from the rows it already wrote.

An episode seal names the raw audit and the collection scope it ran under, so a recorder test that only exercises the
recorder still needs one. ``audit_of`` builds the smallest honest one: one acquisition per camera and row (the pixels the
recorder stored), the row's action as its controller reference, and one binding per row. Not a test module.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter

SCOPE_DOCUMENT = {"kind": "ACT_COLLECTION_SCOPE", "schema_version": 1, "mode": "preselected_target_diagnostic",
                  "scene_id": "default", "seed": 0, "inputs_sha256": "c" * 64}


def audit_of(recorder, work_dir):
    """(audit manifest path, scope path) for the rows ``recorder`` has written so far."""
    work_dir = Path(work_dir)
    scope = work_dir / "collection-scope.json"
    scope.write_bytes(json.dumps(SCOPE_DOCUMENT, sort_keys=True, separators=(",", ":")).encode())
    rows = [json.loads(line) for line in (recorder.root / "records.jsonl").read_text().splitlines()]
    writer = EpisodeAuditWriter(work_dir / "audit-episode", SCOPE_DOCUMENT,
                                {"session_id": recorder.session_id, "attempt_id": recorder.attempt_id,
                                 "reset_epoch": recorder.reset_epoch, "release_epoch": 1},
                                {"inputs_sha256": "c" * 64})
    minter = AcquisitionMinter()
    instants = []
    if not rows:
        # a zero-row episode names no labelled binding; raw unlabelled acquisitions are allowed
        for camera in ("head", "wrist"):
            writer.append_acquisition(minter.mint(
                camera, session_id=recorder.session_id, reset_epoch=recorder.reset_epoch, stamp_s=1.0,
                received_monotonic_ns=1, pixels=np.zeros((480, 640, 3), dtype=np.uint8)))
        writer.append_source("references", {"reference_time_s": 1.1, "source": "CONTROLLER_REFERENCE",
                                            "positions": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6], "accepted": True})
        instants = [1.0, 1.2]
    for index, row in enumerate(rows):
        instant = row["observation"]["sim_time_s"]
        instants.append(instant)
        frames = {}
        for camera, key in (("head", "head_png"), ("wrist", "wrist_png")):
            with Image.open(recorder.root / row["observation"][key]) as image:
                pixels = np.asarray(image).copy()
            frames[camera] = minter.mint(camera, session_id=recorder.session_id, reset_epoch=recorder.reset_epoch,
                                         stamp_s=instant, received_monotonic_ns=1, pixels=pixels)
            writer.append_acquisition(frames[camera])
        writer.append_source("references", {"reference_time_s": round(instant + 0.1, 6),
                                            "source": "CONTROLLER_REFERENCE", "positions": list(row["action"]),
                                            "accepted": True})
        writer.bind_row(index, instant, frames["head"].acquisition_id, frames["wrist"].acquisition_id, index + 1)
    return writer.seal({"start_s": instants[0], "end_s": instants[-1]}), scope


def seal_audited(recorder, work_dir, outcome):
    """Seal ``recorder`` with ``outcome`` against its own audit; returns (seal path, audit manifest, scope)."""
    manifest, scope = audit_of(recorder, work_dir)
    return recorder.finish(outcome, audit_manifest=manifest, scope=scope), manifest, scope

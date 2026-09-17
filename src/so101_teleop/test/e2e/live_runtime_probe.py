#!/usr/bin/env python3
"""Read-only L3 runtime probe.

Reads a live campaign's batch roots (coordinator journals, adaptive
handshakes, cleanup receipts) and prints a JSON summary on stdout.  It never
writes, signals, or mutates anything; it exists so live-sim specs can prove
runtime facts from the same files the production projection reads.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys


def _read_events(journal_root: Path) -> list[dict]:
    events_dir = journal_root / "events"
    if not events_dir.is_dir():
        return []
    events = []
    for segment in sorted(events_dir.glob("*.journal")):
        data = segment.read_bytes()
        offset = 0
        while offset < len(data):
            length = struct.unpack(">I", data[offset + 4 : offset + 8])[0]
            document = json.loads(data[offset + 72 : offset + 72 + length])
            events.append(document)
            offset += 73 + length
    return events


def _probe_batch(batch_root: Path) -> dict:
    events = _read_events(batch_root / "coordinator")
    types = [event.get("type") for event in events if event.get("type")]
    handshake_path = batch_root / "r" / batch_root.name / "handshake.json"
    receipt_path = batch_root / "r" / batch_root.name / "cleanup-receipt.json"
    return {
        "batch_id": batch_root.name,
        "event_count": len(events),
        "event_types": types,
        "terminal": "BATCH_TERMINAL" in types,
        "cleanup_complete": "BATCH_FINISHED" in types,
        "adaptive_handshake": (
            json.loads(handshake_path.read_text()) if handshake_path.is_file() else None
        ),
        "adaptive_cleanup_receipt": (
            json.loads(receipt_path.read_text()) if receipt_path.is_file() else None
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", required=True, type=Path)
    args = parser.parse_args(argv)
    root = args.campaign_root.resolve()
    if not root.is_dir():
        print(json.dumps({"error": "CAMPAIGN_ROOT_MISSING", "root": str(root)}))
        return 2
    batches = [
        _probe_batch(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and ((child / "coordinator").is_dir() or (child / "r").is_dir())
    ]
    print(json.dumps({"campaign_root": str(root), "batches": batches}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

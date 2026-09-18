"""Explicitly requested DEBUG manifest reader.

This entry point is the ONLY reader of the debug install manifest. It is never called
by a runtime decision path: a missing, corrupt, stale or foreign-commit manifest cannot
change execution availability or authority. With ``--verify`` it recomputes the current
prefix bytes and reports drift as diagnostics only, exiting non-zero purely as a
command result (never as an execution gate).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..runtime.debug_provenance import (
    MANIFEST_RELATIVE_PATH, collect_debug_artifacts, coverage_summary,
    read_debug_manifest)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--print", dest="print_document", action="store_true")
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args(arguments)
    prefix = options.prefix
    document = read_debug_manifest(prefix)
    report: dict[str, object] = {
        "manifest": str(Path(prefix) / MANIFEST_RELATIVE_PATH),
        "authority": "DEBUG_ONLY_NOT_RUNTIME_AUTHORITY",
        "present": document is not None,
    }
    if document is None:
        report["diagnostic"] = "DEBUG_MANIFEST_MISSING_OR_UNREADABLE_RUNTIME_UNAFFECTED"
        print(json.dumps(report, sort_keys=True))
        return 0
    artifacts = collect_debug_artifacts(prefix)
    recorded = {str(item["path"]): item for item in document.get("artifacts", [])}
    current = {item.path: item for item in artifacts}
    drift = sorted(
        path for path, item in recorded.items()
        if path not in current or current[path].sha256 != item.get("sha256")
    )
    report.update({
        "kind": document.get("kind"),
        "schema_version": document.get("schema_version"),
        "source_commit": document.get("source_commit"),
        "source_commit_authority": "DEBUG_METADATA_ONLY",
        "source_dirty": document.get("source_dirty"),
        "recorded_count": len(recorded),
        "current_coverage": coverage_summary(artifacts),
        "drift": drift[:50],
        "drift_count": len(drift),
        "extra_count": len(set(current) - set(recorded)),
    })
    if options.print_document:
        report["document"] = document
    print(json.dumps(report, sort_keys=True))
    return 0 if not (options.verify and drift) else 1


if __name__ == "__main__":
    raise SystemExit(main())

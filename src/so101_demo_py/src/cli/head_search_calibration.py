"""The formal head search calibration CLI: run, verify-promoted-config, qualify, serve-teleop.

Every subcommand refuses a run root that already exists, so there is no way to resume or continue a stage.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from so101_demo.act.head_search_qualification import (
    qualification_parser,
    qualify_head_search,
    serve_teleop,
)


def _verify_promoted_config(run_root: Path, approved: str | None) -> int:
    """Compare the promoted bundle byte-for-byte against the digest the user approved."""

    if not approved:
        print("HEAD_SEARCH_APPROVAL_REQUIRED: pass --approved-bundle-sha256", file=sys.stderr)
        return 2
    promoted = run_root / "head-search-bundle.json"
    if not promoted.is_file():
        print(f"HEAD_SEARCH_BUNDLE_MISSING: {promoted} is absent", file=sys.stderr)
        return 2
    document = json.loads(promoted.read_text(encoding="utf-8"))
    from so101_demo.perception_benchmark.contracts import canonical_sha256

    measured = canonical_sha256(document)
    if measured != approved:
        print(
            f"HEAD_SEARCH_APPROVAL_MISMATCH: promoted {measured} differs from approved {approved}",
            file=sys.stderr,
        )
        return 2
    run_root.joinpath("approval-receipt.json").write_text(
        json.dumps(
            {
                "approved_bundle_sha256": approved,
                "promoted_bundle_sha256": measured,
                "verified": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"HEAD_SEARCH_APPROVED {measured}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parsed = qualification_parser().parse_args(argv)
    run_root = Path(parsed.run_root)
    if parsed.command == "verify-promoted-config":
        return _verify_promoted_config(run_root, parsed.approved_bundle_sha256)
    if parsed.command == "qualify":
        evidence_root = (
            Path(parsed.evidence_root) if parsed.evidence_root else run_root / "evidence"
        )
        promoted = (
            Path(parsed.promoted_config)
            if parsed.promoted_config
            else run_root / "head-search-bundle.json"
        )
        evidence = (
            {path.stem: _digest(path) for path in sorted(evidence_root.glob("*.json"))}
            if evidence_root.is_dir()
            else {}
        )
        report = qualify_head_search(
            {
                "run_root": run_root,
                "runtime_id": run_root.name,
                "bundle_sha256": _digest(promoted),
                "evidence": evidence,
            },
            run_root,
        )
        print(f"{report['status']} {report['evidence_sha256_set']}")
        return 0
    if parsed.command == "serve-teleop":
        report = json.loads((run_root / "head-search-qualified-report.json").read_text("utf-8"))
        connection = serve_teleop(report, run_root, bridge_socket_root=parsed.bridge_socket_root)
        print(f"TELEOP_ACCEPTANCE {connection['owner']['pid']}")
        return 0
    print(
        "HEAD_SEARCH_RUN: the production run belongs to Task 13's frozen runtime", file=sys.stderr
    )
    return 2


def _digest(path: Path) -> str:
    import hashlib

    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":  # pragma: no cover - console script entry
    raise SystemExit(main())

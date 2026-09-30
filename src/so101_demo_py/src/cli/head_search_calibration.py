"""The formal head search calibration CLI: run, verify-promoted-config, qualify, serve-teleop.

Every subcommand refuses a run root that already exists, so there is no way to resume or continue a stage.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from so101_demo.act.head_search_qualification import (
    qualification_parser,
    qualify_head_search,
    serve_teleop,
)


def _verify_promoted_config(
    run_root: Path, approved: str | None, promoted_config: Path | None
) -> int:
    """Hash the promoted bundle's bytes and record the approval once, immutably.

    The bundle is hashed as bytes, so a formatting-only difference is caught rather than normalised away,
    and the receipt is created exclusively: a second verification cannot overwrite what was approved. The
    receipt belongs to a run root that does not exist yet, so verification obeys the same no-resume rule as
    every other runner.
    """

    from so101_demo.act.head_search_qualification import _require_new_root, write_exclusive

    if not approved:
        print("HEAD_SEARCH_APPROVAL_REQUIRED: pass --approved-bundle-sha256", file=sys.stderr)
        return 2
    if promoted_config is None:
        print("HEAD_SEARCH_BUNDLE_REQUIRED: pass --promoted-config", file=sys.stderr)
        return 2
    promoted = Path(promoted_config)
    if not promoted.is_file():
        print(f"HEAD_SEARCH_BUNDLE_MISSING: {promoted} is absent", file=sys.stderr)
        return 2
    measured = hashlib.sha256(promoted.read_bytes()).hexdigest()
    if measured != approved:
        print(
            f"HEAD_SEARCH_APPROVAL_MISMATCH: promoted {measured} differs from approved {approved}",
            file=sys.stderr,
        )
        return 2
    try:
        root = _require_new_root(run_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    try:
        write_exclusive(
            root,
            "approval-receipt.json",
            {
                "approved_bundle_sha256": approved,
                "promoted_bundle_sha256": measured,
                "promoted_config": str(promoted),
                "hashed": "bytes",
                "verified": True,
            },
        )
    except FileExistsError:
        print("APPROVAL_RECEIPT_EXISTS: an approval is immutable", file=sys.stderr)
        return 2
    print(f"HEAD_SEARCH_APPROVED {measured}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parsed = qualification_parser().parse_args(argv)
    run_root = Path(parsed.run_root)
    if parsed.command == "verify-promoted-config":
        return _verify_promoted_config(
            run_root, parsed.approved_bundle_sha256, parsed.promoted_config
        )
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
    if parsed.command == "run":
        from so101_demo.act.head_search_qualification import run_head_search

        runtime_path = run_root.parent / "frozen-runtime.json"
        if not runtime_path.is_file():
            print(
                "HEAD_SEARCH_RUNTIME_REQUIRED: the frozen runtime belongs to Task 13",
                file=sys.stderr,
            )
            return 2
        try:
            receipt = run_head_search(
                {"runtime": json.loads(runtime_path.read_text(encoding="utf-8"))}, run_root
            )
        except ValueError as error:
            if "RUN_ROOT_ALREADY_EXISTS" not in str(error):
                raise
            print(str(error), file=sys.stderr)
            return 2
        print(f"RUN_SUCCEEDED {receipt['runtime_id']}")
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

"""Prove the bounded head-search plan against the sealed camera geometry.

This is the entry point Task 11 runs: it reads the geometry seal, builds the bounded stop plan for one
anchor, proves coverage from the field-of-view intervals, records the plan and its statuses, and fails
closed when the safe interval cannot cover the required domain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act.head_search_domain import (
    TARGET_NOT_FOUND,
    TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL,
    HeadSearchDomainError,
    bounded_search_stops,
)


def _path(value: str) -> Path:
    return Path(value).expanduser()


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="head_search_smoke",
        description="Plan and prove the bounded head search for one anchor",
    )
    parser.add_argument("--geometry-seal", required=True, type=_path)
    parser.add_argument("--anchor", default="default")
    parser.add_argument("--contract", type=_path)
    parser.add_argument("--output", type=_path)
    parsed = parser.parse_args(arguments)

    try:
        seal = json.loads(parsed.geometry_seal.read_text(encoding="utf-8"))
        if not isinstance(seal, dict):
            raise HeadSearchDomainError("HEAD_SEARCH_DOMAIN_INVALID: the seal must be a mapping")
        # the sealed geometry lists anchor names and carries each anchor's start angle in the
        # in-frame matrix; a bare mapping is accepted too so an older seal still reads
        anchors = seal.get("anchors") or {}
        matrix = seal.get("in_frame_matrix") or {}
        if parsed.anchor not in anchors:
            raise HeadSearchDomainError(
                f"HEAD_SEARCH_DOMAIN_INVALID: the seal declares no anchor {parsed.anchor!r}"
            )
        if isinstance(anchors, dict):
            anchor = float(anchors[parsed.anchor]["neck_rad"])
        else:
            entry = matrix[parsed.anchor]
            anchor = float(entry.get("neck_start_rad", entry.get("neck_rad")))
        required = seal["required_search_domain_rad"]
        safe = seal["lock_valid_neck_rad"]
        fov = float(seal["horizontal_fov_rad"])
        # the step is never invented: it comes from the sealed contract, the seal itself, or the run stops
        step_source = None
        if parsed.contract is not None:
            contract = json.loads(parsed.contract.read_text(encoding="utf-8"))
            accepted = contract.get("accepted_seal_sha256")
            sealed = seal.get("seal_sha256")
            if not sealed or accepted != sealed:
                raise HeadSearchDomainError(
                    "HEAD_SEARCH_STEP_UNSEALED: the contract is not associated with this geometry seal, "
                    "so its step cannot be applied"
                )
            step_source = contract.get("coarse_step_candidate_rad") or contract.get(
                "coarse_step_rad"
            )
        if step_source is None:
            step_source = (seal.get("camera") or {}).get("coarse_step_rad") or seal.get(
                "coarse_step_candidate_rad"
            )
        if step_source is None:
            raise HeadSearchDomainError(
                "HEAD_SEARCH_DOMAIN_INVALID: the seal and contract declare no coarse step, so coverage "
                "cannot be claimed from an invented one"
            )
        step = float(step_source)
        plan = bounded_search_stops(
            anchor_rad=anchor,
            required_domain_rad=required,
            safe_interval_rad=safe,
            horizontal_fov_rad=fov,
            coarse_step_rad=step,
        )
        if not plan.coverage_complete:
            raise HeadSearchDomainError(
                "HEAD_SEARCH_DOMAIN_UNSAFE: the plan does not cover the required domain"
            )
    except (HeadSearchDomainError, KeyError, OSError, TypeError, ValueError) as error:
        print(json.dumps({"failure": str(error), "status": "ERROR"}, sort_keys=True))
        return 2

    document = {
        "schema_version": 1,
        "anchor": parsed.anchor,
        "anchor_rad": anchor,
        "targets_rad": list(plan.targets_rad),
        "stop_count": len(plan.targets_rad),
        "coverage_complete": plan.coverage_complete,
        "required_domain_rad": list(plan.required_domain_rad),
        "safe_interval_rad": list(plan.safe_interval_rad),
        "horizontal_fov_rad": plan.horizontal_fov_rad,
        "coarse_step_rad": plan.coarse_step_rad,
        "statuses": [TARGET_NOT_FOUND, TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL],
        "seal_sha256": seal.get("seal_sha256"),
    }
    if parsed.output is not None:
        parsed.output.mkdir(parents=True, exist_ok=True)
        plan_path = parsed.output / f"head-search-plan-{parsed.anchor}.json"
        plan_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        document["plan"] = str(plan_path)
    print(json.dumps({"status": "OK", **document}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

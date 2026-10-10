"""Prove the bounded head-search plan against the sealed camera geometry, and fly the production smoke.

Two modes, one entry name, because the plan names this script for both of them:

* **Planning coverage** (this command with no ``--run-root``): read the geometry seal, build the bounded
  stop plan for one anchor, prove coverage from the field-of-view intervals, record the plan and its
  statuses, and fail closed when the safe interval cannot cover the required domain. This is the entry
  the coverage gate runs and it is unchanged.
* **The production smoke** (``--run-root`` present): the production smoke. Every other flag is the
  ``measure-production-smoke`` surface of ``so101_head_search_calibration`` and is forwarded to it
  verbatim, so there is one implementation of the flight, the sealed journal and the aggregator. In this
  mode the coverage proof is still written into the run root - it is the plan the flight walks - but the
  command's success condition is the journal the ``aggregate`` phase's ``production_smoke`` gate reads,
  and the ``--scenario`` flag the planning path accepted and never read now names the condition class
  whose terminal the smoke must end on.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from so101_demo.act.head_search_domain import HeadSearchDomainError, bounded_search_stops
from so101_demo.act.head_search_production_smoke import coverage_proof_document


def _path(value: str) -> Path:
    return Path(value).expanduser()


def main(arguments: list[str] | None = None) -> int:
    # the production smoke is the calibration CLI's own subcommand: intercept before the coverage
    # parser sees flags it does not declare, and forward the invocation verbatim
    forwarded = list(sys.argv[1:] if arguments is None else arguments)
    if "--run-root" in forwarded:
        from so101_demo.cli.head_search_calibration import (
            PRODUCTION_SMOKE_SCRIPT_ENTRY,
            _measure_production_smoke,
        )

        # the subcommand's own parser owns the flags, so the token itself is not forwarded
        return _measure_production_smoke(forwarded, entry=PRODUCTION_SMOKE_SCRIPT_ENTRY)
    arguments = forwarded
    parser = argparse.ArgumentParser(
        prog="head_search_smoke",
        description="Plan and prove the bounded head search for one anchor",
    )
    parser.add_argument("--geometry-seal", required=True, type=_path)
    parser.add_argument("--anchor", default="default")
    parser.add_argument("--contract", type=_path)
    parser.add_argument("--perception-config", type=_path)
    parser.add_argument("--output", type=_path)
    # The plan's coverage and qualification invocations pass --scenario and --evidence-root. The coverage
    # acceptance depends on this command running, so both are accepted here and the
    # evidence root doubles as the output root; every pre-existing flag keeps working.
    parser.add_argument("--scenario", default="default")
    parser.add_argument("--evidence-root", dest="evidence_root", type=_path)
    parsed = parser.parse_args(arguments)
    if parsed.output is None and parsed.evidence_root is not None:
        parsed.output = parsed.evidence_root

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
        declared_seal = None
        if parsed.perception_config is not None:
            # the perception config is the document that names the seal the camera was measured against
            import yaml

            declared = yaml.safe_load(parsed.perception_config.read_text(encoding="utf-8")) or {}
            # the tracked config declares it under geometry_seal; a top-level declaration is accepted too
            declared_seal = (declared.get("geometry_seal") or {}).get(
                "accepted_seal_sha256"
            ) or declared.get("accepted_seal_sha256")
            if declared_seal and seal.get("seal_sha256") and declared_seal != seal["seal_sha256"]:
                raise HeadSearchDomainError(
                    "HEAD_SEARCH_STEP_UNSEALED: the perception config names a different seal"
                )
        if parsed.contract is not None:
            contract = json.loads(parsed.contract.read_text(encoding="utf-8"))
            # the step is applied only when some supplied document names this very seal: the contract may
            # name it directly, or the perception config may, and both are tracked beside this seal
            accepted = contract.get("accepted_seal_sha256") or declared_seal
            sealed = seal.get("seal_sha256")
            if not sealed or accepted != sealed:
                raise HeadSearchDomainError(
                    "HEAD_SEARCH_STEP_UNSEALED: no supplied document is associated with this geometry seal, "
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

    document = coverage_proof_document(seal, parsed.anchor, anchor_rad=anchor, plan=plan)
    if parsed.output is not None:
        parsed.output.mkdir(parents=True, exist_ok=True)
        plan_path = parsed.output / f"head-search-plan-{parsed.anchor}.json"
        plan_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        # The plan's coverage gate checks for coverage-proof.json in the evidence root;
        # the emitted document is that proof, so it is written under both names.
        coverage_path = parsed.output / "coverage-proof.json"
        coverage_path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        document["plan"] = str(plan_path)
        document["coverage_proof"] = str(coverage_path)
    print(json.dumps({"status": "OK", **document}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

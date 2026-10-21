"""CLI (evidence side): write the next boundary-search round as a debug-campaign scene list plus a sidecar state.

Input is either the offline limits of ``act_boundary_prefilter`` (first round) or the state written by
``act_boundary_update`` (later rounds).  One scene per unfinished ray (scene ids ``bnd-<ray>-r<round>``), split
``functional`` as in the earlier debug lists.  The sidecar state records the probe of every scene and is what
``act_boundary_update`` reads once the campaign has finished.  When every ray is final, nothing is written and the
command says so.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from so101_demo.act import boundary_search
from so101_demo.act.scene_list_format import write_new_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="act_boundary_round", description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--limits", type=Path, help="act_boundary_prefilter output (first round)")
    source.add_argument("--state", type=Path, help="act_boundary_update output (later rounds)")
    parser.add_argument("--verified-from", type=Path,
                        help="with --limits: a finished state whose boundary radii are the earlier Teacher PASS points (verification rounds)")
    parser.add_argument("--scenes-output", type=Path, required=True, help="the round's scene list (written once)")
    parser.add_argument("--state-output", type=Path, required=True, help="the sidecar round state (written once)")
    args = parser.parse_args(argv)

    for target in (args.scenes_output, args.state_output):
        if target.exists() or target.is_symlink():
            raise ValueError(f"OUTPUT_EXISTS: {target}")
    if args.limits is not None:
        verified = None
        if args.verified_from is not None:
            earlier = json.loads(args.verified_from.read_text())
            if not boundary_search.is_finished(earlier):
                raise ValueError("BOUNDARY_VERIFIED_STATE_NOT_FINISHED")
            verified = {name: bracket["boundary_m"] for name, bracket in earlier["brackets"].items()}
        state = boundary_search.initial_state(json.loads(args.limits.read_text()), verified)
    else:
        state = json.loads(args.state.read_text())
    pending, scenes = boundary_search.round_state(state)
    if scenes is None:
        print(json.dumps({"status": "FINISHED", "boundary_points": state.get("boundary_points")}, sort_keys=True))
        return 0
    write_new_json(args.scenes_output, scenes)
    write_new_json(args.state_output, pending)
    print(json.dumps({"status": boundary_search.STATUS_PENDING, "round": pending["round"],
                      "scenes": [row["scene_id"] for row in scenes["scenarios"]]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

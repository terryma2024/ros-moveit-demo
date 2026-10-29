"""CLI: merge the sealed frozen indexes of several formal campaigns (one per host) into one index plus an export manifest.

    act_merge_collections --out-dir NEW --formal-list LIST [--stamp YYYYmmddTHHMMSSZ] [--readback-workers N] \\
        --index A/collection-index.json --qualification-report A-report.json --host ai-station [--run-root A] \\
        --index B/collection-index.json --qualification-report B-report.json --host antzb \\
        [--identity-equivalence PROOF --repo REPO --mount-inputs A-inputs-root (after each --index)]

The options that follow an `--index` belong to it. Each source is a sealed run root (default: the directory of its index) whose seal is
read back in full; its QUALIFIED report supplies the controlled identity (compared without `gpu_uuid`) and the GPU it ran on. The merge
refuses (exit 2, nothing written) when a source is unsealed or fails readback, an identity differs, scene sets overlap, or the union is
not the formal list. The identities may differ only in `mount_build` and `image_source_install`, and only with a proof that the two builds differ
in host-orchestration files alone (`act_identity_equivalence`; re-verified here, see `so101_demo.act.identity_equivalence`); the codes are listed in `so101_demo.act.collection_merge`. Writes `collection-index.json` and `manifest.json` into
the new directory, each once. Nothing in the sources is changed.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

from so101_demo.act.collection_merge import MergeRefused, MergeSource, merge_collections

_SOURCE_OPTIONS = {"--index": "index", "--qualification-report": "qualification_report", "--host": "host", "--run-root": "run_root", "--mount-inputs": "mount_inputs"}


def _sources(argv):
    """The sources, from the options in the order given: everything after an `--index` belongs to it."""
    sources, current = [], None
    position = 0
    while position < len(argv):
        token = argv[position]
        if token in _SOURCE_OPTIONS:
            if position + 1 >= len(argv):
                raise MergeRefused(f"MERGE_SOURCE_INVALID: {token} needs a value")
            value = argv[position + 1]
            if token == "--index":
                current = {}
                sources.append(current)
            elif current is None:
                raise MergeRefused(f"MERGE_SOURCE_INVALID: {token} before the first --index")
            field = _SOURCE_OPTIONS[token]
            if field in current:
                raise MergeRefused(f"MERGE_SOURCE_INVALID: {token} given twice for one --index")
            current[field] = value
            position += 2
        else:
            position += 1
    result = []
    for number, fields in enumerate(sources):
        for required in ("index", "qualification_report", "host"):
            if required not in fields:
                raise MergeRefused(f"MERGE_SOURCE_INVALID: source {number} has no --{required.replace('_', '-')}")
        result.append(MergeSource(index=Path(fields["index"]), qualification_report=Path(fields["qualification_report"]),
                                  host=fields["host"], run_root=Path(fields["run_root"]) if "run_root" in fields else None,
                                  mount_inputs=Path(fields["mount_inputs"]) if "mount_inputs" in fields else None))
    return result


def _write_new(path: Path, document) -> None:
    with open(path, "x") as stream:
        stream.write(json.dumps(document, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--formal-list", required=True, type=Path)
    parser.add_argument("--stamp", default=None, help="UTC stamp of the campaign id merged-<stamp> (default: now)")
    parser.add_argument("--readback-workers", type=int, default=4)
    parser.add_argument("--index", action="append", help="a sealed source index; its options follow it")
    parser.add_argument("--qualification-report", action="append")
    parser.add_argument("--host", action="append")
    parser.add_argument("--run-root", action="append")
    parser.add_argument("--mount-inputs", action="append", help="the sealed inputs root of the source (its mount-inputs/ directory)")
    parser.add_argument("--identity-equivalence", type=Path, default=None,
                        help="proof from act_identity_equivalence; required, and re-verified, only when the sources differ in mount_build / image_source_install")
    parser.add_argument("--repo", type=Path, default=Path("."), help="git repository the proof is recomputed in (default: the current directory)")
    args = parser.parse_args(argv)
    try:
        stamp = args.stamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if re.fullmatch(r"\d{8}T\d{6}Z", stamp) is None or args.readback_workers < 1:
            raise MergeRefused("MERGE_SOURCE_INVALID: --stamp must be YYYYmmddTHHMMSSZ and --readback-workers at least 1")
        sources = _sources(argv)
        if args.out_dir.exists():
            raise MergeRefused(f"MERGE_OUTPUT_EXISTS: {args.out_dir}")
        index, manifest = merge_collections(sources, args.formal_list, stamp, readback_workers=args.readback_workers,
                                          identity_equivalence=args.identity_equivalence, repo=args.repo)
        os.mkdir(args.out_dir)
    except MergeRefused as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    _write_new(args.out_dir / "collection-index.json", index)
    _write_new(args.out_dir / "manifest.json", manifest)
    print(f"merged {len(index['committed_episodes'])} episodes of {index['scene_count']} scenes into {args.out_dir} "
          f"(campaign_id {index['campaign_id']})")
    for source in index["provenance"]["sources"]:
        print(f"  {source['host']} ({source['gpu_model']}): {source['committed']} committed of {source['scenes']} scenes, "
              f"index sha256 {source['index_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

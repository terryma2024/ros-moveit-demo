"""CLI: write the identity-equivalence proof that `act_merge_collections --identity-equivalence` re-verifies.

    act_identity_equivalence --repo REPO --reference FULL_SHA [--mount-commit FULL_SHA]... [--host-commit FULL_SHA]... --out PROOF.json

The proof records the reference commit and, for each compared commit, the exact `git diff --name-only --no-renames` over the whole tree and its
sha256. `--mount-commit` is the commit of another source's mounted build; `--host-commit` a commit whose host code ran a stage of a source
(it must be named by that source's `MOUNT-INPUTS.json`). The command refuses (exit 2, nothing written) when a commit is not a full sha of the
repository or a changed file is outside the reviewed allow-list (`so101_demo.act.identity_equivalence`). The merge does not trust the file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from so101_demo.act.collection_merge import MergeRefused
from so101_demo.act.identity_equivalence import build_proof


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--reference", required=True)
    parser.add_argument("--mount-commit", action="append", default=[])
    parser.add_argument("--host-commit", action="append", default=[])
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.out.exists():
            raise MergeRefused(f"MERGE_IDENTITY_EQUIVALENCE_PROOF_INVALID: {args.out} exists")
        proof = build_proof(args.repo, args.reference, args.mount_commit, args.host_commit)
    except MergeRefused as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    with open(args.out, "x") as stream:
        stream.write(json.dumps(proof, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    for entry in proof["comparisons"]:
        print(f"{entry['role']} {entry['commit']}: {len(entry['changed_files'])} changed file(s), sha256 {entry['changed_files_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Recompute sealed collection roots under the code before and after the mount-tree migration and compare the verdicts.

usage: recompute_before_after.py --before REPO --after REPO --root LABEL=RUN_ROOT:CONTRACT [--root ...] --image-mode LABEL --expect LABEL=VERDICT [--expect ...] [--require-module M] [--out DIR] [--python PY]

REPO is a checkout (the commit before the migration, the migrated one); the code that runs is REPO/src/so101_demo_py/src, imported
as `so101_demo`. Each --root is one sealed run (for the migration evidence: one sealed image-mode root and one sealed mount root)
with its gate contract. `collection_qualification_recompute.recompute` reads the originals and writes nothing, so the roots are
never changed; each recompute runs in its own interpreter with only that checkout on its path.

For every root the canonical bytes of the recomputed report (or the exception that replaced it) must be identical before and
after: the verdict that is printed, the sha256 of each result, and exit code 0 only if all roots agree. Results are saved under
--out (default: ./recompute-before-after) as <label>.before.json / <label>.after.json.

Run it where the roots are (ai-station), with ROS sourced (/opt/ros/jazzy and the gate install) and the demo package's dependencies on
the path: without them the readback workers exit and both sides fail the same way, so the script refuses (control_msgs must import).
Every root must give a REPORT with the expected verdict on both sides; a refusal is a failure, not a match.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CHILD = r"""
import json, sys
from pathlib import Path
run_root, contract = sys.argv[1], sys.argv[2]
try:
    for module in sys.argv[3:]:             # the environment the readback workers need (ROS); without it every result is vacuous
        __import__(module)
    from so101_demo.act.collection_qualification_recompute import canonical, recompute
except BaseException as error:
    sys.stdout.write(json.dumps({"outcome": "IMPORT_FAILED", "canonical": type(error).__name__ + ": " + str(error)}))
    raise SystemExit(0)
try:
    document = recompute(Path(run_root), Path(contract))
    out = {"outcome": "REPORT", "canonical": canonical(document).decode("utf-8")}
except ImportError as error:
    out = {"outcome": "IMPORT_FAILED", "canonical": type(error).__name__ + ": " + str(error)}
except BaseException as error:
    out = {"outcome": "RAISED", "canonical": type(error).__name__ + ": " + str(error)}
sys.stdout.write(json.dumps(out))
"""


def run_one(python, repo, run_root, contract, timeout_s, require_modules=("control_msgs",)):
    """The recomputed report (canonical text) of one root under one checkout, or the exception text; never raises."""

    package = Path(repo).resolve() / "src" / "so101_demo_py" / "src"
    if not (package / "__init__.py").is_file():
        return {"outcome": "SETUP", "canonical": f"no package at {package}"}
    with tempfile.TemporaryDirectory(prefix="recompute-shim-") as shim:
        (Path(shim) / "so101_demo").symlink_to(package)
        # The shim goes first so this checkout's so101_demo wins; the caller's PYTHONPATH (so101_teleop, the ROS paths) stays behind it.
        inherited = os.environ.get("PYTHONPATH", "")
        environment = dict(os.environ, PYTHONPATH=shim + (os.pathsep + inherited if inherited else ""),
                           PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1")
        try:
            done = subprocess.run([python, "-c", CHILD, str(run_root), str(contract), *require_modules], env=environment,
                                  capture_output=True, text=True, timeout=timeout_s, cwd=shim)      # cwd first on the path: the shim only
        except subprocess.TimeoutExpired:
            return {"outcome": "TIMEOUT", "canonical": f"no result in {timeout_s} s"}
    try:
        return json.loads(done.stdout)
    except ValueError:
        return {"outcome": "CHILD_FAILED", "canonical": f"rc={done.returncode} {done.stderr.strip()[-400:]}"}


def verdict_of(result):
    if result["outcome"] != "REPORT":
        return result["outcome"]
    document = json.loads(result["canonical"])
    return str(document.get("status", document.get("verdict", "UNKNOWN")))


def compare(roots, before, after, python, out, timeout_s=3600, image_labels=(), expected=None, require_modules=("control_msgs",)):
    """One row per root; `same` is true only if the two results are byte-identical.

    `usable` needs a REPORT on both sides: a refusal (RAISED), an import or module error, or a missing environment (`require_modules`,
    ROS by default) is a setup failure, never a verdict, because the same failure on both sides would otherwise pass vacuously.
    With `expected` ({label: verdict}, the verdict the root recorded when it was sealed) both sides must also give exactly that.
    """

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, (run_root, contract) in roots.items():
        results = {}
        for side, repo in (("before", before), ("after", after)):
            result = run_one(python, repo, run_root, contract, timeout_s, require_modules)
            (out / f"{label}.{side}.json").write_text(json.dumps(result, sort_keys=True, indent=1) + "\n")
            results[side] = result
        same = results["before"] == results["after"]
        usable = all(results[side]["outcome"] == "REPORT" for side in ("before", "after"))
        verdict = verdict_of(results["before"])
        rows.append(dict(label=label, same=same, before=verdict, after=verdict_of(results["after"]),
                         before_sha256=hashlib.sha256(results["before"]["canonical"].encode()).hexdigest(),
                         after_sha256=hashlib.sha256(results["after"]["canonical"].encode()).hexdigest(),
                         expected=(expected or {}).get(label),
                         usable=usable and (expected is None or label not in expected
                                            or (verdict, verdict_of(results["after"])) == (expected[label],) * 2)))
    return rows


def parse_roots(items):
    roots = {}
    for item in items:
        label, _, rest = item.partition("=")
        run_root, _, contract = rest.partition(":")
        if not label or not run_root or not contract or label in roots:
            raise SystemExit(f"--root needs LABEL=RUN_ROOT:CONTRACT with a new label: {item!r}")
        roots[label] = (run_root, contract)
    return roots


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--image-mode", action="append", required=True, metavar="LABEL",
                        help="label of the sealed image-mode root (it must be one of the --root labels)")
    parser.add_argument("--expect", action="append", required=True, metavar="LABEL=VERDICT",
                        help="the verdict each root recorded when it was sealed (e.g. QUALIFIED); needed for every --root")
    parser.add_argument("--require-module", action="append", default=None, metavar="MODULE",
                        help="module the interpreter must import first (default control_msgs: source ROS and the gate install)")
    parser.add_argument("--out", default="recompute-before-after")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout-s", type=float, default=3600)
    args = parser.parse_args(argv)
    roots = parse_roots(args.root)
    unknown = [label for label in args.image_mode if label not in roots]
    if unknown:
        raise SystemExit(f"--image-mode names no --root: {unknown}")
    expected = dict(item.partition("=")[::2] for item in args.expect)
    if set(expected) != set(roots) or not all(expected.values()):
        raise SystemExit(f"--expect needs LABEL=VERDICT for exactly the --root labels: {sorted(roots)}")
    rows = compare(roots, args.before, args.after, args.python, args.out, args.timeout_s, tuple(args.image_mode), expected,
                   tuple(args.require_module) if args.require_module is not None else ("control_msgs",))
    for row in rows:
        print(f"{row['label']}: {'IDENTICAL' if row['same'] else 'DIFFERENT'}  before={row['before']} after={row['after']}  "
              f"sha256 {row['before_sha256'][:12]} / {row['after_sha256'][:12]}")
    ok = all(row["same"] and row["usable"] for row in rows)
    print("RESULT:", "PASS (identical verdicts on every root)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

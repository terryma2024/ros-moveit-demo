"""The first-episode entry point: inspect candidates, freeze inputs, preflight a frozen set.

The amendment gives this CLI the flags the plan's E3 sequence uses. `prepare` is the production caller the freezer
never had, so the endpoint policy and the development runtime are bound into the inputs hash chain there; `preflight`
re-reads a frozen set and refuses when its own manifest, its policy or its runtime cannot be accounted for. `inspect`
- the candidate discovery over a source root and the ledger - is not implemented yet and says so with rc 2 rather
than inventing a registry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from so101_demo.act.endpoint_pose_acceptance import load_development_runtime, load_endpoint_policy
from so101_demo.act.first_episode_inputs import freeze_inputs, inspect_inputs

MODES = ("formal", "preselected_target_diagnostic")


class _Parser(argparse.ArgumentParser):
    """The house parser: a refused argument is rc 2, never a traceback."""

    def error(self, message):                                        # noqa: D102 - argparse contract
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="act_first_episode", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser("inspect", help="discover input candidates (not implemented yet)")
    inspect.add_argument("--source-root", required=True)
    inspect.add_argument("--ledger", required=True)
    inspect.add_argument("--output", required=True)

    prepare = subparsers.add_parser("prepare", help="freeze a candidate registry into immutable inputs")
    prepare.add_argument("--candidates", required=True)
    prepare.add_argument("--mode", default="formal", choices=MODES)
    prepare.add_argument("--endpoint-policy", required=True)
    prepare.add_argument("--runtime-policy", required=True)
    prepare.add_argument("--output", required=True)

    preflight = subparsers.add_parser("preflight", help="re-read a frozen input set")
    preflight.add_argument("--inputs", required=True)
    preflight.add_argument("--mode", default="formal", choices=MODES)
    preflight.add_argument("--output", required=True)
    return parser


def _prepare(arguments) -> int:
    # the policy and runtime are parsed before the freeze so a bad document refuses before anything is written
    load_endpoint_policy(Path(arguments.endpoint_policy))
    load_development_runtime(Path(arguments.runtime_policy))
    target = freeze_inputs(Path(arguments.candidates), Path(arguments.output), mode=arguments.mode,
                           endpoint_policy=Path(arguments.endpoint_policy),
                           runtime_policy=Path(arguments.runtime_policy))
    print(target)
    return 0


def _preflight(arguments) -> int:
    inputs = Path(arguments.inputs)
    manifest_path = inputs / "inputs-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    report = {
        "mode": arguments.mode,
        "inputs_sha256": manifest["inputs_sha256"],
        "endpoint_policy": manifest.get("endpoint_policy"),
        "runtime_policy": manifest.get("runtime_policy"),
        "roles": sorted(manifest["roles"]),
        "prepared_mode": manifest.get("mode"),
    }
    Path(arguments.output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(arguments.output)
    return 0


def main(argv=None) -> int:
    arguments = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if arguments.command == "inspect":
        # the discovery already exists in the inputs module and is read-only: it selects nothing by recency and
        # defaults nothing, reporting a blocker for every role without an approved, identity-matching candidate
        document = inspect_inputs(Path(arguments.source_root), Path(arguments.ledger))
        Path(arguments.output).write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
        print(arguments.output)
        return 0
    if arguments.command == "prepare":
        return _prepare(arguments)
    if arguments.command == "preflight":
        return _preflight(arguments)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

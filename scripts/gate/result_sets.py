#!/usr/bin/env python3
"""Per-package test identity and result sets of a Host gate build base, for the serial-versus-parallel equivalence proof. `python3 -I`; stdlib only.

  collect --build-base DIR --out FILE [--packages p1,p2]
      For every package directory of DIR: the ctest tests (Testing/*/Test.xml, name -> status) and every test case of every xunit/gtest/junit
      file under test_results/ (`<file>::<classname>::<name>` -> passed|failed|skipped). A case that appears twice gets a `#2`, `#3` suffix.
      Timing values are not recorded: only identity and outcome.
  compare A.json B.json
      Exit 0 when the two are identical. Otherwise prints every package/key that differs and exits 1.
"""
import argparse
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import parse


def case_status(case):
    if case.find("skipped") is not None:
        return "skipped"
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    return "passed"


def collect(build_base, packages=None):
    base = Path(build_base)
    out = {}
    for pdir in sorted(p for p in base.iterdir() if p.is_dir()):
        if packages and pdir.name not in packages:
            continue
        ctest = {}
        for xml in sorted(pdir.glob("Testing/*/Test.xml")):
            for test in parse(str(xml)).getroot().iterfind("Testing/Test"):
                name, status = test.findtext("Name"), test.attrib.get("Status", "?")
                ctest[name] = f"{ctest[name]}+{status}" if name in ctest else status
        cases = {}
        for xml in sorted((pdir / "test_results").glob("**/*.xml")):
            rel = xml.relative_to(pdir / "test_results")
            try:
                root = parse(str(xml)).getroot()
            except Exception:
                cases[f"{rel}::UNREADABLE"] = "failed"
                continue
            for case in root.iter("testcase"):
                key = f"{rel}::{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
                n, final = 1, key
                while final in cases:
                    n += 1
                    final = f"{key}#{n}"
                cases[final] = case_status(case)
        if ctest or cases:
            out[pdir.name] = {"ctest": dict(sorted(ctest.items())), "cases": dict(sorted(cases.items()))}
    return out


def compare(a, b):
    problems = []
    for package in sorted(set(a) | set(b)):
        left, right = a.get(package), b.get(package)
        if left is None or right is None:
            problems.append(f"{package}: only in {'A' if right is None else 'B'}")
            continue
        for kind in ("ctest", "cases"):
            for key in sorted(set(left[kind]) | set(right[kind])):
                if left[kind].get(key) != right[kind].get(key):
                    problems.append(f"{package} {kind} {key}: A={left[kind].get(key)} B={right[kind].get(key)}")
    return problems


def summary(sets):
    return {p: {"ctest": len(v["ctest"]), "cases": len(v["cases"])} for p, v in sets.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--build-base", required=True, type=Path)
    c.add_argument("--out", required=True, type=Path)
    c.add_argument("--packages", default=None)
    d = sub.add_parser("compare")
    d.add_argument("a", type=Path)
    d.add_argument("b", type=Path)
    args = parser.parse_args(argv)
    if args.command == "collect":
        sets = collect(args.build_base, args.packages.split(",") if args.packages else None)
        args.out.write_text(json.dumps(sets, sort_keys=True, indent=1) + "\n")
        print(json.dumps(summary(sets), sort_keys=True))
        return 0
    problems = compare(json.loads(args.a.read_text()), json.loads(args.b.read_text()))
    print("\n".join(problems) if problems else "identical")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

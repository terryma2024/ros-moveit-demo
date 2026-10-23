#!/usr/bin/env python3
"""The so101_teleop pytest modules of the Host gate as one xdist run (TELEOP_XDIST=1). Run with `python3 -I`; stdlib only.

  paths  --cmake CMakeLists.txt --root PACKAGE_ROOT [--exclude name,name]
         The files the ctest registrations `so101_add_pytest_test(<name> test/<file>.py)` run, as absolute paths in registration order, without the
         registrations named in --exclude (the serial tests). Refuses (exit 2) an excluded name that is not registered, a registration whose file
         is missing, a duplicate name or a duplicate path: a single pytest run over these paths collects exactly what the separate ctest runs collect.
  sets   --results DIR --out FILE
         The executed tests of the package, from every *.xunit.xml under DIR: "<classname>::<name>" -> pass|fail|error|skipped.
  compare A.json B.json
         Exit 0 when the two sets are identical (same ids, same results), else prints the differences and exits 1.
"""
import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree.ElementTree import parse

REGISTRATION = re.compile(r"so101_add_pytest_test\(\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s+(?P<path>test/[^\s()]+\.py)\s*\)")


class SelectionError(Exception):
    pass


def registered(cmake_text):
    return [(match.group("name"), match.group("path")) for match in REGISTRATION.finditer(cmake_text)]


def selected_paths(cmake_text, root, exclude=()):
    items = registered(cmake_text)
    names = [name for name, _path in items]
    paths = [path for _name, path in items]
    for label, values in (("name", names), ("path", paths)):
        duplicated = sorted({value for value in values if values.count(value) > 1})
        if duplicated:
            raise SelectionError(f"duplicate registration {label}: {', '.join(duplicated)}")
    unknown = sorted(set(exclude) - set(names))
    if unknown:
        raise SelectionError(f"excluded but not registered: {', '.join(unknown)}")
    missing = [path for _name, path in items if not (Path(root) / path).is_file()]
    if missing:
        raise SelectionError(f"registered file missing: {', '.join(missing)}")
    return [str(Path(root) / path) for name, path in items if name not in set(exclude)]


def executed_tests(results_dir):
    tests = {}
    for xml in sorted(Path(results_dir).rglob("*.xunit.xml")):
        for case in parse(xml).getroot().iter("testcase"):
            identifier = f"{case.get('classname', '')}::{case.get('name', '')}"
            if identifier in tests:
                raise SelectionError(f"test id seen twice: {identifier} ({xml.name})")
            tests[identifier] = ("fail" if case.find("failure") is not None else "error" if case.find("error") is not None
                                 else "skipped" if case.find("skipped") is not None else "pass")
    return tests


def compare_sets(a, b):
    problems = [f"only in A: {name}" for name in sorted(set(a) - set(b))] + [f"only in B: {name}" for name in sorted(set(b) - set(a))]
    problems += [f"{name}: A {a[name]} B {b[name]}" for name in sorted(set(a) & set(b)) if a[name] != b[name]]
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    paths = sub.add_parser("paths")
    paths.add_argument("--cmake", type=Path, required=True)
    paths.add_argument("--root", type=Path, required=True)
    paths.add_argument("--exclude", default="")
    sets = sub.add_parser("sets")
    sets.add_argument("--results", type=Path, required=True)
    sets.add_argument("--out", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("a", type=Path)
    compare.add_argument("b", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "paths":
            print("\n".join(selected_paths(args.cmake.read_text(), args.root, [name for name in args.exclude.split(",") if name])))
        elif args.command == "sets":
            tests = executed_tests(args.results)
            args.out.write_text(json.dumps(tests, indent=1, sort_keys=True) + "\n")
            print(f"{len(tests)} tests")
        else:
            problems = compare_sets(json.loads(args.a.read_text()), json.loads(args.b.read_text()))
            print("\n".join(problems[:50]) if problems else "identical")
            return 1 if problems else 0
    except (SelectionError, OSError, ValueError) as error:
        print(f"teleop_pytest: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

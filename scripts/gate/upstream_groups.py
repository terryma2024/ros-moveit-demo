#!/usr/bin/env python3
"""CPU groups and test partition of the upstream tests for the parallel Host gate. Run with `python3 -I`; stdlib only.

  cpus   --groups FILE --share S [--topology FILE] [--packages p1,p2]
         Prints JSON {"groups": {name: "cpulist"}, "rest": "cpulist", ...}. The upstream groups get whole cores (both threads of a core), the fastest
         cores first, until they hold about S of the logical CPUs (at least one core per group); the weights split the cores. The rest is every other
         logical CPU. --topology: `lscpu -p=CPU,CORE,MAXMHZ` output (default: run lscpu).
  spec   --groups FILE --package-lists DIR [--packages p1,p2]
         Checks that the groups cover every ctest test of each package exactly once (DIR/<package>.txt = `ctest -N` output) and prints one line per
         group entry: `<group>\\t<package>\\t<R|E>\\t<regex>`. Refuses (exit 2) a stale selector, an overlap or an uncovered test.
  sets   --build-base DIR --packages p1,p2 --out FILE
         The executed tests per package, from every ctest Test.xml phase and every gtest xml: name -> status, and gtest cases per file.
  compare A.json B.json
         Exit 0 when the two sets are identical, else prints the differences and exits 1.
  timing --build-base DIR --packages p1,p2 [--top N]
         The slowest ctest tests of each package (Execution Time of every Test.xml phase).
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from xml.etree.ElementTree import parse


class GroupError(Exception):
    pass


def parse_groups(text):
    """[(group, weight, package, selector)] in file order; a group keeps one weight."""
    entries, weights = [], {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in re.split(r"\s\|\s", line)]   # a regex may hold `|`, the separator has blanks
        if len(fields) != 4 or not re.fullmatch(r"[a-z][a-z0-9-]*", fields[0]) or not fields[1].isdigit() or int(fields[1]) < 1:
            raise GroupError(f"UPSTREAM_GROUPS_INVALID: line {number}: {line}")
        group, weight, package, selector = fields[0], int(fields[1]), fields[2], fields[3]
        if weights.setdefault(group, weight) != weight:
            raise GroupError(f"UPSTREAM_GROUPS_INVALID: line {number}: group {group} has two weights")
        if selector != "rest":
            if not selector.startswith("-R "):
                raise GroupError(f"UPSTREAM_GROUPS_INVALID: line {number}: selector must be `rest` or `-R <regex>`")
            re.compile(selector[3:])
        entries.append((group, weight, package, selector))
    if not entries:
        raise GroupError("UPSTREAM_GROUPS_INVALID: no group")
    return entries


def group_names(entries):
    names = []
    for group, *_ in entries:
        if group not in names:
            names.append(group)
    return names


def read_topology(text):
    """[(cpu, core, mhz)] from `lscpu -p=CPU,CORE,MAXMHZ` (comment lines start with #)."""
    rows = []
    for line in text.splitlines():
        if line.strip() and not line.startswith("#"):
            cpu, core, mhz = line.split(",")[:3]
            rows.append((int(cpu), int(core), float(mhz or 0)))
    if not rows:
        raise GroupError("UPSTREAM_CPUS_INVALID: empty topology")
    return rows


def cpu_list(cpus):
    """1,2,3,7 -> `1-3,7`."""
    cpus, parts = sorted(cpus), []
    start = prev = None
    for cpu in cpus:
        if start is None:
            start = prev = cpu
        elif cpu == prev + 1:
            prev = cpu
        else:
            parts.append((start, prev))
            start = prev = cpu
    if start is not None:
        parts.append((start, prev))
    return ",".join(str(a) if a == b else f"{a}-{b}" for a, b in parts)


def allocate(entries, topology, share):
    names = group_names(entries)
    weights = {name: next(w for g, w, *_ in entries if g == name) for name in names}
    cores = {}
    for cpu, core, mhz in topology:
        cores.setdefault(core, {"cpus": [], "mhz": mhz})["cpus"].append(cpu)
    ordered = sorted(cores, key=lambda core: (-cores[core]["mhz"], core))      # fastest cores first
    if len(ordered) < len(names) + 1:
        raise GroupError(f"UPSTREAM_CPUS_INVALID: {len(ordered)} cores cannot hold {len(names)} groups and the rest")
    target, taken, count = round(len(topology) * share), 0, 0
    while count < len(ordered) - 1 and (count < len(names) or taken < target):
        taken += len(cores[ordered[count]]["cpus"])
        count += 1
    chosen = ordered[:count]
    # largest remainder split of the chosen cores by weight, at least one each
    total = sum(weights.values())
    quota = {name: max(1, count * weights[name] // total) for name in names}
    remainder = sorted(names, key=lambda n: -(count * weights[n] % total))
    while sum(quota.values()) < count:
        quota[remainder[0]] += 1
        remainder.append(remainder.pop(0))
    while sum(quota.values()) > count:
        quota[max(names, key=lambda n: quota[n])] -= 1
    groups, position = {}, 0
    for name in names:
        members = chosen[position:position + quota[name]]
        position += quota[name]
        groups[name] = sorted(cpu for core in members for cpu in cores[core]["cpus"])
    used = {cpu for cpus in groups.values() for cpu in cpus}
    rest = sorted(cpu for cpu, _, _ in topology if cpu not in used)
    return {"groups": {n: cpu_list(c) for n, c in groups.items()}, "rest": cpu_list(rest),
            "logical_cpus": len(topology), "upstream_cpus": len(used), "share_requested": share,
            "cores": {n: len(groups[n]) // max(1, len(cores[next(c for c in cores if groups[n][0] in cores[c]['cpus'])]['cpus'])) for n in names}}


def ctest_names(text):
    return re.findall(r"^\s*Test\s+#\d+:\s+(\S+)", text, re.M)


def partition(entries, names_by_package):
    """{(group, package): ('R'|'E', regex)} after checking that every test of every package belongs to exactly one group."""
    result, claimed = {}, {}
    for package, names in names_by_package.items():
        own = [e for e in entries if e[2] == package]
        if not own:
            raise GroupError(f"UPSTREAM_PACKAGE_UNGROUPED: {package}")
        if sum(1 for e in own if e[3] == "rest") != 1:
            raise GroupError(f"UPSTREAM_REST_NOT_ONE: {package} needs exactly one `rest` entry")
        taken = set()
        for group, _, _, selector in own:
            if selector == "rest":
                continue
            regex = selector[3:]
            matched = {n for n in names if re.search(regex, n)}
            if not matched:
                raise GroupError(f"UPSTREAM_SELECTOR_STALE: {package} `{regex}` matches no test")
            named = re.fullmatch(r"\^\(?([\w|]+)\)?\$", regex)       # ^name$ or ^(a|b)$: every name has to exist
            if named:
                missing = [n for n in named.group(1).split("|") if n not in names]
                if missing:
                    raise GroupError(f"UPSTREAM_SELECTOR_STALE: {package} `{regex}` names {missing}, which no test has")
            if matched & taken:
                raise GroupError(f"UPSTREAM_SELECTOR_OVERLAP: {package} {sorted(matched & taken)}")
            taken |= matched
            result[(group, package)] = ("R", regex)
        rest_group = next(g for g, _, _, s in own if s == "rest")
        if len(taken) == len(names):
            raise GroupError(f"UPSTREAM_REST_EMPTY: {package} has no test left for `rest`")
        union = "^(" + "|".join(re.escape(n) for n in sorted(taken)) + ")$"
        result[(rest_group, package)] = ("E", union) if taken else ("A", "")
    return result


def spec_lines(entries, parts):
    lines = []
    for group, _, package, _ in entries:
        mode, regex = parts[(group, package)]
        lines.append(f"{group}\t{package}\t{mode}\t{regex}")
    return lines


def collect_sets(build_base, packages):
    out = {}
    for package in packages:
        base = Path(build_base) / package
        tests = {}
        for xml in sorted(base.glob("Testing/*/Test.xml")):
            for test in parse(str(xml)).getroot().iterfind("Testing/Test"):
                name = test.findtext("Name")
                if name in tests:
                    tests[name] = "duplicate"
                else:
                    tests[name] = test.attrib.get("Status")
        cases = {}
        for xml in sorted(base.glob("test_results/**/*.xml")):
            root = parse(str(xml)).getroot()
            cases[xml.name] = int(root.attrib.get("tests", 0)) if root.tag in ("testsuites", "testsuite") else 0
        out[package] = {"ctest": dict(sorted(tests.items())), "gtest_cases": dict(sorted(cases.items()))}
    return out


def compare_sets(a, b):
    problems = []
    for package in sorted(set(a) | set(b)):
        left, right = a.get(package), b.get(package)
        if left is None or right is None:
            problems.append(f"{package}: only in {'A' if right is None else 'B'}")
            continue
        for kind in ("ctest", "gtest_cases"):
            for key in sorted(set(left[kind]) | set(right[kind])):
                if left[kind].get(key) != right[kind].get(key):
                    problems.append(f"{package} {kind} {key}: A={left[kind].get(key)} B={right[kind].get(key)}")
    return problems


def timing(build_base, packages, top):
    rows = {}
    for package in packages:
        found = []
        for xml in sorted((Path(build_base) / package).glob("Testing/*/Test.xml")):
            for test in parse(str(xml)).getroot().iterfind("Testing/Test"):
                for measurement in test.iter("NamedMeasurement"):
                    if measurement.attrib.get("name") == "Execution Time":
                        found.append((float(measurement.findtext("Value")), test.findtext("Name"), test.attrib.get("Status")))
        rows[package] = sorted(found, reverse=True)[:top]
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cpus = sub.add_parser("cpus")
    cpus.add_argument("--groups", required=True, type=Path)
    cpus.add_argument("--share", required=True, type=float)
    cpus.add_argument("--topology", type=Path)
    cpus.add_argument("--packages", default=None, help="only the groups with an entry for one of these packages take CPUs")
    spec = sub.add_parser("spec")
    spec.add_argument("--groups", required=True, type=Path)
    spec.add_argument("--package-lists", required=True, type=Path)
    spec.add_argument("--packages", default=None)
    sets = sub.add_parser("sets")
    sets.add_argument("--build-base", required=True, type=Path)
    sets.add_argument("--packages", required=True)
    sets.add_argument("--out", required=True, type=Path)
    compare = sub.add_parser("compare")
    compare.add_argument("a", type=Path)
    compare.add_argument("b", type=Path)
    slow = sub.add_parser("timing")
    slow.add_argument("--build-base", required=True, type=Path)
    slow.add_argument("--packages", required=True)
    slow.add_argument("--top", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        if args.command == "cpus":
            if not 0 < args.share < 1:
                raise GroupError("UPSTREAM_CPUS_INVALID: --share must be between 0 and 1")
            entries = parse_groups(args.groups.read_text())
            if args.packages:
                entries = [e for e in entries if e[2] in args.packages.split(",")]
                if not entries:
                    raise GroupError("UPSTREAM_GROUPS_INVALID: no group for those packages")
            text = args.topology.read_text() if args.topology else subprocess.check_output(["lscpu", "-p=CPU,CORE,MAXMHZ"], text=True)
            print(json.dumps(allocate(entries, read_topology(text), args.share), sort_keys=True))
        elif args.command == "spec":
            entries = parse_groups(args.groups.read_text())
            wanted = args.packages.split(",") if args.packages else sorted({e[2] for e in entries})
            names = {p: ctest_names((args.package_lists / f"{p}.txt").read_text()) for p in wanted}
            entries = [e for e in entries if e[2] in names]
            print("\n".join(spec_lines(entries, partition(entries, names))))
        elif args.command == "sets":
            args.out.write_text(json.dumps(collect_sets(args.build_base, args.packages.split(",")), sort_keys=True, indent=1) + "\n")
        elif args.command == "compare":
            problems = compare_sets(json.loads(args.a.read_text()), json.loads(args.b.read_text()))
            print("\n".join(problems) if problems else "identical")
            return 1 if problems else 0
        else:
            for package, rows in timing(args.build_base, args.packages.split(","), args.top).items():
                print(package)
                for seconds, name, status in rows:
                    print(f"  {seconds:8.1f}  {name}  {status}")
    except (GroupError, OSError, re.error) as error:
        print(f"REFUSED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""image-env: compare a host with a container image that will run the host-built, mounted install tree (stdlib only).

Subcommands
-----------
capture-image  Read-only. Runs the image with `docker run --rm --network none --read-only` and writes its package manifest.
check-image    Compares this host with that manifest for one install tree. Exit 1 on any "must" difference.
               --plan also writes what `so101_env apply` would have to change on the host (installs and downgrades; no removals).

The must-match set (docs/superpowers/specs/2026-10-21-so101-mount-build-images-design.md, section b):
  1. every apt package installed on both sides is at the same version;
  2. every package in the image that the install tree needs is installed on the host: the dependency closure of the packages named by
     the tree's package.xml files, and the owner of every library `ldd` resolves for an ELF file of the tree inside the image;
  3. the python minor version, the Ubuntu codename and the pip pins of the image's /act/venv (present at the same version on the host venv).
A library the container cannot find is a failure. Packages that only the host has are reported, not refused.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import so101_env as base  # noqa: E402  (same directory)

MUST, SHOULD = base.MUST, base.SHOULD
ROS_PREFIX = base.ROS_PREFIX
IMAGE_VENV_PYTHON = "/act/venv/bin/python"
ROS_LIBRARY_DIRS = ("/opt/ros/jazzy/lib", "/opt/ros/jazzy/opt/mujoco_vendor/lib")


def run_docker(argv, **kwargs):
    """Run a docker command, return stdout; the injectable seam of every function that talks to an image."""
    done = subprocess.run(argv, capture_output=True, text=True, **kwargs)
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:6])}... failed: {done.stderr.strip()[:400]}")
    return done.stdout


def _in_image(image_id, entrypoint, *args, extra=()):
    return ["docker", "run", "--rm", "--network", "none", "--read-only", *extra, "--entrypoint", entrypoint, image_id, *args]


# --------------------------------------------------------------------------
# Parsers (pure)
# --------------------------------------------------------------------------

def parse_dependency_graph(text: str) -> dict[str, set[str]]:
    """`dpkg-query -W -f '${Package}\\t${Version}\\t${Depends}\\t${Pre-Depends}\\n'` into package -> names it depends on."""
    graph: dict[str, set[str]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2 or not parts[0]:
            continue
        names: set[str] = set()
        for field in parts[2:4]:
            for clause in field.split(","):
                for alternative in clause.split("|"):
                    name = re.sub(r"\(.*?\)|\[.*?\]|<.*?>", "", alternative).strip().split(":")[0]
                    if name:
                        names.add(name)
        graph[parts[0].split(":")[0]] = names
    return graph


def resolve_keys(keys: set[str], apt: dict[str, str]) -> tuple[set[str], set[str]]:
    """package.xml dependency keys to installed apt names: ros-jazzy-<key with hyphens> first, then the key itself."""
    resolved, unresolved = set(), set()
    for key in keys:
        ros_name = ROS_PREFIX + key.replace("_", "-")
        if ros_name in apt:
            resolved.add(ros_name)
        elif key in apt:
            resolved.add(key)
        else:
            unresolved.add(key)
    return resolved, unresolved


def dependency_closure(seeds: set[str], graph: dict[str, set[str]], image_apt: dict[str, str]) -> set[str]:
    seen: set[str] = set()
    todo = [name for name in sorted(seeds) if name in image_apt]
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        todo.extend(dep for dep in sorted(graph.get(name, ())) if dep in image_apt and dep not in seen)
    return seen


def parse_ldd(text: str, tree: str) -> tuple[set[str], set[str]]:
    """(resolved paths outside the tree, library names reported `not found`) from `ldd` output."""
    outside, missing = set(), set()
    prefix = tree.rstrip("/") + "/"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.endswith(":") or line.startswith("linux-vdso") or line.startswith("statically"):
            continue
        if "=> not found" in line:
            missing.add(line.split("=>")[0].strip())
            continue
        path = line.split("=>", 1)[1].strip().split(" (")[0] if "=>" in line else line.split(" (")[0]
        if path.startswith("/") and not path.startswith(prefix):
            outside.add(path)
    return outside, missing


def parse_dpkg_s(text: str) -> dict[str, str]:
    """`dpkg -S` style lines `pkg[:arch]: /path` into path -> package."""
    owners: dict[str, str] = {}
    for line in text.splitlines():
        if ": /" not in line or line.startswith("diversion"):
            continue
        name, path = line.split(": /", 1)
        owners.setdefault("/" + path.strip(), name.split(",")[0].strip().split(":")[0])
    return owners


def _pin(line: str) -> tuple[str, str]:
    match = re.match(r"([^=@ ]+)\s*(==|@)\s*(.*)", line)
    return (match.group(1).lower(), match.group(3)) if match else (line.lower(), "")


# --------------------------------------------------------------------------
# Image capture
# --------------------------------------------------------------------------

def capture_image(image_id: str, docker=run_docker) -> dict:
    installed = base.parse_dpkg_query(docker(_in_image(
        image_id, "dpkg-query", "-W", "-f", "${db:Status-Abbrev}\t${Package}\t${Version}\n")))
    graph = parse_dependency_graph(docker(_in_image(
        image_id, "dpkg-query", "-W", "-f", "${Package}\t${Version}\t${Depends}\t${Pre-Depends}\n")))
    os_release = base.parse_os_release(docker(_in_image(image_id, "cat", "/etc/os-release")))
    freeze = base.normalize_freeze(docker(_in_image(image_id, IMAGE_VENV_PYTHON, "-m", "pip", "freeze", "--all", "--local")))
    version = docker(_in_image(image_id, "/usr/bin/python3", "--version")).split()[-1]
    return {"kind": "image-env", "image_id": image_id, "os": os_release, "python3": version, "apt": dict(sorted(installed.items())),
            "depends": {name: sorted(deps) for name, deps in sorted(graph.items()) if name in installed},
            "venv_freeze": freeze}


# --------------------------------------------------------------------------
# What the install tree needs
# --------------------------------------------------------------------------

def tree_dependency_keys(tree: Path) -> set[str]:
    keys: set[str] = set()
    for package_xml in sorted(tree.glob("*/share/*/package.xml")):
        keys |= base.package_xml_dependencies(package_xml.read_text())
    return keys


def tree_library_dirs(tree: Path) -> list[str]:
    return [str(path) for path in sorted(tree.glob("*/lib")) if path.is_dir()]


LDD_SCRIPT = ('find "$TREE" -type f \\( -name "*.so" -o -name "*.so.*" -o -perm /111 \\) | while read -r f; do '
              '[ "$(head -c4 "$f" 2>/dev/null | tail -c3)" = ELF ] && ldd "$f" 2>&1; done')
OWNER_SCRIPT = ('for p in "$@"; do o=$(dpkg -S "$p" 2>/dev/null | head -1); '
                '[ -z "$o" ] && o=$(dpkg -S "$(readlink -f "$p")" 2>/dev/null | head -1); '
                '[ -n "$o" ] && printf "%s: %s\\n" "${o%%: *}" "$p"; done')


def tree_library_owners(image_id: str, tree: Path, docker=run_docker) -> tuple[set[str], set[str], set[str]]:
    """(owner packages, library names not found, resolved paths nobody owns) from running ldd over the tree inside the image."""
    mount = ["--mount", f"type=bind,src={tree},dst={tree},readonly",
             "--env", f"TREE={tree}", "--env", "LD_LIBRARY_PATH=" + ":".join([*tree_library_dirs(tree), *ROS_LIBRARY_DIRS])]
    ldd = docker(_in_image(image_id, "sh", "-c", LDD_SCRIPT, extra=mount))
    outside, missing = parse_ldd(ldd, str(tree))
    owners_text = docker(_in_image(image_id, "sh", "-c", OWNER_SCRIPT, "sh", *sorted(outside)))
    owners = parse_dpkg_s(owners_text)
    return set(owners.values()), missing, {path for path in outside if path not in owners}


def required_packages(manifest: dict, tree: Path, docker=run_docker) -> dict:
    resolved, unresolved = resolve_keys(tree_dependency_keys(tree), manifest["apt"])
    graph = {name: set(deps) for name, deps in manifest["depends"].items()}
    owners, missing, unowned = tree_library_owners(manifest["image_id"], tree, docker)
    closure = dependency_closure(resolved | owners, graph, manifest["apt"])
    return {"required": closure, "unresolved_keys": unresolved, "missing_libraries": missing, "unowned_libraries": unowned}


# --------------------------------------------------------------------------
# Comparison and plan (pure)
# --------------------------------------------------------------------------

def compare(image: dict, host: dict, required: set[str], missing_libraries=frozenset()) -> list[dict]:
    rows: list[dict] = []
    row = base._row
    if image["os"]["codename"] != host["os"]["codename"]:
        rows.append(row(MUST, "os.codename", image["os"]["codename"], host["os"]["codename"], "differ"))
    if base.python_minor(image["python3"]) != base.python_minor(host["python3"]):
        rows.append(row(MUST, "python3.minor", base.python_minor(image["python3"]), base.python_minor(host["python3"]), "differ"))
    for name, version in image["apt"].items():
        have = host["apt"].get(name)
        if have is None:
            if name in required:
                rows.append(row(MUST, f"apt:{name}", version, None, "missing-on-host"))
        elif have != version:
            rows.append(row(MUST, f"apt:{name}", version, have, "newer" if base.compare_versions(have, version) > 0 else "older"))
    for name, version in host["apt"].items():
        if name not in image["apt"]:
            rows.append(row(SHOULD, f"apt:{name}", None, version, "host-only"))
    image_pins = dict(_pin(line) for line in image["venv_freeze"])
    host_pins = dict(_pin(line) for line in host["venv_freeze"])
    for name, version in image_pins.items():
        have = host_pins.get(name)
        if have is None:
            rows.append(row(MUST, f"venv:{name}", version, None, "missing-on-host"))
        elif have != version:
            rows.append(row(MUST, f"venv:{name}", version, have, "differ"))
    for name, version in host_pins.items():
        if name not in image_pins:
            rows.append(row(SHOULD, f"venv:{name}", None, version, "host-only"))
    for library in sorted(missing_libraries):
        rows.append(row(MUST, f"ldd:{library}", "found", None, "not-found-in-image"))
    return rows


must_failures = base.must_failures


def alignment_plan(image: dict, host: dict, required: set[str]) -> dict:
    """What bringing the host to the image would take. Installs and version changes only; nothing is removed."""
    install = {name: image["apt"][name] for name in sorted(required) if name in image["apt"] and name not in host["apt"]}
    change, downgrades = {}, []
    for name, version in image["apt"].items():
        have = host["apt"].get(name)
        if have is not None and have != version:
            change[name] = version
            if base.compare_versions(have, version) > 0:
                downgrades.append(name)
    return {"install": install, "change": change, "downgrades": sorted(downgrades)}


# --------------------------------------------------------------------------
# Host state and commands
# --------------------------------------------------------------------------

def collect_host(venv: Path) -> dict:
    apt = base.parse_dpkg_query(base.run(["dpkg-query", "-W", "-f", "${db:Status-Abbrev}\t${Package}\t${Version}\n"]).stdout)
    info = base.collect_venv(venv)
    if info is None:
        raise SystemExit(f"IMAGE_ENV_HOST_VENV_MISSING: {venv}")
    return {"apt": apt, "os": base.parse_os_release(Path("/etc/os-release").read_text()),
            "python3": base.run(["/usr/bin/python3", "--version"]).stdout.split()[-1], "venv_freeze": info["freeze"]}


def cmd_capture_image(args) -> int:
    manifest = capture_image(args.image)
    Path(args.output).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"captured {len(manifest['apt'])} packages and {len(manifest['venv_freeze'])} pip pins of {args.image} into {args.output}")
    return 0


def cmd_check_image(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text())
    tree = Path(args.tree).resolve()
    needs = required_packages(manifest, tree)
    host = collect_host(Path(args.host_venv))
    rows = compare(manifest, host, needs["required"], needs["missing_libraries"])
    if args.json:
        Path(args.json).write_text(json.dumps({"rows": rows, "unresolved_keys": sorted(needs["unresolved_keys"]),
                                               "unowned_libraries": sorted(needs["unowned_libraries"]),
                                               "required": sorted(needs["required"])}, indent=1) + "\n")
    if args.plan:
        Path(args.plan).write_text(json.dumps(alignment_plan(manifest, host, needs["required"]), indent=1) + "\n")
    print(base.format_table(rows, limit=args.limit))
    failures = must_failures(rows)
    print(f"RESULT: {'FAIL' if failures else 'PASS'} ({len(failures)} must-match difference(s); "
          f"{len(needs['required'])} required packages, {len(needs['unresolved_keys'])} unresolved keys)")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="image_env", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture-image")
    cap.add_argument("--image", required=True)
    cap.add_argument("--output", required=True)
    cap.set_defaults(func=cmd_capture_image)
    chk = sub.add_parser("check-image")
    chk.add_argument("--manifest", required=True)
    chk.add_argument("--tree", required=True, help="the host-built install tree that will be mounted")
    chk.add_argument("--host-venv", default="/data/work/venvs/so101-act-test")
    chk.add_argument("--json")
    chk.add_argument("--plan")
    chk.add_argument("--limit", type=int, default=40)
    chk.set_defaults(func=cmd_check_image)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

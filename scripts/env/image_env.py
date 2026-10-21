#!/usr/bin/env python3
"""image-env: compare a host with a container image that will run the host-built, mounted install tree (stdlib only).

Subcommands
-----------
capture-host   Read-only. Saves this host's apt packages, python version, codename and venv pins.
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
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import so101_env as base  # noqa: E402  (same directory)

MUST, SHOULD = base.MUST, base.SHOULD
ROS_PREFIX = base.ROS_PREFIX
IMAGE_VENV_PYTHON = "/act/venv/bin/python"
# colcon plug-ins that only the image venv carries: the host builds with /usr/bin/colcon and the runtime never imports them.
BUILD_ONLY_PINS = frozenset({"colcon-installed-package-information", "colcon-override-check"})
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

HOST_SPECIFIC_PACKAGES = frozenset({"libxnvctrl0"})     # NVIDIA driver userland: the version follows the host's driver
_ESM_SUFFIX = re.compile(r"[+~]esm\d+")


def narrow_exception(name: str, image_version: str, host_version: str) -> str | None:
    """Why this apt difference is only a warning, or None. Narrow: the same upstream version that differs only by an Ubuntu Pro ESM
    suffix, or a host-specific package. The caller applies it only to packages outside the tree's dependency closure."""
    if name in HOST_SPECIFIC_PACKAGES:
        return "host-specific"
    if (_ESM_SUFFIX.search(image_version) or _ESM_SUFFIX.search(host_version)) \
            and base._split_version(image_version)[1] == base._split_version(host_version)[1]:
        return "esm"
    return None


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
            relation = "newer" if base.compare_versions(have, version) > 0 else "older"
            exempt = name not in required and narrow_exception(name, version, have)
            rows.append(row(SHOULD if exempt else MUST, f"apt:{name}", version, have, f"{relation} ({exempt})" if exempt else relation))
    for name, version in host["apt"].items():
        if name not in image["apt"]:
            rows.append(row(SHOULD, f"apt:{name}", None, version, "host-only"))
    image_pins = dict(_pin(line) for line in image["venv_freeze"])
    host_pins = dict(_pin(line) for line in host["venv_freeze"])
    for name, version in image_pins.items():
        have = host_pins.get(name)
        if have is None:
            rows.append(row(SHOULD if name in BUILD_ONLY_PINS else MUST, f"venv:{name}", version, None, "missing-on-host"))
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


def load_host_state(path: Path) -> dict:
    state = json.loads(Path(path).read_text())
    if not all(key in state for key in ("apt", "os", "python3", "venv_freeze")) or "codename" not in state["os"]:
        raise SystemExit(f"IMAGE_ENV_HOST_STATE_INVALID: {path}")
    return state


def cmd_capture_host(args) -> int:
    state = collect_host(Path(args.host_venv))
    Path(args.output).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    print(f"captured {len(state['apt'])} packages and {len(state['venv_freeze'])} pip pins of this host into {args.output}")
    return 0


def cmd_capture_image(args) -> int:
    manifest = capture_image(args.image)
    Path(args.output).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"captured {len(manifest['apt'])} packages and {len(manifest['venv_freeze'])} pip pins of {args.image} into {args.output}")
    return 0


def preflight_record(*, manifest_bytes: bytes, manifest: dict, record_bytes: bytes, rows: list[dict], host: str) -> dict:
    """The record the campaign reads before a mount-mode start (`container_campaign.mount_build.preflight_problem`)."""
    failures = must_failures(rows)
    exceptions = {row["key"].partition(":")[2]: row["relation"].partition("(")[2].rstrip(")")
                  for row in rows if row["class"] == SHOULD and "(" in row["relation"]}
    return {"schema_version": 1, "kind": "MOUNT_PREFLIGHT", "result": "FAIL" if failures else "PASS",
            "commit": record_bytes.decode("ascii").strip(), "base_image_id": manifest["image_id"],
            "base_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "install_record_sha256": hashlib.sha256(record_bytes).hexdigest(), "must_failures": len(failures),
            "warnings": len([row for row in rows if row["class"] == SHOULD]), "exceptions": dict(sorted(exceptions.items())), "host": host}


def write_preflight(path: Path, *, manifest_path: Path, manifest: dict, tree: Path, rows: list[dict]) -> None:
    record = preflight_record(manifest_bytes=manifest_path.read_bytes(), manifest=manifest, record_bytes=(tree / "BUILD-COMMIT").read_bytes(),
                              rows=rows, host=socket.gethostname())
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    os.replace(temporary, path)
    print(f"preflight record {record['result']} written to {path}")


def cmd_check_image(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text())
    tree = Path(args.tree).resolve()
    needs = required_packages(manifest, tree)
    host = load_host_state(Path(args.host_state)) if args.host_state else collect_host(Path(args.host_venv))
    rows = compare(manifest, host, needs["required"], needs["missing_libraries"])
    if args.json:
        Path(args.json).write_text(json.dumps({"rows": rows, "unresolved_keys": sorted(needs["unresolved_keys"]),
                                               "unowned_libraries": sorted(needs["unowned_libraries"]),
                                               "required": sorted(needs["required"])}, indent=1) + "\n")
    if args.plan:
        Path(args.plan).write_text(json.dumps(alignment_plan(manifest, host, needs["required"]), indent=1) + "\n")
    print(base.format_table(rows, limit=args.limit))
    failures = must_failures(rows)
    if args.preflight:
        write_preflight(Path(args.preflight), manifest_path=Path(args.manifest), manifest=manifest, tree=tree, rows=rows)
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
    host_cmd = sub.add_parser("capture-host", help="save this host's packages, python and venv pins for a later check-image --host-state")
    host_cmd.add_argument("--output", required=True)
    host_cmd.add_argument("--host-venv", default="/data/work/venvs/so101-act-test")
    host_cmd.set_defaults(func=cmd_capture_host)
    chk = sub.add_parser("check-image")
    chk.add_argument("--manifest", required=True)
    chk.add_argument("--tree", required=True, help="the host-built install tree that will be mounted")
    chk.add_argument("--host-venv", default="/data/work/venvs/so101-act-test")
    chk.add_argument("--host-state", help="host state saved by capture-host (compare another host, or a deliberately skewed copy)")
    chk.add_argument("--json")
    chk.add_argument("--plan")
    chk.add_argument("--preflight", help="write the record a mount-mode campaign start requires (host/base-image check result)")
    chk.add_argument("--limit", type=int, default=40)
    chk.set_defaults(func=cmd_check_image)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

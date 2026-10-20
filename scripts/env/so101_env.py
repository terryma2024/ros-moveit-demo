#!/usr/bin/env python3
"""so101-env: capture, check and apply a host environment manifest (stdlib only).

Subcommands
-----------
capture  Read-only. Writes env-manifest.json for this host (the reference).
         Optionally exports a wheel cache (--export-wheels) and a so101-tools
         tarball (--export-tools).
check    Compares this host with a manifest, prints a diff table, exits 1 on
         any "must match" difference.
apply    Makes this host match a manifest (apt versions, venvs, so101-tools),
         then holds the packages and runs check. Needs sudo for apt.
lock     Holds every manifest apt package that is installed at the manifest
         version (used on the reference host).

See scripts/env/README.md for the scope of what is covered.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import itertools
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET

SCHEMA = 1
MUST, SHOULD, HOST = "must", "should", "host"
DEFAULT_WORK_ROOT = "/data/work"
ROS_DISTRO = "jazzy"
ROS_PREFIX = "ros-jazzy-"
# Non-ROS apt packages the repo needs, taken from the docs and Dockerfiles.
# Only the ones that are installed on the reference are recorded.
EXTRA_APT = (
    "build-essential", "cmake", "ccache", "rsync", "curl", "tmux",
    "ca-certificates", "tar", "python3", "python3-pip", "python3-venv",
    "python3-dev", "python3-colcon-common-extensions", "python3-rosdep",
    "libegl1", "libegl-mesa0", "libx11-6", "x11-utils", "python3-gz-transport13",
    "python3-gz-msgs10", "gz-harmonic", "docker.io", "nvidia-container-toolkit",
)
# Packages from packages.osrfoundation.org (Gazebo Harmonic), matched by prefix.
OSRF_PREFIXES = ("gz-", "libgz-", "python3-gz-", "libsdformat", "sdformat")
# GL/EGL userland the MuJoCo camera plugin and mujoco.Renderer load (Mesa and
# glvnd). The NVIDIA userland (libnvidia-gl-*, nvidia-driver-*) is tied to the
# kernel module and the driver version, so it is reported, not applied.
GL_APT_PREFIXES = ("libegl", "libgl1", "libglvnd", "libgles", "libgbm", "libosmesa")
GLVND_VENDOR_DIR = "/usr/share/glvnd/egl_vendor.d"
GL_PROBE_VENV = "so101-act-test"
GL_PROBE_SCRIPT = (
    "import os, mujoco\n"
    "xml = \"<mujoco><worldbody><light pos='0 0 3'/><geom type='sphere' size='.2'/>"
    "<camera name='c' pos='0 -1 .5' xyaxes='1 0 0 0 .5 1'/></worldbody></mujoco>\"\n"
    "m = mujoco.MjModel.from_xml_string(xml); d = mujoco.MjData(m); mujoco.mj_forward(m, d)\n"
    "r = mujoco.Renderer(m, 64, 64); r.update_scene(d, 'c'); img = r.render()\n"
    "print('GLPROBE_OK', img.shape, int(img.max()), flush=True)\n"
    "os._exit(0 if img.max() > 0 else 3)\n"
)
TOOLS_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}
SNAPSHOT_LIST = "/etc/apt/sources.list.d/so101-ros-snapshot.list"
ROS_KEYRING = "/usr/share/keyrings/ros-archive-keyring.gpg"
DEP_TAGS = (
    "depend", "build_depend", "build_export_depend", "exec_depend",
    "test_depend", "buildtool_depend", "buildtool_export_depend", "doc_depend",
)


# --------------------------------------------------------------------------
# Debian version comparison
# --------------------------------------------------------------------------

def _split_version(version: str) -> tuple[int, str, str]:
    epoch = 0
    if ":" in version:
        head, version = version.split(":", 1)
        epoch = int(head)
    revision = ""
    if "-" in version:
        version, revision = version.rsplit("-", 1)
    return epoch, version, revision


def _char_order(char: str) -> int:
    if char == "":
        return 0
    if char == "~":
        return -1
    if char.isalpha():
        return ord(char)
    return ord(char) + 256


def _compare_fragment(a: str, b: str) -> int:
    while a or b:
        lead_a = re.match(r"\D*", a).group()
        lead_b = re.match(r"\D*", b).group()
        for x, y in itertools.zip_longest(lead_a, lead_b, fillvalue=""):
            diff = _char_order(x) - _char_order(y)
            if diff:
                return -1 if diff < 0 else 1
        a, b = a[len(lead_a):], b[len(lead_b):]
        digits_a = re.match(r"\d*", a).group()
        digits_b = re.match(r"\d*", b).group()
        num_a, num_b = int(digits_a or 0), int(digits_b or 0)
        if num_a != num_b:
            return -1 if num_a < num_b else 1
        a, b = a[len(digits_a):], b[len(digits_b):]
    return 0


def compare_versions(a: str, b: str) -> int:
    """Return -1, 0 or 1 like `dpkg --compare-versions` (epochs, ~, build dates)."""
    epoch_a, up_a, rev_a = _split_version(a)
    epoch_b, up_b, rev_b = _split_version(b)
    if epoch_a != epoch_b:
        return -1 if epoch_a < epoch_b else 1
    return _compare_fragment(up_a, up_b) or _compare_fragment(rev_a, rev_b)


# --------------------------------------------------------------------------
# Parsers (pure)
# --------------------------------------------------------------------------

def parse_dpkg_query(text: str) -> dict[str, str]:
    """Parse `dpkg-query -W -f='${db:Status-Abbrev}\\t${Package}\\t${Version}\\n'`."""
    packages: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        status, name, version = (p.strip() for p in parts)
        if status[:2] in ("ii", "hi"):
            packages[name.split(":")[0]] = version
    return packages


def parse_os_release(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            out[key] = value.strip().strip('"')
    return {
        "id": out.get("ID", ""),
        "version_id": out.get("VERSION_ID", ""),
        "codename": out.get("VERSION_CODENAME", ""),
        "pretty": out.get("PRETTY_NAME", ""),
    }


def parse_nvidia_smi(text: str) -> dict[str, str]:
    first = text.strip().splitlines()[0] if text.strip() else ""
    parts = [p.strip() for p in first.split(",")]
    if len(parts) < 3:
        return {"driver": "", "gpu_model": "", "gpu_uuid": ""}
    return {"driver": parts[0], "gpu_model": parts[1], "gpu_uuid": parts[2]}


def parse_pyvenv_cfg(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def normalize_freeze(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines()]
    return sorted(ln for ln in lines if ln and not ln.startswith("#"))


def freeze_sha(lines: list[str]) -> str:
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def python_minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def package_xml_dependencies(text: str) -> set[str]:
    root = ET.fromstring(text)
    keys: set[str] = set()
    for tag in DEP_TAGS:
        for node in root.findall(tag):
            if node.text and node.text.strip():
                keys.add(node.text.strip())
    return keys


def select_apt_scope(installed: dict[str, str], resolved: set[str]) -> dict[str, str]:
    """Pick the apt packages the manifest covers (see README)."""
    chosen: dict[str, str] = {}
    for name, version in installed.items():
        if (
            name.startswith(ROS_PREFIX)
            or name in resolved
            or name in EXTRA_APT
            or name.startswith(OSRF_PREFIXES)
            or name.startswith(GL_APT_PREFIXES)
        ):
            chosen[name] = version
    return dict(sorted(chosen.items()))


# --------------------------------------------------------------------------
# Diff / check (pure)
# --------------------------------------------------------------------------

def _row(cls, key, expected, actual, relation):
    return {
        "class": cls, "key": key, "expected": expected,
        "actual": actual, "relation": relation,
    }


def _scalar(rows, cls, key, expected, actual):
    if expected != actual:
        rows.append(_row(cls, key, expected, actual, "differ"))


def diff_manifests(expected: dict, actual: dict) -> list[dict]:
    """Differences between the reference manifest and this host's state."""
    rows: list[dict] = []
    e_os, a_os = expected["os"], actual["os"]
    _scalar(rows, MUST, "os.codename", e_os["codename"], a_os["codename"])
    _scalar(rows, SHOULD, "os.version_id", e_os["version_id"], a_os["version_id"])
    _scalar(rows, MUST, "python3.minor",
            python_minor(expected["python3"]), python_minor(actual["python3"]))
    _scalar(rows, SHOULD, "python3.version", expected["python3"], actual["python3"])
    _scalar(rows, SHOULD, "nvidia.driver",
            expected["nvidia"]["driver"], actual["nvidia"]["driver"])
    _scalar(rows, SHOULD, "docker.version",
            expected["docker"]["version"], actual["docker"]["version"])
    _scalar(rows, HOST, "kernel", expected["kernel"], actual["kernel"])
    _scalar(rows, HOST, "gpu.model",
            expected["nvidia"]["gpu_model"], actual["nvidia"]["gpu_model"])
    _scalar(rows, HOST, "gpu.uuid",
            expected["nvidia"]["gpu_uuid"], actual["nvidia"]["gpu_uuid"])
    _scalar(rows, HOST, "cpu", expected["host"]["cpu"], actual["host"]["cpu"])
    _scalar(rows, HOST, "memory_kb",
            expected["host"]["memory_kb"], actual["host"]["memory_kb"])
    _scalar(rows, HOST, "apt_sources.sha256",
            expected["apt_sources_sha256"], actual["apt_sources_sha256"])

    e_gl, a_gl = expected.get("gl"), actual.get("gl")
    if e_gl is not None and a_gl is not None:
        for name, digest in e_gl["egl_vendor_files"].items():
            have = a_gl["egl_vendor_files"].get(name)
            if have is None:
                rows.append(_row(MUST, f"glvnd:{name}", digest, None, "missing"))
            elif have != digest:
                rows.append(_row(SHOULD, f"glvnd:{name}", digest, have, "differ"))
        for name, version in e_gl["nvidia_userland"].items():
            have = a_gl["nvidia_userland"].get(name)
            if have != version:
                rows.append(_row(SHOULD, f"nvidia-userland:{name}", version, have, "differ"))

    for name, version in expected["apt"].items():
        have = actual["apt"].get(name)
        if have is None:
            rows.append(_row(MUST, f"apt:{name}", version, None, "missing"))
        elif have != version:
            relation = "newer" if compare_versions(have, version) > 0 else "older"
            rows.append(_row(MUST, f"apt:{name}", version, have, relation))
    for name, version in actual["apt"].items():
        if name.startswith(ROS_PREFIX) and name not in expected["apt"]:
            rows.append(_row(SHOULD, f"apt:{name}", None, version, "extra"))

    for name, venv in expected["venvs"].items():
        have = actual["venvs"].get(name)
        if have is None:
            rows.append(_row(MUST, f"venv:{name}", venv["freeze_sha256"], None, "missing"))
            continue
        _scalar(rows, MUST, f"venv:{name}.python_minor",
                python_minor(venv["python_version"]),
                python_minor(have["python_version"]))
        _scalar(rows, MUST, f"venv:{name}.system_site",
                venv["system_site_packages"], have["system_site_packages"])
        if venv["freeze_sha256"] != have["freeze_sha256"]:
            rows.append(_row(MUST, f"venv:{name}.freeze_sha256",
                             venv["freeze_sha256"], have["freeze_sha256"], "differ"))
            e_set, a_set = set(venv["freeze"]), set(have["freeze"])
            for line in sorted(e_set - a_set):
                rows.append(_row(MUST, f"venv:{name}.pkg", line, None, "missing"))
            for line in sorted(a_set - e_set):
                rows.append(_row(MUST, f"venv:{name}.pkg", None, line, "extra"))
        _scalar(rows, SHOULD, f"venv:{name}.torch",
                venv.get("torch"), have.get("torch"))
    for name in actual["venvs"]:
        if name not in expected["venvs"]:
            rows.append(_row(SHOULD, f"venv:{name}", None, "present", "extra"))

    e_tools, a_tools = expected["tools"], actual["tools"]
    for rel, digest in e_tools.items():
        if rel not in a_tools:
            rows.append(_row(MUST, f"tools:{rel}", digest, None, "missing"))
        elif a_tools[rel] != digest:
            rows.append(_row(MUST, f"tools:{rel}", digest, a_tools[rel], "differ"))
    for rel in a_tools:
        if rel not in e_tools:
            rows.append(_row(MUST, f"tools:{rel}", None, a_tools[rel], "extra"))
    return rows


def must_failures(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["class"] == MUST]


def format_table(rows: list[dict], limit: int = 40) -> str:
    out: list[str] = []
    for cls, title in (
        (MUST, "MUST MATCH"), (SHOULD, "SHOULD MATCH (warnings)"),
        (HOST, "HOST-SPECIFIC (reported only)"),
    ):
        subset = [r for r in rows if r["class"] == cls]
        out.append(f"== {title}: {len(subset)} difference(s)")
        for row in subset[:limit]:
            out.append(
                f"  {row['relation']:<7} {row['key']}  expected={_short(row['expected'])}"
                f"  actual={_short(row['actual'])}"
            )
        if len(subset) > limit:
            out.append(f"  ... {len(subset) - limit} more (see --json)")
    return "\n".join(out)


def _short(value) -> str:
    text = "-" if value is None else str(value)
    return text if len(text) <= 60 else text[:57] + "..."


# --------------------------------------------------------------------------
# Apply planning (pure)
# --------------------------------------------------------------------------

class ApplyRefused(Exception):
    """The manifest cannot be applied to this host."""


def snapshot_source_line(date: str, codename: str) -> str:
    return (
        f"deb [arch=amd64 signed-by={ROS_KEYRING}] "
        f"http://snapshots.ros.org/{ROS_DISTRO}/{date}/ubuntu {codename} main"
    )


def plan_apply(
    manifest: dict,
    state: dict,
    available: dict[str, list[str]] | None = None,
    snapshot_date: str | None = None,
    work_root: str = DEFAULT_WORK_ROOT,
    stamp: str = "STAMP",
) -> list[dict]:
    """Ordered actions that make `state` match `manifest`. No side effects.

    `available` maps package -> versions the configured sources can supply. When
    a wanted version is missing and no snapshot date is given, planning stops.
    """
    if manifest["os"]["codename"] != state["os"]["codename"]:
        raise ApplyRefused(
            f"LTS codename differs: manifest {manifest['os']['codename']!r}, "
            f"host {state['os']['codename']!r}"
        )
    if python_minor(manifest["python3"]) != python_minor(state["python3"]):
        raise ApplyRefused("python3 minor version differs")
    actions: list[dict] = []
    todo = {
        name: version for name, version in manifest["apt"].items()
        if state["apt"].get(name) != version
    }
    if todo:
        missing = sorted(
            n for n, v in todo.items()
            if available is not None and v not in available.get(n, [])
        )
        if missing and not snapshot_date:
            raise ApplyRefused(
                f"{len(missing)} apt version(s) are not available from the configured "
                f"sources (first: {missing[0]}={todo[missing[0]]}); "
                "rerun with --snapshot-date to add a ROS snapshot source"
            )
        if snapshot_date:
            actions.append({
                "kind": "add_snapshot_source", "date": snapshot_date,
                "line": snapshot_source_line(snapshot_date, manifest["os"]["codename"]),
            })
            actions.append({"kind": "apt_update"})
        specs = [f"{n}={v}" for n, v in sorted(todo.items())]
        actions.append({"kind": "apt_simulate", "specs": specs})
        actions.append({"kind": "apt_install", "specs": specs})
    actions.append({"kind": "apt_hold", "packages": sorted(manifest["apt"])})

    root = Path(work_root)
    for name, venv in manifest["venvs"].items():
        have = state["venvs"].get(name)
        if have and have["freeze_sha256"] == venv["freeze_sha256"]:
            continue
        path = str(root / "venvs" / name)
        actions.append({
            "kind": "venv_rebuild", "name": name, "path": path,
            "move_aside_to": f"{path}.pre-align-{stamp}" if have else None,
            "system_site_packages": venv["system_site_packages"],
            "freeze": venv["freeze"],
        })
    if manifest["tools"] != state["tools"]:
        actions.append({
            "kind": "tools_replace", "path": str(root / "so101-tools"),
            "move_aside_to": f"{root}/so101-tools.pre-align-{stamp}"
            if state["tools"] else None,
        })
    actions.append({"kind": "check"})
    return actions


def removals_in_simulation(output: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^Remv (\S+)", output, re.M)]


def wheel_extra_indexes(freeze: list[str]) -> list[str]:
    """Extra index URLs for local-version pins such as torch==2.11.0+cu128."""
    urls: list[str] = []
    for line in freeze:
        local = re.search(r"\+(cu\d+|cpu|rocm[\d.]+)$", line)
        if local:
            url = f"https://download.pytorch.org/whl/{local.group(1)}"
            if url not in urls:
                urls.append(url)
    return urls


# --------------------------------------------------------------------------
# Host access (side effects)
# --------------------------------------------------------------------------

class Log:
    def __init__(self, path: Path | None):
        self.path = path
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, **fields):
        fields["ts"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        line = json.dumps(fields, sort_keys=True)
        print(line, file=sys.stderr)
        if self.path:
            with self.path.open("a") as handle:
                handle.write(line + "\n")


def run(cmd: list[str], check=True, timeout=None, input_text=None, env=None):
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, input=input_text, env=env
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"{shlex.join(cmd)} -> rc={result.returncode}\n{result.stderr[-2000:]}"
        )
    return result


def sudo(cmd: list[str]) -> list[str]:
    return cmd if os.geteuid() == 0 else ["sudo", "-n", *cmd]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_tools(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    if not root.is_dir():
        return hashes
    for current, dirs, files in os.walk(root):
        keep_dirs = []
        for name in sorted(dirs):
            full = Path(current) / name
            if name in TOOLS_EXCLUDE_DIRS:
                continue
            if full.is_symlink():
                hashes[str(full.relative_to(root))] = "symlink:" + os.readlink(full)
            else:
                keep_dirs.append(name)
        dirs[:] = keep_dirs
        for name in sorted(files):
            full = Path(current) / name
            rel = str(full.relative_to(root))
            if name.endswith(".pyc"):
                continue
            if full.is_symlink():
                hashes[rel] = "symlink:" + os.readlink(full)
            elif full.is_file():
                hashes[rel] = sha256_file(full)
    return dict(sorted(hashes.items()))


def collect_venv(path: Path) -> dict | None:
    python = path / "bin" / "python"
    if not python.exists() or not (path / "pyvenv.cfg").exists():
        return None
    cfg = parse_pyvenv_cfg((path / "pyvenv.cfg").read_text())
    version = cfg.get("version") or cfg.get("version_info", "")
    freeze_out = run(
        ["/usr/bin/python3", "-m", "pip", "--python", str(python),
         "freeze", "--all", "--local"]
    ).stdout
    lines = normalize_freeze(freeze_out)
    probe = run(
        [str(python), "-c",
         "import torch;print(torch.__version__, torch.version.cuda)"],
        check=False, timeout=180,
    )
    return {
        "path": str(path),
        "interpreter": os.path.realpath(python),
        "python_version": version,
        "system_site_packages": cfg.get("include-system-site-packages", "false") == "true",
        "created_with_uv": "uv" in cfg,
        "freeze": lines,
        "freeze_sha256": freeze_sha(lines),
        "torch": probe.stdout.strip() if probe.returncode == 0 else None,
    }


def resolve_rosdep_keys(keys: set[str]) -> tuple[set[str], list[str]]:
    resolved: set[str] = set()
    unresolved: list[str] = []
    if shutil.which("rosdep") is None:
        return resolved, sorted(keys)
    for key in sorted(keys):
        try:
            res = run(
                ["rosdep", "resolve", key, "--rosdistro", ROS_DISTRO,
                 "--os", "ubuntu:noble"], check=False, timeout=20,
            )
        except subprocess.TimeoutExpired:
            unresolved.append(key)
            continue
        names = [ln.strip() for ln in res.stdout.splitlines()
                 if ln.strip() and not ln.startswith("#")]
        if res.returncode == 0 and names:
            for line in names:
                resolved.update(line.split())
        else:
            unresolved.append(key)
    return resolved, unresolved


def repo_dependency_keys(repo: Path) -> set[str]:
    xmls = sorted((repo / "src").glob("*/package.xml"))
    own = {ET.fromstring(p.read_text()).findtext("name") for p in xmls}
    keys: set[str] = set()
    for path in xmls:
        keys |= package_xml_dependencies(path.read_text())
    return {k for k in keys if k not in own}


def collect_gl(installed: dict[str, str]) -> dict:
    """glvnd EGL vendor files (sha256) and the NVIDIA GL userland versions."""
    vendors: dict[str, str] = {}
    vendor_dir = Path(GLVND_VENDOR_DIR)
    if vendor_dir.is_dir():
        for path in sorted(vendor_dir.glob("*.json")):
            vendors[path.name] = sha256_file(path)
    nvidia_pkgs = {
        n: v for n, v in installed.items()
        if n.startswith(("libnvidia-gl-", "libnvidia-egl", "nvidia-driver-"))
    }
    return {"egl_vendor_files": vendors, "nvidia_userland": dict(sorted(nvidia_pkgs.items())),
            "mujoco_gl": "egl"}


def gl_probe(work_root: Path) -> tuple[bool, str]:
    """Headless MuJoCo EGL render with the gate's venv python and MUJOCO_GL=egl."""
    python = work_root / "venvs" / GL_PROBE_VENV / "bin" / "python"
    if not python.exists():
        return False, f"missing {python}"
    env = {k: v for k, v in os.environ.items() if k not in ("DISPLAY", "PYOPENGL_PLATFORM")}
    env["MUJOCO_GL"] = "egl"
    result = run([str(python), "-I", "-c", GL_PROBE_SCRIPT], check=False, timeout=120, env=env)
    ok = result.returncode == 0 and "GLPROBE_OK" in result.stdout
    detail = (result.stdout.strip().splitlines() or [""])[-1] if ok else (
        (result.stderr or result.stdout).strip().splitlines()[-1:] or [f"rc={result.returncode}"])[0]
    return ok, detail


def collect_state(
    repo: Path,
    work_root: Path,
    with_scope: bool = True,
    wanted: set[str] | None = None,
) -> dict:
    """Snapshot this host. `wanted` adds installed packages named by a manifest."""
    os_release = parse_os_release(Path("/etc/os-release").read_text())
    installed = parse_dpkg_query(run([
        "dpkg-query", "-W", "-f", "${db:Status-Abbrev}\t${Package}\t${Version}\n"
    ]).stdout)
    resolved: set[str] = set()
    unresolved: list[str] = []
    if with_scope:
        resolved, unresolved = resolve_rosdep_keys(repo_dependency_keys(repo))
    nvidia = run(
        ["nvidia-smi", "--query-gpu=driver_version,name,uuid", "--format=csv,noheader"],
        check=False,
    )
    docker = run(["docker", "--version"], check=False)
    docker_match = re.search(r"version ([^,\s]+)", docker.stdout)
    sources: dict[str, str] = {}
    for path in sorted(Path("/etc/apt/sources.list.d").glob("*")):
        if path.is_file() and path.suffix in (".list", ".sources"):
            sources[path.name] = path.read_text()
    main_list = Path("/etc/apt/sources.list")
    if main_list.is_file():
        sources["sources.list"] = main_list.read_text()
    cpu = ""
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            cpu = line.split(":", 1)[1].strip()
            break
    mem = re.search(r"MemTotal:\s+(\d+)", Path("/proc/meminfo").read_text())
    venvs: dict[str, dict] = {}
    venv_root = work_root / "venvs"
    if venv_root.is_dir():
        for path in sorted(venv_root.iterdir()):
            if ".pre-align-" in path.name:
                continue
            info = collect_venv(path)
            if info:
                venvs[path.name] = info
    return {
        "schema": SCHEMA,
        "created": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "host": {
            "hostname": platform.node(), "cpu": cpu,
            "memory_kb": int(mem.group(1)) if mem else 0,
        },
        "os": os_release,
        "kernel": platform.release(),
        "nvidia": parse_nvidia_smi(nvidia.stdout) if nvidia.returncode == 0
        else {"driver": "", "gpu_model": "", "gpu_uuid": ""},
        "apt_sources": sources,
        "apt_sources_sha256": hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode()).hexdigest(),
        "ros_snapshot": None,
        "apt": select_apt_scope(installed, resolved | (wanted or set())),
        "apt_scope": {
            "rosdep_keys_unresolved": unresolved,
            "extra_apt": list(EXTRA_APT),
            "osrf_prefixes": list(OSRF_PREFIXES),
        },
        "gl": collect_gl(installed),
        "python3": run(["/usr/bin/python3", "--version"]).stdout.split()[-1],
        "venvs": venvs,
        "tools": collect_tools(work_root / "so101-tools"),
        "docker": {"version": docker_match.group(1) if docker_match else ""},
    }


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------

def export_wheels(manifest: dict, out_dir: Path, log: Log) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, venv in manifest["venvs"].items():
        target = out_dir / name
        target.mkdir(exist_ok=True)
        freeze = target / "requirements.txt"
        freeze.write_text("\n".join(venv["freeze"]) + "\n")
        cmd = ["/usr/bin/python3", "-m", "pip", "wheel", "--no-deps",
               "-r", str(freeze), "-w", str(target)]
        for url in wheel_extra_indexes(venv["freeze"]):
            cmd += ["--extra-index-url", url]
        log.event(action="pip_wheel", venv=name, cmd=shlex.join(cmd))
        run(cmd, timeout=7200)
        sums = {w.name: sha256_file(w) for w in sorted(target.glob("*.whl"))}
        (target / "SHA256SUMS.json").write_text(json.dumps(sums, indent=1))
        log.event(action="wheels_done", venv=name, wheels=len(sums))


def export_tools(work_root: Path, tar_path: Path, log: Log) -> None:
    def keep(info: tarfile.TarInfo):
        parts = Path(info.name).parts
        if any(p in TOOLS_EXCLUDE_DIRS for p in parts) or info.name.endswith(".pyc"):
            return None
        return info

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(work_root / "so101-tools", arcname="so101-tools", filter=keep)
    log.event(action="tools_tar", path=str(tar_path), sha256=sha256_file(tar_path))


def cmd_capture(args) -> int:
    log = Log(Path(args.log) if args.log else None)
    state = collect_state(Path(args.repo), Path(args.work_root),
                          with_scope=not args.no_rosdep)
    if args.snapshot_date:
        state["ros_snapshot"] = {"date": args.snapshot_date}
    ok, detail = gl_probe(Path(args.work_root))
    state["gl"]["probe"] = {"ok": ok, "detail": detail}
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=1, sort_keys=True) + "\n")
    log.event(action="capture", output=str(out), apt=len(state["apt"]),
              venvs=sorted(state["venvs"]), tools=len(state["tools"]))
    if args.export_wheels:
        export_wheels(state, Path(args.export_wheels), log)
    if args.export_tools:
        export_tools(Path(args.work_root), Path(args.export_tools), log)
    return 0


def cmd_check(args) -> int:
    manifest = json.loads(Path(args.manifest).read_text())
    state = collect_state(Path(args.repo), Path(args.work_root), with_scope=False,
                          wanted=set(manifest["apt"]))
    rows = diff_manifests(manifest, state)
    if not getattr(args, "no_gl_probe", False):
        ok, detail = gl_probe(Path(args.work_root))
        if not ok:
            rows.append(_row(MUST, "gl.probe", "headless MuJoCo EGL render ok", detail, "failed"))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=1) + "\n")
    print(format_table(rows, limit=args.limit))
    failures = must_failures(rows)
    print(f"RESULT: {'FAIL' if failures else 'PASS'} "
          f"({len(failures)} must-match difference(s))")
    return 1 if failures else 0


def available_versions(names: list[str]) -> dict[str, list[str]]:
    avail: dict[str, list[str]] = {}
    for start in range(0, len(names), 200):
        res = run(["apt-cache", "madison", *names[start:start + 200]], check=False)
        for line in res.stdout.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                avail.setdefault(parts[0], []).append(parts[1])
    return avail


def _verify_wheels(wheel_dir: Path) -> None:
    sums = json.loads((wheel_dir / "SHA256SUMS.json").read_text())
    for name, digest in sums.items():
        if sha256_file(wheel_dir / name) != digest:
            raise RuntimeError(f"wheel checksum mismatch: {name}")


def cmd_apply(args) -> int:
    log = Log(Path(args.log) if args.log else None)
    manifest = json.loads(Path(args.manifest).read_text())
    work_root = Path(args.work_root)
    state = collect_state(Path(args.repo), work_root, with_scope=False,
                          wanted=set(manifest["apt"]))
    stamp = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    snapshot = args.snapshot_date or (manifest.get("ros_snapshot") or {}).get("date")
    todo = [n for n, v in manifest["apt"].items() if state["apt"].get(n) != v]
    available = available_versions(todo) if todo and not snapshot else None
    try:
        plan = plan_apply(manifest, state, available, snapshot, args.work_root, stamp)
    except ApplyRefused as exc:
        log.event(action="refused", reason=str(exc))
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    for action in plan:
        log.event(
            action="plan", kind=action["kind"],
            detail={k: v for k, v in action.items()
                    if k not in ("freeze", "specs", "packages", "kind")},
            count=len(action.get("specs", action.get("packages", []))))
    if args.dry_run:
        return 0

    for action in plan:
        kind = action["kind"]
        log.event(action="begin", kind=kind)
        if kind == "add_snapshot_source":
            run(sudo(["tee", SNAPSHOT_LIST]), input_text=action["line"] + "\n")
        elif kind == "apt_update":
            run(sudo(["apt-get", "update"]), timeout=1800)
            wanted = {n: v for n, v in manifest["apt"].items()
                      if state["apt"].get(n) != v}
            avail = available_versions(list(wanted))
            gone = sorted(n for n, v in wanted.items() if v not in avail.get(n, []))
            if gone:
                log.event(action="blocked", count=len(gone),
                          missing=[f"{n}={wanted[n]}" for n in gone[:20]])
                print(f"BLOCKED: {len(gone)} version(s) unavailable even with the "
                      "snapshot", file=sys.stderr)
                return 3
        elif kind == "apt_simulate":
            res = run(sudo(["apt-get", "-s", "install", "--allow-downgrades",
                            "--no-install-recommends", *action["specs"]]), check=False)
            log.event(action="simulate", rc=res.returncode,
                      tail=res.stdout[-600:] + res.stderr[-600:])
            if res.returncode != 0:
                print(res.stderr[-2000:], file=sys.stderr)
                return 3
            removed = removals_in_simulation(res.stdout)
            if removed and not args.allow_remove:
                log.event(action="blocked", reason="apt would remove packages",
                          removed=removed)
                print(f"BLOCKED: apt would remove {len(removed)} package(s): "
                      f"{' '.join(removed[:15])} (use --allow-remove)", file=sys.stderr)
                return 3
        elif kind == "apt_install":
            run(sudo(["apt-mark", "unhold", *[s.split("=")[0] for s in action["specs"]]]),
                check=False)
            res = run(sudo(["env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install",
                            "-y", "--allow-downgrades", "--allow-change-held-packages",
                            "--no-install-recommends", *action["specs"]]), timeout=7200)
            log.event(action="installed", rc=res.returncode, tail=res.stdout[-400:])
        elif kind == "apt_hold":
            run(sudo(["apt-mark", "hold", *action["packages"]]))
        elif kind == "venv_rebuild":
            wheels = Path(args.wheels) / action["name"]
            _verify_wheels(wheels)
            path = Path(action["path"])
            if action["move_aside_to"]:
                path.rename(action["move_aside_to"])
                log.event(action="moved_aside", src=str(path),
                          dst=action["move_aside_to"])
            venv_cmd = ["/usr/bin/python3", "-m", "venv", "--without-pip"]
            if action["system_site_packages"]:
                venv_cmd.append("--system-site-packages")
            run([*venv_cmd, str(path)])
            run(["/usr/bin/python3", "-m", "pip", "--python", str(path / "bin/python"),
                 "install", "--no-deps", "--no-index", "--find-links", str(wheels),
                 "-r", str(wheels / "requirements.txt")], timeout=7200)
        elif kind == "tools_replace":
            dest = Path(action["path"])
            if action["move_aside_to"]:
                dest.rename(action["move_aside_to"])
                log.event(action="moved_aside", src=str(dest),
                          dst=action["move_aside_to"])
            with tarfile.open(args.tools_tar) as tar:
                tar.extractall(dest.parent, filter="tar")
        elif kind == "check":
            rc = cmd_check(argparse.Namespace(
                manifest=args.manifest, repo=args.repo, work_root=args.work_root,
                json=str(Path(args.log).with_suffix(".check.json")) if args.log else None,
                limit=40))
            log.event(action="final_check", rc=rc)
            return rc
        log.event(action="end", kind=kind)
    return 0


def cmd_lock(args) -> int:
    log = Log(Path(args.log) if args.log else None)
    manifest = json.loads(Path(args.manifest).read_text())
    state = collect_state(Path(args.repo), Path(args.work_root), with_scope=False,
                          wanted=set(manifest["apt"]))
    wrong = [n for n, v in manifest["apt"].items() if state["apt"].get(n) != v]
    if wrong:
        print(f"REFUSED: {len(wrong)} package(s) differ from the manifest; not holding",
              file=sys.stderr)
        return 2
    run(sudo(["apt-mark", "hold", *manifest["apt"]]))
    log.event(action="hold", packages=len(manifest["apt"]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    repo_default = str(Path(__file__).resolve().parents[2])
    parser = argparse.ArgumentParser(prog="so101_env", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--repo", default=repo_default)
        p.add_argument("--work-root", default=DEFAULT_WORK_ROOT)
        p.add_argument("--log", help="JSONL action log (evidence root)")

    cap = sub.add_parser("capture")
    common(cap)
    cap.add_argument("--output", default="env-manifest.json")
    cap.add_argument("--snapshot-date",
                     help="record the ROS snapshot date these versions come from")
    cap.add_argument("--no-rosdep", action="store_true",
                     help="skip rosdep key resolution (non-reference hosts)")
    cap.add_argument("--export-wheels", metavar="DIR")
    cap.add_argument("--export-tools", metavar="TAR")
    cap.set_defaults(func=cmd_capture)

    chk = sub.add_parser("check")
    common(chk)
    chk.add_argument("--manifest", required=True)
    chk.add_argument("--no-gl-probe", action="store_true",
                     help="skip the headless MuJoCo EGL render probe")
    chk.add_argument("--json", help="write all difference rows here")
    chk.add_argument("--limit", type=int, default=40)
    chk.set_defaults(func=cmd_check)

    app = sub.add_parser("apply")
    common(app)
    app.add_argument("--manifest", required=True)
    app.add_argument("--wheels", help="wheel cache dir from capture --export-wheels")
    app.add_argument("--tools-tar", help="tarball from capture --export-tools")
    app.add_argument("--snapshot-date",
                     help="ROS snapshot date (YYYY-MM-DD) to add if versions are missing")
    app.add_argument("--allow-remove", action="store_true",
                     help="let apt remove packages that conflict with the manifest")
    app.add_argument("--dry-run", action="store_true")
    app.set_defaults(func=cmd_apply)

    lock = sub.add_parser("lock")
    common(lock)
    lock.add_argument("--manifest", required=True)
    lock.set_defaults(func=cmd_lock)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

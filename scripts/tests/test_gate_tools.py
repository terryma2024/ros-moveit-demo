"""Fixture-only checks of the repository tools: scripts/gate, scripts/evidence, scripts/images, scripts/run_tools.

Nothing here reads a host path, runs a gate, or needs ROS: the scripts are parsed, the host env files are read, and the small
helpers run against fixture files and a throw-away git repository under tmp_path.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
GATE = SCRIPTS / "gate"
TOOL_DIRS = [GATE, SCRIPTS / "evidence", SCRIPTS / "images", SCRIPTS / "run_tools"]
HOSTS = GATE / "hosts"

REQUIRED_HOST_KEYS = {
    "HOST_NAMES", "W", "EVIDENCE_ROOT", "EVIDENCE_R", "SCRATCH_ROOT", "BUILD_ROOT", "GATE_CCACHE_DIR",
    "DEPS_FREEZE", "TEST_VENV", "DEMO_PYTHON", "DISK_PATH", "DEMO_WORKERS", "GATE_STAGED", "GATE_SCOPE",
    "GATE_SCOPE_MEMORY_HIGH", "GATE_SCOPE_MEMORY_MAX", "GATE_MEM_SAMPLER", "GATE_RESET_SIGINT", "DEMO_DIST",
    "DEMO_MALLOC_ARENA_MAX", "DEMO_MALLOC_TRIM_THRESHOLD", "DEMO_MALLOC_MMAP_THRESHOLD", "GATE_EXTRA_PYTHONPATH",
    "NATIVE_BUILD_DEPS", "BUN_BIN", "BUN_CACHE", "GATE_UPSTREAM_PARALLEL", "GATE_UPSTREAM_CPU_SHARE", "GATE_TELEOP_XDIST",
    "BUILD_PROXY", "BUILD_NO_PROXY",
}
HOST_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
ZSH = shutil.which("zsh")
needs_zsh = pytest.mark.skipif(ZSH is None, reason="zsh is not installed")


def _files(suffix):
    return sorted(p for d in TOOL_DIRS for p in d.rglob(f"*{suffix}") if "__pycache__" not in p.parts)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


known_flakes = _load(GATE / "known_flakes.py", "gate_known_flakes")


def _host_env_files():
    return sorted(HOSTS.glob("*.env"))


def _parse_host_env(path):
    values = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        match = HOST_LINE.match(line)
        assert match, f"{path.name}:{number}: not KEY=VALUE: {line!r}"
        assert match.group(1) not in values, f"{path.name}:{number}: duplicate key {match.group(1)}"
        values[match.group(1)] = match.group(2)
    return values


# --- syntax -----------------------------------------------------------------------------------------------------------

def test_there_are_scripts_to_check():
    assert len(_files(".zsh")) >= 10
    assert len(_files(".py")) >= 8


@needs_zsh
@pytest.mark.parametrize("path", _files(".zsh"), ids=lambda p: str(p.relative_to(SCRIPTS)))
def test_every_zsh_script_parses(path):
    done = subprocess.run([ZSH, "-n", str(path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@pytest.mark.parametrize("path", _files(".py"), ids=lambda p: str(p.relative_to(SCRIPTS)))
def test_every_python_file_compiles(path):
    compile(path.read_text(), str(path), "exec")


# --- host env files -----------------------------------------------------------------------------------------------------

def test_the_known_hosts_have_env_files():
    assert {p.stem for p in _host_env_files()} >= {"ai-station", "antzb"}


@pytest.mark.parametrize("path", _host_env_files(), ids=lambda p: p.stem)
def test_a_host_env_file_has_the_required_keys_and_nothing_else(path):
    keys = set(_parse_host_env(path))
    assert keys - REQUIRED_HOST_KEYS == set(), f"unexpected keys: {sorted(keys - REQUIRED_HOST_KEYS)}"
    assert REQUIRED_HOST_KEYS - keys == set(), f"missing keys: {sorted(REQUIRED_HOST_KEYS - keys)}"


def test_host_names_do_not_overlap_between_hosts():
    seen = {}
    for path in _host_env_files():
        for name in _parse_host_env(path)["HOST_NAMES"].strip("\"'").split():
            assert name == name.lower()
            assert name not in seen, f"{name} is claimed by {seen[name]} and {path.stem}"
            seen[name] = path.stem


@pytest.mark.parametrize("path", _host_env_files(), ids=lambda p: p.stem)
def test_switch_values_are_zero_or_one_and_a_scope_has_limits(path):
    values = _parse_host_env(path)
    for key in ("GATE_STAGED", "GATE_SCOPE", "GATE_MEM_SAMPLER", "GATE_RESET_SIGINT"):
        assert values[key] in {"0", "1"}, key
    assert values["DEMO_WORKERS"].isdigit() and int(values["DEMO_WORKERS"]) >= 1
    if values["GATE_SCOPE"] == "1":
        assert values["GATE_SCOPE_MEMORY_HIGH"] and values["GATE_SCOPE_MEMORY_MAX"]


# --- the entry point and the host loader --------------------------------------------------------------------------------

@needs_zsh
def test_the_entry_point_refuses_an_unknown_host():
    done = subprocess.run([ZSH, str(GATE / "run_host_gate.zsh"), "--host", "no-such-host"], capture_output=True, text=True,
                          env={**os.environ, "GATE_HOST": ""})
    assert done.returncode == 2
    assert "unknown host" in done.stderr


@needs_zsh
def test_the_entry_point_refuses_a_host_name_that_could_leave_the_hosts_directory():
    done = subprocess.run([ZSH, str(GATE / "run_host_gate.zsh"), "--host", "../gate/hosts/antzb"], capture_output=True,
                          text=True, env={**os.environ, "GATE_HOST": ""})
    assert done.returncode == 2
    assert "unknown host" in done.stderr


def _loader(tmp_path, body, hostname=None, env=None):
    script = tmp_path / "probe.zsh"
    script.write_text(f"source {GATE}/load_host.zsh\n{body}\n")
    run_env = {k: v for k, v in os.environ.items() if k not in REQUIRED_HOST_KEYS and k != "GATE_HOST"}
    if hostname is not None:
        stub = tmp_path / "bin"
        stub.mkdir()
        (stub / "hostname").write_text(f"#!/bin/sh\necho {hostname}\n")
        (stub / "hostname").chmod(0o755)
        run_env["PATH"] = f"{stub}:{run_env['PATH']}"
    run_env.update(env or {})
    return subprocess.run([ZSH, str(script)], capture_output=True, text=True, env=run_env)


@needs_zsh
@pytest.mark.parametrize("hostname,expected", [("ai-station", "ai-station"), ("AI-STATION-001", "antzb")])
def test_the_host_is_detected_from_hostname(tmp_path, hostname, expected):
    done = _loader(tmp_path, 'so101_load_host || exit $?; print -r -- "$GATE_HOST $EVIDENCE_R"', hostname=hostname)
    assert done.returncode == 0, done.stderr
    host, evidence_r = done.stdout.split()
    assert host == expected
    assert evidence_r == _expand(_parse_host_env(HOSTS / f"{expected}.env"), "EVIDENCE_R")


@needs_zsh
def test_an_unknown_hostname_is_refused_and_nothing_is_exported(tmp_path):
    done = _loader(tmp_path, 'so101_load_host; print -r -- "rc=$? [${EVIDENCE_R-}]"', hostname="some-other-machine")
    assert "rc=2 []" in done.stdout
    assert "unknown host" in done.stderr


@needs_zsh
def test_a_variable_that_is_already_set_wins_over_the_host_file(tmp_path):
    done = _loader(tmp_path, 'so101_load_host ai-station; print -r -- "$DEMO_WORKERS"', env={"DEMO_WORKERS": "3"})
    assert done.stdout.strip() == "3"


def _expand(values, key):
    """Expand ${NAME} references the way the loader does (values defined earlier in the file)."""
    resolved = {}
    for name, raw in values.items():
        resolved[name] = re.sub(r"\$\{(\w+)\}", lambda m: resolved.get(m.group(1), ""), raw.strip("\"'"))
    return resolved[key]


# --- known-flakes.txt ---------------------------------------------------------------------------------------------------

def test_the_known_flakes_file_follows_the_format():
    entries = known_flakes.load(GATE / "known-flakes.txt")
    assert len(entries) == 6
    assert len({substring for substring, _reason, _date in entries}) == len(entries)


def test_a_well_formed_entry_is_parsed():
    entries = known_flakes.parse("# comment\n\ntest_x | load dependent, passes alone | 2026-10-20\n")
    assert entries == [("test_x", "load dependent, passes alone", "2026-10-20")]


@pytest.mark.parametrize("line", [
    "test_x",
    "test_x | only a reason",
    "test_x | reason | 2026-10-20 | extra",
    " | reason | 2026-10-20",
    "test_x | | 2026-10-20",
    "test_x | reason | 20 Oct 2026",
    "test_x | reason | 2026-13-40",
    " test_x | reason | 2026-10-20",
    "test_x|reason|2026-10-20",
])
def test_a_malformed_line_fails(line):
    with pytest.raises(known_flakes.KnownFlakeError):
        known_flakes.parse("test_ok | fine | 2026-10-20\n" + line + "\n")


def test_the_command_line_check_fails_on_a_malformed_file(tmp_path):
    bad = tmp_path / "flakes.txt"
    bad.write_text("test_ok | fine | 2026-10-20\nbroken line\n")
    good = tmp_path / "good.txt"
    good.write_text("test_ok | fine | 2026-10-20\n")
    run = lambda path: subprocess.run([sys.executable, "-I", str(GATE / "known_flakes.py"), str(path)],  # noqa: E731
                                      capture_output=True, text=True)
    assert run(bad).returncode == 1 and "line 2" in run(bad).stderr
    assert run(good).stdout == "test_ok\n"


# --- no host path in a script -------------------------------------------------------------------------------------------

FORBIDDEN = ("/data/work", "/opt/data/work", "/home/")


def test_no_script_names_a_host_path_outside_the_host_env_files():
    offenders = []
    for directory in TOOL_DIRS:
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc" or path.parent == HOSTS:
                continue
            text = path.read_text(errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                if any(token in line for token in FORBIDDEN):
                    offenders.append(f"{path.relative_to(SCRIPTS)}:{number}: {line.strip()[:100]}")
    assert offenders == []


# --- the result record carries the tools commit ---------------------------------------------------------------------------

def _git(repo, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env).stdout.strip()


@pytest.fixture
def tools_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "scripts" / "gate").mkdir(parents=True)
    (repo / "scripts" / "gate" / "tool.zsh").write_text("echo one\n")
    (repo / "other.txt").write_text("x\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "tools")
    return repo


def _rc_record(*args):
    return subprocess.run([sys.executable, "-I", str(GATE / "rc_record.py"), *map(str, args)], capture_output=True, text=True)


def test_the_tools_record_names_the_commit_of_scripts_gate(tools_repo, tmp_path):
    tools_commit = _git(tools_repo, "rev-parse", "HEAD")
    (tools_repo / "other.txt").write_text("changed outside scripts/gate\n")
    _git(tools_repo, "commit", "-q", "-am", "unrelated")
    out = tmp_path / "gate-tools.txt"

    done = _rc_record("tools", "--repo", tools_repo, "--out", out)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == tools_commit
    text = out.read_text()
    assert f"gate_tools_commit={tools_commit}" in text
    assert f"gate_tools_head={_git(tools_repo, 'rev-parse', 'HEAD')}" in text
    assert "gate_tools_clean=1" in text


def test_the_tools_record_fails_and_keeps_the_diff_stat_when_scripts_gate_is_dirty(tools_repo, tmp_path):
    (tools_repo / "scripts" / "gate" / "tool.zsh").write_text("echo two\n")
    out = tmp_path / "gate-tools.txt"

    done = _rc_record("tools", "--repo", tools_repo, "--out", out)

    assert done.returncode == 1
    text = out.read_text()
    assert "gate_tools_clean=0" in text
    assert "scripts/gate/tool.zsh" in text


def test_the_tools_record_fails_on_an_untracked_file_in_scripts_gate(tools_repo, tmp_path):
    (tools_repo / "scripts" / "gate" / "new.zsh").write_text("echo new\n")
    done = _rc_record("tools", "--repo", tools_repo, "--out", tmp_path / "gate-tools.txt")
    assert done.returncode == 1
    assert "new.zsh" in (tmp_path / "gate-tools.txt").read_text()


def test_the_tools_record_fails_when_nothing_is_tracked_under_scripts_gate(tmp_path):
    repo = tmp_path / "bare"
    repo.mkdir()
    (repo / "a.txt").write_text("a\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "x")
    done = _rc_record("tools", "--repo", repo, "--out", tmp_path / "gate-tools.txt")
    assert done.returncode == 1
    assert "gate_tools_clean=0" in (tmp_path / "gate-tools.txt").read_text()


def test_the_gate_result_record_includes_the_tools_commit(tmp_path):
    decision = tmp_path / "decision.json"
    decision.write_text(json.dumps({
        "decision": "run", "head_tree": "t" * 40, "apt_hash": "a" * 64, "reasons": ["fixture"],
        "baseline_file": None, "baseline_tree": None, "baseline_gate": None,
    }))
    gate = tmp_path / "gates" / "abc123"
    (gate).mkdir(parents=True)
    build = tmp_path / "build"
    for package in ("controller_manager", "hardware_interface_testing"):
        results = build / package / "test_results" / package
        results.mkdir(parents=True)
        (results / "a.xunit.xml").write_text("<testsuite/>")
    out = tmp_path / "record.json"

    done = _rc_record("finish", "--decision", decision, "--gate", gate, "--build-base", build, "--colcon-rc", 0,
                      "--tools-commit", "c0ffee" * 6 + "c0ff", "--out", out)

    assert done.returncode == 0, done.stderr
    record = json.loads(out.read_text())
    assert record["gate_tools_commit"] == "c0ffee" * 6 + "c0ff"
    assert record["green"] is True


def test_the_entry_point_records_the_tools_commit_in_every_result_it_writes():
    text = (GATE / "run_host_gate.zsh").read_text()
    assert "rc_record.py tools" in text
    assert text.count("--tools-commit $tools_commit") == 2
    assert "gate-tools.txt" in text

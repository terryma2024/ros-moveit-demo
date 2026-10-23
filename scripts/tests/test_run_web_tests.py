"""scripts/gate/run_web_tests.zsh: the manual front end test entry. A fake bun records what it is asked to run."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "gate" / "run_web_tests.zsh"
ZSH = shutil.which("zsh")
pytestmark = pytest.mark.skipif(ZSH is None, reason="zsh is not installed")


@pytest.fixture
def fake_bun(tmp_path):
    log = tmp_path / "bun.log"
    bun = tmp_path / "bun"
    bun.write_text(f'#!/bin/sh\necho "$@" >> {log}\n[ "$FAKE_BUN_FAIL" = "$*" ] && exit 7\nexit 0\n')
    bun.chmod(0o755)
    return bun, log


def run(bun, *args, **env):
    return subprocess.run([ZSH, str(SCRIPT), *args], capture_output=True, text=True,
                          env={**os.environ, "BUN_BIN": str(bun), **env})


def web_has_modules():
    return (SCRIPT.parents[2] / "src" / "so101_teleop" / "web" / "node_modules").is_dir()


def test_an_unknown_argument_is_refused(fake_bun):
    done = run(fake_bun[0], "--bogus")
    assert done.returncode == 2 and "unknown argument" in done.stderr and not fake_bun[1].exists()


def test_dry_run_prints_the_commands_and_runs_nothing(fake_bun):
    done = run(fake_bun[0], "--e2e", "--install", "--dry-run")
    assert done.returncode == 0
    lines = [line.split(" ", 2)[2] for line in done.stdout.splitlines()]
    assert lines == ["install --frozen-lockfile", "run test", "run test:e2e"]
    assert not fake_bun[1].exists()


def test_default_runs_only_the_unit_tests(fake_bun):
    if not web_has_modules():
        pytest.skip("web/node_modules is not installed here")
    assert run(fake_bun[0]).returncode == 0
    assert fake_bun[1].read_text().splitlines() == ["run test"]


def test_e2e_follows_the_unit_tests_and_a_failure_stops_the_run(fake_bun):
    if not web_has_modules():
        pytest.skip("web/node_modules is not installed here")
    assert run(fake_bun[0], "--e2e").returncode == 0
    assert fake_bun[1].read_text().splitlines() == ["run test", "run test:e2e"]
    fake_bun[1].unlink()
    done = run(fake_bun[0], "--e2e", FAKE_BUN_FAIL="run test")
    assert done.returncode == 7 and fake_bun[1].read_text().splitlines() == ["run test"]


def test_a_missing_bun_is_an_error():
    done = subprocess.run([ZSH, str(SCRIPT)], capture_output=True, text=True,
                          env={**os.environ, "BUN_BIN": "/nonexistent/bun"})
    assert done.returncode == 3 and "no bun" in done.stderr

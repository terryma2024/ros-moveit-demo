import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SOURCE = ROOT / "scripts" / "capture-ai-station.sh"


def stage_wrapper(tmp_path: Path, helper_body: str) -> Path:
    scripts = tmp_path / "skill" / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "capture-ai-station.sh"
    wrapper.write_bytes(WRAPPER_SOURCE.read_bytes())
    helper = scripts / "ai-station-capture.py"
    helper.write_text(helper_body)
    helper.chmod(0o755)
    return wrapper


def local_helper(manifest_overrides=None, create_desktop=True):
    overrides = manifest_overrides or {}
    return f'''#!/usr/bin/env python3
import argparse, json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--output-root", type=Path, required=True)
parser.add_argument("--test-ghostty-tabs", action="store_true")
args = parser.parse_args()
capture = args.output_root / "helper-session"
capture.mkdir(parents=True)
desktop = capture / "desktop.png"
if {create_desktop!r}:
    desktop.write_bytes(b"desktop")
manifest = {{
    "captured_at": "2026-08-11T12-00-00",
    "desktop": str(desktop),
    "rviz": None,
    "ghostty": None,
    "captured_windows": [],
    "missing_windows": ["rviz", "ghostty"],
    "capture_mode": "desktop_only",
    "ghostty_tab_test": "skipped_no_window" if args.test_ghostty_tabs else "not_requested",
}}
manifest.update({overrides!r})
print(json.dumps(manifest))
'''


def run_wrapper(wrapper: Path, *args, env=None):
    return subprocess.run(
        ["bash", str(wrapper), *map(str, args)],
        capture_output=True,
        text=True,
        env=env,
    )


def test_local_mode_uses_colocated_helper_without_ssh_or_scp(tmp_path):
    wrapper = stage_wrapper(tmp_path, local_helper())
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("ssh", "scp"):
        executable = fake_bin / command
        executable.write_text("#!/bin/sh\nexit 97\n")
        executable.chmod(0o755)
    output_root = tmp_path / "evidence"
    environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

    completed = run_wrapper(
        wrapper, "--local", "--output-root", output_root, env=environment
    )

    assert completed.returncode == 0, completed.stderr
    manifest_path = next(output_root.rglob("manifest.json"))
    manifest = json.loads(manifest_path.read_text())
    assert Path(manifest["desktop"]).read_bytes() == b"desktop"
    assert "RViz: not present" in completed.stdout
    assert "Ghostty: not present" in completed.stdout


def install_fake_remote_commands(tmp_path: Path, manifest: dict):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    log = tmp_path / "remote-calls.log"
    ssh = fake_bin / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        'printf "ssh %s\\n" "$*" >> "$FAKE_CALL_LOG"\n'
        'case "$*" in *ai-station-capture.py*--output-root*) '
        'printf "%s\\n" "$FAKE_REMOTE_MANIFEST" ;; esac\n'
    )
    ssh.chmod(0o755)
    scp = fake_bin / "scp"
    scp.write_text(
        "#!/bin/sh\n"
        'printf "scp %s\\n" "$*" >> "$FAKE_CALL_LOG"\n'
        'last=""; for value in "$@"; do last="$value"; done\n'
        'case "$last" in *:*) ;; *) mkdir -p "$(dirname -- "$last")"; '
        'printf artifact > "$last" ;; esac\n'
    )
    scp.chmod(0o755)
    environment = os.environ | {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_CALL_LOG": str(log),
        "FAKE_REMOTE_MANIFEST": json.dumps(manifest),
        "AI_STATION_SSH_TARGET": "test-ai-station",
    }
    return environment, log


def test_remote_mode_installs_helper_and_copies_only_declared_paths(tmp_path):
    wrapper = stage_wrapper(tmp_path, local_helper())
    manifest = {
        "captured_at": "2026-08-11T12-00-00",
        "desktop": "/tmp/remote/desktop.png",
        "rviz": None,
        "ghostty": None,
        "captured_windows": [],
        "missing_windows": ["rviz", "ghostty"],
        "capture_mode": "desktop_only",
        "ghostty_tab_test": "not_requested",
    }
    environment, log = install_fake_remote_commands(tmp_path, manifest)
    output_root = tmp_path / "remote-evidence"

    completed = run_wrapper(
        wrapper, "--remote", "--output-root", output_root, env=environment
    )

    assert completed.returncode == 0, completed.stderr
    calls = log.read_text()
    assert "ssh test-ai-station" in calls
    assert "scp" in calls and "ai-station-capture.py" in calls
    assert calls.count("/tmp/remote/desktop.png") == 1
    assert "None" not in calls and "null" not in calls
    destination = next(output_root.glob("2026-08-11T12-00-00-*"))
    assert (destination / "desktop.png").read_bytes() == b"artifact"
    assert json.loads((destination / "manifest.json").read_text()) == manifest
    assert "RViz: not present" in completed.stdout
    assert "Ghostty: not present" in completed.stdout


def test_invalid_manifest_is_nonzero(tmp_path):
    wrapper = stage_wrapper(tmp_path, "#!/usr/bin/env python3\nprint('not-json')\n")

    completed = run_wrapper(
        wrapper, "--local", "--output-root", tmp_path / "evidence"
    )

    assert completed.returncode != 0


def test_missing_declared_local_desktop_is_nonzero(tmp_path):
    wrapper = stage_wrapper(tmp_path, local_helper(create_desktop=False))

    completed = run_wrapper(
        wrapper, "--local", "--output-root", tmp_path / "evidence"
    )

    assert completed.returncode != 0


def test_local_tab_flag_preserves_safe_skip_manifest(tmp_path):
    wrapper = stage_wrapper(tmp_path, local_helper())
    output_root = tmp_path / "evidence"

    completed = run_wrapper(
        wrapper,
        "--local",
        "--test-ghostty-tabs",
        "--output-root",
        output_root,
    )

    assert completed.returncode == 0, completed.stderr
    manifest = json.loads(next(output_root.rglob("manifest.json")).read_text())
    assert manifest["ghostty_tab_test"] == "skipped_no_window"

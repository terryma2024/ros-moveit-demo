import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SOURCE = ROOT / "scripts" / "capture-gui.sh"


class CaptureWrapperTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        scripts = self.root / "skill" / "scripts"
        scripts.mkdir(parents=True)
        self.wrapper = scripts / "capture-gui.sh"
        shutil.copyfile(WRAPPER_SOURCE, self.wrapper)
        helper = scripts / "gui-capture.py"
        helper.write_text(
            """#!/usr/bin/env python3
import argparse, json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--output-root', type=Path)
parser.add_argument('--window-id')
parser.add_argument('--list-windows', action='store_true')
parser.add_argument('--platform')
args = parser.parse_args()
if args.list_windows:
    print(json.dumps([{'id': 42, 'owner': 'Codex', 'title': 'moveit-demo'}]))
else:
    capture = args.output_root / 'session'
    capture.mkdir(parents=True)
    image = capture / 'window.png'
    image.write_bytes(b'window')
    print(json.dumps({
        'captured_at': '20260826T120000',
        'platform': 'macos',
        'session_type': 'aqua',
        'capture_mode': 'window',
        'selector': {'query': None, 'window_id': 42},
        'window': {'id': 42},
        'image': str(image),
    }))
"""
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_local_window_capture_uses_colocated_helper_without_ssh(self):
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        for command in ("ssh", "scp"):
            executable = fake_bin / command
            executable.write_text("#!/bin/sh\nexit 97\n")
            executable.chmod(0o755)
        output_root = self.root / "evidence"
        environment = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"}

        completed = subprocess.run(
            [
                "bash",
                str(self.wrapper),
                "--local",
                "--window-id",
                "42",
                "--output-root",
                str(output_root),
            ],
            capture_output=True,
            text=True,
            env=environment,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        manifest = json.loads(next(output_root.rglob("manifest.json")).read_text())
        self.assertEqual(manifest["window"]["id"], 42)
        self.assertEqual(Path(manifest["image"]).read_bytes(), b"window")

    def test_list_windows_needs_no_output_directory(self):
        completed = subprocess.run(
            ["bash", str(self.wrapper), "--local", "--list-windows"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)[0]["id"], 42)


if __name__ == "__main__":
    unittest.main()

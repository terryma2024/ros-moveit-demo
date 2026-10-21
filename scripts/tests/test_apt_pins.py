"""apt_pins: pins from a host and an image manifest, and the pins no apt source offers."""

import json
from pathlib import Path
import subprocess
import sys

TOOL = Path(__file__).resolve().parents[1] / "env/apt_pins.py"


def run(*args):
    return subprocess.run([sys.executable, "-I", str(TOOL), *args], capture_output=True, text=True)


def test_every_image_package_the_host_has_is_pinned_to_the_host_version_and_image_only_packages_are_reported(tmp_path):
    host, image = tmp_path / "host.json", tmp_path / "image.json"
    host.write_text(json.dumps({"apt": {"libc6": "2.39-9", "git": "1:2.43-2", "only-host": "1"}}))
    image.write_text(json.dumps({"apt": {"libc6": "2.39-8", "git": "1:2.43-1", "only-image": "3"}}))
    done = run("generate", "--host", str(host), "--image", str(image))
    assert done.returncode == 0
    assert done.stdout == "git=1:2.43-2\nlibc6=2.39-9\n"
    assert "only-image" in done.stderr and "only-host" not in done.stderr


def test_a_pin_that_no_source_offers_is_listed_and_the_exit_code_says_so(tmp_path):
    pins, madison = tmp_path / "pins", tmp_path / "madison"
    pins.write_text("git=1:2.43-2\nlibc6=2.39-9\n")
    madison.write_text(" libc6 | 2.39-9 | http://mirror noble/main amd64 Packages\n libc6 | 2.39-8 | http://mirror noble-security/main amd64 Packages\n"
                       "    git | 1:2.43-3 | http://mirror noble-updates/main amd64 Packages\n")
    done = run("unavailable", "--pins", str(pins), "--madison", str(madison))
    assert done.returncode == 1 and done.stdout == "git=1:2.43-2\n"
    madison.write_text(madison.read_text() + "    git | 1:2.43-2 | http://mirror noble-updates/main amd64 Packages\n")
    assert run("unavailable", "--pins", str(pins), "--madison", str(madison)).returncode == 0

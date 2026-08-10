from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCENE = PACKAGE_ROOT / "mjcf/scene.xml"


def test_scene_has_no_hidden_grasp_or_follow_mechanism() -> None:
    root = ET.parse(SCENE).getroot()
    assert root.find(".//equality") is None
    assert not root.findall(".//body[@mocap='true']")
    assert not root.findall(".//adhesion")
    assert not root.findall(".//weld")
    cup_actuators = [
        actuator
        for actuator in root.findall(".//actuator/*")
        if "cup" in " ".join(actuator.attrib.values()).lower()
    ]
    assert cup_actuators == []


def test_new_package_has_no_post_start_object_state_write_path() -> None:
    forbidden = re.compile(
        r"(?:cup|object).*(?:qpos|qvel)|(?:qpos|qvel).*(?:cup|object)", re.IGNORECASE
    )
    offenders: list[str] = []
    for path in PACKAGE_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".cpp", ".hpp"}:
            continue
        if path == Path(__file__) or "test" in path.parts:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if forbidden.search(line):
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{line_number}")
    assert offenders == []

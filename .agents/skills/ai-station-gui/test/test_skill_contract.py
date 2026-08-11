from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[2]


def test_skill_prefers_loaded_agent_cua_before_script_fallback():
    text = (ROOT / "SKILL.md").read_text()
    required = (
        "Codex",
        "Claude",
        "Kimi",
        "cua-driver",
        "snapshot -> action -> fresh snapshot",
        "直接运行在 ai-station",
        "不得 SSH 自身",
        "scripts/capture-ai-station.sh",
    )
    assert all(value in text for value in required)
    assert text.index("cua-driver") < text.index("scripts/capture-ai-station.sh")


def test_capture_contract_makes_only_desktop_required():
    text = (ROOT / "references" / "capture-contract.md").read_text()
    assert "desktop" in text
    assert '"rviz": null' in text
    assert '"ghostty": null' in text
    assert "skipped_no_window" in text


def test_capture_contract_defines_local_and_remote_transfer_safety():
    text = (ROOT / "references" / "capture-contract.md").read_text()

    assert "`--local`" in text
    assert "`--remote`" in text
    assert "non-null" in text
    assert "exact remote manifest" in text


def test_current_so101_skills_route_gui_work_to_the_new_owner():
    current_docs = (
        REPOSITORY / ".agents" / "skills" / "so101-dev" / "references" / "ai-station-access.md",
        REPOSITORY / ".agents" / "skills" / "so101-dev" / "references" / "test-and-acceptance.md",
        REPOSITORY / ".agents" / "skills" / "gazebo-video-debug" / "SKILL.md",
    )

    for path in current_docs:
        text = path.read_text()
        assert "ai-station-gui" in text, path
        assert "<repo-root>/scripts/capture-ai-station.sh" not in text, path
        assert "ros2 run so101_gazebo_demo_cpp tile_ai_station_guis.py" not in text, path

    access = current_docs[0].read_text()
    acceptance = current_docs[1].read_text()
    video = current_docs[2].read_text()
    assert "ros2 run so101_teleop tile_ai_station_guis.py" in access
    assert "ros2 run so101_teleop tile_ai_station_guis.py" in acceptance
    assert "ros2 run so101_teleop tile_ai_station_guis.py" in video

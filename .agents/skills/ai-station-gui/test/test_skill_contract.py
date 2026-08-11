from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

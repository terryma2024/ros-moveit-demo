from pathlib import Path

import pytest

from so101_teleop.expert_validation.main import configured_evidence_root


def test_evidence_root_is_required_absolute_and_not_symlink(tmp_path):
    with pytest.raises(RuntimeError, match="SO101_VALIDATION_EVIDENCE_ROOT_REQUIRED"):
        configured_evidence_root({})
    with pytest.raises(RuntimeError, match="EVIDENCE_ROOT_ABSOLUTE"):
        configured_evidence_root({"SO101_VALIDATION_EVIDENCE_ROOT": "relative"})
    root = (tmp_path / "evidence").resolve()
    root.mkdir()
    link = tmp_path / "link"
    link.symlink_to(root, target_is_directory=True)
    with pytest.raises(RuntimeError, match="EVIDENCE_ROOT_SYMLINK"):
        configured_evidence_root({"SO101_VALIDATION_EVIDENCE_ROOT": str(link.absolute())})
    assert configured_evidence_root(
        {"SO101_VALIDATION_EVIDENCE_ROOT": str(root)}
    ) == root


def test_validation_main_module_does_not_import_rclpy():
    import so101_teleop.expert_validation.main as validation_main

    assert "rclpy" not in validation_main.__dict__

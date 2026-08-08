from pathlib import Path
import json
import pytest

from assert_pick_place_evidence import assert_summary


def test_empty_summary_is_rejected(tmp_path: Path) -> None:
    path=tmp_path/"summary.json"; path.write_text("{}")
    with pytest.raises((AssertionError,KeyError)): assert_summary(path)


def test_live_summary_when_requested() -> None:
    import os
    path=os.environ.get("SO101_PY_E2E_SUMMARY")
    if not path: pytest.skip("set SO101_PY_E2E_SUMMARY after the fresh live run")
    assert_summary(Path(path))


def test_runner_waits_for_detached_attachment_state() -> None:
    script = (Path(__file__).parent / "run_pick_place_e2e.sh").read_text()
    assert "/so101/object_attached" in script
    assert '"detached"' in script

import stat

from so101_gazebo_demo_py.diagnostics import PlanningDiagnostics


def test_diagnostics_are_private_and_only_written_for_failure(tmp_path) -> None:
    store = PlanningDiagnostics(tmp_path / "private")
    assert store.write_failure("PLAN_FAILED", {"attempt": 1}) is not None
    path = next((tmp_path / "private").iterdir())
    assert stat.S_IMODE((tmp_path / "private").stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    before = tuple((tmp_path / "private").iterdir())
    assert store.write_success({"attempt": 2}) is None
    assert tuple((tmp_path / "private").iterdir()) == before

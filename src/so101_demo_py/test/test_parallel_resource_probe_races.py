from pathlib import Path

import pytest


def _proc_process(root: Path, pid: int) -> Path:
    process = root / str(pid)
    process.mkdir()
    fields = ["S", *("0" for _ in range(18)), "100", "0"]
    (process / "stat").write_text(
        f"{pid} (opaque-runtime) {' '.join(fields)}\n", encoding="ascii"
    )
    (process / "comm").write_text("opaque-runtime\n", encoding="utf-8")
    (process / "cmdline").write_bytes(b"/opt/opaque-runtime\0")
    (process / "environ").write_bytes(b"PATH=/usr/bin\0")
    return process


def test_transient_proc_metadata_error_is_retried(tmp_path, monkeypatch):
    from so101_demo.parallel_batch.resources import SystemResourceProbe

    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    process = _proc_process(proc_root, 4249)
    comm = process / "comm"
    original = Path.read_text
    reads = 0

    def transient_metadata_error(path, *args, **kwargs):
        nonlocal reads
        if path == comm:
            reads += 1
            if reads == 1:
                raise PermissionError("synthetic transient process race")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", transient_metadata_error)

    assert SystemResourceProbe(proc_root=proc_root).ros_domain_in_use(181) is False
    assert reads == 3


def test_cleanup_domain_probe_rescans_a_transient_proc_race(monkeypatch):
    from so101_demo.cli import parallel_batch_cleanup
    from so101_demo.parallel_batch.resources import ResourceAllocationError

    class Probe:
        calls = 0

        def ros_domain_in_use(self, domain_id):
            assert domain_id == 181
            self.calls += 1
            if self.calls < 3:
                raise ResourceAllocationError(
                    "PROC_METADATA_UNVERIFIABLE: 4249"
                )
            return False

    probe = Probe()
    sleeps = []
    monkeypatch.setattr(parallel_batch_cleanup.time, "sleep", sleeps.append)

    assert parallel_batch_cleanup._ros_domain_in_use_after_quiescence(
        probe, 181
    ) is False
    assert probe.calls == 3
    assert sleeps == [0.05, 0.05]


def test_cleanup_domain_probe_outlives_the_five_second_shutdown_tail(monkeypatch):
    from so101_demo.cli import parallel_batch_cleanup
    from so101_demo.parallel_batch.resources import ResourceAllocationError

    class Probe:
        calls = 0

        def ros_domain_in_use(self, domain_id):
            assert domain_id == 181
            self.calls += 1
            if self.calls <= 101:
                raise ResourceAllocationError(
                    "PROC_METADATA_UNVERIFIABLE: 4249"
                )
            return False

    probe = Probe()
    sleeps = []
    monkeypatch.setattr(parallel_batch_cleanup.time, "sleep", sleeps.append)

    assert parallel_batch_cleanup._ros_domain_in_use_after_quiescence(
        probe, 181
    ) is False
    assert probe.calls == 102
    assert sleeps == [0.05] * 101


def test_cleanup_domain_probe_keeps_persistent_proc_races_fail_closed(
    monkeypatch,
):
    from so101_demo.cli import parallel_batch_cleanup
    from so101_demo.parallel_batch.resources import ResourceAllocationError

    class Probe:
        calls = 0

        def ros_domain_in_use(self, domain_id):
            assert domain_id == 181
            self.calls += 1
            raise ResourceAllocationError(
                "PROC_METADATA_UNVERIFIABLE: 4249"
            )

    probe = Probe()
    sleeps = []
    monkeypatch.setattr(
        parallel_batch_cleanup, "_PROC_SCAN_QUIESCENCE_ATTEMPTS", 3
    )
    monkeypatch.setattr(parallel_batch_cleanup.time, "sleep", sleeps.append)

    with pytest.raises(
        ResourceAllocationError,
        match=r"^PROC_METADATA_UNVERIFIABLE: 4249$",
    ):
        parallel_batch_cleanup._ros_domain_in_use_after_quiescence(
            probe, 181
        )
    assert probe.calls == 3
    assert sleeps == [0.05, 0.05]

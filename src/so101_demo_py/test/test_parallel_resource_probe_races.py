from pathlib import Path


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

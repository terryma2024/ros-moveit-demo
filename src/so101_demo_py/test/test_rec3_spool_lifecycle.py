"""CP-3405: a spooler must never outlive the Recorder that started it (test runs left orphans, PPID 1, hours old, adding load)."""
import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

HELPERS = {
    "chunk": """
        from so101_demo.act.chunk_spool import SpoolProcess
        process = SpoolProcess(sys.argv[1], topic="/rec3_lifecycle_chunks", max_bytes=1 << 20)
        process.start(); assert process.wait_ready(20.0)
    """,
    "controller": """
        from so101_demo.act.controller_spool import ControllerSpoolProcess
        process = ControllerSpoolProcess(sys.argv[1], session_id="s", reset_epoch=1, floor_ns=1, max_bytes=1 << 20)
        process.start(); assert process.wait_ready(20.0)
    """,
}


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        with open(f"/proc/{pid}/stat") as stream:
            return stream.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


@pytest.mark.parametrize("kind", ["chunk", "controller"])
@pytest.mark.parametrize("how", ["sigkill", "os_exit"])
def test_the_spooler_exits_within_a_second_of_its_parents_death(tmp_path, kind, how, isolated_ros_domain):
    script = tmp_path / "parent.py"
    script.write_text("import os, sys, signal, time\n" + textwrap.dedent(HELPERS[kind]) + textwrap.dedent(f"""
        print(process.child.pid, flush=True)
        {'os.kill(os.getpid(), signal.SIGKILL)' if how == 'sigkill' else 'os._exit(0)'}
    """))
    parent = subprocess.Popen([sys.executable, str(script), str(tmp_path / "spool")], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    try:
        parent.wait(timeout=30)
        end = time.monotonic() + 1.0
        while alive(child) and time.monotonic() < end:
            time.sleep(0.02)
        assert not alive(child), "the spooler outlived its parent"
    finally:
        if alive(child):
            os.kill(child, signal.SIGKILL)


def test_every_spool_process_object_registers_an_exit_close():
    import atexit
    from so101_demo.act import chunk_spool, controller_spool
    for module, cls in ((chunk_spool, chunk_spool.SpoolProcess), (controller_spool, controller_spool.ControllerSpoolProcess)):
        assert "_register_exit_close" in dir(cls), cls

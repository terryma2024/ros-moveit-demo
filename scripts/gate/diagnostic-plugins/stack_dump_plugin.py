"""Diagnostic only: dump all thread stacks 7 s into any task_builder test (per-process file under $STACK_DUMP_DIR)."""
import faulthandler
import os

import pytest

_FILE = None


def _stream():
    global _FILE
    if _FILE is None:
        _FILE = open(os.path.join(os.environ["STACK_DUMP_DIR"], f"stacks-{os.getpid()}.log"), "a")
    return _FILE


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    watch = "task_builder" in item.nodeid
    if watch:
        stream = _stream()
        stream.write(f"=== {item.nodeid}\n")
        stream.flush()
        faulthandler.dump_traceback_later(7, repeat=False, file=stream)
    try:
        yield
    finally:
        if watch:
            faulthandler.cancel_dump_traceback_later()

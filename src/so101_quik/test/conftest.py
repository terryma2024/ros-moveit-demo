"""Record each worker's interpreter and fresh scratch directory."""


def pytest_configure(config):
    import os
    from pathlib import Path
    import sys
    import tempfile

    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return
    actual = Path(tempfile.gettempdir()).resolve()
    expected = Path(os.environ["TMPDIR"]).resolve()
    if actual != expected:
        raise RuntimeError(f"QuIK worker {worker} escaped scratch: {actual} != {expected}")
    (actual / f"so101-quik-worker-proof-{worker}.txt").write_text(
        f"worker={worker}\ninterpreter={sys.executable}\ntempdir={actual}\n"
        f"expected={expected}\nrootdir={config.rootpath}\n")

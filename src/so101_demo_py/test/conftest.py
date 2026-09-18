from pathlib import Path


def pytest_configure(config) -> None:
    """Each xdist worker records its own tempfile location and origins.

    The proof file lives inside the run scratch (TMPDIR), so a worker that ignored the
    scratch environment is visible immediately. Serial runs write nothing.
    """

    import os
    import tempfile
    from pathlib import Path

    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return
    directory = Path(tempfile.gettempdir()).resolve()
    expected = Path(os.environ.get("TMPDIR", tempfile.gettempdir())).resolve()
    if directory != expected:
        raise RuntimeError(
            f"xdist worker {worker} tempdir {directory} escaped TMPDIR {expected}")
    proof = directory / f"so101-worker-proof-{worker}.txt"
    import sys

    proof.write_text(
        f"worker={worker}\ninterpreter={sys.executable}\n"
        f"prefix={sys.prefix}\ntempdir={directory}\nexpected={expected}\n"
        f"rootdir={config.rootpath}\n"
    )


def pytest_addoption(parser) -> None:
    parser.addoption("--installed-share", type=Path, default=None)

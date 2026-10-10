from pathlib import Path
import sys

from paths import TEST_DIRECTORIES

for _directory in reversed(TEST_DIRECTORIES):
    if str(_directory) not in sys.path:
        sys.path.insert(0, str(_directory))


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


import pytest  # noqa: E402


@pytest.fixture
def isolated_ros_domain(monkeypatch):
    """A ROS domain of this test's own.

    Tests that publish to fixed topic names (`/arm_controller/controller_state`, ...) and start a spooler process must not share a
    domain with the same test on another xdist worker, or with the live runs (domains 181 and 216-222): the frames of one worker
    arrived in another worker's spooler and produced ORDER_INVALID hazards, gaps that were never seen and shifted sequences.
    Domain 100 + 8 per worker + a per-worker counter keeps parallel workers apart; the child processes inherit it.
    """
    import os

    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    index = int(worker[2:]) if worker.startswith("gw") and worker[2:].isdigit() else 0
    counter = getattr(isolated_ros_domain, "_count", 0) + 1
    isolated_ros_domain._count = counter
    domain = 100 + (index * 8 + counter % 8) % 100
    monkeypatch.setenv("ROS_DOMAIN_ID", str(domain))
    return domain


@pytest.fixture(autouse=True)
def _fresh_readback_state():
    """The memo and its readback guard are process state: no test inherits another's filled cache, trusting gates or open guard."""
    try:
        from so101_demo.act import qc_memo
    except ImportError:
        yield
        return
    qc_memo._CACHE.clear()
    qc_memo._TRUSTING_BUILT[0] = 0
    qc_memo._STRICT[0] = 0
    yield

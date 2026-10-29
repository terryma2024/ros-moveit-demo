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


@pytest.fixture(autouse=True)
def _current_event_loop():
    """A test that drives asyncio from the main thread through the policy's current loop (`LaunchService.run`) needs one to exist.

    `asyncio.run()` in an earlier test of the same worker leaves none, so those tests passed or failed with the order the scheduler
    gave them ("There is no current event loop in thread 'MainThread'"). A worker now always starts a test with a current loop.
    """
    import asyncio

    try:
        asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    yield


#: The domains a graph test may take: 10..215 without the ones the gate and the live runs own (181: the live launch plan, 203/204: the demo and
#: teleop stages of the gate). 216..229 are the live runs, the upstream groups and the JTC stage; 230..232 are not handed out.
RESERVED_ROS_DOMAINS = frozenset({181, 203, 204})
TEST_ROS_DOMAINS = tuple(domain for domain in range(10, 216) if domain not in RESERVED_ROS_DOMAINS)


def ros_domain_slot(worker_index, counter):
    """The ROS domain of the `counter`-th graph test of worker `worker_index`: distinct for every (worker < 25, counter % 8) pair."""
    return TEST_ROS_DOMAINS[(worker_index * 8 + counter % 8) % len(TEST_ROS_DOMAINS)]


@pytest.fixture
def isolated_ros_domain(monkeypatch):
    """A ROS domain of this test's own.

    Tests that publish to fixed topic names (`/arm_controller/controller_state`, ...) and start a spooler process must not share a
    domain with the same test on another xdist worker, or with the live runs (domains 181 and 216-222): the frames of one worker
    arrived in another worker's spooler and produced ORDER_INVALID hazards, gaps that were never seen and shifted sequences.
    Eight domains per worker and a per-worker counter keep parallel workers apart; the child processes inherit it. The slots are laid
    over `TEST_ROS_DOMAINS` (10..215 without the reserved 181, 203 and 204), so up to 25 workers get distinct domains (the old
    `100 + n % 100` gave workers 0 and 13..15 of a 16-worker run the same domains). `ros_domain_slot` is the pure part.
    """
    import os

    worker = os.environ.get("PYTEST_XDIST_WORKER", "gw0")
    index = int(worker[2:]) if worker.startswith("gw") and worker[2:].isdigit() else 0
    counter = getattr(isolated_ros_domain, "_count", 0) + 1
    isolated_ros_domain._count = counter
    domain = ros_domain_slot(index, counter)
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


@pytest.fixture(autouse=True)
def _fresh_export_verification_state(monkeypatch):
    """The collection-verification memo is process state, and the export worker count is the serial path in tests:
    their seams (monkeypatched readbacks) live in this process, so a spawned worker would not see them."""
    monkeypatch.setenv("SO101_ACT_EXPORT_WORKERS", "1")
    try:
        from so101_demo.act.bundle import clear_verification_memo
    except ImportError:
        yield
        return
    clear_verification_memo()
    yield
    clear_verification_memo()


@pytest.fixture(scope="session")
def indoor_pool_act(tmp_path_factory):
    """`assets/mujoco/act` of a copy of the assets in which every procedural indoor texture is written (about 45 s once per worker)."""
    pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    from indoor_pool_tree import build_pool_tree

    return build_pool_tree(tmp_path_factory.mktemp("indoor-pool"))


@pytest.fixture(scope="session")
def indoor_pool_share(indoor_pool_act, tmp_path_factory):
    """A package share directory (`<share>/assets/mujoco/act`) over `indoor_pool_act`, for `scene_variant_run.realize_into` and the episode readers."""
    share = tmp_path_factory.mktemp("indoor-pool-share")
    (share / "assets").mkdir()
    (share / "assets/mujoco").symlink_to(indoor_pool_act.parent)
    return share

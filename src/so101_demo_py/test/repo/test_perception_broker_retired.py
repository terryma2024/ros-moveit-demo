"""The perception broker is retired (mount-tree migration M5): the Linux broker container, the mujoco parallel batch that served it, and
the Expert Validation production service with its web app. No tracked source, script, Dockerfile, CMake or web file may import or name
a removed module.

What stays is named too: the macOS two-worker campaign keeps its in-process MPS broker and the worker-side port, because that campaign
cannot run without them (`parallel_perception_runtime`, `macos_two_worker_broker_port`, `parallel_ipc/broker_transport`).
"""
import re

import pytest
from paths import PACKAGE_ROOT, REPOSITORY

SOURCE = PACKAGE_ROOT / "src"
TELEOP = REPOSITORY / "src/so101_teleop"

REMOVED_PATHS = (
    SOURCE / "cli/parallel_perception_broker.py",
    SOURCE / "cli/mujoco_parallel_batch.py",
    SOURCE / "cli/parallel_batch_cleanup.py",
    SOURCE / "parallel_batch/adaptive_runner.py",
    SOURCE / "parallel_batch/resources.py",
    PACKAGE_ROOT / "docker/parallel-perception",
    REPOSITORY / "scripts/parallel-perception-container.sh",
    REPOSITORY / "scripts/run_so101_adaptive_batch.zsh",
    REPOSITORY / "scripts/run_so101_adaptive_worker_scaling.zsh",
    REPOSITORY / "scripts/so101-teleop-service.py",
    TELEOP / "so101_teleop/expert_validation",
    TELEOP / "so101_teleop/expert_validation_openapi.json",
    TELEOP / "scripts/so101_expert_validation_server.py",
    TELEOP / "config/expert_validation",
    TELEOP / "web/src/expert-validation-app.tsx",
    TELEOP / "web/src/components/expert-validation",
    TELEOP / "web/e2e/expert-validation",
)

#: built from fragments so this file does not match its own search
REMOVED_NAMES = (
    "mujoco_" + "parallel_batch", "parallel_batch_" + "cleanup", "parallel_perception_" + "broker", "so101_parallel_" + "batch",
    "so101_parallel_perception_" + "broker", "parallel-" + "perception-container", "docker/parallel-" + "perception",
    "run_so101_adaptive_" + "batch", "run_so101_adaptive_worker_" + "scaling", "so101_expert_" + "validation_server",
    "so101_teleop." + "expert_validation", "so101_teleop.expert_" + "validation", "expert-validation-" + "app",
    "mujoco_batch." + "request", "mujoco_batch." + "provenance", "mujoco_batch." + "composition", "mujoco_batch." + "worker_process",
    "mujoco_batch." + "rpc_proxies", "mujoco_batch." + "servers", "mujoco_batch." + "outcome", "parallel_batch." + "adaptive_runner",
    "parallel_batch." + "resources import", "resource_allocation." + "allocator", "so101-teleop-" + "service.py",
)

SUFFIXES = {".py", ".zsh", ".sh", ".ts", ".tsx", ".json", ".txt", ".cmake", ".yaml", ".yml", ".xml", ".toml", ".cfg"}
SKIPPED_PARTS = {"node_modules", "dist", "__pycache__", ".git", "test-results"}
#: records of what was done, never instructions: the history stays as written
HISTORY = ("docs",)


def _tracked_text():
    for root in (SOURCE, TELEOP, REPOSITORY / "scripts", REPOSITORY / "tools"):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if (path.is_file() and (path.suffix in SUFFIXES or path.name in {"Dockerfile", "CMakeLists.txt"})
                    and not SKIPPED_PARTS & set(path.parts) and path != PACKAGE_ROOT / "test/repo" / "test_perception_broker_retired.py"):
                yield path


@pytest.mark.parametrize("path", REMOVED_PATHS, ids=lambda path: str(path.relative_to(REPOSITORY)))
def test_removed_paths_are_absent(path):
    assert not path.exists()


def test_nothing_imports_or_names_a_removed_module():
    offenders = []
    for path in _tracked_text():
        text = path.read_text(errors="replace")
        offenders += [(str(path.relative_to(REPOSITORY)), name) for name in REMOVED_NAMES if name in text]
    assert offenders == []


def test_console_scripts_drop_the_broker_entries():
    entries = set(re.findall(r'"([A-Za-z0-9_]+) = ', (PACKAGE_ROOT / "setup.py").read_text()))
    assert not entries & {"so101_parallel_batch", "so101_parallel_batch_cleanup", "so101_parallel_perception_broker"}
    assert {"so101_macos_service_campaign", "act_collect_parallel", "act_rollout_parallel"} <= entries


def test_the_macos_campaign_keeps_the_pieces_it_cannot_run_without():
    for kept in ("runtime/macos_two_worker_broker_port.py", "runtime/parallel_perception_runtime.py",
                 "runtime/parallel_ipc/broker_transport.py", "cli/macos_two_worker_process.py", "cli/macos_service_campaign.py",
                 "parallel_batch/macos_two_worker_campaign.py"):
        assert (SOURCE / kept).is_file(), kept

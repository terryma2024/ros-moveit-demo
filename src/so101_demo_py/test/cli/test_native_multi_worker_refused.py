"""A native (non-container) batch runs exactly one worker; every entry refuses more.

Multi-worker collection exists only as container shards (``act_collect_parallel``). The native batch
family stays as the single-worker runtime library, so the contract, the command line and the
allocation default all say the same thing: one worker.
"""

from __future__ import annotations

from pathlib import Path

from parallel_batch_cli_support import (
    adaptive_argv,
    argv,
    local_start_guard,  # noqa: F401  (autouse pytest fixture)
    verified,
)
import pytest

from so101_demo.parallel_batch.contracts.common import ContractError, RunMode
from so101_demo.parallel_batch.contracts.linux_cuda import BatchKind, BatchRequest


def _request(worker_count):
    return BatchRequest(
        "batch-1", RunMode.DRY_RUN, ("task_start", "cup_test_forward_5cm"), worker_count,
        Path("/tmp/so101-native-single-worker-contract"), BatchKind.FIRST_PASS,
    )


@pytest.mark.parametrize("worker_count", [2, 3, 8])
def test_the_batch_contract_refuses_every_count_but_one(worker_count):
    with pytest.raises(ContractError, match="NATIVE_MULTI_WORKER_UNSUPPORTED"):
        _request(worker_count)


def test_the_batch_contract_still_admits_one_worker():
    assert _request(1).worker_count == 1


@pytest.mark.parametrize("worker_count", ["2", "8"])
def test_the_command_line_refuses_a_multi_worker_count_before_any_resource_work(tmp_path, worker_count):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    root = tmp_path / "refused"
    with pytest.raises(CliError, match="NATIVE_MULTI_WORKER_UNSUPPORTED"):
        prepare_batch(
            argv(root, worker_count=worker_count, point_id=("task_start",)),
            provenance_verifier=verified,
        )
    assert not root.exists()


def test_the_command_line_refuses_the_adaptive_pool(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    root = tmp_path / "adaptive-refused"
    with pytest.raises(CliError, match="NATIVE_MULTI_WORKER_UNSUPPORTED"):
        prepare_batch(adaptive_argv(root, point_id=("task_start",)), provenance_verifier=verified)
    assert not root.exists()


def test_an_omitted_worker_count_is_one_worker_and_equals_an_explicit_one(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    explicit = argv(tmp_path / "batch", worker_count="1", point_id=("task_start",))
    index = explicit.index("--worker-count")
    omitted = explicit[:index] + explicit[index + 2:]
    from_explicit = prepare_batch(explicit, provenance_verifier=verified)
    from_omitted = prepare_batch(omitted, provenance_verifier=verified)
    assert from_explicit.request == from_omitted.request
    assert from_omitted.request.worker_count == 1
    assert from_explicit.manifest["worker_count"] == from_omitted.manifest["worker_count"] == 1


def test_the_allocator_default_is_one_worker():
    from so101_demo.parallel_batch.resource_allocation.allocator import _parser
    from so101_demo.parallel_batch.resource_allocation.models import _DEFAULT_WORKER_COUNT

    assert _DEFAULT_WORKER_COUNT == 1
    parsed = _parser().parse_args(["--config", "/c", "--evidence-root", "/e", "--dry-run"])
    assert parsed.worker_count == 1

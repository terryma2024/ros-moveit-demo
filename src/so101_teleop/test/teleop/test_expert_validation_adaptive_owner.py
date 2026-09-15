import os
from pathlib import Path
import signal
import sys
import time

import pytest

from so101_teleop.expert_validation.adaptive import AdaptiveStartRequest
from so101_teleop.expert_validation.process_owner import (
    CoordinatorOwnershipError,
    ExecutionProcessOwner,
    OwnedAdaptiveWrapper,
)


HELPER = Path(__file__).parents[1] / "fixtures/process_tree_helper.py"
SHA = "b" * 64


def request(tmp_path, batch_id="a20"):
    root = tmp_path.resolve()
    return AdaptiveStartRequest(
        campaign_id="campaign-adaptive",
        batch_id=batch_id,
        preferred_worker_count=8,
        fallback_worker_counts=(6, 4, 2, 1),
        initial_points_per_worker=3,
        worker_start_timeout_s=120.0,
        max_infra_attempts_per_point=5,
        yolo_executor_count=2,
        argv=(
            sys.executable,
            str(HELPER),
            "--mode",
            "wrapper",
            "--root",
            str(root / "r" / batch_id),
            "--batch-id",
            batch_id,
        ),
        environment={"ADAPTIVE_OWNER_TEST": "1"},
        evidence_root=root,
        adaptive_config_sha256=SHA,
        catalog_sha256=SHA,
        yolo_weights_sha256=SHA,
        grounded_sam_manifest_sha256=SHA,
        broker_image_id="sha256:" + SHA,
    )


def test_adaptive_cancel_targets_exact_wrapper_pid_only(tmp_path):
    owner = ExecutionProcessOwner()
    running = owner.spawn(request(tmp_path))
    assert isinstance(running, OwnedAdaptiveWrapper)
    owner.request_cancel(running)
    assert running.pgid != 0
    for _ in range(150):
        if not owner.poll(running).running:
            break
        time.sleep(0.02)
    assert not owner.poll(running).running


@pytest.mark.parametrize("batch_id", ["", "abcdef", "é", "a/b"])
def test_adaptive_request_rejects_noncanonical_short_batch_id(tmp_path, batch_id):
    with pytest.raises(ValueError, match="ADAPTIVE_BATCH_ID"):
        request(tmp_path, batch_id=batch_id)


def test_adaptive_reconnect_rejects_wrapper_pid_reuse(tmp_path):
    owner = ExecutionProcessOwner()
    running = owner.spawn(request(tmp_path))
    try:
        stale = OwnedAdaptiveWrapper(
            **{**running.__dict__, "started_ticks": running.started_ticks + 1}
        )
        with pytest.raises(CoordinatorOwnershipError, match="PROCESS_IDENTITY_MISMATCH"):
            owner.reconnect(stale)
    finally:
        if owner.poll(running).running:
            os.kill(running.pid, signal.SIGINT)

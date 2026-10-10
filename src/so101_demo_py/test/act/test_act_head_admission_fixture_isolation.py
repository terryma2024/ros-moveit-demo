"""Other peers cannot assemble models during a fixed-budget live admission."""
import fcntl
import os

import pytest

from test_act_head_paused_admission import paused_head, next_original_pair
from test_act_head_trajectory_guard import guard


def test_live_admission_excludes_other_workers_model_assembly(paused_head,tmp_path_factory):
    scratch=tmp_path_factory.getbasetemp()
    shared=scratch.parent if os.environ.get('PYTEST_XDIST_WORKER') else scratch
    descriptor=os.open(shared/'head-admission-peer.lock',os.O_RDWR|os.O_NOFOLLOW)
    try:
        with pytest.raises(BlockingIOError):
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
    finally:
        os.close(descriptor)


def test_original_peer_delivers_complete_feedback_before_handing_back_admission(paused_head):
    case=paused_head
    previous=case.row.observer.current_inputs(case.row.clock.monotonic())['joint']['source_ns']
    with next_original_pair(case):
        with case.peer_lock:
            current=case.row.observer.current_inputs(case.row.clock.monotonic())
            assert current['joint']['source_ns']>previous
            assert current['image']['source_ns']==current['info']['source_ns']==current['joint']['source_ns']

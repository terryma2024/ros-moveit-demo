"""Task 12 ownership: nothing trains on a GPU that is busy, and no lease is inherited."""

import json

import pytest

from so101_demo.act.training_owner import TrainingRunOwner


class _Arbiter:
    def __init__(self, state="IDLE"):
        self._state = state

    def state(self):
        return self._state


def _identity(pid=4242, ticks=999):
    return lambda: {"pid": pid, "started_ticks": ticks}


def _lease(**overrides):
    lease = {"device": "cuda", "binding_id": "binding-1", "leases": []}
    lease.update(overrides)
    return lease


def _owner(tmp_path, *, state="IDLE", identity=None, clock=lambda: 100.0):
    return TrainingRunOwner(arbiter=_Arbiter(state), identity=identity or _identity(), clock=clock)


def test_a_free_gpu_is_acquired_and_the_claim_is_recorded(tmp_path):
    owner = _owner(tmp_path)
    receipt = owner.acquire(run_root=tmp_path, dataset_sha256="a" * 64, config_sha256="b" * 64,
                            gpu_lease=_lease())
    assert receipt["device"] == "cuda" and receipt["gpu_binding_id"] == "binding-1"
    written = json.loads((tmp_path / "training-owner.json").read_text())
    assert written == {key: value for key, value in receipt.items() if key != "gpu_binding_id"}
    assert not (tmp_path / "training-owner.json.partial").exists()


def test_collection_the_broker_or_another_training_run_blocks_the_gpu(tmp_path):
    for kind in ("collection", "broker", "training"):
        with pytest.raises(ValueError, match="TRAINING_GPU_BUSY"):
            _owner(tmp_path).acquire(run_root=tmp_path, dataset_sha256="a" * 64,
                                     config_sha256="b" * 64,
                                     gpu_lease=_lease(leases=[{"kind": kind}]))
    assert not (tmp_path / "training-owner.json").exists()   # nothing was claimed


def test_a_busy_arbiter_or_a_non_cuda_binding_is_refused(tmp_path):
    with pytest.raises(ValueError, match="TRAINING_ARBITER_BUSY"):
        _owner(tmp_path, state="COLLECTION").acquire(run_root=tmp_path, dataset_sha256="a" * 64,
                                                     config_sha256="b" * 64, gpu_lease=_lease())
    for bad in ({"device": "cpu", "binding_id": "b", "leases": []},
                {"device": "cuda", "binding_id": "", "leases": []},
                {"device": "cuda", "binding_id": "b"},
                {"device": "cuda", "leases": []}):
        with pytest.raises(ValueError, match="TRAINING_GPU_LEASE_INVALID"):
            _owner(tmp_path).acquire(run_root=tmp_path, dataset_sha256="a" * 64,
                                     config_sha256="b" * 64, gpu_lease=bad)


def test_an_existing_claim_is_re_read_so_no_run_inherits_a_finished_lease(tmp_path):
    owner = _owner(tmp_path)
    owner.acquire(run_root=tmp_path, dataset_sha256="a" * 64, config_sha256="b" * 64,
                  gpu_lease=_lease())
    # the same live owner re-acquiring its own claim is fine
    assert _owner(tmp_path).acquire(run_root=tmp_path, dataset_sha256="a" * 64,
                                    config_sha256="b" * 64,
                                    gpu_lease=_lease())["owner_pid"] == 4242
    # a recycled PID, a stale heartbeat, or a different dataset or config is refused
    with pytest.raises(ValueError, match="TRAINING_OWNER_IDENTITY_DRIFT"):
        _owner(tmp_path, identity=_identity(pid=5151)).acquire(
            run_root=tmp_path, dataset_sha256="a" * 64, config_sha256="b" * 64,
            gpu_lease=_lease())
    with pytest.raises(ValueError, match="TRAINING_HEARTBEAT_EXPIRED"):
        _owner(tmp_path, clock=lambda: 1000.0).acquire(
            run_root=tmp_path, dataset_sha256="a" * 64, config_sha256="b" * 64,
            gpu_lease=_lease())
    with pytest.raises(ValueError, match="TRAINING_DATASET_MISMATCH"):
        _owner(tmp_path).acquire(run_root=tmp_path, dataset_sha256="c" * 64,
                                 config_sha256="b" * 64, gpu_lease=_lease())
    with pytest.raises(ValueError, match="TRAINING_CONFIG_MISMATCH"):
        _owner(tmp_path).acquire(run_root=tmp_path, dataset_sha256="a" * 64,
                                 config_sha256="c" * 64, gpu_lease=_lease())
    # the failed attempts left the original claim intact: evidence is preserved
    assert json.loads((tmp_path / "training-owner.json").read_text())["owner_pid"] == 4242
    with pytest.raises(ValueError, match="TRAINING_RUN_ROOT_INVALID"):
        _owner(tmp_path / "absent").acquire(run_root=tmp_path / "absent",
                                            dataset_sha256="a" * 64, config_sha256="b" * 64,
                                            gpu_lease=_lease())

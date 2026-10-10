"""The collection request crosses every process boundary the way --collection always did (CP-3428, CP-3456).

act_diagnostic_episode (CLI) -> CollectionOptions -> coordinator composition -> the Worker specification file -> the Worker process
(`_build_worker_from_spec`) -> the Worker runtime. The record-only bag recorder is the data path exactly when the collection is on,
so the specification carries no separate switch's value of its own; nothing here reads `os.environ`.
"""
import json

import pytest

from so101_demo.act.collection_orchestration import CollectionOptions
from test_parallel_batch_cli import _scratch_root, argv, local_start_guard, verified  # noqa: F401  (the offline start-guard seam)


class Probe:
    def snapshot(self):
        from so101_demo.parallel_batch.resources import ResourceSnapshot
        return ResourceSnapshot(32, 64.0, 16.0)

    def ros_domain_in_use(self, _domain):
        return False

    def socket_in_use(self, _path):
        return False


class Supervisor:
    def start(self, role, command, **_kwargs):
        return None


def composition_with(collection, name, **extra):
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch

    root = _scratch_root() / name
    spec = prepare_batch(
        argv(root, worker_count="1", point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda _spec: {**verified(_spec), "image_id": "sha256:" + "b" * 64})
    return ProductionBatchComposition(spec, resource_probe=Probe(), claim_root=_scratch_root() / (name + "-claims"),
                                      supervisor=Supervisor(), collection=collection, **extra,
                                      broker_command_builder=lambda owner: ("docker", "run", str(owner.broker_spec_path)))


@pytest.mark.parametrize("mode", ["on", "off"])
def test_the_collection_option_is_in_the_worker_specification_and_the_worker_runtime_receives_it(mode, monkeypatch):
    from so101_demo.cli import mujoco_parallel_batch

    monkeypatch.delenv("SO101_RAW_PILOT", raising=False)   # nothing ambient: the option travels in the specification
    from so101_demo.act import frozen_runtime_inputs

    # the Worker re-reads the frozen Recorder policy from the manifest; the manifest itself is not under test here
    monkeypatch.setattr(frozen_runtime_inputs, "load_recorder_frozen_policy", lambda _path: {"ready_timeout_s": 5.0})
    from unittest import mock

    from so101_demo.runtime.act_diagnostic_episode_station import DiagnosticEpisodeStation

    monkeypatch.setattr(DiagnosticEpisodeStation, "bind", classmethod(lambda cls, manifest, scope: mock.MagicMock()))
    scratch = _scratch_root()
    composition = composition_with(CollectionOptions(mode), f"chain-{mode}",
                                   episode_scope_path=str(scratch / "scope.json"),
                                   episode_inputs_manifest=str(scratch / "inputs" / "inputs-manifest.json"))
    path = composition.worker_specs[0]
    document = json.loads(path.read_text())
    assert document["collection"] == {"mode": mode, "fault": "none", "sandbox_root": None, "raw_pilot": mode == "on"}
    seen = {}
    real = mujoco_parallel_batch.build_worker_runtime

    def capture(resources, run_mode, **kwargs):
        seen["collection"] = kwargs.get("collection")
        return real(resources, run_mode, **kwargs)

    monkeypatch.setattr(mujoco_parallel_batch, "build_worker_runtime", capture)
    _worker, runtime = mujoco_parallel_batch._build_worker_from_spec(path)
    assert seen["collection"] == CollectionOptions(mode)
    assert runtime._collection.enabled is (mode == "on") and runtime._collection.raw_pilot is (mode == "on")

"""Task 11A runtime adapter: no scenario work without an admitted lease."""

from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.parallel_collection_runtime import ActFixedCollectionRuntime
from so101_demo.act.collection import AttemptLedger


class _LeasePort:
    def __init__(self, *, admitted=True, epoch=4):
        self._admitted, self._epoch = admitted, epoch
        self.calls = 0

    def lease(self):
        self.calls += 1
        return {"admitted": self._admitted, "reset_epoch": self._epoch}


class _ResetPort:
    def __init__(self):
        self.calls = 0

    def reset(self, scenario):
        self.calls += 1
        return {"reset_epoch": 4, "ready": True, "proof": {"graph_clear": True},
                "scene_sha256": "a" * 64}


class _JointsPort:
    def read(self):
        return [0.0] * 7


class _PhasePort:
    def __init__(self, *, infra_at=None):
        self.phases, self._infra_at = [], infra_at

    def run(self, phase, prepared):
        self.phases.append(phase)
        return {"phase": phase, "infra_fault": phase == self._infra_at}


class _Recorder:
    def __init__(self):
        self.rows = []

    def append(self, row):
        self.rows.append(row)


class _QCPort:
    def verdict(self, prepared, phases):
        return "PASS"


def _runtime(**overrides):
    defaults = dict(lease_port=_LeasePort(), reset_port=_ResetPort(), joints_port=_JointsPort(),
                    phase_port=_PhasePort(), recorder_port=_Recorder(), qc_port=_QCPort(),
                    ledger=AttemptLedger())
    defaults.update(overrides)
    return ActFixedCollectionRuntime(**defaults)


def _context(scene_id="act-1"):
    return SimpleNamespace(scenario={"scene_id": scene_id, "split": "train", "xy": [0.1, 0.0],
                                     "arm_q": [0.0] * 6, "search_start_rad": 0.0, "seed": 1,
                                     "config_sha256": "a" * 64})


def test_one_scenario_is_prepared_once_and_collected_inside_an_admitted_lease():
    runtime = _runtime()
    record = runtime.collect("act-1", _context(), {"wave_index": 0})
    assert record["status"] == "PASSED" and record["scene_id"] == "act-1"
    assert runtime.reset_port.calls == 1                       # one reset, in preparation only
    assert runtime.phase_port.phases[0] == "SEARCH"
    assert len(runtime.recorder_port.rows) == len(runtime.phase_port.phases)
    assert runtime.ledger.terminal("act-1") == record


def test_no_scenario_work_happens_without_an_admitted_lease():
    runtime = _runtime(lease_port=_LeasePort(admitted=False))
    with pytest.raises(ValueError, match="ACT_COLLECTION_LEASE_UNAVAILABLE"):
        runtime.collect("act-1", _context(), {"wave_index": 0})
    assert runtime.reset_port.calls == 0                       # not even a reset
    assert runtime.phase_port.phases == []
    # with an ADMITTED lease, a scene the context does not describe is still refused
    admitted = _runtime()
    with pytest.raises(ValueError, match="ACT_COLLECTION_SCENARIO_UNAVAILABLE"):
        admitted.collect("act-9", _context(), {"wave_index": 0})
    assert admitted.reset_port.calls == 0


def test_the_boundary_wrapper_is_used_when_supplied_and_infra_faults_propagate():
    seen = []

    def boundary(work):
        seen.append("enter")
        return work(_context().scenario)

    runtime = _runtime(boundary=boundary)
    assert runtime.collect("act-1", _context(), {"wave_index": 0})["status"] == "PASSED"
    assert seen == ["enter"]

    failing = _runtime(phase_port=_PhasePort(infra_at="RECORD"))
    with pytest.raises(RuntimeError, match="COLLECTION_INFRA_FAULT"):
        failing.collect("act-1", _context(), {"wave_index": 0})
    assert failing.ledger.terminal("act-1") is None            # nothing sealed on an infra fault

"""Directed tests for the monitor-neutral original router with a local primary.

The router must deliver every routed original to the local observer and to the
writer sink, latch an invalid original on the primary before the sink runs, and
retire the local primary without importing a monitor module on the local path.
"""

import json
import os
import subprocess
import sys

import pytest

from so101_demo.adapters.act.head_original_router import HeadOriginalRouter
from test_act_head_local_observer import (clock_record, image_record, info_record, joint_record,
                                          observer_setup)


def router_setup(monkeypatch):
    row = observer_setup(monkeypatch, bind_port_sink=False)
    rows = []
    router = HeadOriginalRouter(row.port, lambda kind, record: rows.append((kind, record)))
    router.bind_primary(row.observer)
    return row, router, rows


def test_local_router_imports_no_monitor_module_in_a_fresh_interpreter():
    script = ('import json, sys\n'
              'import so101_demo.adapters.act.head_original_router\n'
              'print(json.dumps(sorted(name for name in sys.modules if "monitor" in name)))\n')
    process = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                             env=dict(os.environ), timeout=120)
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout.strip()) == []


def test_router_delivers_every_original_to_the_observer_and_the_sink(monkeypatch):
    row, router, rows = router_setup(monkeypatch)
    assert row.port._head_original_sink is None
    router('CLOCK', clock_record(row.clock, 1.0))
    router('IMAGE', image_record(row.clock, 1.0))
    router('INFO', info_record(row.clock, 1.0))
    router('JOINT', joint_record(row.clock, 1.0, sequence=1))
    assert [kind for kind, _ in rows] == ['CLOCK', 'IMAGE', 'INFO', 'JOINT']
    snapshot = row.observer.snapshot()
    assert snapshot['clock']['source_ns'] == round(1.0e9)
    assert snapshot['image']['source_ns'] == round(1.0e9)
    assert snapshot['info']['source_ns'] == round(1.0e9)
    assert snapshot['joint']['sequence'] == 1
    assert row.state.faulted is False


def test_router_delivers_a_copy_so_a_sink_mutation_cannot_rewrite_the_original(monkeypatch):
    row, router, rows = router_setup(monkeypatch)
    router('CLOCK', clock_record(row.clock, 1.0))
    rows[-1][1]['source_ns'] = 999
    rows[-1][1]['valid'] = False
    snapshot = row.observer.snapshot()
    assert snapshot['clock']['source_ns'] == round(1.0e9)
    assert snapshot['clock']['valid'] is True


def test_router_latches_the_primary_fault_before_the_sink_runs(monkeypatch):
    row = observer_setup(monkeypatch, bind_port_sink=False)
    seen = []
    router = HeadOriginalRouter(row.port, lambda kind, record: seen.append(row.state.faulted))
    router.bind_primary(row.observer)
    router('CLOCK', clock_record(row.clock, 1.0))
    router('CLOCK', clock_record(row.clock, 1.0))
    assert seen == [False, True]
    assert row.state.faulted is True
    assert row.state.snapshot['fault']['reason'] == 'HEAD_LOCAL_OBSERVER_CLOCK_NONADVANCING'


def test_router_refuses_a_foreign_primary_a_second_bind_and_a_closed_observer(monkeypatch):
    row, router, rows = router_setup(monkeypatch)
    with pytest.raises((ValueError, PermissionError)):
        router.bind_primary(object())
    with pytest.raises(PermissionError):
        router.bind_primary(row.observer)
    other = observer_setup(monkeypatch, bind_port_sink=False)
    with pytest.raises(ValueError):
        router.bind_primary(other.observer)
    other.observer.close()
    other_router = HeadOriginalRouter(other.port, lambda kind, record: None)
    with pytest.raises(ValueError):
        other_router.bind_primary(other.observer)


def test_router_retire_faults_the_local_primary_and_stops_delivery(monkeypatch):
    row, router, rows = router_setup(monkeypatch)
    router('CLOCK', clock_record(row.clock, 1.0))
    before = row.observer.snapshot()['clock']
    router.retire()
    assert row.observer.failed is True and row.state.faulted is True
    assert row.state.snapshot['fault']['reason'] == 'HEAD_PRIMARY_ORIGINAL_ROUTER_RETIRED'
    router('CLOCK', clock_record(row.clock, 1.1))
    assert row.observer.snapshot()['clock'] == before
    assert [kind for kind, _ in rows] == ['CLOCK', 'CLOCK']

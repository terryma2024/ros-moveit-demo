"""Disk dispatch guard uses real free blocks; observations carry no authority."""

import importlib
import json
from types import SimpleNamespace

import pytest


def module():
    return importlib.import_module('so101_demo.runtime.container_campaign.resource_log')


def test_free_space_reads_requested_filesystem_and_available_blocks(tmp_path, monkeypatch):
    mod = module()
    roots = (tmp_path/'first', tmp_path/'second')
    for root in roots:
        root.mkdir()
    seen = []

    def statvfs(path):
        seen.append(path)
        return SimpleNamespace(f_bavail=3 if path == roots[0] else 7, f_frsize=4096,
                               f_bfree=999999)

    monkeypatch.setattr(mod.os, 'statvfs', statvfs)
    assert [mod.read_disk_free_bytes(root) for root in roots] == [12288, 28672]
    assert seen == list(roots)


@pytest.mark.parametrize('free,floor,allowed', [(0,0,False), (1,0,True),
                                               (10,10,False), (11,10,True)])
def test_guard_stops_at_frozen_floor_without_candidate_budget(free, floor, allowed):
    assert module().check_disk_dispatch_guard(free, approved_floor_bytes=floor) is allowed


@pytest.mark.parametrize('free,floor', [(True,0), (-1,0), (1,False), (1,-1), (1.0,0)])
def test_unknown_or_invalid_space_cannot_allow_dispatch(free, floor):
    with pytest.raises(ValueError, match='DISK_DISPATCH_GUARD_INVALID'):
        module().check_disk_dispatch_guard(free, approved_floor_bytes=floor)


@pytest.mark.parametrize('error', [OSError('ENOSPC'), PermissionError('space unreadable')])
def test_read_failure_is_not_replaced_by_zero_or_infinity(tmp_path, monkeypatch, error):
    mod = module()
    def fail(path):
        raise error
    monkeypatch.setattr(mod.os, 'statvfs', fail)
    with pytest.raises(type(error), match=str(error)):
        mod.read_disk_free_bytes(tmp_path)


def test_high_utilization_and_missing_nvml_are_only_retained_observations(tmp_path):
    log = tmp_path/'resource.jsonl'
    observed = {'gpu_utilization': {'value':100, 'unit':'percent', 'source':'selected UUID NVML'}}
    missing = {'gpu_memory': {'reason':'NVML unavailable', 'source':'selected UUID NVML'}}
    module().append_resource_log(log, monotonic_ns=100, observed=observed, missing=missing)
    module().append_resource_log(log, monotonic_ns=200, observed={}, missing={})
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows == [{'monotonic_ns':100, 'observed':observed, 'missing':missing},
                    {'monotonic_ns':200, 'observed':{}, 'missing':{}}]
    assert module().check_disk_dispatch_guard(1, approved_floor_bytes=0)


def test_nonfinite_observation_refused_before_appending(tmp_path):
    log = tmp_path/'resource.jsonl'
    with pytest.raises(ValueError):
        module().append_resource_log(log, monotonic_ns=100,
                                    observed={'rtf':float('nan')}, missing={})
    assert not log.exists()


def test_log_refuses_symlink_target(tmp_path):
    target = tmp_path/'foreign.jsonl'
    target.write_text('preserved\n')
    link = tmp_path/'resource.jsonl'
    link.symlink_to(target)
    with pytest.raises(OSError):
        module().append_resource_log(link, monotonic_ns=100, observed={}, missing={})
    assert target.read_text() == 'preserved\n'

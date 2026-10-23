"""Admission of the instance launcher of a collection start: containers only.

Native collection is retired (mount-tree migration M4): a `native` launcher is refused before any resource is taken, as is any
other unknown value. A stale registry record of a native launch that is not proven stopped still blocks `finish` (a campaign
started before the retirement). Real: admission, the SQLite store, the slot registry and the closed payload schema. Controlled:
the campaign files and the GPU inventory (the container collection fixtures).
"""

from dataclasses import replace

import pytest

from test_container_collection_admission import assert_nothing_acquired, fixture, terminated_services


def test_a_native_launcher_is_refused_before_any_resource(tmp_path):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match='INSTANCE_LAUNCHER_INVALID'):
            workload.start(replace(spec, payload=dict(spec.payload, instance_launcher='native')), allow_existing=False)
        assert_nothing_acquired(workload, store)
    finally:
        store.close()


@pytest.mark.parametrize('payload_edit', ['missing', 'unknown'])
def test_the_launcher_is_a_closed_required_payload_field(tmp_path, payload_edit):
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        payload = dict(spec.payload)
        if payload_edit == 'missing':
            del payload['instance_launcher']
            expected = 'CAMPAIGN_START_SCHEMA'
        else:
            payload['instance_launcher'] = 'docker'
            expected = 'INSTANCE_LAUNCHER_INVALID'
        with pytest.raises(ValueError, match=expected):
            workload.start(replace(spec, payload=payload), allow_existing=False)
        assert_nothing_acquired(workload, store)
    finally:
        store.close()


def test_finish_does_not_settle_a_native_instance_whose_stop_is_unproven(tmp_path):
    from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
    paths, slot, spec, store, workload, inspect = fixture(tmp_path)
    try:
        context = workload.start(spec, allow_existing=False)
        terminated_services(paths, inspect)
        owned = paths['run']/'wave-0'/'w00'/'g1'
        owned.mkdir(parents=True)
        registry = ContainerLaunchRegistry(paths['host']/'launches.sqlite3', create=False)
        registry.register(ContainerLaunch(launch_id='wave-0-w00-g1', role='shard', worker_id='w00', wave_id='wave-0',
            launch_generation=1, container_name=None, image_digest=None, owned_root=str(owned),
            session_id='act-session-w00-g1', launcher='native'))
        registry.close()
        with pytest.raises(ValueError, match='ACT_CONTAINER_CLEANUP_NOT_CONFIRMED'):
            workload.finish(context, cleanup_confirmed=True)
        assert workload.slot_registry.slots() == (slot,)
        assert store._query_one('SELECT * FROM gpu_workload_leases') is not None
    finally:
        store.close()

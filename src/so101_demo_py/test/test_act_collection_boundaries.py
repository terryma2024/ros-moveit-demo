"""Original boundary retention in the existing audit; controlled source records only."""

import base64
import copy
import hashlib
import json

import pytest

from test_act_episode_audit import complete_audit


def original_reset(identity):
    """The V3 verified-reset boundary: the first evidence of the epoch the Recorder retained, on the producer's clock."""
    clock={'sim_time_ns':0,'begin_monotonic_ns':10_000_000_000,'end_monotonic_ns':10_000_000_000}
    return dict(kind='ACT_VERIFIED_RESET_BOUNDARY',schema_version=3,
        session_id=identity['session_id'],attempt_id=identity['attempt_id'],reset_epoch=identity['reset_epoch'],
        source_clock=clock,physical_source=dict(
            session_id=identity['session_id'],reset_epoch=identity['reset_epoch'],simulation_step=0,
            publisher_sequence=1,simulation_time_s=0.,received_wall_s=10.0))


@pytest.mark.parametrize('fault',[None,'foreign','clock','bool_clock','extra','duplicate','v1'])
def test_sole_audit_retains_original_reset_boundary_and_rejects_bad_or_repeated(tmp_path,fault):
    from so101_demo.act.episode_audit import verify_audit_manifest
    writer,window=complete_audit(tmp_path)
    append=getattr(writer,'append_collection_boundary',None)
    assert callable(append),'collection audit has no original reset boundary retention'
    value=original_reset(writer.identity)
    if fault=='foreign':value['reset_epoch']+=1
    if fault=='clock':value['physical_source']['simulation_time_s']+=.002
    if fault=='bool_clock':value['source_clock']['sim_time_ns']=False
    if fault=='v1':value['schema_version']=1
    if fault=='extra':value['command_authority']=True
    if fault=='duplicate':append('verified_reset',value)
    if fault is not None:
        with pytest.raises((ValueError,TypeError)):append('verified_reset',value)
    else:
        append('verified_reset',value)
        path=writer.seal(window)
        assert verify_audit_manifest(path)['identity']==writer.identity
        event=json.loads(path.parent.joinpath('events.jsonl').read_text().splitlines()[-1])
        assert event['payload']['collection_boundary']['value']==value


def test_original_capture_start_clock_survives_seal_readback(tmp_path):
    from so101_demo.act.episode_audit import verify_audit_manifest
    writer,window=complete_audit(tmp_path)
    append=getattr(writer,'append_collection_boundary',None)
    assert callable(append),'actual capture-start clock cannot be retained'
    clock={'sim_time_ns':1_000_000_000,'begin_monotonic_ns':11_000_000_000,'end_monotonic_ns':11_000_000_001}
    append('capture_start',clock)
    path=writer.seal(window)
    assert verify_audit_manifest(path)['identity']==writer.identity
    event=json.loads(path.parent.joinpath('events.jsonl').read_text().splitlines()[-1])
    assert event['payload']['collection_boundary']['value']==clock


@pytest.mark.parametrize('fault',['clock_mapping','scope','duplicate','bool_clock'])
def test_sealed_reader_refuses_resigned_boundary_tamper_after_positive_control(tmp_path,fault):
    from so101_demo.act.episode_audit import verify_audit_manifest
    writer,window=complete_audit(tmp_path)
    writer.append_collection_boundary('verified_reset',original_reset(writer.identity))
    path=writer.seal(window)
    assert verify_audit_manifest(path)['identity']==writer.identity
    events=path.parent/'events.jsonl'
    rows=[json.loads(line) for line in events.read_text().splitlines()]
    row=rows[-1];value=row['payload']['collection_boundary']['value']
    if fault=='clock_mapping':row['sim_time_s']+=.002
    if fault=='scope':value['attempt_id']='foreign'
    if fault=='bool_clock':value['source_clock']['sim_time_ns']=False
    if fault=='duplicate':
        extra=copy.deepcopy(row);extra['sequence']+=1;extra['task_sequence']+=1;rows.append(extra)
    events.write_text(''.join(json.dumps(item,sort_keys=True,separators=(',',':'))+'\n' for item in rows))
    manifest=json.loads(path.read_bytes())
    manifest['files']['events.jsonl'].update(sha256=hashlib.sha256(events.read_bytes()).hexdigest(),size=events.stat().st_size)
    path.write_text(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n')
    with pytest.raises(ValueError,match='COLLECTION_|AUDIT_EVENT_INVALID'):verify_audit_manifest(path)


def test_the_expert_sequence_boundary_stage_is_gone_the_terminal_event_replaces_it():
    """REPLACED_BY: test_teacher_collection (the terminal V2 event follows normal_stop); contract removed, plan R9.9."""
    from so101_demo.act.collection_boundaries import validate_collection_boundary
    now=10_000_000_100
    clock=dict(sim_time_ns=5_000_000,begin_monotonic_ns=now,end_monotonic_ns=now+1)
    document=dict(kind='ACT_COLLECTION_BOUNDARY',schema_version=2,stage='expert_sequence_complete',
        value=dict(source_clock=clock,phase='RETREAT',sequence=3))
    with pytest.raises(ValueError,match='COLLECTION_BOUNDARY_STAGE_INVALID'):
        validate_collection_boundary(document)

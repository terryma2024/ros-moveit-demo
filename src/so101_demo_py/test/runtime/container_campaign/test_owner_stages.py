"""A run collected stage by stage equals the all-in-one run, and every stage that may not start is refused (controlled world)."""

import asyncio
import json
from dataclasses import replace

import pytest

from so101_demo.runtime.container_campaign import stage_records
from test_owner_retry import drive, retry_world


def staged_world(tmp_path, monkeypatch, **kwargs):
    """A world whose phase 1 ran with `stop_after_phase1`; the same owner then runs the later stages."""
    phase = retry_world(tmp_path, monkeypatch, rounds=0, **kwargs)
    phase.owner.stop_after_phase1 = True
    drive(phase)
    return phase


def stage(phase, name):
    async def run():
        return await getattr(phase.owner, 'stage_' + name)(phase.world.manifest)
    return asyncio.run(run())


def normalised(phase, name):
    """The document with this world's root name removed and the digests of files that contain that root left out."""
    raw = (phase.owner.root / name).read_text().replace(str(phase.owner.root), 'ROOT')

    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key != 'sha256'}
        return [strip(item) for item in value] if isinstance(value, list) else value
    return strip(json.loads(raw))


def test_phase1_phase2_finalize_equal_the_all_in_one_run(tmp_path, monkeypatch):
    (tmp_path / 'whole').mkdir()
    (tmp_path / 'staged').mkdir()
    whole = retry_world(tmp_path / 'whole', monkeypatch, rounds=0)
    result = drive(whole)
    staged = staged_world(tmp_path / 'staged', monkeypatch)
    assert not (staged.owner.root / 'collection-index.json').exists()
    stage(staged, 'phase2')
    assert not (staged.owner.root / 'collection-index.json').exists()
    final = stage(staged, 'finalize')
    assert final['processing'] == result['processing'] == 'COMPLETE'
    for name in ('collection-index.json', 'host/campaign-result.json', 'host/processing-result.json'):
        assert normalised(staged, name) == normalised(whole, name), name
    assert [call['round'] for call in staged.scheduler.calls] == [call['round'] for call in whole.scheduler.calls] == [0]
    assert [r['scene_id'] for r in staged.scheduler.calls[0]['rows']] == [r['scene_id'] for r in whole.scheduler.calls[0]['rows']]
    last = stage_records.read_record(staged.owner.root / 'host', stage_records.FINALIZE)
    assert last['previous']['stage'] == 'phase2'


def test_the_records_form_a_chain_and_name_the_runtime_values_of_each_stage(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.runtime_document = {'processor_count': 3}
    phase.owner.config = {n: v for n, v in phase.owner.config.items() if n != 'processor_count'}
    stage(phase, 'phase2')
    stage(phase, 'finalize')
    host = phase.owner.root / 'host'
    first, second, third = (stage_records.read_record(host, name) for name in ('phase1', 'phase2', 'finalize'))
    assert first['previous'] is None
    assert second['previous'] == dict(stage='phase1', sha256=first['sha256'])
    assert third['previous'] == dict(stage='phase2', sha256=second['sha256'])
    assert json.loads((host / 'runtime-used-phase2.json').read_text())['values']['processor_count'] == 3


def test_a_stage_run_twice_is_refused_and_does_nothing_the_second_time(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        stage(phase, 'phase2')
    stage(phase, 'finalize')
    before = (phase.owner.root / 'collection-index.json').read_bytes()
    with pytest.raises(ValueError, match='STAGE_ALREADY_COMPLETE'):
        stage(phase, 'finalize')
    assert len(phase.scheduler.calls) == 1 and (phase.owner.root / 'collection-index.json').read_bytes() == before


def test_phase2_and_finalize_need_the_stage_before_them(tmp_path, monkeypatch):
    phase = retry_world(tmp_path, monkeypatch, rounds=0)                       # no phase 1 record at all
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):
        stage(phase, 'finalize')
    phase.world.registry.close()
    (tmp_path / 'b').mkdir()
    one = staged_world(tmp_path / 'b', monkeypatch)
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_MISSING'):      # phase 1 only: nothing was processed
        stage(one, 'finalize')
    assert one.scheduler.calls == []


def test_a_changed_logic_document_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.context = replace(phase.owner.context, campaign_config_sha256='f' * 64)
    with pytest.raises(ValueError, match='STAGE_LOGIC_DOCUMENT_CHANGED'):
        stage(phase, 'phase2')
    assert phase.scheduler.calls == []


@pytest.mark.parametrize('field', ['source_sha256', 'runtime_config_sha256', 'collection_config_sha256',
                                   'contact_policy_fingerprint'])
def test_inputs_other_than_those_of_phase_1_are_refused(tmp_path, monkeypatch, field):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.context = replace(phase.owner.context, **{field: 'e' * 64})
    with pytest.raises(ValueError, match='STAGE_INPUTS_CHANGED'):
        stage(phase, 'phase2')


def test_other_images_than_those_of_phase_1_are_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    image = dict(phase.owner.config['shard_image'], digest='sha256:' + '9' * 64)
    phase.owner.config = {**phase.owner.config, 'shard_image': image}
    with pytest.raises(ValueError, match='STAGE_IMAGES_CHANGED'):
        stage(phase, 'phase2')


def test_a_phase1_result_changed_after_its_record_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    path = phase.owner.root / 'host/phase1-result.json'
    path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
        stage(phase, 'phase2')


def test_a_record_changed_after_its_successor_named_it_is_refused(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    stage(phase, 'phase2')
    path = stage_records.record_path(phase.owner.root / 'host', 'phase1')
    document = json.loads(path.read_bytes())
    document['scene_count'] += 1
    path.write_bytes(stage_records.canonical_json(document) + b'\n')
    with pytest.raises(ValueError, match='STAGE_PREVIOUS_RECORD_INVALID'):
        stage(phase, 'finalize')
    assert not (phase.owner.root / 'collection-index.json').exists()


def test_a_run_without_a_processing_scheduler_cannot_process(tmp_path, monkeypatch):
    phase = staged_world(tmp_path, monkeypatch)
    phase.owner.processing = None
    with pytest.raises(ValueError, match='STAGE_PROCESSING_UNAVAILABLE'):
        stage(phase, 'phase2')
    with pytest.raises(ValueError, match='STAGE_PROCESSING_UNAVAILABLE'):
        stage(phase, 'finalize')

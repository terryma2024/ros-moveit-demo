"""Parallel pre-training re-checks and the process-local verification memo (resolve, attach, export).

The verification seams (`result_store.verify_container_task_registration`, `processed_result.verify_processed_result`) are replaced in
this process by `schema4_entries`; the pool tests switch the start method to 'fork' so the workers inherit them. A seam that counts
calls writes to a file, because a forked worker's memory is not the parent's.
"""

import os
from pathlib import Path

import pytest

from so101_demo.act import bundle
from so101_demo.act.bundle import clear_verification_memo, export_dataset, resolve_committed_episodes
from so101_demo.act.training import attach_episode_content
from act_export_fixture import ROW_CONTENT
from test_act_bundle import frozen_index
from test_act_bundle_processed import schema4_entries

SCENES = ('001', '002', '003', '004')
MANIFEST = {"episodes": [{"scene_id": scene, "status": "PASSED"} for scene in SCENES]}
RECEIPT_CONFLICT = {'processed_result': dict(path='processed-result.json', sha256='0' * 64)}     # -> EPISODE_RECEIPT_CONFLICT
IDENTITY_INVALID = {'diagnostic_fault': 'topic_drop'}                                            # -> EPISODE_COLLECTION_IDENTITY_INVALID
DIGESTS = dict(source_manifest_sha256='a' * 64, campaign_index_sha256='b' * 64)


def count_regrades(monkeypatch, tmp_path, delay=0.0):
    """Wrap the processed readback (the expensive regrade) so every call, in any process, appends a line to a file."""
    import time
    from so101_demo.act import processed_result
    log = tmp_path / 'regrades.log'
    inner = processed_result.verify_processed_result

    def counted(output, **kwargs):
        with open(log, 'a') as handle:
            handle.write(str(output) + '\n')
        time.sleep(delay)
        return inner(output, **kwargs)
    monkeypatch.setattr(processed_result, 'verify_processed_result', counted)
    return lambda: len(log.read_text().splitlines()) if log.exists() else 0


@pytest.fixture
def fork_pool(monkeypatch):
    monkeypatch.setattr(bundle, '_POOL_START_METHOD', 'fork')


def workspace(tmp_path, monkeypatch, scenes=SCENES, **kwargs):
    entries, _, _ = schema4_entries(tmp_path, monkeypatch, scenes, **kwargs)
    return entries, frozen_index(tmp_path / 'collection-index.json', entries)


def full_pipeline(tmp_path, index, name, workers):
    resolved = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=workers)
    attached = attach_episode_content(resolved, root=tmp_path, workers=workers)
    exported = export_dataset(attached, tmp_path / name, workers=workers, **DIGESTS)
    return resolved, attached, exported


def tree_bytes(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(Path(root).rglob('*')) if path.is_file()}


def test_a_second_step_in_the_same_process_does_not_regrade_again(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001', '002'))
    regrades = count_regrades(monkeypatch, tmp_path)
    resolved = resolve_committed_episodes(manifest={"episodes": MANIFEST["episodes"][:2]}, campaign_index=index)
    assert regrades() == 2
    export_dataset(attach_episode_content(resolved, root=tmp_path), tmp_path / 'dataset', **DIGESTS)
    assert regrades() == 2          # attach and export are memo hits: one regrade per episode for the whole run


def test_the_memo_is_dropped_when_a_verified_file_changes(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001',))
    regrades = count_regrades(monkeypatch, tmp_path)
    manifest = {"episodes": MANIFEST["episodes"][:1]}
    resolve_committed_episodes(manifest=manifest, campaign_index=index)
    resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert regrades() == 1
    seal = Path(entries[0]['collection_evidence']['processing_output']) / 'episode' / 'seal.json'
    stat = seal.stat()
    os.utime(seal, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))          # same bytes, new mtime
    resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert regrades() == 2
    with open(seal, 'ab') as handle:                                              # a different size
        handle.write(b' ')
    resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert regrades() == 3
    clear_verification_memo()
    seal.write_bytes(seal.read_bytes()[:-1])
    resolve_committed_episodes(manifest=manifest, campaign_index=index)
    assert regrades() == 4


def test_a_memo_hit_is_a_copy_the_caller_cannot_use_to_alter_the_memo(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001',))
    first = bundle._verified_collection(entries[0])
    first[1]['export_eligible'] = False
    first[1]['injected'] = True
    second = bundle._verified_collection(entries[0])
    assert second[1]['export_eligible'] is True and 'injected' not in second[1]
    second[1]['status'] = 'FAIL'
    assert bundle._verified_collection(entries[0])[1]['status'] == 'PASS'


def test_a_caller_cannot_prime_the_memo_with_a_proof(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001',))
    regrades = count_regrades(monkeypatch, tmp_path)
    forged = dict(entries[0], proof={'status': 'PASS', 'export_eligible': True}, mode='formal',
                  _proof={'status': 'PASS'}, verification={'mode': 'formal'})
    bundle._verified_collection(forged)
    assert regrades() == 1                       # the extra fields bought nothing: the verification ran
    # an episode whose identity differs from the verified one does not hit the entry of the verified one
    altered = dict(entries[0], verifier_sha256='b' * 64)
    with pytest.raises(ValueError, match='EPISODE_RECEIPT_CONFLICT'):
        bundle._verified_collection(altered)
    assert regrades() == 2
    # a pre-filled dict is not a memo: the only public name is the clearing function
    assert [name for name in dir(bundle) if 'memo' in name.lower() and not name.startswith('_')] == ['clear_verification_memo']


def test_a_failure_is_never_remembered(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001',),
                               processed_overrides={'001': {'act_data_qc': 'FAIL', 'export_eligible': False}})
    regrades = count_regrades(monkeypatch, tmp_path)
    for expected in (1, 2):
        with pytest.raises(ValueError, match='EXPORT_EPISODE_DATA_QC_NOT_PASSED'):
            bundle._verified_collection(entries[0])
        assert regrades() == expected


def test_an_open_readback_session_is_decided_afresh_and_never_memoised(tmp_path, monkeypatch):
    from so101_demo.act.qc_session import qc_session
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001',))
    regrades = count_regrades(monkeypatch, tmp_path)
    with qc_session('readback:check-export'):
        bundle._verified_collection(entries[0])
        bundle._verified_collection(entries[0])
    assert regrades() == 2
    bundle._verified_collection(entries[0])
    assert regrades() == 3          # nothing was remembered by the session calls


def test_the_pool_gives_the_same_outputs_in_the_same_order_as_the_serial_path(tmp_path, monkeypatch, fork_pool):
    entries, index = workspace(tmp_path, monkeypatch)
    regrades = count_regrades(monkeypatch, tmp_path)
    serial = full_pipeline(tmp_path, index, 'dataset-serial', workers=1)
    assert regrades() == len(SCENES)
    clear_verification_memo()
    parallel = full_pipeline(tmp_path, index, 'dataset-parallel', workers=3)
    assert regrades() == 2 * len(SCENES)          # one regrade per episode in the pool, none again in the parent
    assert [item['scene_id'] for item in parallel[0]] == list(SCENES)
    assert parallel[0] == serial[0] and parallel[1] == serial[1]
    assert parallel[2]['export_sha256'] == serial[2]['export_sha256']
    assert tree_bytes(tmp_path / 'dataset-parallel') == tree_bytes(tmp_path / 'dataset-serial')


def test_workers_one_never_starts_a_pool(tmp_path, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError('pool started')
    monkeypatch.setattr(bundle, '_make_pool', forbidden)
    entries, index = workspace(tmp_path, monkeypatch)
    resolved, attached, exported = full_pipeline(tmp_path, index, 'dataset', workers=1)
    assert exported['scene_count'] == len(SCENES)


def test_the_environment_selects_the_worker_count(tmp_path, monkeypatch, fork_pool):
    entries, index = workspace(tmp_path, monkeypatch)
    started = []
    real = bundle._make_pool
    monkeypatch.setattr(bundle, '_make_pool', lambda workers: started.append(workers) or real(workers))
    monkeypatch.setenv('SO101_ACT_EXPORT_WORKERS', '2')
    resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)
    assert started == [2]
    monkeypatch.setenv('SO101_ACT_EXPORT_WORKERS', 'many')
    with pytest.raises(ValueError, match='EXPORT_WORKERS_INVALID'):
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index)
    for bad in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match='EXPORT_WORKERS_INVALID'):
            resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=bad)


@pytest.mark.parametrize('workers', [1, 3])
@pytest.mark.parametrize('failures,expected', [
    ({'003': RECEIPT_CONFLICT, '004': IDENTITY_INVALID}, 'EPISODE_RECEIPT_CONFLICT'),
    ({'003': IDENTITY_INVALID, '004': RECEIPT_CONFLICT}, 'EPISODE_COLLECTION_IDENTITY_INVALID'),
    ({'004': {'act_data_qc': 'FAIL', 'export_eligible': False}, '002': RECEIPT_CONFLICT}, 'EPISODE_RECEIPT_CONFLICT'),
])
def test_the_first_failure_in_manifest_order_is_the_one_raised(tmp_path, monkeypatch, fork_pool, workers, failures, expected):
    entries, index = workspace(tmp_path, monkeypatch, processed_overrides=failures)
    with pytest.raises(ValueError, match=expected):
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=workers)
    # attach and export meet the same refusal when the episodes are handed to them directly
    clear_verification_memo()
    with pytest.raises(ValueError, match=expected):
        attach_episode_content(tuple(entries), root=tmp_path, workers=workers)
    clear_verification_memo()
    with pytest.raises(ValueError, match=expected):
        export_dataset(tuple(dict(entry, content=ROW_CONTENT) for entry in entries), tmp_path / 'never', workers=workers, **DIGESTS)
    assert not (tmp_path / 'never').exists()


@pytest.mark.parametrize('workers', [1, 3])
def test_a_manifest_refusal_keeps_its_place_in_the_order(tmp_path, monkeypatch, fork_pool, workers):
    entries, index = workspace(tmp_path, monkeypatch, processed_overrides={'002': IDENTITY_INVALID, '003': IDENTITY_INVALID})
    episodes = MANIFEST["episodes"]
    # a manifest problem at the second episode precedes the third episode's verification failure, in either path
    with pytest.raises(ValueError, match='MANIFEST_INVALID'):
        resolve_committed_episodes(manifest={"episodes": [episodes[0], 'bad', episodes[2]]}, campaign_index=index, workers=workers)
    # and a verification failure at the second episode precedes a manifest problem at the third
    with pytest.raises(ValueError, match='EPISODE_COLLECTION_IDENTITY_INVALID'):
        resolve_committed_episodes(manifest={"episodes": [episodes[0], episodes[1], 'bad']}, campaign_index=index, workers=workers)


def tamper_frame(entry, name='frames/000000-head.png'):
    path = Path(entry['collection_evidence']['processing_output']) / 'episode' / name
    path.write_bytes(path.read_bytes() + b'x')


@pytest.mark.parametrize('workers', [1, 3])
def test_frame_digests_are_checked_every_time_and_an_earlier_frame_refusal_comes_first(tmp_path, monkeypatch, fork_pool, workers):
    entries, index = workspace(tmp_path, monkeypatch)
    resolved = resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=workers)
    attached = attach_episode_content(resolved, root=tmp_path, workers=workers)
    frame = Path(entries[1]['collection_evidence']['processing_output'], 'episode', 'frames/000000-head.png')
    good = frame.read_bytes()
    tamper_frame(entries[1])                                   # frames are inside the memoised tree: the memo is dropped, the digest checked
    with pytest.raises(ValueError, match='EXPORT_EPISODE_FRAME_DIGEST_MISMATCH'):
        export_dataset(attached, tmp_path / 'd1', workers=workers, **DIGESTS)
    broken = list(attached)
    broken[3] = dict(broken[3], scene_id='bad scene')          # a later, different refusal
    with pytest.raises(ValueError, match='EXPORT_EPISODE_FRAME_DIGEST_MISMATCH'):
        export_dataset(broken, tmp_path / 'd2', workers=workers, **DIGESTS)
    frame.unlink()
    with pytest.raises(ValueError, match='EXPORT_EPISODE_FRAME_MISSING'):
        export_dataset(attached, tmp_path / 'd3', workers=workers, **DIGESTS)
    frame.write_bytes(good)
    assert export_dataset(attached, tmp_path / 'd4', workers=workers, **DIGESTS)['scene_count'] == len(SCENES)
    assert not any((tmp_path / name).exists() for name in ('d1', 'd2', 'd3'))


def test_the_content_digest_checks_in_attach_still_run_after_a_memo_hit(tmp_path, monkeypatch):
    entries, index = workspace(tmp_path, monkeypatch, scenes=('001',))
    resolved = resolve_committed_episodes(manifest={"episodes": MANIFEST["episodes"][:1]}, campaign_index=index)
    attach_episode_content(resolved, root=tmp_path)
    with pytest.raises(ValueError, match='TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH'):
        attach_episode_content((dict(resolved[0], content={'frames': 1}, content_sha256='0' * 64),), root=tmp_path)
    # a records.jsonl that no longer hashes to the seal map is refused even though the commit is remembered: the file moved,
    # and, were the memo kept, the digest check after it would still run
    records = Path(entries[0]['collection_evidence']['processing_output']) / 'episode' / 'records.jsonl'
    records.write_bytes(records.read_bytes() + b' ')
    with pytest.raises(ValueError, match='TRAINING_EPISODE_CONTENT_DIGEST_MISMATCH'):
        attach_episode_content(resolved, root=tmp_path)


def test_a_guarded_session_still_refuses_before_any_worker_starts(tmp_path, monkeypatch):
    from so101_demo.act.qc_session import qc_session
    entries, index = workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(bundle, '_make_pool', lambda *_a: pytest.fail('pool started'))
    with qc_session('bundle'):
        with pytest.raises(ValueError, match='QC_SESSION_IN_EXPORT_PATH'):
            resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=4)
        with pytest.raises(ValueError, match='QC_SESSION_IN_EXPORT_PATH'):
            attach_episode_content(tuple(entries), root=tmp_path, workers=4)
        with pytest.raises(ValueError, match='QC_SESSION_IN_EXPORT_PATH'):
            export_dataset(tuple(entries), tmp_path / 'x', workers=4, **DIGESTS)
    # an entry point's own session shares a recomputation between its calls: serial, no pool, no memo
    with qc_session('readback:check-export'):
        assert len(resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=4)) == len(SCENES)


def test_a_real_spawned_pool_runs_and_leaves_the_refusal_to_the_serial_loop(tmp_path, monkeypatch):
    """No monkeypatched seam in the workers: the evidence does not exist, so every worker reports a failure and the parent raises."""
    entries = []
    for scene in SCENES:
        root = tmp_path / scene
        entries.append(dict(kind='ACT_COMMITTED_EPISODE', schema_version=4, scene_id=scene, split='train', verifier_sha256='c' * 64,
            task_result_sha256='e' * 64, processed_result_sha256='f' * 64,
            collection_evidence=dict(registration=str(root / 'journal' / ('task-' + scene) / 'collected.json'), owner_root=str(root / 'owner'),
                task_id='task-' + scene, result_location=str(root / 'sealed'), scope_path=str(root / 'scope.json'),
                inputs_manifest=str(root / 'inputs.json'), processing_output=str(root / 'processing' / scene / (scene + '-proc-1')))))
    index = frozen_index(tmp_path / 'collection-index.json', entries)
    assert bundle._POOL_START_METHOD == 'spawn'
    ran = []
    real = bundle._map_in_pool
    monkeypatch.setattr(bundle, '_map_in_pool', lambda function, arguments, workers: ran.append(len(arguments)) or real(function, arguments, workers))
    with pytest.raises(ValueError, match='EPISODE_COLLECTION_IDENTITY_INVALID') as parallel:
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=2)
    with pytest.raises(ValueError, match='EPISODE_COLLECTION_IDENTITY_INVALID') as serial:
        resolve_committed_episodes(manifest=MANIFEST, campaign_index=index, workers=1)
    assert ran == [4] and str(parallel.value) == str(serial.value)


def test_the_pool_is_faster_than_the_serial_regrade(tmp_path, monkeypatch, fork_pool):
    import time
    scenes = tuple(f'{number:03d}' for number in range(1, 9))
    entries, index = workspace(tmp_path, monkeypatch, scenes=scenes)
    manifest = {"episodes": [{"scene_id": scene, "status": "PASSED"} for scene in scenes]}
    count_regrades(monkeypatch, tmp_path, delay=0.4)
    started = time.monotonic()
    resolve_committed_episodes(manifest=manifest, campaign_index=index, workers=1)
    serial = time.monotonic() - started
    clear_verification_memo()
    started = time.monotonic()
    resolve_committed_episodes(manifest=manifest, campaign_index=index, workers=4)
    parallel = time.monotonic() - started
    print(f'SPEEDUP serial={serial:.2f}s parallel={parallel:.2f}s ratio={serial / parallel:.1f}')
    assert parallel < serial * 0.6

"""The bounded process pool of per-scene Host readbacks: same outputs as the serial path, failure is refusal, same code tree.

Fixtures are the two-instance journal of `test_task_commit_readback` (`Schedule`) with the per-scene readback replaced by
`readback_double.double` in both paths: in process for the serial path, and in real worker processes (started by the production
code, through a wrapper interpreter that installs the double after the packages are registered) for the pool. Nothing reads a host
evidence path.
"""

import functools
import json
import os
import stat
import sys

import pytest

from readback_double import double
from test_task_commit_readback import Schedule, schedule_factory  # noqa: F401 (fixture)
from so101_demo.runtime.container_campaign import readback_pool, result_verifier
from so101_demo.runtime.container_campaign.readback_pool import (
    assert_same_code_tree, default_readback_workers, import_identity, resolve_readback_workers, run_readbacks,
)

SCENES = [f's{index}' for index in range(6)]
WAVE_INVALID = 'CONTAINER_WAVE_COMMIT_READBACK_INVALID'


@pytest.fixture
def wrapper(tmp_path):
    """An interpreter that runs the worker bootstrap with the double installed after the packages are registered."""
    path = tmp_path/'python-with-double'
    path.write_text(f'#!{sys.executable}\nimport sys\nsource = sys.argv[2]\nmarker = "sys.exit(worker_main(request))"\n'
                    'assert marker in source\n'
                    'exec(compile(source.replace(marker, "import readback_double; readback_double.install(); " + marker),'
                    ' "<bootstrap>", "exec"))\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


@pytest.fixture
def schedule(schedule_factory, wrapper, monkeypatch):  # noqa: F811
    value = schedule_factory(SCENES, qualification=False)
    for index, scene in enumerate(SCENES):
        value.run_task('w00' if index % 2 == 0 else 'w01', scene)
    monkeypatch.setattr(result_verifier, 'verify_container_task_registration', double)
    monkeypatch.setattr(result_verifier, 'run_readbacks', functools.partial(run_readbacks, _executable=wrapper))
    return value


def tree(run):
    return sorted((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in run.rglob('*') if path.is_file())


def chain(error):
    parts = []
    while error is not None:
        parts.append(str(error))
        error = error.__cause__
    return parts


def verify_with(schedule, workers, timeout=None):
    schedule.verifier.readback_workers = workers
    if timeout is not None:
        schedule.verifier.readback_timeout_s = timeout
    return schedule.verify()


def plan_of(monkeypatch, **options):
    monkeypatch.setenv('READBACK_DOUBLE', json.dumps(options))


def test_pool_and_serial_give_the_same_wave_record_whatever_order_the_scenes_finish(schedule, monkeypatch, tmp_path):
    log = tmp_path/'finished.log'
    monkeypatch.setenv('READBACK_DOUBLE_LOG', str(log))
    plan_of(monkeypatch, s0=dict(sleep=3.0), s2=dict(sleep=2.0), s4=dict(sleep=1.0))
    before = tree(schedule.run)
    serial = verify_with(schedule, 1)
    log.unlink()
    pooled = verify_with(schedule, 3)
    finished = log.read_text().split()
    assert sorted(finished) == sorted(SCENES) and finished != SCENES        # completion order was shuffled
    assert pooled == serial
    assert json.dumps(pooled, sort_keys=True) == json.dumps(serial, sort_keys=True)
    assert [row['scene_id'] for row in pooled['case_results']] == SCENES     # committed in scene order
    assert tree(schedule.run) == before                                      # the readback wrote nothing


def test_workers_one_is_the_in_process_serial_path(schedule, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('a worker process was started')

    monkeypatch.setattr(readback_pool.subprocess, 'run', forbidden)
    assert [row['scene_id'] for row in verify_with(schedule, 1)['case_results']] == SCENES


def test_a_wave_of_one_scene_never_starts_a_worker(schedule_factory, wrapper, monkeypatch):  # noqa: F811
    one = schedule_factory(['only'], qualification=False)
    one.run_task('w00', 'only')
    monkeypatch.setattr(result_verifier, 'verify_container_task_registration', double)
    monkeypatch.setattr(readback_pool.subprocess, 'run', lambda *a, **k: pytest.fail('a worker process was started'))
    assert len(verify_with(one, 4)['case_results']) == 1


@pytest.mark.parametrize('failure, expected', [(dict(crash=True), 'CONTAINER_READBACK_WORKER_EXITED:s3:9'),
                                               (dict(garbage=True), 'CONTAINER_READBACK_WORKER_EXITED:s3:3')])
def test_a_crashing_or_unreadable_worker_refuses_the_wave(schedule, monkeypatch, failure, expected):
    plan_of(monkeypatch, s3=failure)
    before = tree(schedule.run)
    with pytest.raises(ValueError, match=WAVE_INVALID) as error:
        verify_with(schedule, 3)
    assert chain(error.value) == [WAVE_INVALID, expected]
    assert tree(schedule.run) == before


def test_a_hanging_worker_times_out_into_a_refusal(schedule, monkeypatch):
    plan_of(monkeypatch, s3=dict(hang=True))
    with pytest.raises(ValueError, match=WAVE_INVALID) as error:
        verify_with(schedule, 3, timeout=6)
    assert chain(error.value) == [WAVE_INVALID, 'CONTAINER_READBACK_WORKER_TIMEOUT:s3']


def test_a_missing_result_file_is_unreadable_not_a_pass(schedule, monkeypatch, wrapper, tmp_path):
    # an interpreter that exits 0 without ever running the worker: no result file
    silent = tmp_path/'silent'
    silent.write_text('#!/bin/sh\ncat > /dev/null\nexit 0\n')
    silent.chmod(0o755)
    monkeypatch.setattr(result_verifier, 'run_readbacks', functools.partial(run_readbacks, _executable=str(silent)))
    with pytest.raises(ValueError, match=WAVE_INVALID) as error:
        verify_with(schedule, 2)
    assert chain(error.value) == [WAVE_INVALID, 'CONTAINER_READBACK_WORKER_UNREADABLE:s0']


def test_a_refusal_in_a_worker_is_the_serial_refusal_and_the_first_in_scene_order_wins(schedule, monkeypatch):
    plan_of(monkeypatch, s2=dict(sleep=2.0, refuse=True), s4=dict(refuse=True))   # row order: s0 s2 s4 s1 s3 s5
    with pytest.raises(ValueError, match=WAVE_INVALID) as serial:
        verify_with(schedule, 1)
    with pytest.raises(ValueError, match=WAVE_INVALID) as pooled:
        verify_with(schedule, 3)
    assert chain(serial.value) == chain(pooled.value) == [WAVE_INVALID, 'REFUSED:s2']


def test_scenes_after_a_known_failure_are_not_started(tmp_path, wrapper, monkeypatch):
    log = tmp_path/'finished.log'
    monkeypatch.setenv('READBACK_DOUBLE_LOG', str(log))
    plan_of(monkeypatch, s0=dict(refuse=True))
    jobs = [dict(scene_id=f's{index}', registration=str(tmp_path/f'r{index}.json'), scope='/x', inputs_manifest='/y')
            for index in range(5)]
    for index in range(5):
        (tmp_path/f'r{index}.json').write_text(json.dumps(dict(scene_id=f's{index}', task_id=f't{index}', worker_id='w00',
                                                               host_output='/o')))
    answers = run_readbacks(jobs, workers=1, _executable=wrapper)
    assert str(answers[0]) == 'REFUSED:s0'
    assert all('SKIPPED' in str(answer) for answer in answers[1:])
    assert log.read_text().split() == ['s0']


def test_a_worker_on_another_code_tree_refuses(schedule, monkeypatch):
    monkeypatch.setenv('READBACK_DOUBLE_TREE', 'worker-side')
    with pytest.raises(ValueError, match=WAVE_INVALID) as error:
        verify_with(schedule, 2)
    assert chain(error.value) == [WAVE_INVALID, 'CONTAINER_READBACK_WORKER_EXITED:s0:3']


def test_a_reply_from_another_code_tree_is_refused_by_the_parent(schedule, monkeypatch):
    monkeypatch.setenv('READBACK_DOUBLE_TREE', 'parent-side')
    with pytest.raises(ValueError, match=WAVE_INVALID) as error:
        verify_with(schedule, 2)
    assert chain(error.value) == [WAVE_INVALID, 'READBACK_WORKER_CODE_TREE_MISMATCH:s0']


def test_a_request_naming_a_tree_that_does_not_exist_is_a_refusal(tmp_path, wrapper):
    identity = {name: dict(file=str(tmp_path/'nowhere'/'__init__.py'), search=[str(tmp_path/'nowhere')])
                for name in import_identity()}
    job = dict(scene_id='s0', registration=str(tmp_path/'r.json'), scope='/x', inputs_manifest='/y')
    (tmp_path/'r.json').write_text(json.dumps(dict(scene_id='s0', task_id='t', worker_id='w00', host_output='/o')))
    answers = run_readbacks([job], workers=1, _executable=wrapper, _request_identity=identity)
    assert isinstance(answers[0], ValueError) and str(answers[0]).startswith('CONTAINER_READBACK_WORKER_EXITED:s0:')


def test_the_workers_import_the_parent_s_code_tree():
    identity = import_identity()
    assert identity['so101_demo']['file'] == sys.modules['so101_demo'].__file__
    assert_same_code_tree(identity)
    with pytest.raises(ValueError, match='READBACK_WORKER_CODE_TREE_MISMATCH'):
        assert_same_code_tree({**identity, 'so101_demo': dict(identity['so101_demo'], file='/elsewhere/__init__.py')})
    with pytest.raises(ValueError, match='READBACK_WORKER_CODE_TREE_MISMATCH'):
        assert_same_code_tree({'so101_teleop': identity.get('so101_teleop', identity['so101_demo'])})


def test_a_real_worker_reports_the_parent_s_tree_and_reads_the_code_it_runs(tmp_path):
    # the production readback function in a real worker: the answer is a refusal of this missing registration, but only after the
    # tree check passed (a mismatch would be exit 3, not a clean refusal)
    job = dict(scene_id='s0', registration=str(tmp_path/'collected.json'), scope=str(tmp_path/'scope.json'),
               inputs_manifest=str(tmp_path/'inputs.json'))
    answers = run_readbacks([job], workers=1)
    assert isinstance(answers[0], ValueError) and str(answers[0]) == 'CONTAINER_TASK_READBACK_INVALID'


def test_default_pool_size_follows_memory_and_cpus():
    gib = 1024**3
    assert default_readback_workers(available_bytes=27*gib, cpu_count=32) == 4
    assert default_readback_workers(available_bytes=8*gib, cpu_count=32) == 2
    assert default_readback_workers(available_bytes=3*gib, cpu_count=32) == 1
    assert default_readback_workers(available_bytes=1*gib, cpu_count=32) == 1
    assert default_readback_workers(available_bytes=27*gib, cpu_count=4) == 2
    assert default_readback_workers(available_bytes=27*gib, cpu_count=1) == 1
    assert 1 <= default_readback_workers() <= readback_pool.DEFAULT_WORKER_CAP


@pytest.mark.parametrize('value', [0, -1, True, '2', 2.0])
def test_a_bad_pool_size_is_refused(value):
    with pytest.raises(ValueError, match='READBACK_WORKERS_INVALID'):
        resolve_readback_workers(value)
    assert resolve_readback_workers(1) == 1 and resolve_readback_workers(None) >= 1


def test_run_readbacks_refuses_a_bad_timeout():
    with pytest.raises(ValueError, match='READBACK_TIMEOUT_INVALID'):
        run_readbacks([], workers=2, timeout_s=0)


# ---- the other places that repeat the readback --------------------------------------------------------------------------


def test_the_recomputation_passes_the_pool_size_to_every_wave_readback(monkeypatch):
    from so101_demo.act import collection_qualification_recompute as recompute_module
    seen = {}

    def fake_verify_wave_records(*args, **kwargs):
        seen.update(kwargs)
        return 'record'

    class Journal(dict):
        pass

    monkeypatch.setattr(result_verifier, 'verify_wave_records', fake_verify_wave_records)
    monkeypatch.setattr('so101_demo.runtime.container_campaign.task_journal.read_task_journal',
                        lambda *args, **kwargs: {'t': dict(failed=None, collected=dict())})
    monkeypatch.setattr(recompute_module, '_ref', lambda path: dict(path=str(path), sha256='0'*64))
    state = object.__new__(recompute_module._Run)
    state.run, state.records, state.reasons = recompute_module.Path('/run'), [], set()
    state.readback_workers, state.readback_timeout_s = 3, 99
    assert state.wave(dict(wave_index=0, scene_ids=['a'])) == 'record'
    assert seen == dict(readback_workers=3, readback_timeout_s=99)


def test_the_builder_the_verifier_and_the_clis_take_the_pool_size(monkeypatch, tmp_path):
    from so101_demo.act import parallel_qualification_verifier as verifier_module
    from so101_demo.act import collection_qualification_recompute as recompute_module
    from so101_demo.cli import act_build_parallel_qualification_report as build_cli
    from so101_demo.cli import act_verify_parallel_qualification as verify_cli
    seen = []

    def fake_recompute(run, contract, **kwargs):
        seen.append(kwargs)
        return dict(status='NOT_QUALIFIED')

    monkeypatch.setattr(recompute_module, 'recompute', fake_recompute)
    monkeypatch.setattr(recompute_module, 'run_layout', lambda root: (tmp_path, None))
    (tmp_path/'host').mkdir()
    verifier_module.build_collection_qualification_report(tmp_path, contract=tmp_path/'c.json', readback_workers=2)
    assert seen == [dict(readback_workers=2)]
    assert build_cli._parser().parse_args(['--contract', 'c', '--campaign-root', 'r', '--registered-root', 'g',
                                           '--readback-workers', '3']).readback_workers == 3
    assert build_cli._parser().parse_args(['--contract', 'c', '--campaign-root', 'r', '--registered-root', 'g']
                                          ).readback_workers is None
    assert verify_cli._parser().parse_args(['--report', 'r', '--registered-root', 'g', '--readback-workers', '1']
                                           ).readback_workers == 1

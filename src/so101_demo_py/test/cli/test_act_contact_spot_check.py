"""`act_contact_spot_check` judges one finished container spot-check run and writes `spot-check-verdict.json`.

Everything here is a fixture: a synthetic run root with the files the judge reads (the campaign's collection index, the task
result, the sealed result, QC report and Teacher manifest, and the frozen inputs) whose numbers are chosen by each test. The
frozen-input reader and the QC report reader are the two controlled boundaries (their own behaviour is covered by their own tests);
the sha256 bindings between the files, the criteria and the verdict document are the judge's own and are real. The thresholds the
judge compares against are read from the proposal the run froze; the tests give it values that are not any real policy's.
"""

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from so101_demo.cli import act_contact_spot_check as judge

LIMIT_FORCE_N = 2.5
LIMIT_COMPRESSION_M = 0.0002
LIMIT_COMPRESSION_UM = LIMIT_COMPRESSION_M * 1e6
FINGERPRINT = 'ab' * 32
DIAGNOSTIC = 'preselected_target_diagnostic'
OVER_SQUEEZE_CLOSE = -0.049
NOMINAL_CLOSE = -0.0476
SCENE = 'spot-00'
TASK = 'wave-0-w00-spot-00'
WINDOW = ('CLOSE_GRIPPER', 'WAIT_GRASP_STABLE', 'MICRO_LIFT', 'WAIT_MICRO_LIFT_STABLE', 'VERIFY_PHYSICAL_GRASP')
ALL_PHASES = ('MOVE_ABOVE_OBJECT', 'DESCEND', *WINDOW, 'LIFT', 'MOVE_ABOVE_PLACE', 'DESCEND_TO_PLACE', 'OPEN_GRIPPER')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, sort_keys=True))
    return path


def phase(*, force=0.4, compression_um=10.0, flags=(), first_force_step=None, first_compression_step=None, pairs=()):
    return dict(begin_sim_s=0.0, finish_sim_s=1.0, status='DONE', code=None, steps=10, peak_force_n=force, peak_force_step=1,
                peak_compression_um=compression_um, peak_compression_step=1, force_margin_n=None, compression_margin_um=None,
                first_force_exceedance_step=first_force_step, first_force_exceedance_n=None,
                first_compression_exceedance_step=first_compression_step, first_compression_exceedance_um=None,
                collision_pairs=[dict(pair=['a', 'b'], first_step=step, max_depth_mm=1.0, max_force_n=1.0, count=1)
                                 for step in pairs], oracle_flags=list(flags), bilateral_contact_lost=[])


def summary(*, overload_phases=(), collision_phases=(), peak_force=0.4, peak_compression_um=10.0, complete=True,
            thresholds=True, overload_step=100, collision_step=None):
    """A `teacher_process_summary`: every phase is quiet except the named ones; `peak_*` is set on CLOSE_GRIPPER."""
    phases = {}
    for name in ALL_PHASES:
        flags = [flag for flag, listed in (('ORACLE_CUP_OVERLOAD', overload_phases), ('ORACLE_COLLISION', collision_phases))
                 if name in listed]
        phases[name] = phase(flags=flags, force=peak_force if name == 'CLOSE_GRIPPER' else 0.4,
                             compression_um=peak_compression_um if name == 'CLOSE_GRIPPER' else 10.0,
                             first_force_step=overload_step if name in overload_phases else None,
                             pairs=(collision_step,) if name in collision_phases else ())
    flags = {'ORACLE_CUP_OVERLOAD': [n for n in ALL_PHASES if n in overload_phases],
             'ORACLE_COLLISION': [n for n in ALL_PHASES if n in collision_phases]}
    return dict(schema='teacher_process_summary', complete=complete, incomplete_reasons=[] if complete else ['WORLD_TRUNCATED'],
                units={}, thresholds=dict(source='r10b', summed_force_n=LIMIT_FORCE_N, compression_um=LIMIT_COMPRESSION_UM,
                                          comparison='strict >') if thresholds is True else thresholds,
                policy=dict(execution_policy_schema=3, execution_policy_sha256='c' * 64, cup_pose_source='broker_rgbd',
                            verdict_source='sim_truth'),
                phases=phases, flags=flags)


class Run:
    pass


HAZARD = 'PHYSICS_RAW_SOURCE_HAZARD'
HAZARD_REASONS = [HAZARD, f'RECORDER_SEAL_FAILED: {HAZARD}', f'RECORDER_SOURCE_CLOSE_FAILED: {HAZARD}']


def hazard_reason(reasons):
    """`runtime.act_processor.processing` for rc 3: the first four report reasons, 120 characters each, 300 in all."""
    return ('OFFLINE_PROCESSOR_INVALID: rc=3; ' + '; '.join(item[:120] for item in reasons[:4]))[:300]


def write_processed(run, scene, qc, *, number=1, fault='none', directory=None):
    """processed-result.json as the phase-2 writer binds it: phase-1 result sha, the recording receipt sha, QC report path and sha
    (under `out/` for a fault)."""
    directory = run.processed_dir if directory is None else directory
    data = directory if fault == 'none' else directory / 'out'
    return dump(directory / 'processed-result.json', dict(
        kind='ACT_PROCESSED_RESULT', schema_version=1, task_id=f'{scene}-proc-{number}', scene_id=scene, proc_attempt=number,
        phase1_result_sha256=sha(run.result), receipt_sha256=sha(run.receipt), diagnostic_fault=fault, act_data_qc=qc,
        qc_report_path='qc-report.json', qc_report_sha256=sha(data / 'qc-report.json')))


def write_hazard_processed(run, scene, *, number=1, reasons=None, **changes):
    """processed-result.json of a run whose raw physics hit the hard-stop force flag: INVALID, NOT_RUN, no QC report, the
    processor report (rc 3) bound under `artifacts` and its reasons in `act_data_reason`."""
    reasons = HAZARD_REASONS if reasons is None else reasons
    run.processor_report = dump(run.processed_dir / 'offline-processor-report.json', dict(verdict='INVALID', rc=3, reasons=reasons))
    document = dict(
        kind='ACT_PROCESSED_RESULT', schema_version=1, task_id=f'{scene}-proc-{number}', scene_id=scene, proc_attempt=number,
        phase1_result_sha256=sha(run.result), receipt_sha256=sha(run.receipt), diagnostic_fault='none', processor_rc=3,
        act_data_status='INVALID', act_data_qc='NOT_RUN', act_data_reason=hazard_reason(reasons), export_eligible=False,
        qc_report_path=None, qc_report_sha256=None, episode_seal_sha256=None,
        artifacts=dict(processor_report=dict(path='offline-processor-report.json', sha256=sha(run.processor_report))))
    document.update(changes)
    return dump(run.processed_dir / 'processed-result.json', document)


def write_receipt(run, manifest_sha=None):
    """raw/recording-receipt.json as `act.offline.recording_receipt` writes it (only the Teacher manifest document matters here)."""
    run.receipt = dump(run.sealed / 'raw/recording-receipt.json', dict(
        kind='ACT_RECORDING_RECEIPT', schema_version=1, raw_files=[],
        documents=dict(teacher_manifest=dict(path='dynamic/dynamic-execute-manifest.json',
                                             sha256=sha(run.manifest) if manifest_sha is None else manifest_sha, size=1))))
    return run.receipt


def make_run(tmp_path, *, kind='nominal', summary_document=None, close=None, qc='PASS', status='COMPLETED',
             endpoint='PASS', scene=SCENE, hazard=False):
    """A synthetic finished spot-check run root. Returns an object with the paths the tests damage."""
    run = Run()
    run.root = root = (tmp_path / 'act-w1s-run').resolve()
    run.kind = kind
    run.frozen = root / 'inputs/frozen'
    proposal = dict(status='DISABLED', policy_fingerprint=FINGERPRINT, payload=dict(thresholds=dict(
        maximum_safe_force_n=LIMIT_FORCE_N, maximum_compression_distance_m=LIMIT_COMPRESSION_M)))
    run.proposal_path = dump(run.frozen / 'contact_proposal/proposal.json', proposal)
    run.frozen_manifest = dump(run.frozen / 'inputs-manifest.json', dict(placeholder=True))
    run.frozen_document = dict(
        mode=DIAGNOSTIC, inputs_sha256='1' * 64, scene_manifest=dict(scene_count=1),
        roles=dict(contact_proposal=dict(path='contact_proposal/proposal.json', sha256=sha(run.proposal_path),
                                         approval='disabled_proposal'),
                   contact_activation=dict(path='x', sha256='0' * 64, approval='spot_check_candidate')),
        teacher_execution_policy=dict(values=dict(
            gripper_close_target_rad=(OVER_SQUEEZE_CLOSE if kind == 'over_squeeze' else NOMINAL_CLOSE) if close is None else close)))
    location = root / 'wave-0/w00/g1/output/tasks' / TASK
    sealed = run.sealed = location / 'attempts' / scene / (scene + '-lease-1') / 'sealed'
    run.manifest = dump(sealed / 'dynamic/dynamic-execute-manifest.json', dict(
        schema='so101-teacher-execute', status='DONE', teacher_execution_status=status,
        teacher_task_result=dict(result=endpoint, rule_version='teacher_endpoint'),
        teacher_process_summary=summary_document if summary_document is not None else summary()))
    run.qc_bound_manifest_sha = sha(run.manifest)
    write_receipt(run)
    run.result = dump(sealed / 'result.json', dict(kind='ACT_COLLECTION_RESULT', act_data_qc=qc))
    # the two-phase layout: the phase-2 QC report and processed-result.json live in <run>/processing/<scene>/<attempt>-proc-<n>,
    # never in the sealed directory (which holds result.json, dynamic/, numeric/, perception/ and raw/)
    run.processed_dir = root / 'processing' / scene / (scene + '-lease-1-proc-1')
    run.qc_path = dump(run.processed_dir / 'qc-report.json', dict(status=qc))
    run.processed = write_hazard_processed(run, scene) if hazard else write_processed(run, scene, qc)
    if hazard:
        run.qc_path.unlink()      # the sealer refused the physics hazard: there is no QC report
    run.task_result = dump(location / 'task-result.json', dict(result=dict(act_data_qc=qc)))
    task = dict(scene_id=scene, worker_id='w00', task_id=TASK, launch_id='wave-0-w00-g1', location=str(location),
                result_status='PASSED', teacher_execution_status=status, teacher_task_result=endpoint,
                act_data_status='INVALID' if hazard else 'VALID' if qc == 'PASS' else 'INVALID',
                act_data_reason=hazard_reason(HAZARD_REASONS) if hazard else None, act_data_qc='NOT_RUN' if hazard else qc,
                export_eligible=False, result_sha256=sha(run.result), task_result_sha256=sha(run.task_result),
                processed_result_sha256=sha(run.processed))
    run.index_document = dict(schema_version=1, kind='act_collection_frozen_index', campaign_id='spot-campaign',
                              qualification=True, scene_count=1, collected_tasks=[task], committed_episodes=[])
    run.index = dump(root / 'collection-index.json', run.index_document)
    return run


@pytest.fixture(autouse=True)
def controlled_readers(monkeypatch):
    """The two controlled boundaries: the frozen-input reader and the QC report reader (each has its own tests)."""
    state = {}

    def frozen(path):
        run = state['run']
        assert Path(path) == run.frozen_manifest
        return copy.deepcopy(run.frozen_document)

    def qc(path):
        run = state['run']
        assert Path(path) == run.qc_path
        return dict(status='PASS', checks={judge.REFERENCE_CHECK: dict(details=dict(teacher_manifest_sha256=run.qc_bound_manifest_sha))})

    monkeypatch.setattr(judge, 'verify_frozen_inputs', frozen)
    monkeypatch.setattr(judge, 'read_qc_report', qc)
    return state


@pytest.fixture
def prepared(controlled_readers):
    def prepare(run):
        controlled_readers['run'] = run
        return run
    return prepare


def judged(run, **kwargs):
    return judge.judge_run(run.root, run.kind, **kwargs)


# ---- the nominal criteria ------------------------------------------------------------------------------------------------------


def test_a_quiet_completed_nominal_run_passes_with_the_proposals_limits_in_the_verdict(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    verdict = judged(run)
    assert verdict['verdict'] == 'PASS' and verdict['reasons'] == [] and verdict['spot_check'] == 'nominal'
    assert verdict['kind'] == 'ACT_CONTACT_SPOT_CHECK_VERDICT' and verdict['schema_version'] == 1
    assert verdict['policy_fingerprint'] == FINGERPRINT
    assert verdict['limits'] == dict(maximum_safe_force_n=LIMIT_FORCE_N, maximum_compression_distance_m=LIMIT_COMPRESSION_M,
                                     maximum_compression_um=LIMIT_COMPRESSION_UM)
    assert verdict['measured']['peak_force_n'] == 0.4 and verdict['measured']['peak_compression_um'] == 10.0
    assert verdict['run'] == str(run.root) and verdict['scene_id'] == SCENE and verdict['task_id'] == TASK
    assert verdict['task_result'] == dict(path=str(run.task_result), sha256=sha(run.task_result))
    assert verdict['teacher_manifest'] == dict(path=str(run.manifest), sha256=sha(run.manifest))
    assert verdict['collection_index'] == dict(path=str(run.index), sha256=sha(run.index))
    assert verdict['proposal'] == dict(path=str(run.proposal_path), sha256=sha(run.proposal_path))
    assert set(verdict['checks']) == {'teacher_completed', 'endpoint_pass', 'no_oracle_flag', 'summary_complete', 'phase2_qc_pass',
                                      'close_target_is_not_the_over_squeeze_value'}
    assert all(verdict['checks'].values())


@pytest.mark.parametrize('change,failed', [
    (dict(status='FAILED'), 'teacher_completed'),
    (dict(endpoint='FAIL'), 'endpoint_pass'),
    (dict(qc='FAIL'), 'phase2_qc_pass'),
    (dict(summary_document=summary(overload_phases=('CLOSE_GRIPPER',))), 'no_oracle_flag'),
    (dict(summary_document=summary(collision_phases=('LIFT',), collision_step=5)), 'no_oracle_flag'),
    (dict(summary_document=summary(complete=False)), 'summary_complete'),
    (dict(close=OVER_SQUEEZE_CLOSE), 'close_target_is_not_the_over_squeeze_value'),
], ids=['not_completed', 'endpoint_fail', 'qc_fail', 'overload_flag', 'collision_flag', 'incomplete_summary', 'over_squeezed_policy'])
def test_each_nominal_criterion_fails_the_verdict_alone(tmp_path, prepared, change, failed):
    run = prepared(make_run(tmp_path, **change))
    verdict = judged(run)
    assert verdict['verdict'] == 'FAIL'
    assert [name for name, ok in verdict['checks'].items() if not ok] == [failed]
    assert verdict['reasons'] == [failed]


# ---- the over-squeeze criteria -------------------------------------------------------------------------------------------------


def over_squeeze(**kwargs):
    base = dict(overload_phases=('CLOSE_GRIPPER', 'WAIT_GRASP_STABLE'), peak_force=LIMIT_FORCE_N * 1.2,
                peak_compression_um=LIMIT_COMPRESSION_UM * 1.2)
    base.update(kwargs)
    return summary(**base)


def test_a_completed_over_squeeze_run_with_the_overload_in_the_window_and_peaks_over_the_limits_passes(tmp_path, prepared):
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=over_squeeze()))
    verdict = judged(run)
    assert verdict['verdict'] == 'PASS' and verdict['reasons'] == []
    assert set(verdict['checks']) == {'teacher_completed', 'close_target_is_over_squeeze', 'overload_in_window',
                                      'peak_over_a_limit', 'summary_thresholds_equal_proposal',
                                      'no_collision_before_first_overload'}
    measured = verdict['measured']
    assert measured['peak_force_n'] == LIMIT_FORCE_N * 1.2 and measured['peak_compression_um'] == LIMIT_COMPRESSION_UM * 1.2
    assert measured['overload_phases'] == ['CLOSE_GRIPPER', 'WAIT_GRASP_STABLE'] and measured['first_overload_step'] == 100
    assert verdict['gripper_close_target_rad'] == OVER_SQUEEZE_CLOSE


def test_over_squeeze_does_not_need_the_endpoint_or_the_qc_to_pass(tmp_path, prepared):
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=over_squeeze(), endpoint='FAIL', qc='FAIL'))
    assert judged(run)['verdict'] == 'PASS'


@pytest.mark.parametrize('kwargs,failed', [
    (dict(status='FAILED'), 'teacher_completed'),
    (dict(close=NOMINAL_CLOSE), 'close_target_is_over_squeeze'),
    (dict(summary_document=over_squeeze(overload_phases=())), 'overload_in_window'),
    (dict(summary_document=over_squeeze(overload_phases=('LIFT',))), 'overload_in_window'),
    (dict(summary_document=over_squeeze(peak_force=LIMIT_FORCE_N, peak_compression_um=LIMIT_COMPRESSION_UM)), 'peak_over_a_limit'),
    (dict(summary_document=over_squeeze(thresholds=dict(source='r10b', summed_force_n=LIMIT_FORCE_N + 0.1,
                                                        compression_um=LIMIT_COMPRESSION_UM))), 'summary_thresholds_equal_proposal'),
    (dict(summary_document=over_squeeze(thresholds=dict(source='r10b', summed_force_n=LIMIT_FORCE_N,
                                                        compression_um=LIMIT_COMPRESSION_UM * 0.9))), 'summary_thresholds_equal_proposal'),
    (dict(summary_document=over_squeeze(thresholds=None)), 'summary_thresholds_equal_proposal'),
    (dict(summary_document=over_squeeze(collision_phases=('CLOSE_GRIPPER',), collision_step=50, overload_step=100)),
     'no_collision_before_first_overload'),
], ids=['not_completed', 'nominal_policy', 'no_overload', 'overload_outside_window', 'peaks_at_the_limits', 'force_threshold',
        'compression_threshold', 'no_thresholds', 'collision_first'])
def test_each_over_squeeze_criterion_fails_the_verdict_alone(tmp_path, prepared, kwargs, failed):
    run = prepared(make_run(tmp_path, kind='over_squeeze', **kwargs))
    verdict = judged(run)
    assert verdict['verdict'] == 'FAIL'
    assert failed in verdict['reasons'] and not verdict['checks'][failed]


def test_a_collision_after_the_first_overload_does_not_fail_the_over_squeeze_run(tmp_path, prepared):
    document = over_squeeze(collision_phases=('LIFT',), collision_step=500, overload_step=100)
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=document))
    verdict = judged(run)
    assert verdict['verdict'] == 'PASS' and verdict['measured']['first_collision_step'] == 500


def test_either_peak_over_its_limit_is_enough(tmp_path, prepared):
    only_force = over_squeeze(peak_compression_um=LIMIT_COMPRESSION_UM * 0.5)
    only_compression = over_squeeze(peak_force=LIMIT_FORCE_N * 0.5)
    for document in (only_force, only_compression):
        run = prepared(make_run(tmp_path / str(id(document)), kind='over_squeeze', summary_document=document))
        assert judged(run)['verdict'] == 'PASS'


def test_the_limits_are_the_frozen_proposals_not_a_constant(tmp_path, prepared):
    # peaks of 1.0 N / 150 um pass against a proposal with low limits and fail against the fixture's
    low = over_squeeze(peak_force=1.0, peak_compression_um=150.0, thresholds=dict(source='r10b', summed_force_n=0.5,
                                                                              compression_um=100.0, comparison='strict >'))
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=low))
    document = json.loads(run.proposal_path.read_text())
    document['payload']['thresholds'] = dict(maximum_safe_force_n=0.5, maximum_compression_distance_m=0.0001)
    run.proposal_path.write_text(json.dumps(document, sort_keys=True))
    run.frozen_document['roles']['contact_proposal']['sha256'] = sha(run.proposal_path)
    verdict = judged(run)
    assert verdict['verdict'] == 'PASS' and verdict['limits']['maximum_safe_force_n'] == 0.5
    run2 = prepared(make_run(tmp_path / 'other', kind='over_squeeze', summary_document=low))
    assert judged(run2)['verdict'] == 'FAIL'


def test_an_expected_fingerprint_must_match_the_frozen_proposal(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    assert judged(run, expected_fingerprint=FINGERPRINT)['verdict'] == 'PASS'
    with pytest.raises(ValueError, match='SPOT_CHECK_FINGERPRINT_MISMATCH'):
        judged(run, expected_fingerprint='cd' * 32)


# ---- inputs the judge refuses (no verdict is written) -----------------------------------------------------------------------


def refused(run, code, **kwargs):
    with pytest.raises(ValueError, match=code):
        judged(run, **kwargs)


def test_an_unknown_spot_check_kind_is_refused(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    with pytest.raises(ValueError, match='SPOT_CHECK_KIND_INVALID'):
        judge.judge_run(run.root, 'other')


@pytest.mark.parametrize('damage', ['not_qualification', 'committed_episode', 'two_tasks', 'no_task', 'wrong_kind', 'without_evidence'])
def test_an_index_that_is_not_a_one_task_spot_check_index_is_refused(tmp_path, prepared, damage):
    run = prepared(make_run(tmp_path))
    document = copy.deepcopy(run.index_document)
    if damage == 'not_qualification':
        document['qualification'] = False
    elif damage == 'committed_episode':
        document['committed_episodes'] = [dict(scene_id=SCENE)]
    elif damage == 'two_tasks':
        document['collected_tasks'] = document['collected_tasks'] * 2
    elif damage == 'no_task':
        document['collected_tasks'] = []
    elif damage == 'wrong_kind':
        document['kind'] = 'campaign'
    else:
        document['scenes_without_evidence'] = [dict(scene_id=SCENE, state='FAULT', reason='x')]
    dump(run.index, document)
    refused(run, 'SPOT_CHECK_INDEX_INVALID')


def test_a_frozen_set_that_is_not_diagnostic_one_scene_is_refused(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    run.frozen_document['mode'] = 'formal'
    refused(run, 'SPOT_CHECK_NOT_DIAGNOSTIC')
    run.frozen_document['mode'] = DIAGNOSTIC
    run.frozen_document['scene_manifest']['scene_count'] = 2
    refused(run, 'SPOT_CHECK_NOT_DIAGNOSTIC')


@pytest.mark.parametrize('damage,code', [
    ('task_result', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('sealed_result', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('manifest', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('proposal', 'SPOT_CHECK_FROZEN_PROPOSAL_INVALID'),
    ('missing_manifest', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('processed_result', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('missing_processed_result', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('qc_report', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('missing_qc_report', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('no_index_processed_sha', 'SPOT_CHECK_BINDING_MISMATCH'),
    ('phase1_result_not_bound', 'SPOT_CHECK_BINDING_MISMATCH'),
])
def test_a_file_that_is_not_the_one_the_index_and_qc_bound_is_refused(tmp_path, prepared, damage, code):
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=over_squeeze()))
    if damage == 'task_result':
        run.task_result.write_text(run.task_result.read_text() + ' ')
    elif damage == 'sealed_result':
        run.result.write_text(run.result.read_text() + ' ')
    elif damage == 'manifest':
        run.manifest.write_text(run.manifest.read_text() + ' ')
    elif damage == 'proposal':
        run.proposal_path.write_text(run.proposal_path.read_text() + ' ')
    elif damage == 'processed_result':
        run.processed.write_text(run.processed.read_text() + ' ')
    elif damage == 'missing_processed_result':
        run.processed.unlink()
    elif damage == 'qc_report':
        run.qc_path.write_text(run.qc_path.read_text() + ' ')
    elif damage == 'missing_qc_report':
        run.qc_path.unlink()
    elif damage == 'no_index_processed_sha':
        document = copy.deepcopy(run.index_document)
        document['collected_tasks'][0]['processed_result_sha256'] = None
        dump(run.index, document)
    elif damage == 'phase1_result_not_bound':
        document = json.loads(run.processed.read_text())
        document['phase1_result_sha256'] = '0' * 64
        dump(run.processed, document)
        index = copy.deepcopy(run.index_document)
        index['collected_tasks'][0]['processed_result_sha256'] = sha(run.processed)
        dump(run.index, index)
    else:
        run.manifest.unlink()
    refused(run, code)


# ---- over-squeeze without a QC report: the physics-hazard outcome ---------------------------------------------------------------


def hazard_run(tmp_path, **kwargs):
    return make_run(tmp_path, kind='over_squeeze', summary_document=over_squeeze(), hazard=True, **kwargs)


def rebind(run, **changes):
    """Rewrite the processed result with `changes` and re-bind it in the index, as a faithful but different phase-2 outcome."""
    document = json.loads(run.processed.read_text())
    document.update(changes)
    dump(run.processed, document)
    index = copy.deepcopy(run.index_document)
    index['collected_tasks'][0]['processed_result_sha256'] = sha(run.processed)
    index['collected_tasks'][0].update({key: value for key, value in changes.items() if key in
                                        ('act_data_status', 'act_data_qc', 'act_data_reason', 'export_eligible')})
    dump(run.index, index)


def test_a_hazard_over_squeeze_run_passes_without_a_qc_report_and_names_its_binding_route(tmp_path, prepared):
    run = prepared(hazard_run(tmp_path))
    assert not run.qc_path.exists()
    verdict = judged(run)
    assert verdict['verdict'] == 'PASS' and verdict['reasons'] == []
    assert verdict['binding_route'] == 'recording_receipt_physics_hazard'
    assert verdict['qc_report'] is None
    assert verdict['teacher_manifest'] == dict(path=str(run.manifest), sha256=sha(run.manifest))
    assert verdict['recording_receipt'] == dict(path=str(run.receipt), sha256=sha(run.receipt))
    assert verdict['processor_report'] == dict(path=str(run.processor_report), sha256=sha(run.processor_report))
    assert verdict['processed_result'] == dict(path=str(run.processed), sha256=sha(run.processed))
    assert verdict['phase2_outcome'] == dict(act_data_status='INVALID', act_data_qc='NOT_RUN', processor_rc=3,
                                             act_data_reason=hazard_reason(HAZARD_REASONS))


@pytest.mark.parametrize('reasons', [[HAZARD], [HAZARD, f'RECORDER_SEAL_FAILED: {HAZARD}'], HAZARD_REASONS])
def test_every_combination_of_the_engines_hazard_latches_is_the_hazard_outcome(tmp_path, prepared, reasons):
    run = hazard_run(tmp_path)
    rebind(run, **json.loads(write_hazard_processed(run, SCENE, reasons=reasons).read_text()))
    assert judged(prepared(run))['verdict'] == 'PASS'


def test_a_hazard_run_that_the_other_criteria_fail_still_fails_the_verdict(tmp_path, prepared):
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=over_squeeze(overload_phases=()), hazard=True))
    verdict = judged(run)
    assert verdict['verdict'] == 'FAIL' and 'overload_in_window' in verdict['reasons']


@pytest.mark.parametrize('damage', [
    'manifest_changed', 'receipt_changed', 'receipt_sha_not_in_processed', 'receipt_lists_other_manifest', 'receipt_missing',
    'receipt_other_path', 'other_reason', 'extra_reason', 'unknown_prefix', 'reason_not_the_reports', 'valid_status',
    'fault_status', 'qc_run', 'half_qc_binding', 'fault_injected', 'rc_not_3', 'report_changed', 'report_missing',
    'report_verdict_valid', 'index_reason_differs', 'index_says_valid', 'export_eligible'])
def test_a_hazard_outcome_that_is_not_exactly_bound_or_not_exactly_the_hazard_is_refused(tmp_path, prepared, damage):
    run = prepared(hazard_run(tmp_path))
    if damage == 'manifest_changed':
        run.manifest.write_text(run.manifest.read_text() + ' ')
    elif damage == 'receipt_changed':
        run.receipt.write_text(run.receipt.read_text() + ' ')
    elif damage == 'receipt_sha_not_in_processed':
        rebind(run, receipt_sha256='0' * 64)
    elif damage == 'receipt_lists_other_manifest':
        write_receipt(run, manifest_sha='0' * 64)
        rebind(run, receipt_sha256=sha(run.receipt))
    elif damage == 'receipt_missing':
        run.receipt.unlink()
    elif damage == 'receipt_other_path':
        document = json.loads(run.receipt.read_text())
        document['documents']['teacher_manifest']['path'] = 'dynamic/other.json'
        dump(run.receipt, document)
        rebind(run, receipt_sha256=sha(run.receipt))
    elif damage in ('other_reason', 'extra_reason', 'unknown_prefix'):
        reasons = dict(other_reason=[HAZARD, 'RECORDER_SEAL_FAILED: PHYSICS_RAW_CONTINUITY_INVALID'],
                       extra_reason=[HAZARD, 'TEACHER_TASK_NOT_PASSED: FAIL'],
                       unknown_prefix=[HAZARD, f'RECORDER_NOT_AN_ENGINE_LATCH: {HAZARD}'])[damage]
        rebind(run, **json.loads(write_hazard_processed(run, SCENE, reasons=reasons).read_text()))
    elif damage == 'reason_not_the_reports':
        rebind(run, act_data_reason=hazard_reason([HAZARD]))
    elif damage == 'valid_status':
        rebind(run, act_data_status='VALID')
    elif damage == 'fault_status':
        rebind(run, act_data_status='FAULT')
    elif damage == 'qc_run':
        rebind(run, act_data_qc='FAIL')
    elif damage == 'half_qc_binding':
        rebind(run, qc_report_path='qc-report.json')
    elif damage == 'fault_injected':
        rebind(run, diagnostic_fault='SOME_FAULT')
    elif damage == 'rc_not_3':
        rebind(run, processor_rc=2)
    elif damage == 'report_changed':
        run.processor_report.write_text(run.processor_report.read_text() + ' ')
    elif damage == 'report_missing':
        run.processor_report.unlink()
    elif damage == 'report_verdict_valid':
        document = json.loads(run.processor_report.read_text())
        document['verdict'] = 'VALID'
        dump(run.processor_report, document)
        rebind(run, artifacts=dict(processor_report=dict(path='offline-processor-report.json', sha256=sha(run.processor_report))))
    elif damage == 'index_reason_differs':
        index = copy.deepcopy(run.index_document)
        index['collected_tasks'][0]['act_data_reason'] = 'OTHER'
        dump(run.index, index)
    elif damage == 'index_says_valid':
        index = copy.deepcopy(run.index_document)
        index['collected_tasks'][0]['act_data_status'] = 'VALID'
        dump(run.index, index)
    else:
        rebind(run, export_eligible=True)
    refused(run, 'SPOT_CHECK_BINDING_MISMATCH')


def test_a_hazard_outcome_is_refused_for_a_missing_processed_result_too(tmp_path, prepared):
    run = prepared(hazard_run(tmp_path))
    run.processed.unlink()
    refused(run, 'SPOT_CHECK_BINDING_MISMATCH')


def test_a_nominal_run_without_a_qc_report_is_still_refused_even_with_the_hazard_outcome(tmp_path, prepared):
    run = prepared(make_run(tmp_path, kind='nominal', hazard=True))
    refused(run, 'SPOT_CHECK_BINDING_MISMATCH')


def test_a_qc_route_over_squeeze_run_also_needs_the_receipt_to_bind_the_same_manifest(tmp_path, prepared):
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=over_squeeze()))
    verdict = judged(run)
    assert verdict['binding_route'] == 'qc_report_and_recording_receipt' and verdict['recording_receipt']['sha256'] == sha(run.receipt)
    write_receipt(run, manifest_sha='0' * 64)
    run.processed = write_processed(run, SCENE, 'PASS')
    index = copy.deepcopy(run.index_document)
    index['collected_tasks'][0]['processed_result_sha256'] = sha(run.processed)
    dump(run.index, index)
    refused(run, 'SPOT_CHECK_BINDING_MISMATCH')


def test_the_qc_report_is_found_under_the_fault_out_directory_when_the_processor_faulted(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    out = run.processed_dir / 'out'
    out.mkdir()
    run.qc_path = Path(shutil.move(str(run.qc_path), str(out / 'qc-report.json')))
    run.processed = write_processed(run, SCENE, 'PASS', fault='SOME_FAULT')
    index = copy.deepcopy(run.index_document)
    index['collected_tasks'][0]['processed_result_sha256'] = sha(run.processed)
    dump(run.index, index)
    assert judged(run)['verdict'] == 'PASS'


def test_several_processing_attempts_with_the_bound_processed_result_are_refused_but_unbound_ones_are_ignored(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    other = run.root / 'processing' / SCENE / (SCENE + '-lease-1-proc-2')
    other.mkdir(parents=True)
    (other / 'processed-result.json').write_text(run.processed.read_text())      # same bytes: two candidates
    refused(run, 'SPOT_CHECK_BINDING_MISMATCH')
    (other / 'processed-result.json').write_text('{}')                            # different bytes: not the bound one
    assert judged(run)['verdict'] == 'PASS'


def test_the_verdict_names_the_bound_qc_report_and_processed_result(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    verdict = judged(run)
    assert verdict['qc_report'] == dict(path=str(run.qc_path), sha256=sha(run.qc_path))
    assert verdict['processed_result'] == dict(path=str(run.processed), sha256=sha(run.processed))


def test_a_summary_that_is_not_well_formed_is_refused(tmp_path, prepared):
    document = over_squeeze()
    document['flags']['ORACLE_CUP_OVERLOAD'] = []        # disagrees with the phases it is derived from
    run = prepared(make_run(tmp_path, kind='over_squeeze', summary_document=document))
    refused(run, 'SPOT_CHECK_SUMMARY_INVALID')


def test_a_missing_proposal_threshold_is_refused(tmp_path, prepared):
    run = prepared(make_run(tmp_path))
    document = json.loads(run.proposal_path.read_text())
    del document['payload']['thresholds']['maximum_safe_force_n']
    run.proposal_path.write_text(json.dumps(document, sort_keys=True))
    run.frozen_document['roles']['contact_proposal']['sha256'] = sha(run.proposal_path)
    refused(run, 'SPOT_CHECK_FROZEN_PROPOSAL_INVALID')


# ---- the CLI ---------------------------------------------------------------------------------------------------------------------


def test_the_cli_writes_the_verdict_once_and_exits_with_its_result(tmp_path, prepared, capsys):
    run = prepared(make_run(tmp_path))
    output = tmp_path / 'spot-check-verdict.json'
    argv = ['--run', str(run.root), '--spot-check', 'nominal', '--output', str(output)]
    assert judge.main(argv) == 0
    written = json.loads(output.read_text())
    assert written['verdict'] == 'PASS' and json.loads(capsys.readouterr().out.strip().splitlines()[-1]) == dict(
        verdict='PASS', output=str(output), sha256=sha(output))
    # the file is written once: a second call is refused and leaves the first verdict
    before = output.read_bytes()
    assert judge.main(argv) == 2 and output.read_bytes() == before


def test_the_cli_exit_codes_are_pass_zero_fail_one_refused_two(tmp_path, prepared, capsys):
    run = prepared(make_run(tmp_path, qc='FAIL'))
    output = tmp_path / 'fail-verdict.json'
    assert judge.main(['--run', str(run.root), '--spot-check', 'nominal', '--output', str(output)]) == 1
    assert json.loads(output.read_text())['verdict'] == 'FAIL'
    refused_output = tmp_path / 'refused-verdict.json'
    assert judge.main(['--run', str(run.root), '--spot-check', 'over_squeeze', '--output', str(refused_output),
                       '--expected-fingerprint', 'cd' * 32]) == 2
    assert not refused_output.exists() and 'SPOT_CHECK_FINGERPRINT_MISMATCH' in capsys.readouterr().err
    with pytest.raises(SystemExit) as caught:
        judge.main(['--run', str(run.root), '--spot-check', 'other', '--output', str(tmp_path / 'x.json')])
    assert caught.value.code == 2


def test_the_console_script_is_registered():
    from paths import PACKAGE_ROOT
    assert '"act_contact_spot_check = so101_demo.cli.act_contact_spot_check:main"' in (PACKAGE_ROOT / 'setup.py').read_text()

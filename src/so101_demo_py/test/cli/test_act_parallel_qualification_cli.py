"""The two qualification-report commands: `act_build_parallel_qualification_report` and `act_verify_parallel_qualification`.

Exit codes under test: 0 qualified or verified, 3 not qualified or verification refused, 2 usage or path refusal with nothing
written, 1 an unexpected error. The world (`collection_qualification_world.py`) is a 40-scene, two-wave, eight-instance run built
by the production producers; its episode bytes, QC recomputation, Docker and provenance documents and frozen-input reader are
controlled, and its rule files are TEST-ONLY synthetic values that no human approved. The builder and the verifier are the real
ones; only the world around them is controlled. Nothing here is container, physical or qualification evidence.
"""

import hashlib
import json

import pytest

from collection_qualification_world import build_world, install_controlled_world
from so101_demo.cli import act_build_parallel_qualification_report as build_cli
from so101_demo.cli import act_verify_parallel_qualification as verify_cli
from so101_demo.act.parallel_qualification_verifier import build_collection_qualification_report
from so101_demo.runtime.parallel_ipc.frames import canonical_json


def sha_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def controlled(monkeypatch):
    install_controlled_world(monkeypatch)
    return monkeypatch


def fresh_world(tmp_path, **kwargs):
    (tmp_path/'world').mkdir()
    return build_world(tmp_path/'world', **kwargs)


@pytest.fixture(scope='module')
def shared_worlds(tmp_path_factory):
    """One never-reported world (refusals and the unexpected-error case) and one reported world (the verifier command)."""
    patch = pytest.MonkeyPatch()
    install_controlled_world(patch)
    try:
        unreported = build_world(tmp_path_factory.mktemp('unreported'))
        reported = build_world(tmp_path_factory.mktemp('reported'))
        build_collection_qualification_report(reported.run, contract=reported.contract_path)
    finally:
        patch.undo()
    return unreported, reported


def build_argv(world, **overrides):
    values = {'contract': world.contract_path, 'campaign-root': world.run, 'registered-root': world.root}
    values.update({name.replace('_', '-'): value for name, value in overrides.items()})
    argv = []
    for name, value in values.items():
        if value is not None:
            argv += ['--'+name, str(value)]
    return argv


def run_build(world, capsys, **overrides):
    capsys.readouterr()
    code = build_cli.main(build_argv(world, **overrides))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_build_writes_a_qualified_report_once_and_prints_it(tmp_path, controlled, capsys):
    world = fresh_world(tmp_path)
    code, out, err = run_build(world, capsys)
    assert code == 0, err
    printed = json.loads(out)
    assert set(printed) == {'status', 'report', 'sha256', 'reasons'}
    assert printed['status'] == 'QUALIFIED' and printed['reasons'] == [] and printed['report'] == str(world.report_path)
    assert printed['sha256'] == sha_of(world.report_path)
    assert json.loads(world.report_path.read_bytes())['status'] == 'QUALIFIED'
    before = world.report_path.read_bytes()
    code, out, err = run_build(world, capsys)
    assert code == 2 and out == '' and 'QUALIFICATION_REPORT_EXISTS' in err
    assert world.report_path.read_bytes() == before


def test_build_of_a_run_that_does_not_qualify_writes_the_report_and_exits_three(tmp_path, controlled, capsys):
    world = fresh_world(tmp_path)
    (world.run/'host/dispatch-fault.json').write_bytes(canonical_json(dict(type='ValueError', reason='controlled'))+b'\n')
    code, out, err = run_build(world, capsys)
    assert code == 3, err
    printed = json.loads(out)
    assert printed['status'] == 'NOT_QUALIFIED' and printed['reasons'] and printed['sha256'] == sha_of(world.report_path)
    assert json.loads(world.report_path.read_bytes())['reasons'] == printed['reasons']


@pytest.mark.parametrize('problem', ['contract_absent', 'campaign_root_elsewhere', 'campaign_root_relative',
                                     'registered_root_relative', 'registered_root_not_the_runs_root', 'no_layout',
                                     'registered_root_a_file'])
def test_build_refusals_exit_two_and_write_nothing(shared_worlds, tmp_path, controlled, capsys, problem):
    world, _ = shared_worlds
    overrides = {}
    if problem == 'contract_absent': overrides['contract'] = tmp_path/'absent-gate.json'
    elif problem == 'campaign_root_elsewhere':
        elsewhere = tmp_path/'elsewhere'
        elsewhere.mkdir()
        overrides['campaign_root'] = elsewhere
    elif problem == 'campaign_root_relative': overrides['campaign_root'] = world.run.relative_to(world.root.parent)
    elif problem == 'registered_root_relative': overrides['registered_root'] = world.root.relative_to(world.root.parent)
    elif problem == 'registered_root_not_the_runs_root': overrides['registered_root'] = world.inputs
    elif problem == 'registered_root_a_file': overrides['registered_root'] = world.contract_path
    else:
        bare = world.root/'run-without-layout'
        bare.mkdir()
        (bare/'host').mkdir()
        overrides['campaign_root'] = bare
    before = sorted(str(path) for path in world.root.rglob('*'))
    code, out, err = run_build(world, capsys, **overrides)
    assert code == 2 and out == '' and err.startswith('act_build_parallel_qualification_report: ')
    assert not world.report_path.exists()
    assert not [path for path in world.root.rglob('qualification-report.json')]
    assert sorted(str(path) for path in world.root.rglob('*')) == before or problem == 'no_layout'


def test_build_unexpected_error_exits_one(shared_worlds, controlled, capsys):
    world, _ = shared_worlds

    def explode(*args, **kwargs):
        raise RuntimeError('controlled unexpected failure')
    controlled.setattr(build_cli, 'build_collection_qualification_report', explode)
    code, out, err = run_build(world, capsys)
    assert code == 1 and out == '' and 'controlled unexpected failure' in err and not world.report_path.exists()


def test_build_without_required_arguments_is_a_usage_error(capsys):
    for argv in ([], ['--contract', '/x'], ['--contract', '/x', '--campaign-root', '/y']):
        with pytest.raises(SystemExit) as raised:
            build_cli.main(argv)
        assert raised.value.code == 2


# ---- the verifier command -------------------------------------------------------------------------------------------------


def identity_argv(world):
    return ['--campaign-config', str(world.campaign_path), '--source', str(world.inputs/'source.tar'),
            '--runtime-config', str(world.runtime), '--collection-config', str(world.collection),
            '--contact-policy-fingerprint', world.identity['contact_policy_fingerprint']]


def run_verify(world, capsys, *extra, report=None, registered_root=None):
    capsys.readouterr()
    code = verify_cli.main(['--report', str(report or world.report_path), '--registered-root',
                            str(registered_root or world.root), *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_verify_prints_the_proof_and_exits_zero_with_and_without_an_expected_identity(shared_worlds, controlled, capsys):
    _, world = shared_worlds
    before = {str(path): path.stat().st_mtime_ns for path in world.run.rglob('*') if path.is_file()}
    code, out, err = run_verify(world, capsys, *identity_argv(world))
    assert code == 0, err
    proof = json.loads(out)
    assert proof['kind'] == 'ACT_COLLECTION_QUALIFICATION_READBACK' and proof['status'] == 'PASS'
    assert proof['report_sha256'] == sha_of(world.report_path) and proof['task_count'] == 40
    assert proof['controlled_identity'] == world.contract['controlled_identity']
    code, out_without, err = run_verify(world, capsys)
    assert code == 0 and json.loads(out_without) == proof
    assert before == {str(path): path.stat().st_mtime_ns for path in world.run.rglob('*') if path.is_file()}


def test_verify_identity_that_differs_exits_three(shared_worlds, controlled, capsys):
    _, world = shared_worlds
    argv = identity_argv(world)
    argv[argv.index('--contact-policy-fingerprint')+1] = 'f'*64
    code, out, err = run_verify(world, capsys, *argv)
    assert code == 3 and out == '' and 'COLLECTION_QUALIFICATION_IDENTITY_MISMATCH' in err


@pytest.mark.parametrize('dropped', ['--campaign-config', '--source', '--runtime-config', '--collection-config',
                                     '--contact-policy-fingerprint'])
def test_verify_identity_arguments_are_all_or_none(shared_worlds, controlled, capsys, dropped):
    _, world = shared_worlds
    argv = identity_argv(world)
    index = argv.index(dropped)
    del argv[index:index+2]
    code, out, err = run_verify(world, capsys, *argv)
    assert code == 2 and out == '' and 'identity' in err


def test_verify_unreadable_identity_inputs_are_a_usage_refusal(shared_worlds, controlled, capsys):
    _, world = shared_worlds
    argv = identity_argv(world)
    argv[argv.index('--source')+1] = str(world.inputs/'absent.tar')
    code, out, err = run_verify(world, capsys, *argv)
    assert code == 2 and out == ''
    argv = identity_argv(world)
    argv[argv.index('--contact-policy-fingerprint')+1] = 'not-a-hash'
    code, out, err = run_verify(world, capsys, *argv)
    assert code == 2 and out == ''


def test_verify_refusals_exit_three(shared_worlds, tmp_path, controlled, capsys):
    unreported, world = shared_worlds
    legacy = unreported.run/'host/qualification-report.json'
    legacy.write_text(json.dumps(dict(status='PASSED', worker_count=8)))
    try:
        code, out, err = run_verify(unreported, capsys, report=legacy, registered_root=unreported.root)
        assert code == 3 and out == '' and 'COLLECTION_QUALIFICATION_REPORT_INVALID' in err
    finally:
        legacy.unlink()
    document = json.loads(world.report_path.read_bytes())
    original = world.report_path.read_bytes()
    try:
        world.report_path.write_bytes(canonical_json(dict(document, reasons=['TASK_FAILED:forged']))+b'\n')
        code, out, err = run_verify(world, capsys)
        assert code == 3 and out == '' and 'COLLECTION_QUALIFICATION_RECOMPUTE_MISMATCH' in err
    finally:
        world.report_path.write_bytes(original)


def test_verify_path_refusals_exit_two(shared_worlds, tmp_path, controlled, capsys):
    _, world = shared_worlds
    elsewhere = tmp_path/'elsewhere'
    elsewhere.mkdir()
    cases = (dict(registered_root=elsewhere), dict(report=world.run/'host/../host/qualification-report.json'),
             dict(report=world.inputs/'source.tar'))
    for overrides in cases:
        code, out, err = run_verify(world, capsys, **overrides)
        assert code == 2 and out == '' and 'COLLECTION_QUALIFICATION_PATH_INVALID' in err


def test_verify_unexpected_error_exits_one(shared_worlds, controlled, capsys):
    _, world = shared_worlds

    def explode(*args, **kwargs):
        raise RuntimeError('controlled unexpected failure')
    controlled.setattr(verify_cli, 'verify_collection_qualification', explode)
    code, out, err = run_verify(world, capsys)
    assert code == 1 and out == '' and 'controlled unexpected failure' in err


def test_verify_without_required_arguments_is_a_usage_error():
    for argv in ([], ['--report', '/x']):
        with pytest.raises(SystemExit) as raised:
            verify_cli.main(argv)
        assert raised.value.code == 2

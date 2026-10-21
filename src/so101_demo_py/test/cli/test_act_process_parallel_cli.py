"""`act_process_parallel`: the later stages of a campaign whose phase 1 ran with `act_collect_parallel --stop-after-phase1`.

The world is the one of the container campaign integration test (real admission, owner, coordinator and registry; Docker, the
Teacher socket and the instance control channel are doubles). The refusals are the ones the stage records make before anything is
admitted: nothing is taken for them, so no lease, slot or container exists afterwards."""

import json

import pytest

from so101_demo.cli import act_process_parallel as process_cli
from so101_demo.runtime.container_campaign import stage_records
from test_container_task_campaign_integration import (  # noqa: F401 - fixtures and the world builder
    _short_polls, argv_for, controlled_verifier, make_world, shared)

PROCESS_OPTIONS = ('campaign-id', 'run-id', 'worker-count', 'manifest', 'source', 'collection-config', 'runtime-config',
                   'campaign-config', 'qualification-report')


def process_argv(world, *stage, **overrides):
    """The arguments of `act_process_parallel` for the world: the collection arguments it shares, and the stage."""
    argv = argv_for(world, **overrides)
    keep, index = [], 0
    while index < len(argv):
        name = argv[index]
        if name in ('--qualification', '--spot-check'):
            keep.append(name)
            index += 1
        else:
            if name[2:] in PROCESS_OPTIONS:
                keep += argv[index:index + 2]
            index += 2
    return keep + list(stage)


OPENED = []
STORE_ROOTS = []


def close_stores():
    """The CLIs leave the unified store open to their process's end; in one test process each call closes it."""
    while OPENED:
        OPENED.pop().store.close()


@pytest.fixture(autouse=True)
def _service_store_released(monkeypatch):
    from so101_demo.cli import act_collect_parallel as collect_cli
    opened = OPENED
    for module in (collect_cli, process_cli):
        real = module.compose_services

        def compose(*args, _real=real, **kwargs):
            services = _real(*args, **kwargs)
            opened.append(services)
            STORE_ROOTS.append(services.store.root)
            return services
        monkeypatch.setattr(module, 'compose_services', compose)
    yield
    close_stores()


def collect_phase1(world, capsys):
    capsys.readouterr()
    from so101_demo.cli.act_collect_parallel import main
    code = main(argv_for(world) + ['--stop-after-phase1'], edges=world.edges)
    close_stores()
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return json.loads(captured.out.strip().splitlines()[-1])


def process(world, capsys, *stage, **overrides):
    capsys.readouterr()
    code = process_cli.main(process_argv(world, *stage, **overrides), edges=world.edges)
    close_stores()
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def stopped(tmp_path, shared, monkeypatch, capsys):
    world = make_world(tmp_path, shared, monkeypatch, plane='W1', polls_to_finish=2)
    controlled_verifier(monkeypatch)
    summary = collect_phase1(world, capsys)
    world.summary = summary
    world.run_root = world.evidence / 'run-one'
    world.containers_before = len(world.docker.runs(shard=False)) + len(world.docker.runs(shard=True))
    return world


def containers(world):
    return len(world.docker.runs(shard=False)) + len(world.docker.runs(shard=True))


def test_phase_one_stops_with_a_record_and_the_later_stages_are_not_yet_done(stopped):
    assert stopped.summary['stop'] == 'PHASE1_ONLY'
    record = stage_records.read_record(stopped.run_root / 'host', stage_records.PHASE1)
    assert record['previous'] is None and record['qualification'] is True
    assert not (stopped.run_root / 'host/phase2-complete.json').exists()


@pytest.mark.parametrize('stage', [[], ['--phase2', '--finalize']])
def test_exactly_one_stage_is_selected(stopped, capsys, stage):
    if len(stage) == 2:
        with pytest.raises(SystemExit):
            process(stopped, capsys, *stage)
        return
    code, _, err = process(stopped, capsys, *stage)
    assert code == 2 and 'STAGE_SELECTION_INVALID' in err
    assert containers(stopped) == stopped.containers_before


def test_a_retry_round_of_a_qualification_run_is_refused_before_admission(stopped, capsys):
    code, _, err = process(stopped, capsys, '--retry-round', '1')
    assert code == 2 and 'STAGE_RETRY_ON_QUALIFICATION_RUN' in err
    assert containers(stopped) == stopped.containers_before


@pytest.mark.parametrize('number', ['0', '4'])
def test_a_retry_round_outside_the_limit_is_refused(stopped, capsys, number):
    code, _, err = process(stopped, capsys, '--retry-round', number)
    assert code == 2 and 'STAGE_RETRY_ROUNDS_EXCEEDED' in err


def test_the_finalize_needs_the_phase_two_record(stopped, capsys):
    code, _, err = process(stopped, capsys, '--finalize')
    assert code == 2 and 'STAGE_PREVIOUS_RECORD_MISSING' in err
    assert containers(stopped) == stopped.containers_before


def test_an_altered_record_is_refused_before_admission(stopped, capsys):
    path = stopped.run_root / 'host/phase1-complete.json'
    document = json.loads(path.read_text())
    document['worker_count'] = 3
    path.write_text(json.dumps(document))
    code, _, err = process(stopped, capsys, '--phase2')
    assert code == 2 and 'STAGE_PREVIOUS_RECORD_INVALID' in err
    assert containers(stopped) == stopped.containers_before


def test_a_changed_campaign_config_is_refused_before_admission(stopped, capsys):
    stopped.campaign_path.write_text(stopped.campaign_path.read_text() + '\n')
    code, _, err = process(stopped, capsys, '--phase2')
    assert code == 2 and ('STAGE_LOGIC_DOCUMENT_CHANGED' in err or 'CONFIG' in err)
    assert containers(stopped) == stopped.containers_before


def test_a_run_that_does_not_exist_is_refused(stopped, capsys):
    code, _, err = process(stopped, capsys, '--phase2', **{'run_id': 'no-such-run'})
    assert code == 2 and 'CAMPAIGN_RUN_MISSING' in err



# ---- end to end: a stage takes its own admission, runs, settles and leaves the GPU free ------------------------------------

def contexts(stopped):
    """(operation, generation) of every admission of the campaign, from the unified store."""
    from so101_teleop.unified.intent_store import IntentStore
    store = IntentStore.open(STORE_ROOTS[-1])
    try:
        return [(row['operation_id'], json.loads(row['context_json'])['execution_generation'])
                for row in store._query_all('SELECT operation_id, context_json FROM act_campaign_contexts ORDER BY 1')], \
            store._query_one('SELECT * FROM gpu_workload_leases'), \
            store._query_all('SELECT * FROM act_worker_slots WHERE active=1')
    finally:
        store.close()


def test_phase_two_is_admitted_on_its_own_and_settles_before_the_finalize(stopped, capsys):
    code, out, err = process(stopped, capsys, '--phase2')
    assert code == 0, err
    assert stage_records.read_record(stopped.run_root / 'host', stage_records.PHASE2)['previous']['stage'] == 'phase1'
    admissions, lease, active = contexts(stopped)
    assert len(admissions) == 2 and sorted(generation for _, generation in admissions) == [1, 2]
    assert lease is None and active == []
    code, out, err = process(stopped, capsys, '--finalize')
    assert code == 0, err
    admissions, lease, active = contexts(stopped)
    assert sorted(generation for _, generation in admissions) == [1, 2, 3] and lease is None and active == []


def test_a_second_phase_one_of_the_same_campaign_id_is_refused_by_admission(stopped, capsys):
    from so101_demo.cli.act_collect_parallel import main
    capsys.readouterr()
    code = main(argv_for(stopped, **{'run_id': 'run-two'}) + ['--stop-after-phase1'], edges=stopped.edges)
    close_stores()
    captured = capsys.readouterr()
    assert code == 1 and 'ADMISSION_REFUSED' in captured.err      # the same command id with another run is not the first admission
    admissions, lease, active = contexts(stopped)
    assert len(admissions) == 1 and lease is None and active == []


def test_a_stage_that_ran_is_refused_when_asked_again(stopped, capsys):
    assert process(stopped, capsys, '--phase2')[0] == 0
    code, _, err = process(stopped, capsys, '--phase2')
    assert code == 2 and 'STAGE_ALREADY_COMPLETE' in err
    assert len(contexts(stopped)[0]) == 2

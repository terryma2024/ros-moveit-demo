"""Directed tests for the formal stage-one execution entry.

`run --execution-inputs <absolute-json>` must parse exactly one closed document,
refuse anything else with return code 2, resolve the one installed resource
provider before touching the run root, run the provider through the single
composition, and seal the run exactly once with 0 or 1.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_act_head_execution_composition import build_inputs as _composition_inputs
from test_act_head_execution_composition import local_stack


def build_inputs(tmp_path, **kwargs):
    inputs, policy = _composition_inputs(tmp_path, **kwargs)
    document = json.loads(inputs.document_path.read_text())
    document['stop_declaration'] = {'trigger': 'OPERATOR_STOP', 'teardown_timeout_s': 1.}
    document['seal_expectation'] = {'completion': True, 'artifacts': ['manifest.json', 'events.jsonl', 'completion.json', 'seal.json']}
    document['log_capture'] = {'stdout': 'stdout.log', 'stderr': 'stderr.log'}
    document['fault_stop_probes'] = []
    inputs.document_path.write_text(json.dumps(document)+'\n')
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs
    return HeadExecutionInputs.parse(inputs.document_path), policy


def module():
    import importlib
    return importlib.import_module('so101_demo.cli.head_execution_run')


def cli_module():
    import importlib
    return importlib.import_module('so101_demo.cli.head_search_calibration')


@pytest.mark.parametrize('arguments',[['run','--help'],['run','--execution-inputs','/abs/input.json','--help']])
def test_formal_run_help_advertises_execution_inputs_without_starting_resources(arguments,capsys):
    try: code = cli_module().main(arguments)
    except SystemExit as exit_request: code = exit_request.code
    assert code == 0
    assert '--execution-inputs' in capsys.readouterr().out


def test_formal_entry_accepts_its_own_readback_flag(monkeypatch):
    calls = []
    monkeypatch.setattr(module(),'main',lambda arguments: calls.append(arguments) or 0)
    arguments = ['--execution-inputs','/abs/input.json','--print-readback']
    assert cli_module().main(['run',*arguments]) == 0
    assert calls == [arguments]


def fake_provider(monkeypatch, events, *, outcome=0, failure=None, bind=True):
    """A provider that binds one local stack through the composition and reports an outcome."""

    def provide(composition, inputs):
        events.append(('provide', composition.readback()['run']))
        if failure is not None:
            raise failure
        if bind:
            stack = local_stack(monkeypatch, composition.policy,
                                epoch=inputs.run['epoch'], session=inputs.run['session_id'],
                                generation=inputs.run['generation'])
            composition.bind_ros(node=stack.node, port=stack.port)
            composition.bind_owner(owner=stack.neck_owner)
            composition.bind_detector(object(), runtime_device='cuda:0')
            composition.bind_inference(stack.owner)
            composition.bind_runtime(observer=stack.observer, runtime=stack.runtime)
            composition.bind_search(stack.search)
        return outcome

    return provide


def test_entry_requires_an_absolute_input_document(tmp_path, capsys):
    assert module().main([]) == 2
    assert module().main(['--execution-inputs']) == 2
    assert module().main(['--execution-inputs', str(tmp_path / 'missing.json')]) == 2
    captured = capsys.readouterr()
    assert 'EXECUTION_INPUTS' in captured.err


def test_entry_uses_the_installed_provider_and_seals_its_refusal(tmp_path, capsys):
    """The installed provider refuses undeclared model admission material before construction."""

    inputs, policy = build_inputs(tmp_path)
    provider = module().resolve_provider()
    assert callable(provider)
    assert module().main(['--execution-inputs', str(inputs.document_path)]) == 1
    captured = capsys.readouterr()
    assert 'EXECUTION_PROVIDER_ADMISSION_ABSENT' in captured.err
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['execution'] == 'FAILED'


def test_entry_leaves_no_run_root_when_the_provider_module_is_absent(tmp_path, capsys, monkeypatch):
    """An absent provider is resolved before any filesystem effect, so nothing is created."""

    inputs, policy = build_inputs(tmp_path)
    monkeypatch.setattr(module(), 'resolve_provider', lambda provider=None: None)
    assert module().main(['--execution-inputs', str(inputs.document_path)]) == 2
    assert 'EXECUTION_PROVIDER_ABSENT' in capsys.readouterr().err
    assert not inputs.run_root.exists()


def test_entry_runs_the_provider_through_one_composition(tmp_path, monkeypatch, capsys):
    inputs, policy = build_inputs(tmp_path)
    events = []
    provider = fake_provider(monkeypatch, events)
    assert module().main(['--execution-inputs', str(inputs.document_path),
                          '--print-readback'], provider=provider) == 0
    readback = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert readback['run'] == inputs.run
    assert readback['complete'] is True and readback['sealed'] is True
    assert readback['device'] == 'cuda:0' and readback['allow_cpu_fallback'] is False
    assert events == [('provide', inputs.run)]
    manifest = json.loads((inputs.run_root / 'manifest.json').read_text())
    assert manifest['execution_inputs']['sha256'] == inputs.document_sha256
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['execution'] == 'SUCCEEDED' and completion['business_return_code'] == 0
    assert (inputs.run_root / 'seal.json').is_file()


def test_entry_seals_a_provider_failure_as_return_code_one(tmp_path, monkeypatch, capsys):
    inputs, policy = build_inputs(tmp_path)
    events = []
    provider = fake_provider(monkeypatch, events, failure=PermissionError('the stack refused to start'))
    assert module().main(['--execution-inputs', str(inputs.document_path)],
                         provider=provider) == 1
    assert 'EXECUTION_RUN_FAILED' in capsys.readouterr().err
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['execution'] == 'FAILED' and completion['business_return_code'] == 1
    assert 'the stack refused to start' in completion['failure']
    assert (inputs.run_root / 'seal.json').is_file()


def test_entry_seals_a_business_failure_with_return_code_one(tmp_path):
    inputs, policy = build_inputs(tmp_path)
    assert module().main(['--execution-inputs', str(inputs.document_path)],
                         provider=fake_provider(None, [], outcome=1, bind=False)) == 1
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['execution'] == 'FAILED' and completion['business_return_code'] == 1


def test_entry_refuses_an_invalid_provider_outcome(tmp_path, capsys):
    inputs, policy = build_inputs(tmp_path)
    assert module().main(['--execution-inputs', str(inputs.document_path)],
                         provider=fake_provider(None, [], outcome='maybe', bind=False)) == 1
    assert 'invalid outcome' in capsys.readouterr().err
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['execution'] == 'FAILED'


def test_entry_cannot_seal_while_an_owned_producer_remains_live(tmp_path, capsys):
    inputs, _ = build_inputs(tmp_path)

    def unfinished_provider(composition, inputs):
        composition.begin_resource_lifetime('controlled-live-producer')
        return 0

    assert module().main(['--execution-inputs', str(inputs.document_path)],
                         provider=unfinished_provider) == 1
    assert 'EXECUTION_PRODUCERS_UNRETIRED' in capsys.readouterr().err
    assert not (inputs.run_root / 'completion.json').exists()
    assert not (inputs.run_root / 'seal.json').exists()


def test_entry_refuses_a_missing_provider_outcome(tmp_path):
    inputs, _ = build_inputs(tmp_path)
    assert module().main(['--execution-inputs', str(inputs.document_path)],
                         provider=fake_provider(None, [], outcome=None, bind=False)) == 1
    completion = json.loads((inputs.run_root / 'completion.json').read_text())
    assert completion['execution'] == 'FAILED'


def test_run_command_is_mutually_exclusive_with_the_legacy_phase_flags(tmp_path, capsys):
    inputs, policy = build_inputs(tmp_path)
    cli = cli_module()
    assert cli.main(['run', '--execution-inputs', str(inputs.document_path), '--run-root',
                     str(tmp_path / 'legacy')]) == 2
    captured = capsys.readouterr()
    assert '--execution-inputs' in captured.err and '--run-root' in captured.err
    assert not inputs.run_root.exists()
    # The same command without a legacy flag reaches the new entry: the installed
    # provider refuses the fixture's undeclared detector admission material.
    assert cli.main(['run', '--execution-inputs', str(inputs.document_path)]) == 1
    assert 'EXECUTION_PROVIDER_ADMISSION_ABSENT' in capsys.readouterr().err

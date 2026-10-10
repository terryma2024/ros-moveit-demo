"""Development entry boundaries refuse obsolete or incomplete execution claims."""
import pytest

from test_act_head_execution_inputs import input_tree


@pytest.mark.parametrize('field,value', [
    ('stop_declaration', {'trigger': 'OPERATOR_STOP', 'teardown_timeout_s': 1.}),
    ('seal_expectation', {'completion': True, 'artifacts': ['seal.json']}),
    ('log_capture', {'stdout': 'stdout.log', 'stderr': 'stderr.log'}),
    ('fault_stop_probes', []),
])
def test_partial_run_declarations_return_named_input_refusal(tmp_path, field, value):
    from so101_demo.act.head_execution_inputs import HeadExecutionInputs, HeadExecutionInputsRefused
    path, document = input_tree(tmp_path, **{field: value})
    with pytest.raises(HeadExecutionInputsRefused, match='EXECUTION_INPUTS_REFUSED'):
        HeadExecutionInputs.parse(path)
    assert not (tmp_path/'evidence/run-001').exists()


def test_removed_online_bootstrap_entry_refuses_before_import_or_run_root(tmp_path, monkeypatch, capsys):
    import builtins
    from so101_demo.cli.head_search_calibration import main
    actual_import = builtins.__import__
    def reject_bootstrap_import(name, *args, **kwargs):
        if 'head_feedback_bootstrap' in name or 'head_monitor' in name:
            pytest.fail('obsolete online execution dependency imported')
        return actual_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', reject_bootstrap_import)
    root = tmp_path/'old-bootstrap'
    assert main(['measure-feedback-bootstrap', '--run-root', str(root)]) == 2
    stderr = capsys.readouterr().err
    assert 'HEAD_ONLINE_BOOTSTRAP_REMOVED' in stderr
    assert '--execution-inputs' in stderr
    assert not root.exists()


def test_development_descriptor_cannot_claim_qualified_teleop_by_report_label():
    from so101_teleop.head_camera import HeadCameraBackend
    backend = HeadCameraBackend(descriptor={
        'execution_scope': 'MUJOCO_DEVELOPMENT_UNQUALIFIED',
        'operation': 'HEAD_FILE_STAGE1_DEVELOPMENT',
        'qualification_report': {'status': 'HEAD_SEARCH_QUALIFIED'},
    })
    assert backend.qualified() is False

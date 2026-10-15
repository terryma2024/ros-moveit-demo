"""The task execution reports the recording phase that the instance puts into its status."""

from test_task_builder import Rig, flow, env, shared_env  # noqa: F401  (fixtures and the wired task rig)


def test_execution_reports_recording_until_the_bag_recorder_has_stopped(flow, monkeypatch):
    seen = []
    rig = Rig(flow, monkeypatch, hooks={'reset': lambda rig: seen.append(('reset', rig.execution.recording_phase())),
                                        'seal': lambda rig: seen.append(('seal', rig.execution.recording_phase()))})
    assert rig.execution.recording_phase() == 'RECORDING'
    rig.execution.run()
    assert seen[-1] == ('seal', 'POST_RECORDING')
    assert all(phase == 'RECORDING' for name, phase in seen if name == 'reset')
    assert rig.execution.recording_phase() == 'POST_RECORDING'

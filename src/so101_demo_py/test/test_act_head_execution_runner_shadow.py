"""The runner's shadow-stop-window hooks: off unless the environment names a directory."""

from types import SimpleNamespace

import pytest

from so101_demo.adapters.act.head_shadow_stop_window import ENVIRONMENT_VARIABLE, ShadowStopWindow
from test_act_head_stop_window_subscriber import Rig


@pytest.fixture
def rig(isolated_ros_domain):
    value = Rig()
    try:
        yield value
    finally:
        value.close()


def runner():
    import importlib
    return importlib.import_module('so101_demo.cli.head_execution_runner')


class FakeRuntime:
    def __init__(self):
        self.observers = []

    def bind_stop_window_observer(self, observer):
        self.observers.append(observer)


def stack_and_inputs(rig, run_id='hcai-1'):
    return (SimpleNamespace(node=SimpleNamespace(context=rig.context)),
            SimpleNamespace(run={'run_id': run_id}))


def test_without_the_environment_switch_nothing_is_started_or_bound(rig):
    stack, inputs = stack_and_inputs(rig)
    runtime = FakeRuntime()
    assert runner()._start_shadow(stack, inputs, runtime, environ={}) is None
    assert runtime.observers == []


def test_with_the_switch_the_shadow_starts_and_binds_the_raw_stop_observer(rig, tmp_path):
    stack, inputs = stack_and_inputs(rig)
    runtime = FakeRuntime()
    shadow = runner()._start_shadow(stack, inputs, runtime, environ={ENVIRONMENT_VARIABLE: str(tmp_path)})
    try:
        assert isinstance(shadow, ShadowStopWindow)
        assert runtime.observers == [shadow.on_raw_stop_confirmed]
        assert shadow.path.name == 'shadow-stop-window-hcai-1.jsonl' and shadow.path.parent == tmp_path
        assert shadow.subscriber.thread.is_alive()
    finally:
        runner()._finish_shadow(shadow)
    assert not shadow.subscriber.thread.is_alive()


def test_a_misconfigured_switch_fails_the_run_loudly(rig, tmp_path):
    stack, inputs = stack_and_inputs(rig)
    with pytest.raises(ValueError, match='SHADOW_DIRECTORY_INVALID'):
        runner()._start_shadow(stack, inputs, FakeRuntime(), environ={ENVIRONMENT_VARIABLE: 'relative'})


def test_finishing_none_is_a_noop_and_a_failing_finish_never_raises():
    runner()._finish_shadow(None)

    class Broken:
        def finish(self, *, timeout_s):
            raise RuntimeError('boom')

    runner()._finish_shadow(Broken())

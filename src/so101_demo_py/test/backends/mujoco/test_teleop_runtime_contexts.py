"""Evidence reads and resets inside an ACT instance must not touch the process-global rclpy context.

Real rclpy contexts, no live graph: the point is who initialises and who shuts down which context. A retained RGB-D
source (or any other task component) owns the default context while the Teacher context probe reads evidence.
"""

import pytest



@pytest.fixture
def container_environment(monkeypatch, tmp_path, isolated_ros_domain):
    """The instance marker alone: no ROS namespace, the fixed identity's root namespace."""
    import rclpy

    monkeypatch.delenv("ROS_NAMESPACE", raising=False)
    monkeypatch.setenv("SO101_ACT_INSTANCE_ROOT", str(tmp_path))
    rclpy.try_shutdown()
    yield
    rclpy.try_shutdown()


@pytest.fixture
def default_context_holder(container_environment):
    """What the retained RGB-D source does: initialise the default context and keep a node on it."""
    import rclpy
    from so101_demo.ros.process_init import global_init_options

    rclpy.init(**global_init_options())
    node = rclpy.create_node("retained_rgbd_source")
    yield node
    node.destroy_node()


def assert_holder_untouched(node):
    import rclpy

    assert rclpy.ok(), "the default context was shut down under its holder"
    publisher = node.create_publisher(__import__("std_msgs.msg", fromlist=["String"]).String, "/holder_probe", 1)
    node.destroy_publisher(publisher)


def test_evidence_read_does_not_initialise_or_shut_down_the_default_context(default_context_holder):
    from so101_demo.backends.mujoco import teleop_runtime

    with pytest.raises(RuntimeError) as failure:
        teleop_runtime.current_evidence("session-a", timeout_s=0.2)

    assert "must only be called once" not in str(failure.value)
    assert str(failure.value) == "pause service unavailable"   # it got as far as the (absent) simulator
    assert_holder_untouched(default_context_holder)


def test_reset_does_not_initialise_or_shut_down_the_default_context(default_context_holder):
    from so101_demo.backends.mujoco import teleop_runtime
    from so101_demo.backends.mujoco.reset import ResetFailed

    with pytest.raises(ResetFailed):
        teleop_runtime.transactional_reset("session-a", timeout_s=0.2, act_profile=True)

    assert_holder_untouched(default_context_holder)


def test_repeated_evidence_reads_leave_no_context_behind(container_environment):
    import rclpy
    from so101_demo.backends.mujoco import teleop_runtime

    for _read in range(3):
        with pytest.raises(RuntimeError, match="pause service unavailable"):
            teleop_runtime.current_evidence("session-a", timeout_s=0.1)
        assert not rclpy.ok()   # nothing was left initialised in the default context


def test_the_instance_scope_uses_a_private_context_and_no_namespace_arguments(container_environment, monkeypatch):
    import rclpy
    from rclpy.signals import SignalHandlerOptions
    from so101_demo.backends.mujoco import teleop_runtime

    seen = []
    original_init = rclpy.init

    def init(*args, **kwargs):
        seen.append(kwargs)
        return original_init(*args, **kwargs)

    monkeypatch.setattr(rclpy, "init", init)
    scope = teleop_runtime._RosScope()
    try:
        assert scope.context is not None and not rclpy.ok()   # private; the default context was not initialised
        assert seen == [dict(context=scope.context, signal_handler_options=SignalHandlerOptions.NO)]
        assert "args" not in seen[0]
    finally:
        scope.close()


def test_without_the_instance_marker_the_default_context_is_still_used(monkeypatch, isolated_ros_domain):
    """Host and macOS callers are unchanged: they initialise and shut down the default context themselves."""
    import rclpy
    from so101_demo.backends.mujoco import teleop_runtime

    monkeypatch.delenv("SO101_ACT_INSTANCE_ROOT", raising=False)
    rclpy.try_shutdown()
    seen = []
    original_create_node = rclpy.create_node

    def create_node(name, **kwargs):
        seen.append((name, kwargs.get("context"), rclpy.ok()))
        return original_create_node(name, **kwargs)

    monkeypatch.setattr(rclpy, "create_node", create_node)
    with pytest.raises(RuntimeError, match="pause service unavailable"):
        teleop_runtime.current_evidence("session-a", timeout_s=0.1)

    assert seen == [("so101_teleop_mujoco_evidence", None, True)]
    assert not rclpy.ok()

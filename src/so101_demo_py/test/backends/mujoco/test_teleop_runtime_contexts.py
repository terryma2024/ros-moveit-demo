"""Evidence reads and resets inside a container stack must not touch the process-global rclpy context.

Real rclpy contexts, no live graph: the point is who initialises and who shuts down which context. A retained RGB-D
source (or any other task component) owns the default context while the Teacher context probe reads evidence.
"""

import pytest

NAMESPACE = "/act/campaign_w1f_20261012T220436Z/w00"


@pytest.fixture
def container_environment(monkeypatch):
    import rclpy

    monkeypatch.setenv("SO101_ACT_CONTAINER_NAMESPACE", NAMESPACE)
    monkeypatch.setenv("ROS_NAMESPACE", NAMESPACE)
    monkeypatch.setenv("ROS_DOMAIN_ID", "231")
    rclpy.try_shutdown()
    yield
    rclpy.try_shutdown()


@pytest.fixture
def default_context_holder(container_environment):
    """What the retained RGB-D source does: initialise the default context and keep a node on it."""
    import rclpy
    from so101_demo.runtime.container_campaign.ros_namespace import container_ros_global_init_options

    rclpy.init(**container_ros_global_init_options())
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


def test_without_a_container_marker_the_default_context_is_still_used(monkeypatch):
    """Host and macOS callers are unchanged: they initialise and shut down the default context themselves."""
    import rclpy
    from so101_demo.backends.mujoco import teleop_runtime

    monkeypatch.delenv("SO101_ACT_CONTAINER_NAMESPACE", raising=False)
    monkeypatch.setenv("ROS_DOMAIN_ID", "231")
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

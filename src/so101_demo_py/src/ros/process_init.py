"""How a process that owns its signals initialises rclpy."""

from ..runtime.act_instance.identity import instance_root


def in_instance_process(*, environment=None):
    """True in an ACT instance process: the explicit instance marker, or the retired per-worker namespace marker."""
    from ..runtime.container_campaign.ros_namespace import container_ros_namespace
    return (instance_root(environment=environment) is not None
            or container_ros_namespace(environment=environment) is not None)


def global_init_options(*, environment=None):
    """Keyword arguments for `rclpy.init` on a default or private context of an ACT instance process.

    The instance main is the container's PID 1 and handles SIGTERM and SIGINT itself, so rclpy must not replace those
    handlers. Without the instance marker this is empty and the call stays a bare `rclpy.init()`."""
    namespaced = _namespaced_options(environment)
    if namespaced:
        return namespaced
    if instance_root(environment=environment) is None:
        return {}
    from rclpy.signals import SignalHandlerOptions
    return dict(signal_handler_options=SignalHandlerOptions.NO)


def _namespaced_options(environment):
    # The retired per-worker namespace marker; removed with the namespace code.
    from ..runtime.container_campaign.ros_namespace import container_ros_global_init_options
    return container_ros_global_init_options(environment=environment)

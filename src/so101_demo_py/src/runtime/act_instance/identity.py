"""The fixed ROS identity of one ACT instance, and the explicit marker that an ACT instance process runs.

An instance owns its ROS graph alone: the container's private network and IPC namespaces are the isolation, so the domain
and every node, topic, service, action and controller name are the same in every instance. Only the Host-assigned
identities (worker id, launch generation, simulation session id, runtime id, token, container name, owned root, task id)
differ, and they are never ROS names.

`INSTANCE_ROOT_ENV` is the instance marker. Its value is the instance's owned root. It is the only switch for the
instance-process behavior that is not about addressing: a private rclpy context for evidence reads and resets, no rclpy
signal handlers, and the recorder's bag-root decision. Generic processes without it keep their original behavior.
`INSTANCE_OUTPUT_ENV` names the instance's output directory as the instance sees it (the layout's `output_root`); the
recorder proves it is `<owned_root>/output` itself. Every descendant of the instance inherits both, which is also how the
Host finds an instance's survivors without knowing their process groups.
"""

from collections.abc import Mapping
import os
from pathlib import Path

ACT_INSTANCE_ROS_DOMAIN_ID = 181
ACT_INSTANCE_ROS_NAMESPACE = "/"
INSTANCE_ROOT_ENV = "SO101_ACT_INSTANCE_ROOT"
INSTANCE_OUTPUT_ENV = "SO101_ACT_INSTANCE_OUTPUT"
SIMULATION_SESSION_ENV = "SO101_MUJOCO_SESSION_ID"

#: Everything but the session id, in launch order. Discovery stays on localhost even though the network is private.
_FIXED_ENVIRONMENT = (
    ("ROS_DOMAIN_ID", str(ACT_INSTANCE_ROS_DOMAIN_ID)),
    ("MUJOCO_GL", "egl"),
    ("ROS_LOCALHOST_ONLY", "1"),
    ("ROS_AUTOMATIC_DISCOVERY_RANGE", "LOCALHOST"),
)


def instance_environment(*, mujoco_session_id):
    """The instance's ROS and renderer environment as `NAME=value` entries; there is never a `ROS_NAMESPACE`."""
    if type(mujoco_session_id) is not str or not mujoco_session_id:
        raise ValueError("ACT_INSTANCE_SESSION_INVALID")
    return [name + "=" + value for name, value in _FIXED_ENVIRONMENT] + [
        SIMULATION_SESSION_ENV + "=" + mujoco_session_id]


FASTDDS_PROFILE_RELATIVE = "share/so101_demo_py/config/dds/fastdds-collection.xml"


def fastdds_profile_environment(install_prefix):
    """The Fast DDS default-profile entry for every ROS process of an instance. Only the shard runs ROS (the Teacher and the
    processor join no graph). It is deliberately outside `instance_environment` and the fixed identity. Only
    FASTRTPS_DEFAULT_PROFILES_FILE is set: RMW_FASTRTPS_USE_QOS_FROM_XML stays unset, so QoS comes from the ROS API."""
    return ["FASTRTPS_DEFAULT_PROFILES_FILE=" + str(Path(install_prefix) / FASTDDS_PROFILE_RELATIVE)]


def verify_instance_environment(environment, *, session_id=None):
    """Refuse a process environment that is not the fixed identity (drift in domain, a namespace, or the renderer)."""
    if not isinstance(environment, Mapping):
        raise ValueError("ACT_INSTANCE_ENVIRONMENT_DRIFT")
    if (any(environment.get(name) != value for name, value in _FIXED_ENVIRONMENT)
            or environment.get("ROS_NAMESPACE") not in (None, "")
            or session_id is not None and environment.get(SIMULATION_SESSION_ENV) != session_id):
        raise ValueError("ACT_INSTANCE_ENVIRONMENT_DRIFT")


def instance_root(*, environment=None):
    """The owned root named by the instance marker, or None in a process that is not an ACT instance."""
    values = os.environ if environment is None else environment
    value = values.get(INSTANCE_ROOT_ENV)
    if value is None:
        return None
    root = Path(value)
    if not value or not root.is_absolute() or ".." in root.parts:
        raise ValueError("ACT_INSTANCE_ROOT_INVALID")
    return str(root)


def instance_output(*, environment=None):
    """The output directory the instance marker names, or None in a process that is not an ACT instance."""
    values = os.environ if environment is None else environment
    value = values.get(INSTANCE_OUTPUT_ENV)
    if value is None:
        return None
    path = Path(value)
    if not value or not path.is_absolute() or ".." in path.parts:
        raise ValueError("ACT_INSTANCE_OUTPUT_INVALID")
    return str(path)


def mark_instance(owned_root, output_root, *, environment=None):
    """Set the instance marker once the entry has validated its spec; the value is the instance's owned root and its output."""
    values = os.environ if environment is None else environment
    root, output = Path(owned_root), Path(output_root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("ACT_INSTANCE_ROOT_INVALID")
    if not output.is_absolute() or ".." in output.parts:
        raise ValueError("ACT_INSTANCE_OUTPUT_INVALID")
    values[INSTANCE_ROOT_ENV] = str(root)
    values[INSTANCE_OUTPUT_ENV] = str(output)

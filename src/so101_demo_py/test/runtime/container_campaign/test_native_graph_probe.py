"""The Host's graph probe against a real ROS 2 graph, on a ROS domain of this test's own (never the instance's domain 181).

Real: `ros2 node list`, DDS discovery with localhost-only settings and a live rclpy node. The only choice made here is the
domain, which the repository fixture isolates per xdist worker.
"""

import os
from pathlib import Path
import shutil
import time

import pytest

from so101_teleop.unified.act_stack import ActStackLaunch
from so101_teleop.unified.act_stack_probes import RosGraphClearProbe


def probe_on(domain, tmp_path, **options):
    ros2 = shutil.which('ros2')
    assert ros2, 'ros2 must be on PATH in the test environment'
    environment = dict(os.environ, ROS_LOCALHOST_ONLY='1', ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST')
    launch = ActStackLaunch(ros2_executable=Path(ros2), session_id='probe-check', evidence_root=tmp_path,
                            ros_domain_id=domain, environment=environment)
    return RosGraphClearProbe(launch, **options)


def test_the_probe_with_a_spin_reports_a_live_node_every_time_and_a_clear_graph_after_it_is_gone(
        isolated_ros_domain, monkeypatch, tmp_path):
    import rclpy
    from rclpy.context import Context

    monkeypatch.setenv('ROS_LOCALHOST_ONLY', '1')
    monkeypatch.setenv('ROS_AUTOMATIC_DISCOVERY_RANGE', 'LOCALHOST')
    probe = probe_on(isolated_ros_domain, tmp_path, timeout_s=10., spin_time_s=3.)
    assert probe() is True                                                # nothing on this domain
    context = Context()
    rclpy.init(context=context)
    node = rclpy.create_node('host_probe_victim', context=context)
    try:
        time.sleep(1.)
        assert [probe(), probe(), probe()] == [False, False, False]       # a node is a node, however often it is asked
    finally:
        node.destroy_node()
        rclpy.shutdown(context=context)
    time.sleep(2.)
    assert probe() is True


def test_the_probe_configuration_is_closed():
    from dataclasses import dataclass

    @dataclass
    class Launch:
        pass
    with pytest.raises(ValueError, match='ACT_STACK_GRAPH_PROBE_CONFIG_INVALID'):
        RosGraphClearProbe(Launch())

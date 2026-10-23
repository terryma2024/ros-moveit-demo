"""Tests that start a real ROS graph run concurrently on the gate's xdist workers, so none of them may name a fixed ROS domain or session id
of its own: two stand-in stacks, or two sessions of one id, on one domain answer each other's questions (the `ready_session` cross-talk).
A graph test takes its domain from `isolated_ros_domain`; this file refuses a fixed domain or session id that two test modules share."""

from collections import defaultdict
from pathlib import Path
import re

import conftest

TESTS = Path(__file__).resolve().parents[1]
#: A module that creates a real node or context.
REAL_GRAPH = re.compile(r"rclpy\.init\(|rclpy\.create_node\(|\bContext\(\)")
#: A literal ROS domain: a `DOMAIN* = "232"` constant, `domain_id=231`, or a setenv call of ROS_DOMAIN_ID with a number.
LITERAL_DOMAIN = re.compile(r"""^(?:[A-Z_]*DOMAIN[A-Z_]*)\s*=\s*["']?(\d+)["']?\s*(?:#.*)?$|\bdomain_id\s*=\s*(\d+)\b|setenv\(\s*["']ROS_DOMAIN_ID["']\s*,\s*["'](\d+)["']""",
                            re.M)
LITERAL_SESSION = re.compile(r"""^(?:[A-Z_]*SESSION[A-Z_]*)\s*=\s*["']([^"']+)["']""", re.M)
#: Modules that import rclpy names but start no graph of their own (checked by the whole-suite audit): none needs an entry today.
NO_OWN_GRAPH = {
    "act/test_act_pick_place_calibration_measurement_runtime_descriptor.py", "backends/mujoco/test_act_model_reset.py",
    "runtime/test_act_execution_stack_launch.py", "runtime/test_act_rig_stack_composition.py", "runtime/test_launch_composition.py",
    "runtime/test_moveit_planning_scene_colour_publishing.py", "runtime/test_perception_pick_place_launch.py",
    "runtime/test_task_station_launch.py", "runtime/test_text_pick_agent_e2e_launch.py", "runtime/test_text_pick_agent_launch.py",
    "support/act_contact_throughput_bench.py", "support/macos_camera_topic_probe.py",
}


def modules():
    for path in sorted(TESTS.rglob("*.py")):
        if "__pycache__" not in path.parts and path.name != "conftest.py" and path != Path(__file__).resolve() and path.name != "test_no_fixed_ros_domains.py":      # the other guard quotes domains as data
            yield path.relative_to(TESTS).as_posix(), path.read_text()


def test_the_worker_slots_are_distinct_for_up_to_25_workers_and_avoid_the_reserved_domains():
    slots = [conftest.ros_domain_slot(worker, counter) for worker in range(25) for counter in range(8)]
    assert len(set(slots)) == len(slots) == 200
    assert not set(slots) & conftest.RESERVED_ROS_DOMAINS
    assert min(slots) >= 10 and max(slots) <= 215
    assert conftest.ros_domain_slot(3, 11) == conftest.ros_domain_slot(3, 3)      # the counter cycles over the worker's own eight


def test_every_module_that_starts_a_real_graph_takes_its_domain_from_the_fixture():
    missing = [name for name, text in modules()
               if REAL_GRAPH.search(text) and name not in NO_OWN_GRAPH and "isolated_ros_domain" not in text]
    assert missing == []


def test_no_two_graph_modules_share_a_fixed_ros_domain_or_session_id_and_none_has_a_domain_of_its_own():
    domains, sessions = defaultdict(set), defaultdict(set)
    for name, text in modules():
        if not REAL_GRAPH.search(text) or name in NO_OWN_GRAPH:
            continue      # a domain number in the data of another module (a declared `ros=dict(domain_id=42)`) starts nothing
        for match in LITERAL_DOMAIN.finditer(text):
            domains[next(group for group in match.groups() if group)].add(name)
        for match in LITERAL_SESSION.finditer(text):
            sessions[match.group(1)].add(name)
    assert {value: sorted(names) for value, names in domains.items()} == {}      # the domain comes from `isolated_ros_domain`
    assert {value: sorted(names) for value, names in sessions.items() if len(names) > 1} == {}

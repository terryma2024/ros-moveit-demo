import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


PROBE = Path(__file__).parent / 'headless' / 'readiness_probe.py'


def load_probe_module():
    assert PROBE.exists(), 'persistent readiness probe is missing'
    spec = importlib.util.spec_from_file_location('panda_readiness_probe', PROBE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_readiness_milestones_require_complete_runtime_evidence():
    module = load_probe_module()
    tracker = module.ReadinessTracker()

    tracker.observe_nodes(['/move_group'])
    tracker.observe_action_servers(arm=True, hand=False)
    tracker.observe_controllers(
        {
            'joint_state_broadcaster': 'active',
            'panda_arm_controller': 'active',
            'panda_hand_controller': 'inactive',
        }
    )
    assert tracker.take_new_milestones() == []

    tracker.observe_action_servers(arm=True, hand=True)
    tracker.observe_controllers(
        {
            'joint_state_broadcaster': 'active',
            'panda_arm_controller': 'active',
            'panda_hand_controller': 'active',
        }
    )
    assert tracker.take_new_milestones() == ['CORE_READY']
    assert tracker.take_new_milestones() == []

    tracker.observe_joint_names(['panda_joint1', 'panda_finger_joint1'])
    tracker.observe_scene_objects(['table', 'coke'])
    tracker.begin_completion_phase()
    assert tracker.snapshot()['joint_state'] is False
    assert tracker.snapshot()['planning_scene_coke'] is False

    tracker.observe_joint_names(['panda_joint1', 'panda_finger_joint1'])
    assert tracker.take_new_milestones() == []

    tracker.observe_scene_objects(['table', 'coke'])
    assert tracker.take_new_milestones() == ['ALL_READY']
    assert tracker.take_new_milestones() == []
    assert tracker.snapshot() == {
        'move_group': True,
        'arm_action_server': True,
        'hand_action_server': True,
        'controllers': {
            'joint_state_broadcaster': 'active',
            'panda_arm_controller': 'active',
            'panda_hand_controller': 'active',
        },
        'joint_state': True,
        'planning_scene_coke': True,
    }


def test_probe_times_out_with_observable_missing_evidence(tmp_path):
    env = os.environ.copy()
    env.update(
        {
            'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp',
            'ROS_DOMAIN_ID': '104',
            'ROS_LOG_DIR': str(tmp_path / 'ros-logs'),
        }
    )

    result = subprocess.run(
        [sys.executable, str(PROBE), '--timeout', '0.1', '--poll-period', '0.02'],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report == {
        'status': 'TIMEOUT',
        'move_group': False,
        'arm_action_server': False,
        'hand_action_server': False,
        'controllers': {},
        'joint_state': False,
        'planning_scene_coke': False,
    }


def test_probe_observes_real_ros_actions_controllers_joint_state_and_scene(tmp_path):
    provider_ready = tmp_path / 'provider-ready'
    env = os.environ.copy()
    env.update(
        {
            'RMW_IMPLEMENTATION': 'rmw_fastrtps_cpp',
            'ROS_DOMAIN_ID': '105',
            'ROS_LOG_DIR': str(tmp_path / 'ros-logs'),
            'PROVIDER_READY': str(provider_ready),
        }
    )
    provider_source = r"""
import os
from pathlib import Path
import rclpy
from control_msgs.action import FollowJointTrajectory, GripperCommand
from controller_manager_msgs.msg import ControllerState
from controller_manager_msgs.srv import ListControllers
from moveit_msgs.msg import CollisionObject
from moveit_msgs.srv import GetPlanningScene
from rclpy.action import ActionServer
from sensor_msgs.msg import JointState

rclpy.init()
node = rclpy.create_node('move_group', enable_rosout=False)

async def execute_arm(_goal_handle):
    return FollowJointTrajectory.Result()

async def execute_hand(_goal_handle):
    return GripperCommand.Result()

arm = ActionServer(
    node,
    FollowJointTrajectory,
    '/panda_arm_controller/follow_joint_trajectory',
    execute_arm,
)
hand = ActionServer(
    node,
    GripperCommand,
    '/panda_hand_controller/gripper_cmd',
    execute_hand,
)

def list_controllers(_request, response):
    response.controller = [
        ControllerState(name=name, type='test/controller', state='active')
        for name in (
            'joint_state_broadcaster',
            'panda_arm_controller',
            'panda_hand_controller',
        )
    ]
    return response

def get_scene(_request, response):
    response.scene.world.collision_objects = [CollisionObject(id='coke')]
    return response

controller_service = node.create_service(
    ListControllers,
    '/controller_manager/list_controllers',
    list_controllers,
)
scene_service = node.create_service(GetPlanningScene, '/get_planning_scene', get_scene)
joint_publisher = node.create_publisher(JointState, '/joint_states', 10)

def publish_joint_state():
    message = JointState()
    message.name = ['panda_joint1', 'panda_finger_joint1']
    joint_publisher.publish(message)

timer = node.create_timer(0.05, publish_joint_state)
Path(os.environ['PROVIDER_READY']).write_text('ready', encoding='utf-8')
try:
    rclpy.spin(node)
finally:
    node.destroy_node()
    rclpy.try_shutdown()
"""
    provider = subprocess.Popen(
        [sys.executable, '-c', provider_source],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not provider_ready.exists() and time.monotonic() < deadline:
            if provider.poll() is not None:
                stdout, stderr = provider.communicate()
                raise AssertionError(stdout + stderr)
            time.sleep(0.05)
        assert provider_ready.exists(), 'ROS readiness provider did not start'

        result = subprocess.run(
            [sys.executable, str(PROBE), '--timeout', '10', '--poll-period', '0.02'],
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    finally:
        provider.terminate()
        provider.wait(timeout=5)

    assert result.returncode == 0, result.stdout + result.stderr
    reports = [json.loads(line) for line in result.stdout.splitlines()]
    assert [report['status'] for report in reports] == ['CORE_READY', 'ALL_READY']
    assert reports[-1] == {
        'status': 'ALL_READY',
        'move_group': True,
        'arm_action_server': True,
        'hand_action_server': True,
        'controllers': {
            'joint_state_broadcaster': 'active',
            'panda_arm_controller': 'active',
            'panda_hand_controller': 'active',
        },
        'joint_state': True,
        'planning_scene_coke': True,
    }

"""The real controller-manager and parameter calls, against in-test service servers."""

import threading
import time

import pytest
import rclpy
from controller_manager_msgs.msg import ControllerState
from controller_manager_msgs.srv import ListControllers, SwitchController
from rcl_interfaces.msg import ParameterType, ParameterValue, SetParametersResult
from rcl_interfaces.srv import GetParameters, SetParameters
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor

from so101_demo.adapters.act.head_neck_services import NeckControllerServices


class Servers:
    def __init__(self, context):
        self.node = rclpy.create_node('fake_controller_manager', context=context)
        self.state, self.params, self.switches, self.set_calls = 'inactive', {}, [], []
        self.node.create_service(ListControllers, '/controller_manager/list_controllers', self.list)
        self.node.create_service(SwitchController, '/controller_manager/switch_controller', self.switch)
        self.node.create_service(GetParameters, '/neck_controller/get_parameters', self.get)
        self.node.create_service(SetParameters, '/neck_controller/set_parameters', self.set)

    def list(self, request, response):
        response.controller = [
            ControllerState(name='arm_controller', type='joint_trajectory_controller/JointTrajectoryController',
                            state='active'),
            ControllerState(name='neck_controller', type='so101_mujoco_support/HeadNeckTrajectoryController',
                            state=self.state)]
        return response

    def switch(self, request, response):
        self.switches.append((list(request.activate_controllers), list(request.deactivate_controllers),
                              request.strictness))
        if list(request.activate_controllers) == ['neck_controller']:
            self.state = 'active'
        response.ok = True
        return response

    def get(self, request, response):
        for name in request.names:
            value = self.params.get(name)
            if isinstance(value, bool):
                response.values.append(ParameterValue(type=ParameterType.PARAMETER_BOOL, bool_value=value))
            elif isinstance(value, int):
                response.values.append(ParameterValue(type=ParameterType.PARAMETER_INTEGER, integer_value=value))
            elif isinstance(value, float):
                response.values.append(ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=value))
            elif isinstance(value, str):
                response.values.append(ParameterValue(type=ParameterType.PARAMETER_STRING, string_value=value))
            elif isinstance(value, list):
                response.values.append(ParameterValue(type=ParameterType.PARAMETER_STRING_ARRAY, string_array_value=value))
            else:
                response.values.append(ParameterValue(type=ParameterType.PARAMETER_NOT_SET))
        return response

    def set(self, request, response):
        for parameter in request.parameters:
            self.set_calls.append((parameter.name, parameter.value.integer_value))
            accepted = parameter.name != 'refused'
            response.results.append(SetParametersResult(successful=accepted, reason='' if accepted else 'no'))
            if accepted:
                self.params[parameter.name] = parameter.value.integer_value
        return response


@pytest.fixture
def rig(isolated_ros_domain):
    context = Context()
    rclpy.init(context=context)
    servers = Servers(context)
    client_node = rclpy.create_node('owner_client', context=context)
    executor = SingleThreadedExecutor(context=context)
    executor.add_node(servers.node)
    executor.add_node(client_node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    services = NeckControllerServices(client_node)
    try:
        yield servers, services
    finally:
        services.close()
        executor.shutdown()
        thread.join(2.)
        context.shutdown()


def deadline(seconds=3.):
    return time.monotonic() + seconds


def test_controller_returns_the_neck_type_and_state(rig):
    servers, services = rig
    assert services.controller(deadline=deadline()) == dict(
        type='so101_mujoco_support/HeadNeckTrajectoryController', state='inactive')
    servers.state = 'active'
    assert services.controller(deadline=deadline())['state'] == 'active'


def test_switch_uses_strict_activate_asap_and_reports_ok(rig):
    servers, services = rig
    assert services.switch(activate=('neck_controller',), deactivate=(), deadline=deadline()) is True
    assert servers.switches == [(['neck_controller'], [], SwitchController.Request.STRICT)]
    assert servers.state == 'active'


def test_get_parameters_converts_the_values_to_python(rig):
    servers, services = rig
    servers.params.update({'open_loop_control': False, 'interpolation_method': 'splines',
                           'head_deadman_timeout_s': 0.2, 'head_activation_id': 3,
                           'joints': ['neck_yaw_joint']})
    values = services.get_parameters(('open_loop_control', 'interpolation_method', 'head_deadman_timeout_s',
                                      'head_activation_id', 'joints'), deadline=deadline())
    assert values == {'open_loop_control': False, 'interpolation_method': 'splines',
                      'head_deadman_timeout_s': 0.2, 'head_activation_id': 3, 'joints': ['neck_yaw_joint']}


def test_set_integer_reports_acceptance_and_the_refusal_reason(rig):
    servers, services = rig
    assert services.set_integer('head_deadman_peer_pid', 4242, deadline=deadline()) == (True, '')
    assert servers.set_calls[-1] == ('head_deadman_peer_pid', 4242)
    assert services.set_integer('refused', 1, deadline=deadline()) == (False, 'no')


def test_an_unanswered_service_times_out(rig):
    servers, services = rig
    with pytest.raises(TimeoutError, match='HEAD_NECK_SERVICE_UNAVAILABLE'):
        NeckControllerServices(services.node, controller='other_controller').get_parameters(
            ('x',), deadline=deadline(.3))


def test_close_destroys_the_clients(rig):
    servers, services = rig
    receipt = services.close()
    assert receipt['closed'] is True and services.close()['closed'] is True

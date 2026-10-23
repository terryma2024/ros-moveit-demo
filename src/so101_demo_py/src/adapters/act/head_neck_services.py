"""Bounded controller-manager and neck-parameter calls on the owner's already-spinning node.

The owner's node is spun by the provider's executor thread, so every call is an asynchronous request
polled until its deadline (the same pattern as ``HeadSceneServices``).
"""

import time

from controller_manager_msgs.srv import ListControllers, SwitchController
from rcl_interfaces.msg import Parameter as ParameterMessage
from rcl_interfaces.msg import ParameterType, ParameterValue
from rcl_interfaces.srv import GetParameters, SetParameters
from rclpy.parameter import parameter_value_to_python


class NeckControllerServices:
    def __init__(self, node, controller='neck_controller'):
        self.node, self.controller_name = node, controller
        self.clients = {}
        try:
            for name, (kind, endpoint) in dict(
                    controllers=(ListControllers, '/controller_manager/list_controllers'),
                    switch=(SwitchController, '/controller_manager/switch_controller'),
                    get=(GetParameters, f'/{controller}/get_parameters'),
                    set=(SetParameters, f'/{controller}/set_parameters')).items():
                self.clients[name] = node.create_client(kind, endpoint)
        except Exception:
            self.close()
            raise
        self._closed = None

    def _call(self, name, request, *, deadline):
        client = self.clients[name]
        while not client.wait_for_service(timeout_sec=min(.02, max(0., deadline - time.monotonic()))):
            if time.monotonic() >= deadline:
                raise TimeoutError('HEAD_NECK_SERVICE_UNAVAILABLE:' + name)
        future = client.call_async(request)
        while not future.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                future.cancel()
                raise TimeoutError('HEAD_NECK_SERVICE_TIMEOUT:' + name)
            time.sleep(min(.002, remaining))
        result = future.result()
        if result is None:
            raise ValueError('HEAD_NECK_SERVICE_EMPTY:' + name)
        return result

    def controller(self, *, deadline):
        """The neck controller's type and lifecycle state, or None when the manager does not list it."""
        response = self._call('controllers', ListControllers.Request(), deadline=deadline)
        for row in response.controller:
            if row.name == self.controller_name:
                return dict(type=row.type, state=row.state)
        return None

    def switch(self, *, activate, deactivate, deadline):
        request = SwitchController.Request()
        request.activate_controllers, request.deactivate_controllers = list(activate), list(deactivate)
        request.strictness = request.STRICT
        request.activate_asap = True
        remaining_ns = max(1, round((deadline - time.monotonic()) * 1e9))
        request.timeout.sec, request.timeout.nanosec = divmod(remaining_ns, 1_000_000_000)
        return self._call('switch', request, deadline=deadline).ok is True

    def get_parameters(self, names, *, deadline):
        request = GetParameters.Request()
        request.names = list(names)
        response = self._call('get', request, deadline=deadline)
        if len(response.values) != len(request.names):
            raise ValueError('HEAD_NECK_PARAMETER_REPLY_INVALID')
        return {name: (None if value.type == ParameterType.PARAMETER_NOT_SET else parameter_value_to_python(value))
                for name, value in zip(request.names, response.values)}

    def set_integer(self, name, value, *, deadline):
        request = SetParameters.Request()
        request.parameters = [ParameterMessage(name=name, value=ParameterValue(
            type=ParameterType.PARAMETER_INTEGER, integer_value=int(value)))]
        response = self._call('set', request, deadline=deadline)
        if len(response.results) != 1:
            raise ValueError('HEAD_NECK_PARAMETER_REPLY_INVALID')
        return response.results[0].successful is True, response.results[0].reason

    def close(self):
        if getattr(self, '_closed', None) is not None:
            return dict(self._closed)
        failures = []
        for name, client in tuple(self.clients.items()):
            try:
                if self.node.destroy_client(client) is not True:
                    failures.append(name)
            except Exception as error:
                failures.append(name + ':' + type(error).__name__)
            self.clients.pop(name)
        self._closed = dict(closed=not failures, failures=failures)
        return dict(self._closed)

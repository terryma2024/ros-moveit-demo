import json
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize('eventual_ready', [False, True])
def test_main_readiness_retires_only_lost_readonly_query_without_reusing_stale_list(
        monkeypatch, capsys, eventual_ready):
    import threading
    import rclpy
    import rclpy.action
    from rclpy.client import Client as RosClient
    from rclpy.task import Future
    from controller_manager_msgs.srv import ListControllers
    from so101_demo.cli import motion_stack_ready as module
    now = [0.]; requests = []; retired = []
    names = ('joint_state_broadcaster', 'arm_controller', 'gripper_controller', 'neck_controller')
    class Client:
        def __init__(self):
            self._lock = threading.Lock(); self._pending_requests = {}
        def service_is_ready(self): return True
        def call_async(self, request):
            assert type(request) is ListControllers.Request
            assert not self._pending_requests, 'overlapping client query bookkeeping'
            requests.append(request); future = Future()
            if len(requests) == 1 or eventual_ready and len(requests) >= 3:
                rows = names if len(requests) >= 3 else ('joint_state_broadcaster', 'gripper_controller', 'neck_controller')
                future.set_result(SimpleNamespace(controller=[SimpleNamespace(name=n, state='active') for n in rows]))
            else:
                self._pending_requests[len(requests)] = future
            return future
        def remove_pending_request(self, future):
            assert not future.done()
            retired.append(future)
            RosClient.remove_pending_request(self, future)
    client = Client()
    node = SimpleNamespace(create_client=lambda kind, name: client if kind is ListControllers else
        SimpleNamespace(service_is_ready=lambda: True), destroy_node=lambda: None)
    monkeypatch.setattr(rclpy, 'init', lambda: None)
    monkeypatch.setattr(rclpy, 'shutdown', lambda: None)
    monkeypatch.setattr(rclpy, 'ok', lambda: True)
    monkeypatch.setattr(rclpy, 'create_node', lambda name: node)
    monkeypatch.setattr(rclpy, 'spin_until_future_complete',
        lambda *args, **kw: now.__setitem__(0, now[0] + (kw['timeout_sec'] if not args[1].done() else .01)))
    monkeypatch.setattr(rclpy, 'spin_once', lambda *args, **kw: now.__setitem__(0, now[0] + .01))
    monkeypatch.setattr(rclpy.action, 'ActionClient', lambda *args: SimpleNamespace(server_is_ready=lambda: True))
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: now[0],
        monotonic_ns=lambda: round(now[0] * 1e9)))
    assert module.main(['--timeout-s', '5', '--include-neck']) == (0 if eventual_ready else 1)
    result = json.loads(capsys.readouterr().out)
    assert retired, 'a lost read-only response blocked all later fresh controller observations'
    assert result['ready'] is eventual_ready
    evidence = result['evidence']['controller_query']
    assert evidence['query_timeouts'] == len(retired)
    assert now[0] <= 5.01 and evidence['pending'] is False
    if eventual_ready:
        assert len(requests) == 3 and evidence['responses_completed'] == 2
        assert evidence['controllers'] == {n: 'active' for n in names}
        assert evidence['last_response_monotonic_ns'] > 1_000_000_000
    else:
        assert evidence['controllers'] == {}
        assert evidence['responses_completed'] == 1
        assert result['failure_code'] == 'MOTION_STACK_CONTROLLER_CALL_TIMEOUT'
        assert evidence['last_completed_controllers'] == {
            n: 'active' for n in ('joint_state_broadcaster', 'gripper_controller', 'neck_controller')}


@pytest.mark.parametrize('eventual_ready',[False,True])
def test_readiness_retains_original_empty_to_all_role_query_evidence(monkeypatch,capsys,eventual_ready):
    import rclpy
    import rclpy.action
    from controller_manager_msgs.srv import ListControllers
    from so101_demo.cli import motion_stack_ready as module
    now=[0.]
    requests=[]
    names=(*module.CONTROLLER_NAMES,'neck_controller')
    class Client:
        def service_is_ready(self):return True
        def call_async(self,request):
            requests.append(request)
            rows=[SimpleNamespace(name=name,state='active') for name in names] if eventual_ready and len(requests)>=3 else []
            return SimpleNamespace(done=lambda:True,result=lambda:SimpleNamespace(controller=rows))
    client=Client()
    node=SimpleNamespace(create_client=lambda kind,name:client if kind is ListControllers else SimpleNamespace(service_is_ready=lambda:True),destroy_node=lambda:None)
    monkeypatch.setattr(rclpy,'init',lambda:None)
    monkeypatch.setattr(rclpy,'shutdown',lambda:None)
    monkeypatch.setattr(rclpy,'ok',lambda:True)
    monkeypatch.setattr(rclpy,'create_node',lambda name:node)
    def advance(*args,**kwargs):now[0]+=.01
    monkeypatch.setattr(rclpy,'spin_until_future_complete',advance)
    monkeypatch.setattr(rclpy,'spin_once',advance)
    monkeypatch.setattr(rclpy.action,'ActionClient',lambda *args:SimpleNamespace(server_is_ready=lambda:True))
    monkeypatch.setattr(module,'time',SimpleNamespace(monotonic=lambda:now[0],monotonic_ns=lambda:round(now[0]*1e9)))
    assert module.main(['--timeout-s','.5','--include-neck'])==(0 if eventual_ready else 1)
    result=json.loads(capsys.readouterr().out)
    evidence=result['evidence']['controller_query']
    assert evidence['requests_started']==evidence['responses_completed']==len(requests)>0
    assert evidence['last_response_monotonic_ns']>0 and evidence['pending'] is False
    assert evidence['service_visible'] and evidence['service_seen']
    assert evidence['controllers']==({name:'active' for name in names} if eventual_ready else {})
    assert result['ready'] is eventual_ready
    if not eventual_ready:assert result['failure_code']=='MOTION_STACK_CONTROLLER_NOT_ACTIVE'


def test_readiness_reports_all_required_dependencies() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    result = evaluate_readiness(
        controllers={
            "joint_state_broadcaster": "active",
            "arm_controller": "active",
            "gripper_controller": "active",
        },
        services={
            "/apply_planning_scene": True,
            "/get_planning_scene": True,
            "/plan_kinematic_path": True,
        },
        actions={
            "/execute_trajectory": True,
            "/arm_controller/follow_joint_trajectory": True,
            "/gripper_controller/follow_joint_trajectory": True,
        },
    )

    assert result.ready
    assert result.failure_code is None


def test_diagnostic_readiness_requires_neck_controller_and_action():
    from so101_demo.cli.motion_stack_ready import evaluate_readiness, CONTROLLER_NAMES, MOVEIT_SERVICE_NAMES, MOVEIT_ACTION_NAMES
    controllers={name:'active' for name in CONTROLLER_NAMES}
    services={name:True for name in MOVEIT_SERVICE_NAMES}
    actions={name:True for name in MOVEIT_ACTION_NAMES}
    result=evaluate_readiness(controllers=controllers,services=services,actions=actions,require_neck=True)
    assert not result.ready and result.evidence['dependency']=='neck_controller'
    controllers['neck_controller']='inactive'
    result=evaluate_readiness(controllers=controllers,services=services,actions=actions,require_neck=True)
    assert not result.ready and result.evidence['dependency']=='neck_controller'
    controllers['neck_controller']='active'
    result=evaluate_readiness(controllers=controllers,services=services,actions=actions,require_neck=True)
    assert not result.ready and result.evidence['dependency']=='/neck_controller/follow_joint_trajectory'
    actions['/neck_controller/follow_joint_trajectory']=True
    assert evaluate_readiness(controllers=controllers,services=services,actions=actions,require_neck=True).ready


def test_readiness_reports_first_missing_dependency_by_stable_order() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    result = evaluate_readiness(
        controllers={"joint_state_broadcaster": "inactive"},
        services={},
        actions={},
    )

    assert not result.ready
    assert result.phase == "CONTROLLERS"
    assert result.failure_code == "MOTION_STACK_CONTROLLER_NOT_ACTIVE"
    assert result.evidence["dependency"] == "joint_state_broadcaster"


def test_readiness_reports_moveit_service_before_actions() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    controllers = {
        "joint_state_broadcaster": "active",
        "arm_controller": "active",
        "gripper_controller": "active",
    }
    result = evaluate_readiness(
        controllers=controllers,
        services={"/apply_planning_scene": True, "/get_planning_scene": False},
        actions={},
    )

    assert result.phase == "MOVEIT_SERVICES"
    assert result.failure_code == "MOTION_STACK_MOVEIT_SERVICE_UNAVAILABLE"
    assert result.evidence["dependency"] == "/get_planning_scene"


def test_readiness_reports_missing_motion_action() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    controllers = {
        "joint_state_broadcaster": "active",
        "arm_controller": "active",
        "gripper_controller": "active",
    }
    services = {
        "/apply_planning_scene": True,
        "/get_planning_scene": True,
        "/plan_kinematic_path": True,
    }
    result = evaluate_readiness(
        controllers=controllers,
        services=services,
        actions={"/execute_trajectory": False},
    )

    assert result.phase == "ACTIONS"
    assert result.failure_code == "MOTION_STACK_ACTION_UNAVAILABLE"
    assert result.evidence["dependency"] == "/execute_trajectory"


def test_controller_query_is_not_gated_by_the_moveit_graph() -> None:
    """Direct controller traffic must start as soon as its own service is visible.

    Waiting for the whole MoveIt service/action graph before the first controller query is
    what made the earlier failure unattributable: a station stuck in hardware bring-up and a
    station with missing MoveIt services looked identical.
    """

    from so101_demo.cli.motion_stack_ready import controller_query_allowed

    assert controller_query_allowed(controller_service_visible=True)
    assert not controller_query_allowed(controller_service_visible=False)


def test_readiness_separates_dds_invisibility_from_a_call_timeout() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    invisible = evaluate_readiness(
        controllers={},
        services={},
        actions={},
        controller_service_visible=False,
    )
    timed_out = evaluate_readiness(
        controllers={},
        services={},
        actions={},
        controller_service_visible=True,
        controller_call_timed_out=True,
    )
    not_active = evaluate_readiness(
        controllers={"joint_state_broadcaster": "inactive"},
        services={},
        actions={},
    )

    assert invisible.failure_code == "MOTION_STACK_CONTROLLER_SERVICE_INVISIBLE"
    assert timed_out.failure_code == "MOTION_STACK_CONTROLLER_CALL_TIMEOUT"
    assert not_active.failure_code == "MOTION_STACK_CONTROLLER_NOT_ACTIVE"
    assert len(
        {invisible.failure_code, timed_out.failure_code, not_active.failure_code}
    ) == 3
    assert invisible.phase == timed_out.phase == not_active.phase == "CONTROLLERS"


def test_readiness_ignores_the_call_timeout_once_controllers_answer() -> None:
    from so101_demo.cli.motion_stack_ready import evaluate_readiness

    result = evaluate_readiness(
        controllers={
            "joint_state_broadcaster": "active",
            "arm_controller": "active",
            "gripper_controller": "active",
        },
        services={
            "/apply_planning_scene": True,
            "/get_planning_scene": True,
            "/plan_kinematic_path": True,
        },
        actions={
            "/execute_trajectory": True,
            "/arm_controller/follow_joint_trajectory": True,
            "/gripper_controller/follow_joint_trajectory": True,
        },
        controller_service_visible=True,
        controller_call_timed_out=True,
    )

    assert result.ready
    assert result.failure_code is None


def test_controller_query_keeps_one_pending_request_until_response() -> None:
    from so101_demo.cli.motion_stack_ready import poll_controller_states

    class Future:
        def __init__(self) -> None:
            self.complete = False

        def done(self) -> bool:
            return self.complete

        def result(self):
            controller = type(
                "Controller", (), {"name": "arm_controller", "state": "active"}
            )
            return type("Response", (), {"controller": [controller()]})()

    class Client:
        def __init__(self) -> None:
            self.calls = 0
            self.future = Future()

        def service_is_ready(self) -> bool:
            return True

        def call_async(self, _request):
            self.calls += 1
            return self.future

    client = Client()
    spin_calls = []

    def request_factory():
        return object()

    def spin(*args, **kwargs):
        spin_calls.append((args, kwargs))

    pending, observed = poll_controller_states(
        client,
        None,
        request_factory=request_factory,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
    )
    assert pending is client.future
    assert observed is None
    assert client.calls == 1

    pending, observed = poll_controller_states(
        client,
        pending,
        request_factory=request_factory,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
    )
    assert pending is client.future
    assert observed is None
    assert client.calls == 1

    client.future.complete = True
    pending, observed = poll_controller_states(
        client,
        pending,
        request_factory=request_factory,
        spin_until_future_complete=spin,
        node=object(),
        timeout_s=0.25,
    )
    assert pending is None
    assert observed == {"arm_controller": "active"}
    assert client.calls == 1
    assert len(spin_calls) == 3


def _run_paced_main(monkeypatch, capsys, *, timeout_s, active_from_request=None, never_done=False):
    import rclpy
    import rclpy.action
    from controller_manager_msgs.srv import ListControllers
    from so101_demo.cli import motion_stack_ready as module
    now = [0.]; requests = []; retired = []; starts = []
    names = module.CONTROLLER_NAMES
    class Future:
        def __init__(self, rows): self.rows = rows; self.finished = not never_done
        def done(self): return self.finished
        def result(self): return SimpleNamespace(controller=self.rows)
    class Client:
        def service_is_ready(self): return True
        def call_async(self, request):
            assert type(request) is ListControllers.Request
            requests.append(request); starts.append(now[0])
            active = active_from_request is not None and len(requests) >= active_from_request
            rows = [SimpleNamespace(name=n, state='active' if active else 'inactive') for n in names]
            return Future(rows)
        def remove_pending_request(self, future): retired.append(future)
    client = Client()
    node = SimpleNamespace(create_client=lambda kind, name: client if kind is ListControllers else
        SimpleNamespace(service_is_ready=lambda: True), destroy_node=lambda: None)
    monkeypatch.setattr(rclpy, 'init', lambda: None)
    monkeypatch.setattr(rclpy, 'shutdown', lambda: None)
    monkeypatch.setattr(rclpy, 'ok', lambda: True)
    monkeypatch.setattr(rclpy, 'create_node', lambda name: node)
    monkeypatch.setattr(rclpy, 'spin_until_future_complete',
        lambda *args, **kw: now.__setitem__(0, now[0] + (kw['timeout_sec'] if never_done else 0.)))
    monkeypatch.setattr(rclpy, 'spin_once', lambda *args, **kw: now.__setitem__(0, now[0] + .001))
    monkeypatch.setattr(rclpy.action, 'ActionClient', lambda *args: SimpleNamespace(server_is_ready=lambda: True))
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: now[0],
        monotonic_ns=lambda: round(now[0] * 1e9)))
    rc = module.main(['--timeout-s', str(timeout_s)])
    return rc, json.loads(capsys.readouterr().out), now[0], requests, starts, retired


def test_controller_probe_paces_new_requests_to_the_minimum_interval(monkeypatch, capsys):
    import math
    from so101_demo.cli import motion_stack_ready as module
    rc, result, _, requests, starts, _ = _run_paced_main(monkeypatch, capsys, timeout_s=2.0)
    evidence = result['evidence']['controller_query']
    bound = math.ceil(2.0 / 0.1) + 1
    assert rc == 1
    assert evidence['requests_started'] == len(requests)
    assert evidence['requests_started'] <= bound, (
        f"requests_started={evidence['requests_started']} exceeds bound {bound}")
    assert len(requests) >= 15
    assert all(b - a >= 0.1 - 1e-9 for a, b in zip(starts, starts[1:]))
    assert module.CONTROLLER_QUERY_MIN_INTERVAL_S == 0.1


def test_paced_probe_still_reports_ready_within_one_interval(monkeypatch, capsys):
    rc, result, elapsed, requests, _, _ = _run_paced_main(
        monkeypatch, capsys, timeout_s=2.0, active_from_request=2)
    assert rc == 0 and result['ready'] is True
    assert len(requests) == 2
    assert elapsed <= 0.1 + 0.002


def test_paced_probe_still_retires_a_pending_query_after_one_second(monkeypatch, capsys):
    rc, result, _, requests, starts, retired = _run_paced_main(
        monkeypatch, capsys, timeout_s=2.5, never_done=True)
    evidence = result['evidence']['controller_query']
    assert rc == 1
    assert result['failure_code'] == 'MOTION_STACK_CONTROLLER_CALL_TIMEOUT'
    assert evidence['query_timeouts'] == len(retired) >= 2
    assert all(b - a >= 1.0 - 1e-9 for a, b in zip(starts, starts[1:]))

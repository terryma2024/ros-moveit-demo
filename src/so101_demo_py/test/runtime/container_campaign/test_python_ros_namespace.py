"""Addressing gates for private container Python contexts; no motion or hardware."""

import importlib

import pytest


def module():
    return importlib.import_module('so101_demo.runtime.container_campaign.ros_namespace')


def test_unmarked_generic_and_macos_processes_keep_original_init_arguments():
    assert module().container_ros_init_options(environment={})=={}
    assert module().container_ros_init_options(environment={'ROS_NAMESPACE':'/generic'})=={}


@pytest.mark.parametrize('problem',['root','relative','mismatch'])
def test_invalid_or_conflicting_container_namespace_refuses_before_context_init(problem):
    namespace={'root':'/','relative':'act/worker','mismatch':'/act/campaign/w00'}[problem]
    environment=dict(SO101_ACT_CONTAINER_NAMESPACE=namespace,
        ROS_NAMESPACE='/foreign' if problem=='mismatch' else namespace)
    with pytest.raises(ValueError):module().container_ros_init_options(environment=environment)


def test_actual_jazzy_context_resolves_python_endpoints_in_private_namespace():
    import rclpy
    namespace='/act/context_test/w00'
    options=module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=namespace,ROS_NAMESPACE=namespace))
    context=rclpy.context.Context()
    context.init(**options,domain_id=231)
    node=None
    try:
        node=rclpy.create_node('scope_probe',context=context)
        assert node.get_namespace()==namespace
        assert node.resolve_topic_name('/cup_pose')==namespace+'/cup_pose'
        assert node.resolve_service_name('/mujoco_ros2_control_node/set_pause')==namespace+'/mujoco_ros2_control_node/set_pause'
        assert node.resolve_topic_name('/tf')==namespace+'/tf'
        assert node.resolve_topic_name('/task_camera/color')==namespace+'/task_camera/color'
    finally:
        if node is not None:node.destroy_node()
        context.shutdown()


# Node names of the namespaced stack of the first real container run (`/act/campaign_w1f_20261012T220436Z/w00`). Seen in that run: the eight
# required nodes plus `neck_controller` (the gate's `missing` list was empty), `controller_manager` and
# `move_group_private_94319910618432` (the first entries of its `unexpected` list), and a MoveIt node whose logger name is
# `act.campaign_w1f_20261012T220436Z.w00.moveit` - the node `moveit` directly in the stack namespace. The other internal and
# generated names are the ones the unnamespaced stack has; the rest of that run's list was cut off by the 300 character cap.
REAL_STACK_NAMESPACE='/act/campaign_w1f_20261012T220436Z/w00'
REAL_STACK_RELATIVE_NODES=('arm_controller','controller_manager','gripper_controller','joint_state_broadcaster','move_group',
    'move_group_private_94319910618432','moveit','moveit_2','moveit_simple_controller_manager','mujoco_ros2_control_node',
    'neck_controller','robot_state_publisher','robotsystem','so101_base_to_camera_link',
    'so101_camera_link_to_task_camera_frame','transform_listener_impl_abcdef')


def real_stack_nodes(*,without=(),extra=()):
    names=[name for name in REAL_STACK_RELATIVE_NODES if name not in without]
    return tuple(sorted(REAL_STACK_NAMESPACE+'/'+name for name in names)+list(extra))


def test_the_namespaced_stack_of_a_real_run_is_accepted():
    from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
    assert RuntimeBinding.worker_node_inventory_matches(real_stack_nodes(),teacher_profile=True,namespace=REAL_STACK_NAMESPACE)


def test_a_namespaced_stack_is_still_refused_when_anything_is_off():
    from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
    def accepted(nodes):
        return RuntimeBinding.worker_node_inventory_matches(tuple(sorted(nodes)),teacher_profile=True,namespace=REAL_STACK_NAMESPACE)
    assert not accepted(real_stack_nodes(extra=('/foreign/node',)))                                  # outside the namespace
    assert not accepted(real_stack_nodes(extra=(REAL_STACK_NAMESPACE+'/stray_node',)))                   # unknown node inside it
    assert not accepted(real_stack_nodes(extra=('/act/campaign_w1f_other/w00/arm_controller',)))     # another stack's node
    assert not accepted(real_stack_nodes(without=('arm_controller',)))                               # required node missing
    assert not accepted(real_stack_nodes(without=('neck_controller',)))
    assert not accepted(real_stack_nodes(without=('moveit',)))                                       # the MoveIt node is required
    assert not accepted(real_stack_nodes(extra=(REAL_STACK_NAMESPACE+'/arm_controller',)))              # duplicate
    assert not accepted(real_stack_nodes(without=('moveit',),extra=(REAL_STACK_NAMESPACE+'/move_group/moveit',)))
    assert not accepted(real_stack_nodes(extra=(REAL_STACK_NAMESPACE+'/moveit_3',)))                     # second generated moveit_N
    assert not accepted(tuple(name.removeprefix(REAL_STACK_NAMESPACE) for name in real_stack_nodes()))   # un-namespaced names
    assert not RuntimeBinding.worker_node_inventory_matches(real_stack_nodes()[::-1],teacher_profile=True,
        namespace=REAL_STACK_NAMESPACE)                                                              # unsorted


def test_the_inventory_scope_agrees_with_the_readiness_observer():
    from so101_demo.cli.act_stack_ready import graph_in_namespace
    scoped=[(node.rsplit('/',1)[1],node.rsplit('/',1)[0]) for node in real_stack_nodes()]
    assert graph_in_namespace(REAL_STACK_NAMESPACE,scoped)
    foreign=scoped+[('stray','/foreign')]
    assert not graph_in_namespace(REAL_STACK_NAMESPACE,foreign)


def test_a_real_context_flattens_the_moveit_node_into_the_stack_namespace():
    import rclpy
    options=module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=REAL_STACK_NAMESPACE,ROS_NAMESPACE=REAL_STACK_NAMESPACE))
    context=rclpy.context.Context()
    context.init(**options,domain_id=231)
    node=None
    try:
        # MoveIt creates its node as ('moveit', '/move_group'); the stack-wide `__ns` rule replaces that namespace
        node=rclpy.create_node('moveit',namespace='/move_group',context=context)
        assert node.get_fully_qualified_name()==REAL_STACK_NAMESPACE+'/moveit'
    finally:
        if node is not None:node.destroy_node()
        context.shutdown()


def test_the_unnamespaced_inventory_is_unchanged():
    from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
    base=tuple(sorted(RuntimeBinding.expected_worker_nodes()+('/neck_controller',
        '/controller_manager','/move_group/moveit','/moveit_simple_controller_manager','/robotsystem',
        '/move_group_private_1','/moveit_2','/transform_listener_impl_abcdef')))
    assert RuntimeBinding.worker_node_inventory_matches(base,teacher_profile=True)
    assert RuntimeBinding.worker_node_inventory_matches(tuple(n for n in base if n!='/neck_controller'))
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(sorted(n for n in base if n!='/move_group/moveit'
                                                                         )+['/moveit']),teacher_profile=True)
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(sorted(base+('/moveit',))),teacher_profile=True)
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(sorted(base+('/foreign/node',))),teacher_profile=True)


# ---- reset and evidence contexts (argument construction only) -----------------------------------------------------
# These tests build and inspect the arguments `rclpy.init` receives. They do not reach a ROS graph, so they do not prove that
# a real namespaced stack answers the reset and evidence calls; that needs a later real-container run.

NAMESPACE='/act/campaign/w00'
RESET_WORLD='/mujoco_ros2_control_node/reset_world'


class _InitReached(Exception):
    """Raised by the node factory so the call under test stops right after `rclpy.init`."""


@pytest.fixture
def init_calls(monkeypatch):
    import rclpy
    from so101_demo.backends.mujoco import teleop_runtime
    calls=[]
    def init(*args,**kwargs):
        calls.append((args,kwargs))
    def create_node(*args,**kwargs):
        raise _InitReached
    monkeypatch.setattr(rclpy,'init',init)
    monkeypatch.setattr(rclpy,'create_node',create_node)
    return teleop_runtime,calls


def reset_and_evidence_calls(teleop_runtime):
    for call in (lambda:teleop_runtime.current_evidence('session',timeout_s=.1),
                 lambda:teleop_runtime.transactional_reset('session',timeout_s=.1),
                 lambda:teleop_runtime.transactional_reset('session',timeout_s=.1,act_profile=True)):
        with pytest.raises(_InitReached):call()
        yield


def mark_container(monkeypatch):
    monkeypatch.setenv('SO101_ACT_CONTAINER_NAMESPACE',NAMESPACE)
    monkeypatch.setenv('ROS_NAMESPACE',NAMESPACE)


def test_reset_and_evidence_init_carry_container_remaps(init_calls,monkeypatch):
    teleop_runtime,calls=init_calls
    mark_container(monkeypatch)
    list(reset_and_evidence_calls(teleop_runtime))
    assert len(calls)==3
    for args,kwargs in calls:
        assert args==() and '__ns:='+NAMESPACE in kwargs['args']
        assert kwargs['args'][:2]==['--ros-args','-r']
        assert RESET_WORLD+':='+NAMESPACE+RESET_WORLD in kwargs['args']
        assert '/mujoco_ros2_control_node/set_pause:='+NAMESPACE+'/mujoco_ros2_control_node/set_pause' in kwargs['args']
        assert '/so101/simulation/evidence:='+NAMESPACE+'/so101/simulation/evidence' in kwargs['args']
        assert '/joint_states:='+NAMESPACE+'/joint_states' in kwargs['args']


def test_reset_world_is_remapped():
    import rclpy
    assert (RESET_WORLD,NAMESPACE+RESET_WORLD) in module().namespace_remappings(NAMESPACE)
    options=module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=NAMESPACE,ROS_NAMESPACE=NAMESPACE))
    context=rclpy.context.Context()
    context.init(**options,domain_id=232)
    node=None
    try:
        node=rclpy.create_node('reset_probe',context=context)
        assert node.resolve_service_name(RESET_WORLD)==NAMESPACE+RESET_WORLD
    finally:
        if node is not None:node.destroy_node()
        context.shutdown()


def test_marker_absent_keeps_bare_init(init_calls,monkeypatch):
    teleop_runtime,calls=init_calls
    monkeypatch.delenv('SO101_ACT_CONTAINER_NAMESPACE',raising=False)
    monkeypatch.setenv('ROS_NAMESPACE','/generic')
    list(reset_and_evidence_calls(teleop_runtime))
    assert calls==[((),{}),((),{}),((),{})]


def test_container_init_installs_no_signal_handlers(init_calls,monkeypatch):
    from rclpy.signals import SignalHandlerOptions
    teleop_runtime,calls=init_calls
    mark_container(monkeypatch)
    list(reset_and_evidence_calls(teleop_runtime))
    assert [kwargs['signal_handler_options'] for _args,kwargs in calls]==[SignalHandlerOptions.NO]*3
    # the shared options stay free of it: Context.init and the Recorder's own explicit option would otherwise collide
    assert 'signal_handler_options' not in module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=NAMESPACE,ROS_NAMESPACE=NAMESPACE))
    assert module().container_ros_global_init_options(environment={})=={}


def test_every_goal_lane_resolves_to_the_names_native_retirement_uses():
    """The task's cancel and status endpoints, under the container options, are the ones native retirement reaches."""
    import rclpy
    from so101_demo.runtime.container_campaign.controller_stop import _LANES
    from so101_demo.runtime.parallel_ros_ports.observations import _GOAL_LANES
    options=module().container_ros_init_options(environment=dict(
        SO101_ACT_CONTAINER_NAMESPACE=NAMESPACE,ROS_NAMESPACE=NAMESPACE))
    context=rclpy.context.Context()
    context.init(**options,domain_id=232)
    node=None
    try:
        node=rclpy.create_node('lane_probe',context=context)
        assert set(_GOAL_LANES.items())<=set(_LANES.items())          # same lane prefixes (the neck lane is native-only)
        for name,prefix in _GOAL_LANES.items():
            native=NAMESPACE+_LANES[name]
            assert node.resolve_service_name(prefix+'/cancel_goal')==native+'/cancel_goal',name
            assert node.resolve_topic_name(prefix+'/status')==native+'/status',name
    finally:
        if node is not None:node.destroy_node()
        context.shutdown()


# ---- default-context initialisers keep the shard's own signal handlers ---------------------------------------------------

def default_context_initialisers(monkeypatch):
    """The task-path calls that initialise the process-global default context in the shard (PID 1)."""
    from types import SimpleNamespace
    from so101_demo.ros.rgbd_snapshot import RosRgbdSnapshotSource
    from so101_demo.runtime.parallel_ros_ports import observations
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    reset=observations.ResetBoundaryReceipt('reset-2','session',1.,1.,2,(0.,)*6)
    def gate():
        import so101_demo.backends.mujoco.teleop_runtime as teleop
        monkeypatch.setattr(teleop,"current_evidence",lambda *args,**kwargs:SimpleNamespace(reset_epoch=2,left_fingertip_contacts=(),
            right_fingertip_contacts=()))
        return observations.observe_parallel_initial_gate(reset,namespace=NAMESPACE)
    pose=SimpleNamespace(source_stamp_ns=1,pose_world=SimpleNamespace(values=(0.,)*7))
    return {'rgbd_source':RosRgbdSnapshotSource,
            'shutdown_observation':lambda:observations.observe_worker_shutdown('session',timeout_s=.1),
            'initial_gate':gate,
            'pose_publication':lambda:ParallelRosRuntimePorts(SimpleNamespace(),catalog={}).publish_pose(pose)}


def fake_default_context(monkeypatch):
    import rclpy
    calls=[]
    monkeypatch.setattr(rclpy,'ok',lambda *args,**kwargs:False)
    monkeypatch.setattr(rclpy,'init',lambda *args,**kwargs:calls.append((args,kwargs)))
    monkeypatch.setattr(rclpy,'shutdown',lambda *args,**kwargs:None)
    monkeypatch.setattr(rclpy,'try_shutdown',lambda *args,**kwargs:None)
    def create_node(*args,**kwargs):
        raise _InitReached
    monkeypatch.setattr(rclpy,'create_node',create_node)
    return calls


@pytest.mark.parametrize('site',['rgbd_source','shutdown_observation','initial_gate','pose_publication'])
def test_default_context_initialisers_install_no_signal_handlers_in_a_container(site,monkeypatch):
    from rclpy.signals import SignalHandlerOptions
    calls=fake_default_context(monkeypatch)
    mark_container(monkeypatch)
    call=default_context_initialisers(monkeypatch)[site]
    with pytest.raises(_InitReached):call()
    (args,kwargs),=calls
    assert args==() and kwargs['signal_handler_options']==SignalHandlerOptions.NO
    assert '__ns:='+NAMESPACE in kwargs['args']


@pytest.mark.parametrize('site',['rgbd_source','shutdown_observation','initial_gate','pose_publication'])
def test_default_context_initialisers_are_unchanged_outside_a_container(site,monkeypatch):
    calls=fake_default_context(monkeypatch)
    monkeypatch.delenv('SO101_ACT_CONTAINER_NAMESPACE',raising=False)
    call=default_context_initialisers(monkeypatch)[site]
    with pytest.raises(_InitReached):call()
    assert calls==[((),{})]

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


def test_current_worker_inventory_accepts_only_its_own_complete_scoped_graph():
    from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
    namespace='/act/campaign/w00'
    base=tuple(sorted(RuntimeBinding.expected_worker_nodes()+('/neck_controller',
        '/controller_manager','/move_group/moveit','/moveit_simple_controller_manager','/robotsystem',
        '/move_group_private_1','/moveit_2','/transform_listener_impl_abcdef')))
    scoped=tuple(namespace+name for name in base)
    assert RuntimeBinding.worker_node_inventory_matches(scoped,teacher_profile=True,namespace=namespace)
    assert not RuntimeBinding.worker_node_inventory_matches(base,teacher_profile=True,namespace=namespace)
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(sorted(scoped+('/foreign/node',))),
        teacher_profile=True,namespace=namespace)
    assert not RuntimeBinding.worker_node_inventory_matches(tuple(n for n in scoped if not n.endswith('/neck_controller')),
        teacher_profile=True,namespace=namespace)

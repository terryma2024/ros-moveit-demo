"""Actual ROS typed readonly values, not planned configuration, bind Head mode."""
import pytest
from rcl_interfaces.msg import ParameterDescriptor,ParameterType,ParameterValue
from rcl_interfaces.srv import DescribeParameters,GetParameters
from so101_demo.act.head_simulation_policy import HeadSimulationPolicy


def validate(values,descriptors,policy):
    try:
        from so101_demo.adapters.act.head_native_policy_readback import validate_native_policy_readback
    except ModuleNotFoundError:
        pytest.fail('Actual native policy readback validator is missing')
    return validate_native_policy_readback(values,descriptors,policy)


def responses():
    policy=HeadSimulationPolicy.parse(HeadSimulationPolicy.default_document())
    values=GetParameters.Response(values=[
        ParameterValue(type=ParameterType.PARAMETER_STRING,string_value=policy.mode),
        ParameterValue(type=ParameterType.PARAMETER_INTEGER,integer_value=50_000_000)])
    descriptors=DescribeParameters.Response(descriptors=[
        ParameterDescriptor(name='head_simulation_mode',type=ParameterType.PARAMETER_STRING,read_only=True),
        ParameterDescriptor(name='head_fault_connection_timeout_ns',type=ParameterType.PARAMETER_INTEGER,read_only=True)])
    return policy,values,descriptors


def test_actual_typed_controller_values_and_readonly_descriptors_bind_exact_policy():
    policy,values,descriptors=responses()
    assert validate(values,descriptors,policy)==dict(
        head_simulation_mode=policy.mode,head_fault_connection_timeout_ns=50_000_000,
        read_only=True,dynamic_typing=False)


@pytest.mark.parametrize('damage',['missing_value','extra_value','missing_descriptor',
    'extra_descriptor','wrong_mode','wrong_budget','legacy_budget','mode_type','budget_type',
    'descriptor_type','descriptor_name','mutable','dynamic','untyped_values','untyped_descriptors'])
def test_actual_native_readback_rejects_unbound_or_different_service_configuration(damage):
    policy,values,descriptors=responses()
    if damage=='missing_value':values.values=values.values[:1]
    elif damage=='extra_value':values.values.append(ParameterValue())
    elif damage=='missing_descriptor':descriptors.descriptors=descriptors.descriptors[:1]
    elif damage=='extra_descriptor':descriptors.descriptors.append(ParameterDescriptor())
    elif damage=='wrong_mode':values.values[0].string_value='hardware'
    elif damage=='wrong_budget':values.values[1].integer_value=50_000_001
    elif damage=='legacy_budget':values.values[1].integer_value=2_000_000
    elif damage=='mode_type':values.values[0].type=ParameterType.PARAMETER_NOT_SET
    elif damage=='budget_type':values.values[1].type=ParameterType.PARAMETER_DOUBLE
    elif damage=='descriptor_type':descriptors.descriptors[1].type=ParameterType.PARAMETER_DOUBLE
    elif damage=='descriptor_name':descriptors.descriptors.reverse()
    elif damage=='mutable':descriptors.descriptors[0].read_only=False
    elif damage=='dynamic':descriptors.descriptors[1].dynamic_typing=True
    elif damage=='untyped_values':values={'values':values.values}
    else:descriptors={'descriptors':descriptors.descriptors}
    with pytest.raises(PermissionError,match='HEAD_NATIVE_POLICY_READBACK_INVALID'):
        validate(values,descriptors,policy)


@pytest.mark.parametrize('damage',['none','wrong_budget','mutable'])
def test_query_reads_real_owned_ros_service_before_any_motion(monkeypatch,damage):
    import os,threading,uuid
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from so101_demo.act.head_monitor import digest
    from so101_demo.adapters.act import head_native_policy_readback
    query=getattr(head_native_policy_readback,'read_native_policy',None)
    if query is None:pytest.fail('Actual native parameter service reader is missing')
    monkeypatch.setenv('ROS_DOMAIN_ID',str(130+int(uuid.uuid4().hex[:4],16)%90))
    context=Context();rclpy.init(context=context)
    owner=Node('neck_controller',context=context);reader=Node('head_readback_test',context=context)
    executor=SingleThreadedExecutor(context=context);thread=None
    try:
        policy,_,_=responses()
        owner.declare_parameter('head_simulation_mode',policy.mode,
            ParameterDescriptor(read_only=damage!='mutable'))
        owner.declare_parameter('head_fault_connection_timeout_ns',
            50_000_001 if damage=='wrong_budget' else 50_000_000,ParameterDescriptor(read_only=True))
        executor.add_node(owner);executor.add_node(reader)
        thread=threading.Thread(target=executor.spin,name='head-readback-test-services');thread.start()
        if damage!='none':
            with pytest.raises(PermissionError,match='HEAD_NATIVE_POLICY_READBACK_INVALID'):
                query(reader,policy,timeout_s=2.)
        else:
            receipt=query(reader,policy,timeout_s=2.)
            assert receipt['values']==dict(head_simulation_mode=policy.mode,
                head_fault_connection_timeout_ns=50_000_000,read_only=True,dynamic_typing=False)
            assert receipt['remote_node']=='/neck_controller' and receipt['reader_node']=='/head_readback_test'
            assert receipt['simulation_policy_sha256']==digest(policy.readback())
            assert receipt['motion_authority'] is False
            assert receipt['query_wall_s']<=receipt['completed_wall_s']<receipt['deadline_wall_s']
        assert not list(reader.clients)  # owned read-only clients retired, no action/native clients
    finally:
        assert executor.shutdown(timeout_sec=2.) is True
        if thread is not None:thread.join(2.);assert not thread.is_alive()
        owner.destroy_node();reader.destroy_node();context.shutdown()

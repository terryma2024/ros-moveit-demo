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
        ParameterValue(type=ParameterType.PARAMETER_INTEGER,integer_value=50_000_000),
        ParameterValue(type=ParameterType.PARAMETER_STRING,
            string_value='quintic_measured_prefix_v1'),
        ParameterValue(type=ParameterType.PARAMETER_BOOL,bool_value=False)])
    descriptors=DescribeParameters.Response(descriptors=[
        ParameterDescriptor(name='head_simulation_mode',type=ParameterType.PARAMETER_STRING,read_only=True),
        ParameterDescriptor(name='head_fault_connection_timeout_ns',type=ParameterType.PARAMETER_INTEGER,read_only=True),
        ParameterDescriptor(name='head_measured_prefix_guard',type=ParameterType.PARAMETER_STRING,read_only=True),
        ParameterDescriptor(name='speed_scaling_input_enabled',type=ParameterType.PARAMETER_BOOL,read_only=True)])
    return policy,values,descriptors


def test_actual_typed_controller_values_and_readonly_descriptors_bind_exact_policy():
    policy,values,descriptors=responses()
    assert validate(values,descriptors,policy)==dict(
        head_simulation_mode=policy.mode,head_fault_connection_timeout_ns=50_000_000,
        head_measured_prefix_guard='quintic_measured_prefix_v1',
        speed_scaling_input_enabled=False,
        read_only=True,dynamic_typing=False)


@pytest.mark.parametrize('damage',['missing_value','extra_value','missing_descriptor',
    'extra_descriptor','wrong_mode','wrong_budget','legacy_budget','mode_type','budget_type',
    'descriptor_type','descriptor_name','mutable','dynamic','untyped_values','untyped_descriptors',
    'missing_guard','wrong_guard','guard_type','guard_mutable','switch_true','switch_type',
    'switch_mutable'])
def test_actual_native_readback_rejects_unbound_or_different_service_configuration(damage):
    policy,values,descriptors=responses()
    if damage=='missing_value':values.values=values.values[:1]
    elif damage=='extra_value':values.values.append(ParameterValue())
    elif damage=='missing_descriptor':descriptors.descriptors=descriptors.descriptors[:1]
    elif damage=='extra_descriptor':descriptors.descriptors.append(ParameterDescriptor())
    elif damage=='wrong_mode':values.values[0].string_value='hardware'
    elif damage=='wrong_budget':values.values[1].integer_value=50_000_001
    elif damage=='missing_guard':values.values=values.values[:2]
    elif damage=='wrong_guard':values.values[2].string_value=''
    elif damage=='guard_type':values.values[2].type=ParameterType.PARAMETER_INTEGER
    elif damage=='guard_mutable':descriptors.descriptors[2].read_only=False
    elif damage=='switch_true':values.values[3].bool_value=True
    elif damage=='switch_type':values.values[3].type=ParameterType.PARAMETER_STRING
    elif damage=='switch_mutable':descriptors.descriptors[3].read_only=False
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
    from so101_demo.act.head_evidence_identity import digest
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
        owner.declare_parameter('head_measured_prefix_guard',
            '' if damage=='wrong_guard' else 'quintic_measured_prefix_v1',
            ParameterDescriptor(read_only=damage!='guard_mutable'))
        owner.declare_parameter('speed_scaling_input_enabled',damage=='switch_true',
            ParameterDescriptor(read_only=damage!='switch_mutable'))
        executor.add_node(owner);executor.add_node(reader)
        thread=threading.Thread(target=executor.spin,name='head-readback-test-services');thread.start()
        if damage!='none':
            with pytest.raises(PermissionError,match='HEAD_NATIVE_POLICY_READBACK_INVALID'):
                query(reader,policy,timeout_s=2.)
        else:
            receipt=query(reader,policy,timeout_s=2.)
            assert receipt['values']==dict(head_simulation_mode=policy.mode,
                head_fault_connection_timeout_ns=50_000_000,
                head_measured_prefix_guard='quintic_measured_prefix_v1',
                speed_scaling_input_enabled=False,
                read_only=True,dynamic_typing=False)
            assert receipt['remote_node']=='/neck_controller' and receipt['reader_node']=='/head_readback_test'
            assert receipt['simulation_policy_sha256']==digest(policy.readback())
            assert receipt['motion_authority'] is False
            assert receipt['query_wall_s']<=receipt['completed_wall_s']<receipt['deadline_wall_s']
        assert not list(reader.clients)  # owned read-only clients retired, no action/native clients
    finally:
        assert executor.shutdown(timeout_sec=2.) is True
        if thread is not None:thread.join(2.);assert not thread.is_alive()
        owner.destroy_node();reader.destroy_node();context.shutdown()

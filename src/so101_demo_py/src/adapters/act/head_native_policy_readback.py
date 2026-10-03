"""Read actual once-bound neck parameters; this grants no motion authority."""
import math
import time

from rcl_interfaces.msg import ParameterType
from rcl_interfaces.srv import DescribeParameters,GetParameters

from so101_demo.act.head_simulation_policy import HeadSimulationPolicy
from so101_demo.act.head_monitor import digest

_NAMES=('head_simulation_mode','head_fault_connection_timeout_ns')


def validate_native_policy_receipt(receipt,policy,*,reader_node):
    fields={'remote_node','reader_node','values','simulation_policy_sha256',
        'query_wall_s','completed_wall_s','deadline_wall_s','motion_authority'}
    expected=dict(head_simulation_mode=policy.mode,
        head_fault_connection_timeout_ns=round(policy.native_close_timeout_s*1e9),
        read_only=True,dynamic_typing=False)
    if (type(receipt) is not dict or set(receipt)!=fields or type(reader_node) is not str
            or not reader_node.startswith('/') or receipt['remote_node']!='/neck_controller'
            or receipt['reader_node']!=reader_node or receipt['motion_authority'] is not False
            or receipt['simulation_policy_sha256']!=digest(policy.readback())
            or type(receipt['values']) is not dict or set(receipt['values'])!=set(expected)
            or any(type(receipt['values'][key]) is not type(value) or receipt['values'][key]!=value
                for key,value in expected.items())
            or any(type(receipt[key]) not in (int,float) or not math.isfinite(receipt[key])
                for key in ('query_wall_s','completed_wall_s','deadline_wall_s'))
            or not 0<=receipt['query_wall_s']<=receipt['completed_wall_s']<receipt['deadline_wall_s']):
        raise PermissionError('HEAD_NATIVE_POLICY_RECEIPT_INVALID')


def validate_native_policy_readback(values,descriptors,policy):
    if (not isinstance(policy,HeadSimulationPolicy)
            or type(values) is not GetParameters.Response
            or type(descriptors) is not DescribeParameters.Response
            or len(values.values)!=2 or len(descriptors.descriptors)!=2):
        raise PermissionError('HEAD_NATIVE_POLICY_READBACK_INVALID')
    expected_types=(ParameterType.PARAMETER_STRING,ParameterType.PARAMETER_INTEGER)
    for name,kind,value,descriptor in zip(_NAMES,expected_types,values.values,descriptors.descriptors):
        if (value.type!=kind or descriptor.name!=name or descriptor.type!=kind
                or descriptor.read_only is not True or descriptor.dynamic_typing is not False):
            raise PermissionError('HEAD_NATIVE_POLICY_READBACK_INVALID')
    mode,budget=values.values[0].string_value,values.values[1].integer_value
    if mode!=policy.mode or budget!=round(policy.native_close_timeout_s*1e9):
        raise PermissionError('HEAD_NATIVE_POLICY_READBACK_INVALID')
    return dict(head_simulation_mode=mode,head_fault_connection_timeout_ns=budget,
        read_only=True,dynamic_typing=False)


def read_native_policy(node,policy,*,timeout_s=5.,cancelled=None):
    """Use the entry's already-spinning node; own two readonly clients once."""
    if (not isinstance(policy,HeadSimulationPolicy) or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=5
            or cancelled is not None and not callable(cancelled)):
        raise ValueError('HEAD_NATIVE_POLICY_QUERY_CONFIG_INVALID')
    started=time.monotonic();deadline=started+timeout_s;clients=[];futures=[]
    def current():
        if not node.context.ok() or cancelled is not None and cancelled():
            raise PermissionError('HEAD_NATIVE_POLICY_QUERY_RETIRED')
        if time.monotonic()>=deadline:raise TimeoutError('HEAD_NATIVE_POLICY_QUERY_DEADLINE')
    def unique_owner():
        count=node.get_node_names_and_namespaces().count(('neck_controller','/'))
        if count>1:
            raise PermissionError('HEAD_NATIVE_POLICY_QUERY_OWNER_AMBIGUOUS')
        return count==1
    try:
        for kind,name in ((GetParameters,'get_parameters'),(DescribeParameters,'describe_parameters')):
            clients.append(node.create_client(kind,'/neck_controller/'+name))
        while not all(client.service_is_ready() for client in clients) or not unique_owner():
            current();time.sleep(min(.002,max(0.,deadline-time.monotonic())))
        current()
        for client,kind in zip(clients,(GetParameters,DescribeParameters)):
            current();futures.append(client.call_async(kind.Request(names=list(_NAMES))))
        while not all(future.done() for future in futures):
            current();time.sleep(min(.002,max(0.,deadline-time.monotonic())))
        while not unique_owner():
            current();time.sleep(min(.002,max(0.,deadline-time.monotonic())))
        current()
        values=validate_native_policy_readback(*(future.result() for future in futures),policy)
        current()
        return dict(remote_node='/neck_controller',reader_node=node.get_fully_qualified_name(),
            values=values,simulation_policy_sha256=digest(policy.readback()),
            query_wall_s=started,completed_wall_s=time.monotonic(),deadline_wall_s=deadline,
            motion_authority=False)
    finally:
        for future in futures:
            if not future.done():future.cancel()
        failed=False
        for client in clients:
            if node.destroy_client(client) is not True:failed=True
        if failed:raise PermissionError('HEAD_NATIVE_POLICY_QUERY_RETIRE_UNCONFIRMED')

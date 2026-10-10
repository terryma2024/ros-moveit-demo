"""Bounded close-only transport for the local Head primary-fault channel.

It carries no ROS action, ARM, reservation, inference, or fallback close authority.
The owning primary process supplies the native PID/start identity and capability.
"""

import ctypes
import hashlib
import json
import os
from pathlib import Path
import time


class _NativeResult(ctypes.Structure):
    _fields_=[('phase',ctypes.c_uint32),('error_number',ctypes.c_uint32),
        ('reply_size',ctypes.c_uint32),('phases_present',ctypes.c_uint32),
        ('entry_ns',ctypes.c_uint64),('ack_ns',ctypes.c_uint64),('ended_ns',ctypes.c_uint64),
        ('phases_ns',ctypes.c_uint64*6),('reply',ctypes.c_uint8*154)]


class _ExpectedIdentity(ctypes.Structure):
    _fields_=[('role',ctypes.c_uint8),('incarnation_length',ctypes.c_uint8),
        ('incarnation',ctypes.c_uint8*64),('boot_length',ctypes.c_uint8),('boot',ctypes.c_uint8*64)]


def _load_transport(simulation_policy=None):
    from ament_index_python.packages import get_package_prefix
    path=Path(get_package_prefix('so101_mujoco_support'))/'lib/libso101_head_revocation_transport.so'
    try:
        if not path.is_file() or path.is_symlink():raise RuntimeError('native transport is not a copied artifact')
        library=ctypes.CDLL(str(path))
        for name in ('so101_head_revocation_abi','so101_head_revocation_result_size'):
            function=getattr(library,name);function.argtypes=[];function.restype=ctypes.c_uint32
        abi=library.so101_head_revocation_abi()
        if abi!=2 or library.so101_head_revocation_result_size()!=ctypes.sizeof(_NativeResult):
            raise RuntimeError('native transport ABI mismatch')
        origin=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            abi=abi,clock='CLOCK_MONOTONIC')
        if simulation_policy is None:
            exchange=library.so101_head_revocation_exchange
        else:
            maximum=library.so101_head_revocation_simulation_max_budget_ns
            maximum.argtypes=[];maximum.restype=ctypes.c_uint64
            if maximum()!=250000000:
                raise RuntimeError('native simulation transport ceiling mismatch')
            exchange=library.so101_head_revocation_simulation_exchange
            origin.update(mode=simulation_policy.mode,maximum_budget_ns=maximum(),
                simulation_policy_sha256=hashlib.sha256(json.dumps(
                    simulation_policy.readback(),sort_keys=True,separators=(',',':'),
                    allow_nan=False).encode()).hexdigest())
        exchange.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_uint8),ctypes.c_uint64,
            ctypes.c_uint32,ctypes.c_int32,ctypes.c_uint64,ctypes.c_uint64,ctypes.c_uint64,
            ctypes.c_uint32,ctypes.POINTER(_ExpectedIdentity),ctypes.POINTER(_NativeResult)]
        exchange.restype=ctypes.c_uint32
        if time.get_clock_info('monotonic').implementation!='clock_gettime(CLOCK_MONOTONIC)':
            raise RuntimeError('native transport clock mismatch')
        return library,exchange,origin
    except (OSError,AttributeError,RuntimeError) as error:
        raise RuntimeError('HEAD_REVOKER_NATIVE_TRANSPORT_REQUIRED') from error


class NativeRevocationClient:
    _connection_bound_s=.002

    def __init__(self, path, *, capability, native_owner, generation,
                 timeout_s, monotonic=time.monotonic, simulation_policy=None, event_log_enabled=True):
        if simulation_policy is not None:
            from ...act.head_simulation_policy import HeadSimulationPolicy
            simulation_policy=(simulation_policy if isinstance(simulation_policy,HeadSimulationPolicy)
                else HeadSimulationPolicy.parse(simulation_policy))
        self._simulation_policy=simulation_policy
        bound=(self._connection_bound_s if simulation_policy is None
            else simulation_policy.native_close_timeout_s)
        self.path=Path(path)
        self.capability=capability
        self.native_owner=dict(native_owner)
        self.generation=generation
        self.timeout=timeout_s
        self.monotonic=monotonic
        self._last_exchange=None
        self._event_log_enabled=event_log_enabled
        if (type(generation) is not int or not 0<generation<2**64
                or type(timeout_s) not in (int,float) or not 0<timeout_s<=bound
                or (simulation_policy is not None and timeout_s!=bound)
                or monotonic is not time.monotonic or type(event_log_enabled) is not bool
                or not isinstance(capability,bytes) or len(capability)!=32 or not any(capability)
                or set(self.native_owner)!= {'uid','pid','start_ticks'}
                or any(type(value) is not int for value in self.native_owner.values())
                or not 0<=self.native_owner['uid']<2**32
                or not 0<self.native_owner['pid']<2**31
                or not 0<self.native_owner['start_ticks']<2**64
                or len(os.fsencode(self.path))>107 or '\x00' in str(self.path)
                or not self.path.is_absolute() or self.path!=Path(os.path.normpath(self.path))):
            raise ValueError('HEAD_REVOKER_CONFIG_INVALID')
        # Resolve the exact installed ABI before safety activation, never on a
        # fault path. Only the implementation is cached; authentication is not.
        self._library,self._native_exchange,self.transport_origin=(
            _load_transport() if simulation_policy is None else _load_transport(simulation_policy))
        self._scope=(self.capability,self.generation,dict(self.native_owner),self.path,
            self.timeout,self._simulation_policy)

    @property
    def exchange_trace(self):
        trace=self._last_exchange
        return None if trace is None else dict(trace,native_owner=dict(trace['native_owner']),phases=dict(trace['phases']))

    def _exchange(self, *, identity=False, operation=None, expected_identity=None, overall_deadline_ns=None):
        # The compiled ABI constructs only identity and close frames, never
        # ARM/reserve. Refuse changed scope before serialization or C coercion.
        if (self.capability,self.generation,self.native_owner,self.path,
                self.timeout,self._simulation_policy)!=self._scope:
            raise PermissionError('HEAD_REVOKER_SCOPE_CHANGED')
        operation=(1 if identity else 2) if operation is None else operation
        if type(operation) is not int or operation not in (1,2,3,4):
            raise ValueError('HEAD_REVOKER_OPERATION_INVALID')
        expected=None
        if operation==4:
            from .head_control_protocol import identity_fields
            fields=identity_fields(expected_identity,self.generation)
            expected=_ExpectedIdentity();expected.role=fields['role']
            for name,length_name in [('incarnation','incarnation_length'),('boot','boot_length')]:
                value=fields[name].encode('ascii');setattr(expected,length_name,len(value))
                getattr(expected,name)[:len(value)]=value
        elif expected_identity is not None:
            raise ValueError('HEAD_REVOKER_OPERATION_INVALID')
        if overall_deadline_ns is not None and (type(overall_deadline_ns) is not int or overall_deadline_ns<=0):
            raise ValueError('HEAD_STARTUP_DEADLINE_INVALID')
        capability=(ctypes.c_uint8*32).from_buffer_copy(self.capability)
        output=_NativeResult();path=os.fsencode(self.path);owner=dict(self.native_owner)
        started=self.monotonic();request_ns=round(started*1e9);budget_ns=round(self.timeout*1e9)
        if overall_deadline_ns is not None:
            budget_ns=min(budget_ns,overall_deadline_ns-request_ns)
            if budget_ns<=0:raise TimeoutError('HEAD_STARTUP_DEADLINE_EXPIRED')
        # CDLL releases the GIL once. The compiled transport checks every path
        # and peer on this exchange and includes delayed native entry in the
        # same absolute caller-request deadline. It creates no worker.
        code=self._native_exchange(path,capability,self.generation,owner['uid'],owner['pid'],
            owner['start_ticks'],request_ns,budget_ns,operation,
            None if expected is None else ctypes.byref(expected),ctypes.byref(output))
        returned=self.monotonic()
        if self._event_log_enabled:
            names=('path_verified','connected','request_peer_verified','sent','reply_received','reply_peer_verified')
            phases=('path','connect','request_peer','send','receive','reply_peer','final_deadline','complete')
            error_type={1:'ValueError',2:'PermissionError',3:'PermissionError',4:'OSError',5:'TimeoutError',
                        6:'RuntimeError',7:'RuntimeError'}.get(code)
            self._last_exchange=dict(request_wall_s=request_ns*1e-9,deadline_wall_s=(request_ns+budget_ns)*1e-9,
                native_owner=owner,generation=self.generation,phase=phases[output.phase] if output.phase<8 else 'invalid',
                phases={name:output.phases_ns[i]*1e-9 for i,name in enumerate(names) if output.phases_present&(1<<i)},
                entry_wall_s=output.entry_ns*1e-9,ended_wall_s=output.ended_ns*1e-9,
                caller_return_wall_s=returned,error_type=error_type,error_number=output.error_number,
                native_transport=dict(self.transport_origin),operation={1:'identity',2:'close',3:'bootstrap_identity',4:'close_scoped'}[operation])
        if code:
            exception={1:ValueError,2:PermissionError,3:PermissionError,4:OSError,5:TimeoutError,
                       6:RuntimeError,7:RuntimeError}.get(code,RuntimeError)
            raise exception('HEAD_REVOKER_NATIVE_EXCHANGE_REFUSED_'+str(code))
        if overall_deadline_ns is not None and round(returned*1e9)>=overall_deadline_ns:
            raise TimeoutError('HEAD_STARTUP_DEADLINE_EXPIRED')
        if (output.phase!=7 or not request_ns<=output.ack_ns<request_ns+budget_ns
                or output.reply_size>154):raise RuntimeError('HEAD_REVOKER_NATIVE_RECEIPT_INVALID')
        return bytes(output.reply[:output.reply_size]),dict(request_wall_s=request_ns*1e-9,
            ack_wall_s=output.ack_ns*1e-9,native_owner=owner,generation=self.generation,
            native_transport=dict(self.transport_origin),caller_return_wall_s=returned)

    def close_strict(self):
        reply,receipt=self._exchange()
        if (len(reply)!=16 or reply[:5]!=b'SOGA\x01' or reply[6:8]!=bytes(2)
                or reply[5] not in (0,1)
                or int.from_bytes(reply[8:16],'big')!=self.generation):
            raise RuntimeError('HEAD_REVOKER_ACK_INVALID')
        if reply[5]!=0:raise RuntimeError('HEAD_REVOKER_REJECTED')
        return dict(receipt,ack_validated=True)

    def identity(self, *, overall_deadline_ns=None):
        reply,receipt=self._exchange(identity=True,overall_deadline_ns=overall_deadline_ns)
        if (reply[:7]!=b'SOID\x01\x01\x03'
                or int.from_bytes(reply[7:15],'big')!=self.generation):
            raise RuntimeError('HEAD_REVOKER_IDENTITY_INVALID')
        values=[];offset=15
        for _ in range(2):
            if offset>=len(reply):raise RuntimeError('HEAD_REVOKER_IDENTITY_INVALID')
            length=reply[offset];offset+=1
            if not 0<length<=64 or offset+length>len(reply):
                raise RuntimeError('HEAD_REVOKER_IDENTITY_INVALID')
            value=reply[offset:offset+length]
            if any(byte<32 or byte>126 for byte in value):
                raise RuntimeError('HEAD_REVOKER_IDENTITY_INVALID')
            values.append(value.decode('ascii'));offset+=length
        if offset!=len(reply):raise RuntimeError('HEAD_REVOKER_IDENTITY_INVALID')
        self._check_startup_deadline(overall_deadline_ns)
        return dict(receipt,role=3,incarnation=values[0],boot=values[1])

    def bootstrap_identity(self, *, overall_deadline_ns):
        from .head_control_protocol import parse_identity_scope
        reply,receipt=self._exchange(operation=3,overall_deadline_ns=overall_deadline_ns)
        identity=parse_identity_scope(reply,generation=self.generation)
        if identity['status']!='AVAILABLE':raise PermissionError('HEAD_REVOKER_BOOTSTRAP_SCOPE_REFUSED')
        self._check_startup_deadline(overall_deadline_ns)
        return dict(receipt,**identity,ack_validated=True)

    def close_scoped_strict(self, *, expected_identity):
        from .head_control_protocol import identity_fields,parse_identity_scope
        expected=identity_fields(expected_identity,self.generation)
        reply,receipt=self._exchange(operation=4,expected_identity=expected)
        result=parse_identity_scope(reply,generation=self.generation,close=True)
        if result['status'] not in ('ARMED_CLOSED','NOT_ARMED_CLOSED') or identity_fields(result,self.generation)!=expected:
            raise RuntimeError('HEAD_REVOKER_SCOPED_CLOSE_REFUSED')
        return dict(receipt,**result,ack_validated=True)

    def _check_startup_deadline(self,deadline):
        if deadline is not None and time.monotonic_ns()>=deadline:
            raise TimeoutError('HEAD_STARTUP_DEADLINE_EXPIRED')

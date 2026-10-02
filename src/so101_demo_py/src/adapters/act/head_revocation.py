"""Bounded close-only transport for the independently exec'd Head monitor.

No ROS action, arm, reservation, inference, or fallback close authority lives here.
The entrypoint supplies the actual owned native PID/start identity and capability.
"""

import os
from pathlib import Path
import socket
import stat
import struct
import time

from .controller_reservation_provision import _private_parent, _process_start_ticks


class NativeRevocationClient:
    def __init__(self, path, *, capability, native_owner, generation,
                 timeout_s, monotonic=time.monotonic):
        self.path=Path(path)
        self.capability=capability
        self.native_owner=dict(native_owner)
        self.generation=generation
        self.timeout=timeout_s
        self.monotonic=monotonic
        if (type(generation) is not int or not 0<generation<2**64
                or type(timeout_s) not in (int,float) or not 0<timeout_s<=.002
                or not callable(monotonic)
                or not isinstance(capability,bytes) or len(capability)!=32 or not any(capability)
                or set(self.native_owner)!= {'uid','pid','start_ticks'}
                or any(type(value) is not int for value in self.native_owner.values())
                or not 0<=self.native_owner['uid']<2**32
                or not 0<self.native_owner['pid']<2**31
                or not 0<self.native_owner['start_ticks']<2**64
                or len(os.fsencode(self.path))>107):
            raise ValueError('HEAD_REVOKER_CONFIG_INVALID')

    def _verify_peer(self,connection):
        pid,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if (uid!=self.native_owner['uid'] or pid!=self.native_owner['pid']
                or _process_start_ticks(pid)!=self.native_owner['start_ticks']):
            raise PermissionError('HEAD_REVOKER_NATIVE_PEER_INVALID')

    def _remaining(self, deadline):
        remaining=deadline-self.monotonic()
        if remaining<=0:raise TimeoutError('HEAD_REVOKER_TIMEOUT')
        return remaining

    def _exchange(self, body, *, identity=False):
        started=self.monotonic();deadline=started+self.timeout
        _private_parent(self.path)
        endpoint=self.path.lstat()
        if (not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid!=os.geteuid()
                or stat.S_IMODE(endpoint.st_mode)!=0o600):
            raise PermissionError('HEAD_REVOKER_PATH_INVALID')
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(self._remaining(deadline))
            connection.connect(str(self.path))
            # Authenticate the connected endpoint before writing capability
            # bytes. A correct-looking reply from another process has no value.
            self._verify_peer(connection)
            connection.settimeout(self._remaining(deadline))
            connection.sendall(len(body).to_bytes(4,'big')+body)
            def read(size):
                result=bytearray()
                while len(result)<size:
                    connection.settimeout(self._remaining(deadline))
                    value=connection.recv(size-len(result))
                    if not value:raise RuntimeError('HEAD_REVOKER_REPLY_INCOMPLETE')
                    result.extend(value)
                return bytes(result)
            if identity:
                size=int.from_bytes(read(4),'big')
                if not 17<=size<=145:raise RuntimeError('HEAD_REVOKER_IDENTITY_INVALID')
                reply=read(size)
            else:reply=read(16)
            self._verify_peer(connection)
            self._remaining(deadline)
        return reply,dict(request_wall_s=started,ack_wall_s=self.monotonic(),
                          native_owner=dict(self.native_owner),generation=self.generation)

    def close_strict(self):
        body=b'SOGR'+bytes((1,2))+self.capability+self.generation.to_bytes(8,'big')+bytes(16)
        reply,receipt=self._exchange(body)
        if (len(reply)!=16 or reply[:5]!=b'SOGA\x01' or reply[6:8]!=bytes(2)
                or reply[5] not in (0,1)
                or int.from_bytes(reply[8:16],'big')!=self.generation):
            raise RuntimeError('HEAD_REVOKER_ACK_INVALID')
        if reply[5]!=0:raise RuntimeError('HEAD_REVOKER_REJECTED')
        return dict(receipt,ack_validated=True)

    def identity(self):
        reply,receipt=self._exchange(b'SOIA'+bytes((1,1))+self.capability+bytes((3,)),identity=True)
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
        return dict(receipt,incarnation=values[0],boot=values[1])

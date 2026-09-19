"""Linux kernel lifetime guard for the absolute action names in one ROS domain."""

import errno
import os
import socket
import sys


class DomainAuthority:
    def __init__(self,domain):
        if type(domain) is not int or domain<0:raise ValueError('ROS_DOMAIN_INVALID')
        self.domain=domain;self.socket=None
        self.kernel_name=f'so101-act-authority-u{os.getuid()}-d{domain}'
        if len(self.kernel_name.encode())+1>107:raise ValueError('AUTHORITY_SCOPE_TOO_LONG')

    def acquire(self):
        if not sys.platform.startswith('linux'):raise RuntimeError('DOMAIN_AUTHORITY_PLATFORM_UNAVAILABLE')
        if self.socket is not None:raise RuntimeError('AUTHORITY_ALREADY_ACQUIRED')
        guard=socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)
        try:guard.bind('\0'+self.kernel_name)
        except OSError as error:
            guard.close()
            if error.errno==errno.EADDRINUSE:raise RuntimeError('CONTROL_BROKER_ALREADY_RUNNING') from error
            raise
        self.socket=guard
        return self

    def close(self):
        if self.socket is not None:self.socket.close();self.socket=None

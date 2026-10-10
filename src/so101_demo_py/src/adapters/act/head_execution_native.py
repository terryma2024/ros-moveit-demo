"""Fresh Head credentials for the owned controller and independent fault peer."""

import hashlib
import os
from pathlib import Path

from so101_teleop.unified.controller_reservation_paths import (
    controller_reservation_directory, prepare_controller_reservation_directory,
)
from .controller_reservation_provision import (
    _process_start_ticks, write_controller_reservation_provision,
    write_head_primary_fault_provision,
)


_ENVIRONMENT_FIELDS = ('SO101_ACT_RESERVATION_ROOT',
                       'SO101_ACT_CONTROLLER_RESERVATION_DIR', 'SO101_SIMULATION_SESSION_ID')


def _owned_native_peer(process, environment):
    if (process.poll() is not None or type(process.pid) is not int
            or process.pid == os.getpid() or process.pid <= 0):
        raise PermissionError('HEAD_EXECUTION_NATIVE_CHILD_INVALID')
    proc = Path('/proc') / str(process.pid)
    owner = dict(uid=proc.stat().st_uid, pid=process.pid,
                 start_ticks=_process_start_ticks(process.pid))
    if owner['uid'] != os.geteuid():
        raise PermissionError('HEAD_EXECUTION_NATIVE_CHILD_INVALID')
    if (not isinstance(process.args, (list, tuple)) or not process.args
            or not Path(process.args[0]).is_absolute()
            or (proc / 'exe').resolve(strict=True) != Path(process.args[0]).resolve(strict=True)):
        raise PermissionError('HEAD_EXECUTION_NATIVE_EXECUTABLE_INVALID')
    actual_environment = dict(item.split(b'=', 1) for item in
                              (proc / 'environ').read_bytes().split(b'\x00') if b'=' in item)
    if any(actual_environment.get(key.encode('ascii')) != os.fsencode(environment[key])
           for key in _ENVIRONMENT_FIELDS):
        raise PermissionError('HEAD_EXECUTION_NATIVE_PROCESS_SCOPE_INVALID')
    if process.poll() is not None:
        raise PermissionError('HEAD_EXECUTION_NATIVE_CHILD_INVALID')
    return owner, str((proc / 'exe').resolve(strict=True))


def provision_owned_native(inputs, stack, policy):
    """Publish once after the controller child exists; never invent credentials.

    Only the declared session's private directory is used. The two provisions
    name the primary actor, with a separate native-child identity in the fault
    provision. Credentials remain in memory; retained receipts carry hashes.
    """
    environment = inputs.document['ros']['environment']
    session = inputs.run['session_id']
    try:
        root = Path(environment['SO101_ACT_RESERVATION_ROOT'])
        declared = Path(environment['SO101_ACT_CONTROLLER_RESERVATION_DIR'])
        expected = controller_reservation_directory(root, session)
        if (declared != expected or environment['SO101_SIMULATION_SESSION_ID'] != session
                or any(stack.environment.get(key) != environment[key]
                       for key in _ENVIRONMENT_FIELDS)):
            raise ValueError('HEAD_EXECUTION_NATIVE_SCOPE_INVALID')
        if len(os.fsencode(expected / 'neck-primary-revoke.sock')) > 107:
            raise ValueError('HEAD_EXECUTION_NATIVE_SOCKET_PATH_TOO_LONG')
        process = stack.processes[0]
        owner, executable = _owned_native_peer(process, environment)
    except (KeyError, IndexError, AttributeError, OSError, TypeError) as error:
        raise PermissionError('HEAD_EXECUTION_NATIVE_SCOPE_INVALID') from error
    directory = prepare_controller_reservation_directory(root, session)
    # Native polling can expose main authority only after both files exist.
    fault_capability = write_head_primary_fault_provision(
        directory / 'neck-primary-revoke.provision', session_id=session,
        native_owner=owner, socket_path=directory / 'neck-primary-revoke.sock')
    main_capability = write_controller_reservation_provision(
        directory / 'neck.provision', role='neck', session_id=session)
    current_owner, current_executable = _owned_native_peer(process, environment)
    if current_owner != owner or current_executable != executable:
        raise PermissionError('HEAD_EXECUTION_NATIVE_CHILD_CHANGED')
    if main_capability == fault_capability:
        raise PermissionError('HEAD_EXECUTION_NATIVE_CAPABILITIES_NOT_INDEPENDENT')
    receipts = {}
    if inputs.event_log_enabled:
        for name in ('neck.provision', 'neck-primary-revoke.provision'):
            path = directory / name
            payload = path.read_bytes()
            receipts[name] = dict(path=str(path), sha256=hashlib.sha256(payload).hexdigest(),
                                  bytes=len(payload))
    return dict(native_keywords=dict(directory=str(directory), capability=main_capability,
                                    native_owner=owner, generation=inputs.run['generation'],
                                    session_id=session),
                revoker_keywords=dict(path=str(directory / 'neck-primary-revoke.sock'),
                                      capability=fault_capability, native_owner=owner,
                                      generation=inputs.run['generation'],
                                      timeout_s=policy.native_close_timeout_s,
                                      simulation_policy=policy),
                provision_receipts=receipts,
                native_child=dict(owner=owner, executable=executable))

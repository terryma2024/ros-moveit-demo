"""One production transport shared by Head execution and historical restarts."""

import copy
import math
import os
from pathlib import Path
import signal
import subprocess
import time

from .head_search_transport_measurement import MujocoRosTransport

STACK_LOG = 'transport-stack.log'
CONTROLLERS = ('joint_state_broadcaster', 'arm_controller', 'gripper_controller', 'neck_controller')
#: the controllers the spawners activate; the neck is only configured, the neck owner activates it
ACTIVE_AT_SPAWN = CONTROLLERS[:3]
NECK = 'neck_controller'


class RestartStack(MujocoRosTransport):
    """The production ACT composition: MuJoCo, the camera plugin, TF and the four controllers.

    ``so101_demo.act.head_search_transport_measurement.MujocoRosTransport`` is the frozen, measured
    producer of exactly this transport (EGL, headless, the camera plugin publishing ``/head_camera``
    on the simulator's own clock). This subclass uses that composition with the settings a restart needs:

    * the remaining three controller spawners of the ACT profile (the base starts
      ``joint_state_broadcaster`` only), so the stack under test is the production composition. The neck
      spawner passes ``--inactive``: the Head neck controller needs the owner's heartbeat helper pid before
      it may activate, so it is configured here and activated by the neck owner; and
    * the Head TF publisher follows the original 100 Hz JointState cadence, so
      exact Header transforms do not wait for the publisher's 20 Hz default.
    """

    def __init__(
        self,
        *,
        controller_config_path,
        environment,
        teardown_timeout_s=None,
        event_log_enabled=True,
        batch_spawners=False,
        **kwargs,
    ) -> None:
        if type(event_log_enabled) is not bool:
            raise ValueError('HEAD_STACK_LOG_FLAG_INVALID')
        if type(batch_spawners) is not bool:
            raise ValueError('HEAD_STACK_BATCH_SPAWNERS_INVALID')
        super().__init__(controller_config_path=controller_config_path, **kwargs)
        self.event_log_enabled = event_log_enabled
        self.batch_spawners = batch_spawners
        self.controller_config_path = Path(controller_config_path)
        self.environment = dict(environment)
        if (teardown_timeout_s is not None
                and (type(teardown_timeout_s) not in (int, float)
                     or not math.isfinite(teardown_timeout_s) or teardown_timeout_s <= 0)):
            raise ValueError('HEAD_STACK_RETIREMENT_BUDGET_INVALID')
        self.teardown_timeout_s = teardown_timeout_s
        self._retirement_receipt = None
        self._spawners = {}

    def _spawn(self, argv, name: str):
        argv = list(argv)
        if self.batch_spawners and name == 'spawner joint_state_broadcaster':
            if len(argv) < 2 or argv[1] != CONTROLLERS[0]:
                raise ValueError('HEAD_STACK_BATCH_COMMAND_INVALID')
            # Upstream spawners serialize on one ROS_HOME lock, before creating
            # their ROS nodes. One supported multi-controller invocation avoids
            # repeating service discovery while preserving every active controller.
            argv[2:2] = ACTIVE_AT_SPAWN[1:]
            name = 'spawner ' + ' '.join(ACTIVE_AT_SPAWN)
        if name == 'robot_state_publisher':
            argv.extend(('-p', 'publish_frequency:=100.0'))
        self.workspace.mkdir(parents=True, exist_ok=True)
        handle = subprocess.DEVNULL
        if self.event_log_enabled:
            handle = open(self.log_path, "ab")  # noqa: SIM115 - closed on stop
            self.handles.append(handle)
        if self.event_log_enabled and self.logger is not None:
            self.logger(f"starting {name}: {' '.join(argv)}")
        process = subprocess.Popen(  # noqa: S603 - the argv is built from installed package prefixes
            list(argv),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=self.environment,
        )
        if name.startswith('spawner '):
            self._spawners[name.removeprefix('spawner ')] = process
        return process

    def wait_startup(self, *, deadline):
        """Reap every owned spawner before reset, using its original deadline."""
        groups = ((' '.join(ACTIVE_AT_SPAWN), NECK) if self.batch_spawners else CONTROLLERS)
        if (type(deadline) not in (int, float) or not math.isfinite(deadline)
                or set(self._spawners) != set(groups)):
            raise PermissionError('HEAD_STACK_SPAWNERS_INVALID')
        outcomes = []
        for controller in groups:
            process = self._spawners[controller]
            try:
                code = process.wait(timeout=max(0., deadline-time.monotonic()))
            except subprocess.TimeoutExpired as error:
                raise TimeoutError('HEAD_STACK_SPAWNER_TIMEOUT') from error
            outcomes.append(dict(controller=controller, pid=process.pid,
                                 argv=process.args, rc=code))
            if code != 0:
                raise PermissionError('HEAD_STACK_SPAWNER_FAILED')
        return dict(ready=True, children=outcomes)

    def start(self) -> None:
        from so101_demo.act.head_search_transport_measurement import _package_executable

        self.workspace.mkdir(parents=True, exist_ok=True)
        if self.log_path is None:
            self.log_path = self.workspace / STACK_LOG
        super().start()
        for controller in (CONTROLLERS[1:] if not self.batch_spawners else (NECK,)):
            command = [_package_executable("controller_manager", "spawner"), controller,
                       "--controller-manager-timeout", str(self.startup_timeout_s),
                       "--param-file", str(self.controller_config_path)]
            if controller == NECK:
                command.append("--inactive")
            self.processes.append(self._spawn(command, f"spawner {controller}"))

    def stop(self):
        """Retire this Head run within its declared budget, retaining every outcome."""
        if self.teardown_timeout_s is None:
            return super().stop()
        if self._retirement_receipt is not None:
            return copy.deepcopy(self._retirement_receipt)
        started = time.monotonic()
        deadline = started + self.teardown_timeout_s
        graceful_deadline = deadline - min(.1, self.teardown_timeout_s * .25)
        children = tuple(self.processes)
        errors, forced_kill = [], []

        def signal_owned(process, value):
            if process.poll() is not None:
                return
            try:
                # Every child starts its own session. Never signal a foreign
                # group or the provider's group if ownership has changed.
                if os.getpgid(process.pid) != process.pid:
                    raise PermissionError('HEAD_CHILD_PROCESS_GROUP_INVALID')
                os.killpg(process.pid, value)
            except ProcessLookupError:
                process.poll()
            except OSError as error:
                errors.append(dict(pid=process.pid, operation='signal',
                                   error=type(error).__name__))

        for process in children:
            signal_owned(process, signal.SIGINT)
        for process in children:
            try:
                process.wait(timeout=max(0., graceful_deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        for process in children:
            if process.poll() is None:
                forced_kill.append(process.pid)
                signal_owned(process, signal.SIGKILL)
        for process in children:
            try:
                process.wait(timeout=max(0., deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                errors.append(dict(pid=process.pid, operation='wait',
                                   error='HEAD_CHILD_EXIT_UNCONFIRMED'))
        for handle in self.handles:
            try:
                handle.close()
            except OSError as error:
                errors.append(dict(operation='log_close', error=type(error).__name__))
        outcomes = [dict(pid=process.pid, argv=process.args, rc=process.poll())
                    for process in children]
        retired = all(row['rc'] is not None for row in outcomes)
        self.head_retirement_children = outcomes
        self._retirement_receipt = dict(retired=retired,
            closed=retired and not forced_kill and not errors
            and all(row['rc'] == 0 for row in outcomes),
            children=outcomes, forced_kill=forced_kill, errors=errors,
            elapsed_s=time.monotonic()-started, budget_s=self.teardown_timeout_s)
        return copy.deepcopy(self._retirement_receipt)

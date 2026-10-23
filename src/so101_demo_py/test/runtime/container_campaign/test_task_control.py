"""Real Host adapter; the external Docker owner/control exchange is controlled."""

import asyncio
import importlib
import time
from types import SimpleNamespace

import pytest


def modules():
    import so101_demo.runtime.container_campaign as package
    from pathlib import Path
    assert (Path(package.__file__).parent/'task_contracts.py').is_file(), 'task contracts are missing'
    assert (Path(package.__file__).parent/'task_control.py').is_file(), 'Host task adapter is missing'
    return (importlib.import_module('so101_demo.runtime.container_campaign.task_contracts'),
            importlib.import_module('so101_demo.runtime.container_campaign.task_control'))


class ExternalOwner:
    """Only native start/stop and remote status are external to the Host adapter."""

    def __init__(self):
        self.launch = SimpleNamespace(launch_id='instance-01')
        self.context = SimpleNamespace(deadline_monotonic_s=time.monotonic()+30)
        self.max_bytes = 4096
        self.startup_budget = self.stop_budget = 5
        self.calls = []
        self.fail_assignment_reply = False
        self.returned_id = 'scene-001'
        self.released = True

    async def start(self):
        self.calls.append('start')

    def control_client(self):
        return self

    async def call_task(self, packet):
        self.calls.append(packet.operation)
        if packet.operation == 'assign_task':
            self.returned_id = packet.payload['task_id']
            if self.fail_assignment_reply:
                raise ConnectionError('assignment reply lost')
            return dict(task_id=self.returned_id, state='ACCEPTED', fault_reason=None)
        if packet.operation == 'get_status':
            return dict(instance_id='instance-01', state='READY', fault_reason=None,
                        resources_released=False, task=dict(task_id=self.returned_id,
                        state='SUCCEEDED', fault_reason=None))
        return dict(instance_id='instance-01', state='STOPPING', task=None,
                    fault_reason=None, resources_released=False)

    async def close(self):
        self.calls.append('close')
        return dict(terminated=self.released, launch_id='instance-01', errors=[])


def task(contracts):
    return contracts.TaskSpec(task_id='scene-001', inputs_ref=dict(path='/act/input/task.json',
                             sha256='a'*64), deadline_monotonic_s=time.monotonic()+10)


def test_only_four_operations():
    contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        assert (await control.start()).state == 'READY'
        assert (await control.assign_task(task(contracts))).task_id == 'scene-001'
        status = await control.get_status('scene-001')
        assert status.task.state == 'SUCCEEDED'
        stopped = await control.terminate('finished')
        assert stopped.state == 'TERMINATED' and stopped.resources_released is True
    asyncio.run(run())
    assert owner.calls == ['start', 'assign_task', 'get_status', 'terminate', 'close']


def test_lost_assignment_reply_queries_without_resend():
    contracts, module = modules()
    owner = ExternalOwner()
    owner.fail_assignment_reply = True
    control = module.ContainerTaskControl(owner=owner)
    current = task(contracts)
    async def run():
        await control.start()
        with pytest.raises(ConnectionError):
            await control.assign_task(current)
        result = await control.assign_task(current)
        assert result.task_id == 'scene-001' and result.state == 'SUCCEEDED'
    asyncio.run(run())
    assert owner.calls == ['start', 'assign_task', 'get_status']


def test_unknown_task_cannot_return_previous_success():
    contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        await control.assign_task(task(contracts))
        owner.returned_id = 'previous-task'
        with pytest.raises(ValueError, match='TASK_ID_MISMATCH'):
            await control.get_status('scene-001')
    asyncio.run(run())


def test_unconfirmed_stop_is_not_reported_as_released():
    _contracts, module = modules()
    owner = ExternalOwner()
    owner.released = False
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        result = await control.terminate('fault')
        assert result.state == 'STOPPING' and result.resources_released is False
        assert (await control.get_status()).resources_released is False
    asyncio.run(run())


def test_terminate_remains_available_after_status_socket_loss():
    _contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    async def failed(_packet):
        raise ConnectionError('container exited')
    async def run():
        await control.start()
        owner.call_task = failed
        result = await control.terminate('container fault')
        assert result.resources_released is True
        assert (await control.get_status()).state == 'TERMINATED'
    asyncio.run(run())
    assert owner.calls == ['start', 'close']


def test_terminate_remains_available_after_campaign_deadline():
    _contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        owner.context.deadline_monotonic_s = time.monotonic()-1
        result = await control.terminate('deadline reached')
        assert result.resources_released is True
        again = await control.terminate('deadline reached')
        assert again.resources_released is True
    asyncio.run(run())
    assert owner.calls.count('close') == 1


def test_raw_container_success_does_not_prove_host_resource_release():
    _contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    async def reply(_packet):
        return dict(instance_id='instance-01', state='TERMINATED', resources_released=True,
                    task=None, fault_reason='container fault')
    async def run():
        await control.start()
        owner.call_task = reply
        result = await control.get_status()
        assert result.state == 'STOPPING' and result.resources_released is False
    asyncio.run(run())


def test_same_task_id_with_changed_input_is_not_sent_again():
    contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    current = task(contracts)
    changed = current.model_dump()
    changed['inputs_ref']['sha256'] = 'b'*64
    async def run():
        await control.start()
        await control.assign_task(current)
        with pytest.raises(ValueError, match='TASK_INPUT_CHANGED'):
            await control.assign_task(contracts.TaskSpec.model_validate(changed))
    asyncio.run(run())
    assert owner.calls == ['start', 'assign_task']


def test_pending_task_prevents_second_task_assignment():
    contracts, module = modules()
    owner = ExternalOwner()
    control = module.ContainerTaskControl(owner=owner)
    current = task(contracts)
    second = current.model_copy(update={'task_id': 'scene-002'})
    async def run():
        await control.start()
        await control.assign_task(current)
        with pytest.raises(ValueError, match='TASK_INSTANCE_BUSY'):
            await control.assign_task(second)
    asyncio.run(run())
    assert owner.calls == ['start', 'assign_task']


class ProofOwner(ExternalOwner):
    """Controlled owner double offering the real shard owner's two Host-side proof calls."""

    def __init__(self):
        super().__init__()
        self.exit_document = None
        self.proof_ok = False

    def instance_exit(self):
        return self.exit_document

    async def prove_stopped(self):
        self.calls.append('prove_stopped')
        return dict(terminated=self.proof_ok, launch_id='instance-01', errors=[])


def exit_record(reason, confirmed=True):
    return dict(schema_version=1, kind='ACT_SHARD_INSTANCE_EXIT', state='STOPPING', fault_reason=reason,
                task=None, cleanup_confirmed=confirmed, cleanup_errors=[])


def test_exited_instance_status_keeps_fault_and_stop_proof():
    _contracts, module = modules()
    owner = ProofOwner()
    owner.exit_document = exit_record('Coordinator status polling timed out')
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        result = await control.terminate('finished')
        # The Host never polled this fault; it comes from the child's own exit record.
        assert result.fault_reason == 'Coordinator status polling timed out'
        assert result.state == 'TERMINATED' and result.resources_released is True
        assert (await control.get_status()).fault_reason == 'Coordinator status polling timed out'
    asyncio.run(run())
    assert owner.calls == ['start', 'terminate', 'close']


def test_host_observed_fault_is_not_replaced_by_the_exit_record():
    _contracts, module = modules()
    owner = ProofOwner()
    owner.exit_document = exit_record('later reason')
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        control._status = control._status.model_copy(update={'fault_reason': 'seen by Host'})
        assert (await control.terminate('x')).fault_reason == 'seen by Host'
    asyncio.run(run())


def test_unproven_exit_keeps_fault_but_never_claims_release():
    _contracts, module = modules()
    owner = ProofOwner()
    owner.released = False
    owner.exit_document = exit_record('native stop failed', confirmed=False)
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        result = await control.terminate('fault')
        assert result.fault_reason == 'native stop failed'
        assert result.state == 'STOPPING' and result.resources_released is False
    asyncio.run(run())


def test_missing_exit_record_falls_back_to_the_terminate_reason():
    _contracts, module = modules()
    owner = ProofOwner()
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        assert (await control.terminate('CONTAINER_INSTANCE_EXECUTION_FAULT')).fault_reason == (
            'CONTAINER_INSTANCE_EXECUTION_FAULT')
    asyncio.run(run())


def test_late_exit_is_proven_on_repeated_terminate():
    _contracts, module = modules()
    owner = ProofOwner()
    owner.released = False
    control = module.ContainerTaskControl(owner=owner)
    async def run():
        await control.start()
        first = await control.terminate('fault')
        assert first.resources_released is False and owner.calls == ['start', 'terminate', 'close']
        again = await control.terminate('fault')
        assert again.state == 'STOPPING' and again.resources_released is False
        status = await control.get_status()
        assert status.state == 'STOPPING' and status.resources_released is False
        owner.proof_ok = True
        released = await control.terminate('fault')
        assert released.state == 'TERMINATED' and released.resources_released is True
        assert (await control.get_status()).resources_released is True
        await control.terminate('fault')
    asyncio.run(run())
    assert owner.calls == ['start', 'terminate', 'close', 'prove_stopped', 'prove_stopped', 'prove_stopped']

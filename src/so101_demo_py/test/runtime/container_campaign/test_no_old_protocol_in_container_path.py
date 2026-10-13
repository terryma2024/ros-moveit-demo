"""The container path carries none of the superseded Worker callback protocol.

A source scan, not a behaviour test: it fails when a module of the container path imports or names the old
Coordinator transport, Worker runner or driver, the owner heartbeat channel, or the per-Worker control files.
"""

from pathlib import Path

import pytest

import so101_demo
import so101_teleop

PACKAGE=Path(so101_demo.__file__).resolve().parent
TELEOP=Path(so101_teleop.__file__).resolve().parent
CONTAINER_CAMPAIGN=PACKAGE/'runtime/container_campaign'

REMOVED_MODULES=('worker_transport','worker_runner','collection_worker','collection_driver','worker_builder','heartbeat')
FORBIDDEN=('worker_transport','worker_runner','collection_worker','collection_driver','worker_builder',
           'CollectionCoordinatorProxy','CollectionCoordinatorTransport','ContainerWorkerRunner',
           'ContainerCollectionWorker','CollectionShardDriver','OwnerHeartbeatMonitor','OwnerHeartbeatChannel',
           'container_watchdog','owner_heartbeat','worker-spec','coordinator.sock','heartbeat_teacher')


def scanned_files():
    files=sorted(CONTAINER_CAMPAIGN.rglob('*.py'))
    files+=[PACKAGE/'cli/campaign_shard.py']
    files+=sorted((PACKAGE/'runtime/act_instance').glob('*.py'))
    files+=[TELEOP/'unified'/name for name in ('child_runtime.py','bridge.py','ros_child.py')]
    return files


def test_scan_covers_the_container_path_modules():
    files=scanned_files()
    assert all(path.is_file() for path in files)
    assert {path.name for path in files}>={'task_builder.py','task_executor.py','shard_owner.py','campaign_shard.py','program.py','spec.py','layout.py',
                                           'child_runtime.py','bridge.py','ros_child.py'}


@pytest.mark.parametrize('name',REMOVED_MODULES)
def test_removed_module_files_do_not_exist(name):
    assert not (CONTAINER_CAMPAIGN/(name+'.py')).exists()


@pytest.mark.parametrize('path',scanned_files(),ids=lambda path:path.name)
def test_no_old_protocol_name_in_container_path_module(path):
    text=path.read_text()
    assert [token for token in FORBIDDEN if token in text]==[]


# The collection entry points carry none of the superseded builder, injected factories, resume or worker-spec protocol.
ENTRY_FORBIDDEN=('build_fixed_collection_spec','service_factory','context_factory','worker_spec','_CollectionWorkerSpec',
                 '--resume')
ENTRY_MODULES=(PACKAGE/'cli/act_collect_parallel.py',PACKAGE/'runtime/act_fixed_collection_composition.py',
               TELEOP/'unified/ipc.py')


@pytest.mark.parametrize('path',ENTRY_MODULES,ids=lambda path:path.name)
def test_no_legacy_collection_entry_name_in_cli_composition_or_ipc(path):
    text=path.read_text()
    assert [token for token in ENTRY_FORBIDDEN if token in text]==[]

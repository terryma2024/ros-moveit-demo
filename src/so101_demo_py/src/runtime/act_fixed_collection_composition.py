"""Prepare collection operation specs for unified campaign admission and build the campaign owner that runs them."""

from __future__ import annotations

import hashlib
from pathlib import Path

from so101_demo.runtime.container_campaign.coordinator import ConcurrentCollectionCoordinator
from so101_demo.runtime.container_campaign.owner import ContainerCampaignOwner
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.result_verifier import ContainerWaveResultVerifier
from so101_demo.runtime.container_campaign.service_owner import ContainerServiceOwner
from so101_demo.runtime.container_campaign.native_launcher import NativeInstanceLauncher
from so101_demo.runtime.container_campaign.shard_launcher import ContainerShardLauncher
from so101_demo.runtime.inference.config import validate_file_ref


def collection_parallel_runtime(path):
    """The parallel runtime file the collection config binds, as the `{path, sha256}` reference the shards are given.

    The path is resolved against the installed package share, the hash is the collection config's own (the loader has already
    compared it with the file's bytes)."""
    from ament_index_python.packages import get_package_share_directory
    from so101_demo.act.collection_config import load_collection_config

    share = Path(get_package_share_directory('so101_demo_py'))
    binding = load_collection_config(Path(path), package_share=share)['parallel_runtime']
    return dict(path=str((share/binding['path']).resolve(strict=True)), sha256=binding['sha256'])


def _collection_runtime(path):
    """Resolve lease/domain budgets from the frozen collection runtime binding."""
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    return _load_runtime_config(validate_file_ref(collection_parallel_runtime(path)))


def prepare_collection_operation(arguments, *, services, contact_policy_fingerprint):
    """Prepare a real operation without admitting, allocating or writing files.

    Generation is the next persistent validation generation. The unified entry
    compares and commits that allocation atomically with admission; a competing
    admission makes this proposal stale. No admitted context exists here.

    `arguments.qualification_report` is the formal plane's container qualification report (a regular file whose sha256 the payload
    carries; admission verifies it from the run it belongs to) and `None` for a qualification run.
    `contact_policy_fingerprint` is the explicit value the caller took from the campaign's frozen inputs
    (`case_inputs.campaign_binding`); no contact proposal, receipt or calibration report is named or read here.
    """
    from dataclasses import asdict
    import re

    from so101_demo.act.parallel_collection_contracts import (
        read_document,validate_run_contract,
    )
    from so101_demo.runtime.container_campaign.paths import validate_registered_evidence_root
    from so101_demo.runtime.inference.config import load_campaign_config
    from so101_teleop.unified.admission import _COLLECTION_PAYLOAD_KEYS
    from so101_teleop.unified.contracts import Domain,OperationSpec
    from so101_teleop.unified.worker_slots import ActWorkerSlot

    spot_check = getattr(arguments,'spot_check',False)
    if type(spot_check) is not bool or (spot_check and arguments.qualification is not True):
        raise ValueError('COLLECTION_RUN_CONTRACT_MISMATCH')
    if (type(arguments.qualification) is not bool or type(arguments.worker_count) is not int
            or arguments.worker_count not in ((1,) if spot_check else (1,2,8) if arguments.qualification else (8,))):
        raise ValueError('COLLECTION_WORKER_COUNT_INVALID')
    workload = services.act_workload
    if workload is None:
        raise ValueError(f'ACT_COLLECTION_UNIFIED_SERVICE_UNAVAILABLE: {services.act_error}')
    root = Path(arguments.root)
    config_path = Path(arguments.campaign_config)
    config_digest = _digest(config_path)
    config = load_campaign_config(config_path,roles=('teacher',),expected_sha256=config_digest)
    # max_concurrent_recordings, max_tasks_in_flight and min_assignment_gap_s are optional at every worker count: the hashed
    # config states them when the run wants them, and absent means no such limit.
    registered = validate_registered_evidence_root(config['evidence_root'],config['evidence_root'],
                                                  registration=workload.root_registration)
    if (not root.is_absolute() or root.resolve(strict=True) != root or not root.is_dir()
            or root == registered or not root.is_relative_to(registered)
            or not (root/'.campaign-layout.json').is_file()):
        raise ValueError('COLLECTION_NEW_RUN_REQUIRED')
    stage = getattr(arguments,'stage',None)
    if stage is None:
        if (root/'host/launches.sqlite3').exists() or (root/'campaign-index.json').exists():
            raise ValueError('COLLECTION_NEW_RUN_REQUIRED')
    elif (type(stage) is not str or re.fullmatch(r'[a-z0-9][a-z0-9-]*',stage) is None
            or not (root/'host/launches.sqlite3').is_file() or not (root/'campaign-index.json').is_file()):
        raise ValueError('COLLECTION_STAGE_RUN_MISSING')           # a later stage continues a run that phase 1 left
    campaign_id = arguments.campaign_id
    if type(campaign_id) is not str or re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*',campaign_id) is None:
        raise ValueError('COLLECTION_CAMPAIGN_ID_INVALID')
    runtime = _collection_runtime(arguments.collection_config)
    # collect_timeout_s, process_timeout_s and processing_reserve_s are optional; any of them must fit the admitted total
    from so101_demo.runtime.container_campaign.processing_limits import (
        check_phase_limits,effective_batch_total_s,effective_limits)
    limits = effective_limits(config,getattr(arguments,'runtime_document',None))
    total_s,_source = effective_batch_total_s(limits,runtime.batch_hard_timeout_s)
    check_phase_limits(limits,total_s)
    if arguments.qualification and limits.get('retry_invalid_max_rounds',0):
        raise ValueError('COLLECTION_RETRY_QUALIFICATION_FORBIDDEN')
    launcher = getattr(arguments, 'instance_launcher', 'container')
    if launcher not in ('container', 'native'):
        raise ValueError('COLLECTION_INSTANCE_LAUNCHER_INVALID')
    if launcher == 'native' and arguments.worker_count != 1:
        raise ValueError('COLLECTION_NATIVE_SINGLE_WORKER_ONLY')
    if arguments.worker_count > runtime.max_worker_count:
        raise ValueError('COLLECTION_RUNTIME_WORKER_COUNT_INVALID')
    fingerprint = contact_policy_fingerprint
    if type(fingerprint) is not str or re.fullmatch(r'[0-9a-f]{64}',fingerprint) is None:
        raise ValueError('COLLECTION_POLICY_INVALID')
    manifest = read_document(arguments.manifest)
    if arguments.qualification:
        plane,contract = validate_run_contract(manifest)
        if ((plane == 'spot_check') != spot_check or contract['worker_count'] != arguments.worker_count
                or arguments.qualification_report is not None):
            raise ValueError('COLLECTION_RUN_CONTRACT_MISMATCH')
    elif arguments.qualification_report is None:
        raise ValueError('EIGHT_WORKER_QUALIFICATION_REQUIRED')
    with workload.arbiter.store._thread_lock:
        generation = workload.arbiter.store.execution_generation(Domain.VALIDATION)+1
    slots = []
    for index in range(arguments.worker_count):
        slots.append(asdict(ActWorkerSlot(campaign_id,f'w{index:02d}',generation)))
    payload = dict(campaign_id=campaign_id,backend='mujoco',worker_count=arguments.worker_count,
        contact_policy_fingerprint=fingerprint,evidence_root=str(root),
        service_epoch=workload.service_epoch,resource_binding_id=workload.resource_binding_id,
        qualification_mode=arguments.qualification,instance_launcher=launcher,
        qualification_receipt_path=str(arguments.qualification_report) if arguments.qualification_report is not None else None,
        qualification_receipt_sha256=_digest(arguments.qualification_report)
            if arguments.qualification_report is not None else None,
        worker_slots=slots,registered_evidence_root=str(registered),campaign_config_path=str(config_path),
        campaign_config_sha256=config_digest)
    for name,path in (('source',arguments.source),('manifest',arguments.manifest),
            ('runtime_config',arguments.runtime_config),('collection_config',arguments.collection_config)):
        payload[name+'_path'],payload[name+'_sha256'] = str(path),_digest(path)
    if config['controlled_runtime'] != dict(path=payload['runtime_config_path'],sha256=payload['runtime_config_sha256']):
        raise ValueError('CAMPAIGN_CONFIG_BINDING_MISMATCH')
    if set(payload) != _COLLECTION_PAYLOAD_KEYS:
        raise ValueError('FIXED_COLLECTION_PAYLOAD_SCHEMA_DRIFT')
    return OperationSpec(command_id='collection-'+campaign_id+('' if stage is None else '-'+stage),domain=Domain.VALIDATION,
        kind='act_collection_start',payload=payload,runtime_id=workload.runtime_id,
        execution_generation=generation,
        deadline_ns=workload.clock_ns()+int(total_s*1e9))

def _digest(path) -> str:
    target = Path(path)
    if not target.is_file() or target.is_symlink():
        raise ValueError("FIXED_COLLECTION_INPUT_UNREADABLE")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def build_container_campaign_owner(context, *, config, paths, slots, manifest_path, scene_manifest, case_inputs,
                                   parallel_runtime, approved_inputs, qualification, approved_disk_floor_bytes,
                                   docker_runner=None, service_query=None, namespace_reader=None, control_factory=None,
                                   instance_launcher='container', native=None, admit_processor_slots=None,
                                   collection_mode='formal', runtime_document=None, stop_after_phase1=False,
                                   stage=None):
    """Build the campaign owner for an admitted collection; spawns nothing and writes only the launch registry.

    Order: the launch registry first (admission's `finish` opens it with `create=False`, so a construction failure below can
    still be settled), then the Teacher-only service owner, the shard launcher, the wave coordinator, the wave verifier and the
    owner. No timeout is invented; each comes from a frozen field:
      - Teacher startup budget = the parallel runtime's `initializing_hard_timeout_s`;
      - Teacher receive budget = the campaign config's `teacher_service.queue_timeout_s + inference_timeout_s`;
      - Teacher stop budget = the parallel runtime's `worker_recovery_timeout_s`;
      - the shard launcher derives its own budgets from the same runtime; the coordinator reads the runtime itself;
      - the campaign deadline is the one admission froze into `context` (the campaign config's `batch_hard_timeout_s`, else the runtime yaml's; not changed here).
    `approved_disk_floor_bytes` is the caller's value from the frozen inputs. `docker_runner`, `service_query`,
    `namespace_reader` and `control_factory` are the external edges (Docker, the Teacher socket, `/proc`, the container's control
    channel); `None` keeps each owner's production default.

    `instance_launcher` is `container` (one Docker container per slot) or `native` (one Host process group, one worker);
    admission has already refused `native` for anything else. Both run the same instance program, and the Teacher service
    is a container either way.

    `collection_mode` is the plane's collection mode, written into every task document as a cross-check: `formal`, or
    `preselected_target_diagnostic` for a contact-policy spot check.

    Phase 2 (processing): with an `admit_processor_slots(context, slots)` (the unified service's), the owner gets a `ProcessingScheduler`
    over `ContainerProcessorLauncher` (container launcher) or `NativeProcessorLauncher` (native launcher: one Host-process processor,
    the same `campaign_processor` program). Without `admit_processor_slots` the campaign ends after phase 1. `native` is a mapping of
    the native launcher's edges (`install_prefix` is required; `command`, `base_environment`, `popen` and `graph_probe_factory` default
    to production; `processor_command` is the native processor's own command, default its module).
    """
    from so101_demo.cli.mujoco_batch.request import _load_runtime_config

    def given(**values):
        return {name: value for name, value in values.items() if value is not None}

    # a later stage opens the registry phase 1 created; its Teacher and its processors register beside the earlier launches
    registry = ContainerLaunchRegistry(Path(paths['host'])/'launches.sqlite3', create=stage is None)
    try:
        runtime = _load_runtime_config(validate_file_ref(parallel_runtime))
        from so101_demo.runtime.container_campaign.processing_limits import effective_batch_total_s,effective_limits
        limits = effective_limits(config,runtime_document)
        campaign_total_s,_total_source = effective_batch_total_s(limits,runtime.batch_hard_timeout_s)
        teacher = config['teacher_service']
        services = ContainerServiceOwner(admitted_context=context, config=config, paths=paths, roles=('teacher',),
            registry=registry, startup_timeout_s=runtime.initializing_hard_timeout_s,
            receive_budget_s=teacher['queue_timeout_s']+teacher['inference_timeout_s'],
            stop_timeout_s=runtime.worker_recovery_timeout_s,
            **given(docker_runner=docker_runner, query=service_query, stage=stage))
        shard_arguments = dict(context=context, config=config, paths=paths, registry=registry,
            parallel_runtime=parallel_runtime, approved_inputs=tuple(approved_inputs),
            config_paths=(Path(context.campaign_config_path),),
            **given(docker_runner=docker_runner, namespace_reader=namespace_reader))
        if instance_launcher == 'native':
            if 'mount_build' in config:
                # mount mode mounts the build into containers; a native instance runs the Host's own install
                raise ValueError('COLLECTION_MOUNT_BUILD_NEEDS_CONTAINER_LAUNCHER')
            if 'shard_cpuset' in config:
                raise ValueError('COLLECTION_CPUSET_NEEDS_CONTAINER_LAUNCHER')    # the plan is a docker option
            launcher = NativeInstanceLauncher(**(native or {}), **shard_arguments)
        elif instance_launcher == 'container':
            launcher = ContainerShardLauncher(**shard_arguments)
        else:
            raise ValueError('COLLECTION_INSTANCE_LAUNCHER_INVALID')
        coordinator = ConcurrentCollectionCoordinator(context=context, config=runtime, case_inputs=case_inputs,
            scene_manifest=scene_manifest, max_recording_shards=config.get('max_concurrent_recordings'),
            max_tasks_in_flight=config.get('max_tasks_in_flight'), min_assignment_gap_s=config.get('min_assignment_gap_s'),
            collection_mode=collection_mode, **given(control_factory=control_factory))
        verifier = ContainerWaveResultVerifier(root=paths['run'], registry=registry, case_inputs=case_inputs,
            qualification=qualification)
        processing = None
        if admit_processor_slots is not None and instance_launcher in ('container', 'native'):
            from so101_demo.runtime.container_campaign.processing_scheduler import ProcessingScheduler
            if instance_launcher == 'native':
                # the same scheduler and the same processor program, as one Host process (a native single worker has one processor)
                from so101_demo.runtime.container_campaign.native_launcher import NativeProcessorLauncher
                edges = native or {}
                processors = NativeProcessorLauncher(context=context, paths=paths, registry=registry,
                    parallel_runtime=parallel_runtime, approved_inputs=tuple(approved_inputs),
                    config_paths=(Path(context.campaign_config_path),), install_prefix=edges['install_prefix'],
                    **given(command=edges.get('processor_command'), base_environment=edges.get('base_environment'),
                            popen=edges.get('popen')))
                limit = 1
            else:
                from so101_demo.runtime.container_campaign.cpuset import cpus_for, cpuset_from_config
                from so101_demo.runtime.container_campaign.mount_build import mount_from_config
                from so101_demo.runtime.container_campaign.processor_launcher import ContainerProcessorLauncher
                processors = ContainerProcessorLauncher(context=context, paths=paths, registry=registry,
                    images=dict(head=config['head_service']['image'], teacher=config['teacher_service']['image'],
                                shard=config['shard_image']),
                    parallel_runtime=parallel_runtime, approved_inputs=tuple(approved_inputs),
                    config_paths=(Path(context.campaign_config_path),), mount_build=mount_from_config(config),
                    cpuset_cpus=cpus_for(cpuset_from_config(config), 'processor', worker_count=context.worker_count),
                    **given(docker_runner=docker_runner, namespace_reader=namespace_reader))
                limit = None
            processing = ProcessingScheduler(context=context, runtime=runtime, config=limits, root=paths['run'],
                launcher=processors, admit_slots=lambda slots: admit_processor_slots(context, slots),
                case_inputs=case_inputs, max_processors=limit, **given(control_factory=control_factory))
        return ContainerCampaignOwner(admitted_context=context, config=config, root=paths['run'], service_owner=services,
            slots=slots, manifest_path=manifest_path, qualification=qualification, launcher=launcher,
            coordinator=coordinator, verifier=verifier, approved_disk_floor_bytes=approved_disk_floor_bytes,
            processing=processing,campaign_total_s=campaign_total_s,runtime_document=runtime_document,
            stop_after_phase1=stop_after_phase1)
    except BaseException:
        registry.close()
        raise

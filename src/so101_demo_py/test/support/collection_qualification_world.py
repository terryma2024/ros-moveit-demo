"""A 40-scene, two-wave, eight-instance container-collection run on disk, for the qualification report and its verifier. Not a test module.

REAL producer output (the production functions wrote it, nothing here re-implements them):
`make_campaign_paths` (run layout and `.campaign-layout.json`), `ContainerLaunchRegistry` (the Teacher and sixteen shard launches,
registered, container-bound, child-bound and settled through `prove_terminated`, which re-reads the shard stop evidence),
`ContainerTaskJournal` (`assign`/`collect` of forty tasks), `reserve_task_output`/`write_task_result`/`read_container_task_result`,
`task_builder.result_summary`, the sealed results (`ActCollectionResultStore` with `EpisodeRecorder` and `EpisodeAuditWriter`,
including the manifest-free perception no-pose form), `topic_loss.build_document`/`qc_check`, `partition_waves`,
`reserve_qualification_scenes`, `verify_wave_records` (which wrote `wave-N-verified.json`), `build_frozen_index`,
`validate_qualification_contract`, `load_campaign_config`, `append_resource_log` and the owner's own `_write`.

CONTROLLED (labelled so nothing here reads as qualification evidence): the episode bytes (a synthetic zero-row episode), the
independent QC recomputation (`episode_qc.recompute_native_qc` and `result_store._verify_result_qc` return the report the store
published, as the existing readback tests do), the Docker inspect documents and container ids, the shard stop evidence (written
with `retirement._write` in the exact closed shape `read_shard_stop_evidence` re-reads), the Teacher/shard provenance, ready and
cleanup files, the shard specs (the production key set, written directly), the frozen inputs manifest and per-scene scopes
(a diagnostic-mode manifest with a side file that carries the roles and scene binding a real formal set carries inside itself,
because a real formal set needs a formal episode audit that no fixture can produce), and the TEST-ONLY synthetic rule files.
The campaign owner itself was not run: its documents are written with its own writer in its own shape.
"""

import contextlib
import copy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from collection_quality_rules import write_synthetic_rules
from so101_demo.act import episode_qc, result_store, topic_loss
from so101_demo.act.collection_scope import build_collection_scope, write_collection_scope
from so101_demo.act.episode_audit.writer import EpisodeAuditWriter
from so101_demo.act.parallel_collection import partition_waves, reserve_qualification_scenes
from so101_demo.act.parallel_collection_contracts import scene_ids, validate_qualification_contract
from so101_demo.act.recorder import EpisodeRecorder
from so101_demo.act.result_store import ActCollectionResultStore
from so101_demo.parallel_batch.contracts.identity import LeaseIdentity
from so101_demo.runtime.container_campaign import retirement
from so101_demo.runtime.container_campaign.paths import host_task_output, make_campaign_paths
from so101_demo.runtime.container_campaign.process_identity import (
    ContainerChildBinding, ContainerOwnerKey, pid_namespace_inode, read_process_owner,
)
from so101_demo.runtime.container_campaign.registry import ContainerLaunch, ContainerLaunchRegistry
from so101_demo.runtime.container_campaign.resource_log import append_resource_log
from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index, verify_wave_records
from so101_demo.runtime.container_campaign.service_owner import _write
from so101_demo.runtime.container_campaign.task_builder import result_summary
from so101_demo.runtime.container_campaign.task_contracts import InputRef, TaskSpec
from so101_demo.runtime.container_campaign.task_journal import ContainerTaskJournal, read_container_task_result
from so101_demo.runtime.container_campaign.task_results import reserve_task_output, write_task_result
from so101_demo.runtime.inference.config import load_campaign_config
from so101_demo.runtime.parallel_ipc.frames import canonical_json
from act_result_teacher import sealed_teacher
from test_act_qc_report_publication import fail_teacher_reference, report
from test_act_seal_and_downgrade import IDENTITY, PROVENANCE

GPU = 'GPU-28221cec-9d21-7753-fd5a-da645740df19'
WORKERS = tuple(f'w{index:02d}' for index in range(8))
CAMPAIGN_ID = 'campaign-one'
STARTED = '2026-10-12T01:02:03.123Z'
MODE = 'preselected_target_diagnostic'
INFERENCE_IMAGE = dict(digest='sha256:'+'b'*64, package_source_sha256='c'*64, install_sha256='d'*64)
#: the shard image is built separately from the inference image, so its package source hash differs too
SHARD_IMAGE = dict(INFERENCE_IMAGE, digest='sha256:'+'e'*64, package_source_sha256='f'*64)
#: the sealed documents are written once per scene; these two scene indexes are the controlled business failures of the default world
TEACHER_FAILED = (3, 11)
QC_FAILED = (7,)
PENDING = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return dict(path=str(path), sha256=sha(path))


def write_json(path, document):
    Path(path).write_text(json.dumps(document, sort_keys=True))
    return Path(path)


def controlled_frozen_reader(path):
    """The strict frozen-set reader is replaced by a read of the controlled manifest and its side file (see the module docstring)."""
    return {**json.loads(path.read_bytes()), **json.loads((path.parent/'controlled-frozen-binding.json').read_bytes())}


def install_controlled_world(patch):
    """Everything a recomputation over a built world needs controlled: the QC recomputation and the frozen-inputs reader."""
    from so101_demo.act import collection_qualification_recompute

    install_controlled_qc(patch)
    patch.setattr(collection_qualification_recompute, 'read_frozen_inputs', controlled_frozen_reader)


def install_controlled_qc(patch):
    """The QC recomputation is replaced by the report the store published (the existing readback tests' double)."""
    def recompute(episode_root, **kwargs):
        root = Path(episode_root)
        if str(root) in PENDING:
            return copy.deepcopy(PENDING[str(root)])
        return episode_qc.read_qc_report(root.parent/'qc-report.json')

    def verified(report_path, *, scope=None, **kwargs):
        mode = json.loads(Path(scope).read_bytes())['mode']
        return episode_qc.read_qc_report(report_path), sha(report_path), mode

    patch.setattr(episode_qc, 'recompute_native_qc', recompute)
    patch.setattr(result_store, '_verify_result_qc', verified)


def seal_task(task_dir, lease, scope_path, inputs_path, *, seed, outcome, qc, pose=True, loss=False):
    """One real sealed result under `task_dir`. `qc` is PASS, or FAIL through the Teacher-reference check; `loss` fails the gate."""
    scene = lease.point_id
    workspace = task_dir/'attempts'/scene/lease.attempt_id
    scope = json.loads(scope_path.read_bytes())
    inputs_sha = json.loads(inputs_path.read_bytes())['inputs_sha256']
    store = ActCollectionResultStore(workspace, lease, clock=lambda: lease.lease_issued_monotonic_s+.5,
                                     scope=scope_path, inputs_manifest=inputs_path)
    if not pose:
        # the real store's manifest-free form: no episode, no Teacher manifest, no QC (a perception no-pose terminal)
        store.audit_manifest = workspace/'working/episode/audit/audit-manifest.json'
        return store.seal(store.episode_root/'seal.json', teacher=dict(execution_status='INDETERMINATE',
            task_result='UNCONFIRMED', data_status='INVALID', data_reason='PERCEPTION_NO_POSE'))
    recorder = EpisodeRecorder(store.episode_root, session_id='session-1', attempt_id=lease.attempt_id, reset_epoch=2,
                               provenance=PROVENANCE)
    identity = {**IDENTITY, 'attempt_id': lease.attempt_id, 'scene_id': scene, 'seed': seed, 'mode': MODE,
                'lease': asdict(lease)}
    writer = EpisodeAuditWriter(store.episode_root, scope, identity, dict(inputs_sha256=inputs_sha))
    audit = writer.seal(dict(start_s=1., end_s=1., label_cutoff_s=1.))
    store.audit_manifest = audit
    seal = recorder.finish(dict(status='FAILED', reason='controlled stop', pick_place_validation_success=False,
                                stopped_confirmed=True), audit_manifest=audit, scope=scope_path)
    wanted = {key: writer.identity[key] for key in ('session_id', 'reset_epoch', 'attempt_id')}
    lost = 3 if loss else 0
    document = topic_loss.build_document(identity=wanted, window=dict(start_s=1., end_s=1.),
        transport_lost=dict(reported=lost, unattributed=0),
        topics={'/clock': dict(used=True, missing_in_window=lost)}, reasons=['TOPIC_MESSAGES_LOST'] if loss else [])
    (store.working/topic_loss.DOCUMENT_NAME).write_bytes(topic_loss.canonical(document))
    expected = report()
    expected['identity'] = writer.identity
    expected.update(inputs_sha256=inputs_sha, scope_sha256=sha(scope_path), audit_manifest_sha256=sha(audit),
                    episode_seal_sha256=sha(seal))
    expected['checks'][topic_loss.CHECK_NAME] = topic_loss.qc_check(store.episode_root, identity=writer.identity)
    if loss:
        expected['status'], expected['reason'] = 'FAIL', expected['checks'][topic_loss.CHECK_NAME]['reason']
    if qc == 'FAIL':
        fail_teacher_reference(expected, 'TEACHER_REFERENCE_END_AFTER_RECORDING')
    PENDING[str(store.episode_root)] = expected
    return store.seal(seal, teacher=sealed_teacher(store, outcome, data='VALID'))


def stop_evidence(spec, owner, process):
    """The shard's own stop documents in the exact closed shape `read_shard_stop_evidence` re-reads (controlled, no ROS)."""
    root = Path(spec['owned_root'])
    audit_root = root/'retirement'
    audit_root.mkdir(mode=0o700)
    native = dict(pid=501, pgid=501, started_ticks=100, argv_sha256='a'*64, environment_sha256='b'*64)
    lane_prefix = {'arm': '/arm_controller/follow_joint_trajectory/_action',
                   'gripper': '/gripper_controller/follow_joint_trajectory/_action',
                   'neck': '/neck_controller/follow_joint_trajectory/_action', 'moveit': '/execute_trajectory/_action'}
    lanes = {name: dict(action_prefix=prefix, cancel_sent_monotonic_ns=1_000_000_100,
        cancel_received_monotonic_ns=1_000_000_200, cancel_return_code=0, goals_canceling=[],
        status_received_monotonic_ns=1_000_000_300, statuses=[]) for name, prefix in lane_prefix.items()}
    goal = canonical_json(dict(schema_version=2, kind='ACT_CONTROLLER_STOP_OBSERVATION',
        started_monotonic_ns=1_000_000_000, completed_monotonic_ns=1_000_000_400,
        lanes=lanes))
    stack = canonical_json(dict(schema_version=1, leader_pid=native['pid'], pgid=native['pgid'],
        started_ticks=native['started_ticks'], argv_sha256=native['argv_sha256'], session_id=spec['simulation_session_id'],
        ros_domain_id=181, group_clear=True, graph_clear=True, physical_stop_confirmed=True,
        parent_exited=False, term_sent=True, kill_sent=False, finished_at_monotonic_ns=1_000_000_500))
    retirement._write(audit_root, 'controller-stop.json', goal)
    retirement._write(audit_root, 'stack-stop.json', stack)
    retirement._write(audit_root, 'audit.json', canonical_json(dict(schema_version=2, kind='ACT_SHARD_STOP_AUDIT',
        generation=spec['launch_generation'], process_owner=asdict(process), pid_namespace_inode=pid_namespace_inode(),
        session_id=spec['simulation_session_id'], ros_domain_id=181,
        native_owner=native, controller_stop_sha256=hashlib.sha256(goal).hexdigest(),
        native_stop_sha256=hashlib.sha256(stack).hexdigest(), errors=[])))
    retirement._write(root, 'shard-stop.json', canonical_json(dict(schema_version=1, kind='shard_stop_receipt',
        generation=spec['launch_generation'], process_owner=asdict(process), pid_namespace_inode=pid_namespace_inode(),
        goals_stopped=True, controllers_stopped=True, ros_children_exited=True, ros_graph_empty=True, forced=False)))


def inspect_document(owner):
    return dict(Id=owner.container_id, Image=owner.image_digest, State=dict(StartedAt=owner.docker_started_at,
        Running=False, Restarting=False, Pid=0, Status='exited', ExitCode=0))


def provenance_document(owner, image):
    return dict(container_id=owner.container_id, docker_started_at=owner.docker_started_at, image_digest=owner.image_digest,
        provenance=dict(schema_version=1, kind='ACT_CONTAINER_IMAGE_READBACK',
            package_source_sha256=image['package_source_sha256'], install_sha256=image['install_sha256'],
            git_commit='1'*40, submodules={}, runtime=dict(interpreter='/act/venv/bin/python',
                dependencies={'numpy': '1.26.4'}, module_origins={'so101_demo': '/act/install/lib/so101_demo/__init__.py'},
                package_prefixes={'so101_demo_py': '/act/install'})))


class World(SimpleNamespace):
    """Paths and parsed documents of one built run; `restoring` makes in-place edits safe for a module-scoped world."""

    @contextlib.contextmanager
    def restoring(self, *paths):
        """Remember each file's bytes (or absence) and put them back on exit, whatever the edit did."""
        saved = {Path(path): (Path(path).read_bytes() if Path(path).is_file() else None) for path in paths}
        try:
            yield
        finally:
            for path, data in saved.items():
                if data is None:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                else:
                    if path.is_symlink() or path.exists():
                        path.unlink()
                    path.write_bytes(data)

    def edit_json(self, path, mutate):
        document = json.loads(Path(path).read_bytes())
        mutate(document)
        Path(path).write_bytes(canonical_json(document)+b'\n')

    def snapshot(self):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
                for path in sorted(self.run.rglob('*'))}


def build_world(base, *, rules=None, tag='run-1', no_pose=(), teacher_failed=TEACHER_FAILED, qc_failed=QC_FAILED,
                loss_failed=(), reassign=None, surplus_early=(), evidence_root=None, images=None, source_bytes=None,
                runtime_bytes=None, collection_bytes=None, fingerprint='1'*64, formal_scenes=None):
    """Build the whole run under `base`; `install_controlled_qc` must already be active.

    The tuples are scene indexes of the controlled business outcomes (0-39): `no_pose` seals the manifest-free perception
    no-pose form, `teacher_failed` a Teacher FAIL with valid data, `qc_failed` a Teacher-reference QC FAIL and `loss_failed`
    a failing topic-loss gate. The defaults are the labelled synthetic default world; they are not measured results.
    `reassign` maps a scene to the worker that collected it instead of the planned one and `surplus_early` lists the waves whose
    surplus task is assigned before its worker's second reserved task; such a wave fails the real scheduling rule, so its
    `wave-N-verified.json` (and the campaign result and index) are not written, exactly as the owner would not write them.

    A caller whose formal campaign must share this run's evidence root and controlled identity passes: `evidence_root` (an
    existing registered root to build the run under instead of `base/'evidence'`), `images` (the inference and shard image
    documents), the bytes of the source, runtime and collection files, the contact policy `fingerprint`, and `formal_scenes`
    (an existing scene list file used as the gate's formal split manifest, so the formal campaign's own list hashes equal)."""
    scene_count = 40
    base = Path(base).resolve()
    inference_image, shard_image = images if images is not None else (INFERENCE_IMAGE, SHARD_IMAGE)
    if evidence_root is None:
        root = base/'evidence'
        root.mkdir()
    else:
        root = Path(evidence_root).resolve(strict=True)
    paths = make_campaign_paths(root, tag)
    run = paths['run']
    inputs = base/'inputs'
    inputs.mkdir()
    scenes = [f'load-{index:02d}' for index in range(scene_count)]
    rows = lambda names, offset: [dict(scene_id=name, seed=offset+index, split='validation') for index, name in enumerate(names)]
    scene_file = write_json(inputs/'qualification-scenes.json', dict(scenarios=rows(scenes, 200)))
    functional = write_json(inputs/'functional-scenes.json',
        dict(scenarios=rows([f'functional-{i:02d}' for i in range(8)], 100)))
    formal = (Path(formal_scenes) if formal_scenes is not None
              else write_json(inputs/'formal-scenes.json', dict(scenarios=rows([f'formal-{i:02d}' for i in range(3)], 300))))
    runtime = inputs/'runtime.yaml'
    runtime.write_bytes(runtime_bytes if runtime_bytes is not None else b'runtime: controlled\n')
    collection = inputs/'collection.yaml'
    collection.write_bytes(collection_bytes if collection_bytes is not None else b'collection: controlled\n')
    source = inputs/'source.tar'
    source.write_bytes(source_bytes if source_bytes is not None else b'source: controlled\n')
    proposal = write_json(inputs/'contact-proposal.json', dict(policy_fingerprint=fingerprint))
    identity = dict(source_sha256=sha(source), runtime_config_sha256=sha(runtime), collection_config_sha256=sha(collection),
        contact_policy_fingerprint=fingerprint, gpu_uuid=GPU, image_source_install=dict(inference=inference_image, shard=shard_image))
    rule_refs = rules if rules is not None else write_synthetic_rules(inputs)
    contract_path = write_json(inputs/'gate.json', dict(schema_version=1, kind='ACT_PARALLEL_COLLECTION_GATE',
        qualification_run_id='gate-run', worker_count=8, scene_manifest=ref(scene_file), functional_manifest=ref(functional),
        formal_split_manifest=ref(formal), controlled_identity=identity, quality_rules=rule_refs))
    contract_raw = contract_path.read_bytes()
    weights = inputs/'teacher.pt'
    weights.write_bytes(b'teacher-weights')
    service = dict(image=dict(inference_image), model=dict(model_id='teacher-model', weights=ref(weights),
        classes={'0': 'plastic_cup'}, score_threshold=.25), instances=3, torch_threads=1, torch_interop_threads=1,
        max_inflight_requests=8, max_frame_bytes=2**20, max_image_height=480, max_image_width=640, queue_timeout_s=.75,
        inference_timeout_s=1.25)
    campaign_path = write_json(inputs/'campaign.json', dict(schema_version=1, kind='ACT_CONTAINER_CAMPAIGN',
        evidence_root=str(root), controlled_runtime=ref(runtime), head_service=service, teacher_service=service,
        shard_image=dict(shard_image), gpu_uuid=GPU, qualification_contract=ref(contract_path)))
    config = load_campaign_config(campaign_path, roles=('teacher',))
    contract = validate_qualification_contract(json.loads(contract_raw), check_rules=rules is None)
    # ---- frozen inputs and per-scene scopes (controlled; see the module docstring) -----------------------------------------
    frozen_dir = run/'inputs'/'frozen'
    (frozen_dir/'roles').mkdir(parents=True)
    (run/'inputs'/'scopes').mkdir()
    role_proposal = frozen_dir/'roles'/'contact-proposal.json'
    role_proposal.write_bytes(proposal.read_bytes())
    (frozen_dir/'roles'/'runtime.yaml').write_bytes(runtime.read_bytes())
    (frozen_dir/'roles'/'collection.yaml').write_bytes(collection.read_bytes())
    (frozen_dir/'scene_manifest').mkdir()
    (frozen_dir/'scene_manifest'/'scenes.json').write_bytes(scene_file.read_bytes())
    inputs_manifest = frozen_dir/'inputs-manifest.json'
    inputs_manifest.write_bytes(canonical_json(dict(inputs_sha256='a'*64, mode=MODE))+b'\n')
    write_json(frozen_dir/'controlled-frozen-binding.json', dict(
        roles=dict(runtime_config=dict(path='roles/runtime.yaml', sha256=sha(runtime)),
                   collection_config=dict(path='roles/collection.yaml', sha256=sha(collection)),
                   contact_proposal=dict(path='roles/contact-proposal.json', sha256=sha(role_proposal))),
        scene_manifest=dict(path='scene_manifest/scenes.json', sha256=sha(scene_file), scene_count=len(scenes))))
    scopes = {}
    for index, scene in enumerate(scenes):
        path = run/'inputs'/'scopes'/(scene+'.json')
        write_collection_scope(build_collection_scope(MODE, scene_id=scene, seed=200+index, inputs_sha256='a'*64), path)
        scopes[scene] = path
    # ---- the Teacher service and the registry ------------------------------------------------------------------------------
    registry = ContainerLaunchRegistry(run/'host'/'launches.sqlite3')
    process = read_process_owner(os.getpid())
    teacher_launch = ContainerLaunch(launch_id='teacher-g1', role='teacher', worker_id=None, wave_id=None, launch_generation=1,
        container_name='so101-qualification-teacher', image_digest=inference_image['digest'], owned_root=str(paths['services']['teacher']))
    teacher_owner = ContainerOwnerKey(hashlib.sha256(b'teacher').hexdigest(), STARTED, inference_image['digest'], 1)
    registry.register(teacher_launch)
    registry.bind_container('teacher-g1', teacher_owner)
    registry.prove_terminated('teacher-g1', inspect_document(teacher_owner))
    _write(run/'teacher-service.json', service)
    _write(run/'host'/'teacher-ready.json', dict(schema_version=1, kind='service_ready', request_id='ready-1',
        service_generation=run.name+'-teacher-g1', image_digest=inference_image['digest'],
        package_source_sha256=inference_image['package_source_sha256'], model_id='teacher-model',
        weights_sha256=service['model']['weights']['sha256'], service_config_sha256=hashlib.sha256(canonical_json(service)).hexdigest(),
        gpu_uuid=GPU, configured_instances=3, loaded_instances=3, ready=True))
    _write(run/'host'/'teacher-provenance.json', provenance_document(teacher_owner, inference_image))
    # ---- the plan, the shards and the forty tasks --------------------------------------------------------------------------
    waves = partition_waves(tuple(scenes), max_wave_size=20)
    plans = [dict(wave_index=index, scene_ids=list(wave), assignment=reserve_qualification_scenes(wave, WORKERS))
             for index, wave in enumerate(waves)]
    _write(run/'campaign-index.json', dict(schema_version=1, kind='act_collection_campaign_index', qualification=True,
        scene_count=len(scenes), waves=plans))
    clock = iter(range(10, 10**6))
    seeds = {scene: 200+index for index, scene in enumerate(scenes)}
    verified_waves, shard_specs, owners, build_errors = [], {}, {}, []
    for plan in plans:
        wave_index = plan['wave_index']
        wave_id, generation = f'wave-{wave_index}', wave_index+1
        instances = {}
        for number, worker in enumerate(WORKERS):
            owned = run/wave_id/worker/f'g{generation}'
            for name in ('control', 'output', 'task-inputs', 'tmp'):
                (owned/name).mkdir(parents=True, mode=0o700)
            owners[wave_id, worker] = owned
            instances[f'{wave_id}-{worker}-g{generation}'] = dict(owner_root=str(owned), worker_id=worker,
                launch_generation=generation, wave_id=wave_id)
            session = f'session-{wave_index}-{number}'
            spec = dict(schema_version=2, kind='ACT_CONTAINER_SHARD', workload_kind='act_collection', campaign_id=CAMPAIGN_ID,
                worker_id=worker, launch_generation=generation, execution_generation=1,
                runtime_id=f'runtime-{wave_index}-{number}', service_epoch='epoch-1', service_token='0'*64,
                owned_root=str(owned),
                simulation_session_id=session, gpu_uuid=GPU, controlled_runtime=ref(runtime),
                business_identity=dict(manifest_sha256=hashlib.sha256(contract_raw).hexdigest(),
                    runtime_config_sha256=identity['runtime_config_sha256'],
                    collection_config_sha256=identity['collection_config_sha256'],
                    contact_policy_fingerprint=identity['contact_policy_fingerprint']),
                parallel_runtime=ref(runtime), campaign_config=ref(campaign_path), wave_id=wave_id,
                deadline_monotonic_s=1e9)
            shard_specs[wave_id, worker] = spec
            _write(run/f'shard-{wave_id}-{worker}-g{generation}.json', spec)
        journal = ContainerTaskJournal(run/'host'/wave_id/'task-journal', instances=instances, clock=lambda: float(next(clock)))
        reserved = plan['assignment']['reserved_by_worker']
        order = []
        surplus = plan['assignment']['surplus']
        for position, worker in enumerate(WORKERS):
            first, second = reserved[worker]
            extra = surplus[position] if position < len(surplus) else None
            sequence = [first, extra, second] if wave_index in surplus_early else [first, second, extra]
            order += [(worker, scene) for scene in sequence if scene is not None]
        order = [((reassign or {}).get(scene, worker), scene) for worker, scene in order]
        for worker, scene in order:
            owned = owners[wave_id, worker]
            task_id = f'{wave_id}-{worker}-{scene}'
            index = scenes.index(scene)
            document = owned/'task-inputs'/(task_id+'.json')
            document.write_text(json.dumps(dict(task_id=task_id, worker_id=worker, launch_generation=generation,
                                                wave_id=wave_id, scene_id=scene)))
            task = TaskSpec(task_id=task_id, inputs_ref=InputRef(**ref(document)), deadline_monotonic_s=1e9)
            assigned = journal.assign(instance_id=f'{wave_id}-{worker}-g{generation}', task=task,
                                      host_output=host_task_output(owned, task_id))
            issued = assigned['assigned_monotonic_s']+.25
            lease = LeaseIdentity(batch_id=f'{CAMPAIGN_ID}-{wave_id}', coordinator_epoch=1, worker_id=worker,
                worker_generation=generation, point_id=scene, attempt_id=scene+'-lease-1', lease_generation=1,
                lease_issued_monotonic_s=issued, lease_deadline_monotonic_s=issued+.5)
            task_dir = reserve_task_output(owned/'output', task_id)
            location = seal_task(task_dir, lease, scopes[scene], inputs_manifest, seed=seeds[scene],
                outcome='FAILED' if index in teacher_failed else 'PASSED', qc='FAIL' if index in qc_failed else 'PASS',
                pose=index not in no_pose, loss=index in loss_failed)
            summary = result_summary(task_input=SimpleNamespace(scene_id=scene,
                refs=dict(scope=ref(scopes[scene]), inputs_manifest=ref(inputs_manifest))), lease=lease,
                reset=SimpleNamespace(reset_epoch='reset-2', simulation_session_id='session-1'), location=str(location),
                task_root=task_dir)
            write_task_result(owned/'output', task_id, summary)
            journal.collect(task_id=task_id, result=read_container_task_result(owned, task_id=task_id))
        # the shards of this wave: registered, bound, then stopped with their stop evidence
        records = []
        for number, worker in enumerate(WORKERS):
            spec, owned = shard_specs[wave_id, worker], owners[wave_id, worker]
            launch = ContainerLaunch(launch_id=f'{wave_id}-{worker}-g{generation}', role='shard', worker_id=worker,
                wave_id=wave_id, launch_generation=generation, container_name=f'so101-qualification-{worker}-g{generation}',
                image_digest=shard_image['digest'], owned_root=str(owned), session_id=spec['simulation_session_id'])
            owner = ContainerOwnerKey(hashlib.sha256(launch.container_name.encode()).hexdigest(), STARTED,
                                      shard_image['digest'], generation)
            registry.register(launch)
            registry.bind_container(launch.launch_id, owner)
            registry.bind_child(launch.launch_id, ContainerChildBinding(owner, process, pid_namespace_inode(),
                                                                         str(owned/'control/normal.sock')))
            _write(owned/'actual-container-provenance.json', provenance_document(owner, shard_image))
            _write(owned/'runtime-ready.json', dict(schema_version=2, kind='ACT_SHARD_RUNTIME_READY', generation=generation,
                process_owner=asdict(process), readiness_sha256='0'*64))
            stop_evidence(spec, owner, process)
            registry.prove_terminated(launch.launch_id, inspect_document(owner))
            _write(owned/'host-cleanup.json', dict(terminated=True, launch_id=launch.launch_id, errors=[]))
            records.append(launch.launch_id)
        wave_records = [record for record in registry.records() if record['launch']['wave_id'] == wave_id]
        case_inputs = {scene: dict(scope=ref(scopes[scene]), inputs_manifest=ref(inputs_manifest)) for scene in plan['scene_ids']}
        try:
            verified = verify_wave_records(run, plan, wave_records, case_inputs, True)
        except ValueError as error:
            build_errors.append((wave_index, error.__cause__))
            continue
        _write(run/'host'/f'wave-{wave_index}-verified.json', verified)
        verified_waves.append(verified)
    if not build_errors:
        _write(run/'host'/'campaign-result.json', dict(campaign_id=CAMPAIGN_ID, scene_count=len(scenes), waves=verified_waves))
        _write(run/'collection-index.json', build_frozen_index(campaign_id=CAMPAIGN_ID, qualification=True,
            scene_count=len(scenes), waves=verified_waves))
    _write(run/'host'/'campaign-cleanup.json', dict(terminated=True, services=dict(terminated=True, launch_ids=['teacher-g1'],
        errors={}), shards=[dict(terminated=True, launch_id=item['launch']['launch_id'], errors=[])
                            for item in registry.records() if item['launch']['role'] == 'shard'], stop_reason='CAMPAIGN_CLOSING'))
    append_resource_log(run/'host'/'resources.jsonl', monotonic_ns=1, observed={'disk_free_bytes': 1}, missing={})
    registry.close()
    return World(base=base, root=root, run=run, inputs=inputs, scenes=scenes, plans=plans, contract_path=contract_path,
        contract=contract, campaign_path=campaign_path, config=config, scene_file=scene_file, functional=functional,
        formal=formal, rule_refs=rule_refs, identity=identity, runtime=runtime, collection=collection, inputs_manifest=inputs_manifest,
        scopes=scopes, specs=shard_specs, owners=owners, registry_path=run/'host'/'launches.sqlite3', service=service,
        report_path=run/'host'/'qualification-report.json', build_errors=build_errors)

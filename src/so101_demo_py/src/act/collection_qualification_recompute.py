"""Full recomputation of an eight-instance container-collection qualification run from its originals.

`recompute(run_root, contract_path)` returns the report document a run deserves. It reads the gate contract and its rule files,
the run layout, the launch registry (read-only), the task journals, the shard specs, the Teacher and shard provenance, the frozen
inputs and every sealed result, and re-derives each wave record, the campaign result and the frozen index with the same
functions the campaign owner used. It consumes no number that a previous report, memo or in-memory verdict claims, and it writes
nothing: the builder writes the document, the independent verifier compares it byte for byte.

Every refusal is a reason code in a closed vocabulary (`REASON_CODES`); a run that cannot be read at all raises instead. The
sources the recomputation cannot find under the run root are hash-pinned references the run itself names: the gate contract and
its scene and rule files (pinned by the shard specs' `manifest_sha256` and the contract's own refs) and the campaign config
(pinned by the shard specs). `source_sha256` has no original under the run; it is bound only through that hash chain.
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from so101_demo.act.collection_quality_gates import QUALITY_ORDER, apply_rule, evaluate_scene, file_ref
from so101_demo.act.parallel_collection import partition_waves, reserve_qualification_scenes
from so101_demo.act.parallel_collection_contracts import (
    read_document, scene_ids, validate_qualification_contract, validate_quality_rule,
)
from so101_demo.runtime.inference.config import _open_regular, load_campaign_config, validate_file_ref
from so101_demo.runtime.parallel_ipc.frames import _pairs, canonical_json

KIND = 'ACT_PARALLEL_COLLECTION_QUALIFICATION'
WORKERS = tuple(f'w{index:02d}' for index in range(8))
WAVES = (0, 1)
#: the closed vocabulary; a code with a parameter is `CODE:parameter`
REASON_CODES = frozenset({
    'CAMPAIGN_CONFIG_UNREADABLE', 'CAMPAIGN_INDEX_MISSING', 'CAMPAIGN_RESULT_MISMATCH', 'CAMPAIGN_RESULT_MISSING',
    'CLEANUP_UNCONFIRMED', 'DISPATCH_FAULT', 'EVIDENCE_INVALID', 'FROZEN_INDEX_MISMATCH', 'FROZEN_INDEX_MISSING',
    'FROZEN_INPUTS_INVALID', 'IDENTITY_MISMATCH', 'INSTANCE_SHORT', 'LAUNCH_TOPOLOGY_INVALID', 'PLAN_MISMATCH',
    'PROVENANCE_CONTAINER_MISMATCH', 'QUALITY_GATE_FAILED', 'QUALITY_RULE_UNDEFINED', 'REGISTRY_UNREADABLE',
    'PHASE1_NOT_RECORDED', 'PROCESSING_FAULT', 'PROCESSING_MISSING', 'PROCESSING_RECORD_INVALID',
    'RESERVED_COLLECTED_ELSEWHERE', 'SCOPE_MISMATCH', 'SHARD_SPEC_INVALID', 'SHARD_SPEC_MISSING', 'SURPLUS_BEFORE_RESERVED',
    'TASK_FAILED', 'TASK_UNFINISHED', 'TEACHER_SERVICE_INVALID', 'WAVE_RECOMPUTE_INVALID', 'WAVE_RECORD_MISMATCH',
    'WAVE_VERIFIED_MISSING'})
_LIMIT = 16*1024*1024
_SPEC_IDENTITY = ('manifest_sha256', 'runtime_config_sha256', 'collection_config_sha256', 'contact_policy_fingerprint')
_RUN_ERRORS = (OSError, ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError, sqlite3.Error)


def canonical(document):
    return canonical_json(document)+b'\n'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def read_frozen_inputs(path):
    """The strict verified frozen input set. A seam only for tests whose frozen set is controlled; production passes through.

    A qualification is evidence about the formal collection, so the set must be a formal-mode one whose contact receipt is a user
    activation. A diagnostic-mode set (a container contact-policy spot check) or a plan-signed candidate receipt can never be
    qualified, whatever else its run says: it is refused here, and the run's report then names `FROZEN_INPUTS_INVALID`."""
    from so101_demo.act.diagnostic_episode_inputs import verify_frozen_inputs

    frozen = verify_frozen_inputs(Path(path))
    try:
        approval = frozen['roles']['contact_activation']['approval']
    except (KeyError, TypeError) as error:
        raise ValueError('FROZEN_INPUTS_NOT_FORMAL_ACTIVATION') from error
    if frozen.get('mode') != 'formal' or approval != 'user_activation':
        raise ValueError('FROZEN_INPUTS_NOT_FORMAL_ACTIVATION')
    return frozen


def _bytes(path):
    with _open_regular(path) as stream:
        raw = stream.read(_LIMIT+1)
    if len(raw) > _LIMIT:
        raise ValueError('document too large')
    return raw


def _parse(raw):
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs,
                       parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
    if type(value) is not dict:
        raise ValueError('object required')
    return value


def _try_bytes(path):
    try:
        return _bytes(path)
    except (OSError, ValueError):
        return None


def _ref(path):
    return dict(path=str(path), sha256=sha256(_bytes(path)))


def run_layout(run_root):
    """The canonical run directory and its layout document; anything else is `QUALIFICATION_RUN_INVALID`."""
    try:
        run = Path(run_root)
        if not run.is_absolute() or '..' in run.parts or run.resolve(strict=True) != run or not run.is_dir():
            raise ValueError('run path')
        layout = _parse(_bytes(run/'.campaign-layout.json'))
        if (set(layout) != {'root', 'run_id', 'uid', 'gid'} or type(layout['root']) is not str
                or type(layout['run_id']) is not str or run != Path(layout['root'])/layout['run_id']
                or (layout['uid'], layout['gid']) != (os.getuid(), os.getgid())):
            raise ValueError('layout identity')
        return run, layout
    except _RUN_ERRORS as error:
        raise ValueError('QUALIFICATION_RUN_INVALID') from error


def contract_documents(contract_path):
    """`(raw bytes, validated contract)` of the gate contract; rule files are judged later, one reason per rule."""
    try:
        raw = _bytes(Path(contract_path))
        return raw, validate_qualification_contract(_parse(raw), check_rules=False)
    except _RUN_ERRORS as error:
        raise ValueError('QUALIFICATION_CONTRACT_UNREADABLE') from error


def campaign_contract_path(run_root):
    """The gate contract path the run's own campaign config names, found through the shard specs (verifier use)."""
    run, _ = run_layout(run_root)
    try:
        spec = _parse(_bytes(run/'shard-wave-0-w00-g1.json'))
        config = load_campaign_config(Path(spec['campaign_config']['path']), roles=('teacher',),
                                      expected_sha256=spec['campaign_config']['sha256'])
        return Path(config['qualification_contract']['path'])
    except _RUN_ERRORS as error:
        raise ValueError('QUALIFICATION_CONTRACT_UNREADABLE') from error


def frozen_identity_problems(frozen, manifest_path, contract):
    """Identity keys on which a verified frozen input set differs from the contract (same fields `campaign_binding` reads)."""
    identity, problems = contract['controlled_identity'], []
    try:
        roles = frozen['roles']
        found = dict(runtime_config_sha256=roles['runtime_config']['sha256'],
                     collection_config_sha256=roles['collection_config']['sha256'],
                     contact_policy_fingerprint=read_document(
                         Path(manifest_path).parent/roles['contact_proposal']['path'])['policy_fingerprint'])
        bound = frozen['scene_manifest']['sha256']
    except _RUN_ERRORS:
        return ['frozen_inputs']
    problems.extend(key for key, value in found.items() if value != identity[key])
    if bound != contract['scene_manifest']['sha256']:
        problems.append('scene_manifest')
    # the rig: the frozen set and the contract's identity name the same profile (neither naming one is rig v1)
    from .rig_profile import DEFAULT_RIG, rig_from_frozen
    try:
        frozen_rig = rig_from_frozen(frozen).profile_sha256
    except _RUN_ERRORS:
        return ['frozen_inputs']
    if frozen_rig != identity.get('rig_profile_sha256', DEFAULT_RIG.profile_sha256):
        problems.append('rig_profile_sha256')
    return problems


def _image_problem(document, image):
    try:
        report = document['provenance']
        from so101_demo.runtime.container_campaign.provenance import _report

        _report(report)
        return not (document['image_digest'] == image['digest']
                    and report['package_source_sha256'] == image['package_source_sha256']
                    and report['install_sha256'] == image['install_sha256'])
    except (ImportError,)+_RUN_ERRORS:
        return True


class _Run:
    """The state of one recomputation; every method appends reason codes and never raises on a bad original."""

    def __init__(self, run, layout, contract_path, raw, contract, readback_workers=None, readback_timeout_s=None):
        self.readback_workers, self.readback_timeout_s = readback_workers, readback_timeout_s
        self.run, self.layout, self.contract_path, self.contract = run, layout, Path(contract_path), contract
        self.contract_sha = sha256(raw)
        self.identity = contract['controlled_identity']
        self.reasons = set()
        self.records = ()
        self.config = None
        self.spec_gpus = set()
        self.processors = {}
        self.combined = None
        self.two_phase = False

    def mismatch(self, key):
        self.reasons.add('IDENTITY_MISMATCH:'+key)

    def gpu(self):
        """The GPU every original must name: the contract's (identity version 1) or the campaign config's (version 2, where the GPU
        is the environment and the report records it)."""
        if 'gpu_uuid' in self.identity:
            return self.identity['gpu_uuid']
        return None if self.config is None else self.config['gpu_uuid']

    def environment(self):
        if 'gpu_uuid' in self.identity:
            return None
        config = self.config or {}
        return dict(gpu_uuid=config.get('gpu_uuid'), gpu_model=config.get('gpu_model'))

    # ---- plan and rules ------------------------------------------------------------------------------------------------

    def plan(self):
        ids = scene_ids(self.contract['scene_manifest'], count=40)
        self.scenes = list(ids)
        self.plans = [dict(wave_index=index, scene_ids=list(wave), assignment=reserve_qualification_scenes(wave, WORKERS))
                      for index, wave in enumerate(partition_waves(ids, max_wave_size=20))]
        if len(self.plans) != len(WAVES):
            raise ValueError('wave count')
        expected = canonical(dict(schema_version=1, kind='act_collection_campaign_index', qualification=True,
                                  scene_count=len(ids), waves=self.plans))
        stored = _try_bytes(self.run/'campaign-index.json')
        self.campaign_index = None
        if stored is None:
            self.reasons.add('CAMPAIGN_INDEX_MISSING')
            return
        self.campaign_index = _ref(self.run/'campaign-index.json')
        if stored != expected:
            self.reasons.add('PLAN_MISMATCH')

    def rules(self):
        self.rule = {}
        for name in QUALITY_ORDER:
            try:
                self.rule[name] = validate_quality_rule(name, read_document(validate_file_ref(self.contract['quality_rules'][name])))
            except _RUN_ERRORS:
                self.rule[name] = None
                self.reasons.add('QUALITY_RULE_UNDEFINED:'+name)

    # ---- registry, topology and identity ---------------------------------------------------------------------------------

    def topology(self, registry):
        expected = {'teacher-g1': ('teacher', None, None, 1)}
        expected.update({f'wave-{wave}-{worker}-g{wave+1}': ('shard', f'wave-{wave}', worker, wave+1)
                         for wave in WAVES for worker in WORKERS})
        actual, self.processors, slots = {}, {}, {}
        for record in self.records:
            launch = record['launch']
            if launch['role'] == 'processor':
                # phase 2: `processing-pNN-g<k>`, any number of slots, each slot with launch generations 1..k without a gap
                worker, generation = launch['worker_id'], launch['launch_generation']
                if (launch['launch_id'] != f'processing-{worker}-g{generation}' or launch['wave_id'] is not None
                        or launch['launch_id'] in self.processors):
                    self.reasons.add('LAUNCH_TOPOLOGY_INVALID')
                self.processors[launch['launch_id']] = (worker, generation)
                slots.setdefault(worker, []).append(generation)
                continue
            actual[launch['launch_id']] = (launch['role'], launch['wave_id'], launch['worker_id'], launch['launch_generation'])
        if (len(self.records)-len(self.processors) != len(expected) or actual != expected
                or any(sorted(generations) != list(range(1, len(generations)+1)) for generations in slots.values())):
            self.reasons.add('LAUNCH_TOPOLOGY_INVALID')
        for record in self.records:
            launch = record['launch']
            image = self.identity['image_source_install']['inference' if launch['role'] == 'teacher' else 'shard']
            if launch['image_digest'] != image['digest']:
                self.mismatch('image_source_install')

    def specs(self):
        self.spec, campaign_ids, configs = {}, set(), set()
        for wave in WAVES:
            for worker in WORKERS:
                label = f'wave-{wave}/{worker}'
                try:
                    spec = read_document(self.run/f'shard-wave-{wave}-{worker}-g{wave+1}.json')
                except _RUN_ERRORS:
                    self.reasons.add('SHARD_SPEC_MISSING:'+label)
                    continue
                try:
                    if (spec['kind'] != 'ACT_CONTAINER_SHARD' or spec['worker_id'] != worker or spec['wave_id'] != f'wave-{wave}'
                            or spec['launch_generation'] != wave+1
                            or spec['owned_root'] != str(self.run/f'wave-{wave}'/worker/f'g{wave+1}')
                            or set(spec['business_identity']) != set(_SPEC_IDENTITY)):
                        raise ValueError('spec identity')
                    campaign_ids.add(spec['campaign_id'])
                    configs.add(json.dumps(spec['campaign_config'], sort_keys=True))
                    business = spec['business_identity']
                    if business['manifest_sha256'] != self.contract_sha:
                        self.mismatch('manifest_sha256')
                    for key in _SPEC_IDENTITY[1:]:
                        if business[key] != self.identity[key]:
                            self.mismatch(key)
                    if 'gpu_uuid' in self.identity:
                        if spec['gpu_uuid'] != self.identity['gpu_uuid']:
                            self.mismatch('gpu_uuid')
                    else:
                        self.spec_gpus.add(spec['gpu_uuid'])
                    self.spec[wave, worker] = spec
                except _RUN_ERRORS:
                    self.reasons.add('SHARD_SPEC_INVALID:'+label)
        self.campaign_id = next(iter(campaign_ids)) if len(campaign_ids) == 1 else None
        if len(campaign_ids) > 1 or len(configs) > 1:
            self.reasons.add('SHARD_SPEC_INVALID:campaign')
        if len(configs) == 1:
            self.campaign_config(json.loads(next(iter(configs))))

    def campaign_config(self, reference):
        try:
            self.config = config = load_campaign_config(Path(reference['path']), roles=('teacher',),
                                                        expected_sha256=reference['sha256'])
        except _RUN_ERRORS:
            self.reasons.add('CAMPAIGN_CONFIG_UNREADABLE')
            return
        images = self.identity['image_source_install']
        if config['qualification_contract'] != dict(path=str(self.contract_path), sha256=self.contract_sha):
            self.mismatch('campaign_contract')
        if config['evidence_root'] != self.layout['root']:
            self.mismatch('evidence_root')
        if config['gpu_uuid'] != self.gpu() or any(value != config['gpu_uuid'] for value in self.spec_gpus):
            self.mismatch('gpu_uuid')
        if config['teacher_service']['image'] != images['inference'] or config['shard_image'] != images['shard']:
            self.mismatch('image_source_install')
        if config['controlled_runtime']['sha256'] != self.identity['runtime_config_sha256']:
            self.mismatch('runtime_config_sha256')

    def services(self):
        images = self.identity['image_source_install']
        try:
            ready = read_document(self.run/'host'/'teacher-ready.json')
            from so101_demo.runtime.inference.contract import validate_service_response

            validate_service_response(ready)
            service = read_document(self.run/'teacher-service.json')
            if ready['kind'] != 'service_ready' or ready['ready'] is not True or ready['loaded_instances'] != ready['configured_instances']:
                self.reasons.add('TEACHER_SERVICE_INVALID')
            if (ready['image_digest'] != images['inference']['digest']
                    or ready['package_source_sha256'] != images['inference']['package_source_sha256']):
                self.mismatch('image_source_install')
            if ready['gpu_uuid'] != self.gpu():
                self.mismatch('gpu_uuid')
            if (ready['service_config_sha256'] != sha256(canonical_json(service))
                    or (self.config is not None and service != self.config['teacher_service'])):
                self.reasons.add('TEACHER_SERVICE_INVALID')
        except _RUN_ERRORS:
            self.reasons.add('TEACHER_SERVICE_INVALID')
        owners = {record['launch']['launch_id']: record['owner'] for record in self.records}
        sources = [(self.run/'host'/'teacher-provenance.json', images['inference'], 'teacher-g1')]
        sources += [(self.run/f'wave-{wave}'/worker/f'g{wave+1}'/'actual-container-provenance.json', images['shard'],
                     f'wave-{wave}-{worker}-g{wave+1}') for wave in WAVES for worker in WORKERS]
        sources += [(self.run/'processing'/worker/f'g{generation}'/'actual-container-provenance.json', images['shard'], launch_id)
                    for launch_id, (worker, generation) in self.processors.items()]
        for path, image, launch_id in sources:
            try:
                document = read_document(path)
                if _image_problem(document, image):
                    self.mismatch('image_source_install')
                owner = owners.get(launch_id)
                if owner is not None and document['container_id'] != owner['container_id']:
                    self.reasons.add('PROVENANCE_CONTAINER_MISMATCH:'+launch_id)
            except _RUN_ERRORS:
                self.mismatch('image_source_install')

    def frozen(self):
        self.frozen_set = None
        path = self.run/'inputs'/'frozen'/'inputs-manifest.json'
        try:
            self.frozen_set = read_frozen_inputs(path)
        except _RUN_ERRORS:
            self.reasons.add('FROZEN_INPUTS_INVALID')
            return
        for key in frozen_identity_problems(self.frozen_set, path, self.contract):
            if key == 'frozen_inputs':
                self.reasons.add('FROZEN_INPUTS_INVALID')
            else:
                self.mismatch(key)

    # ---- waves ---------------------------------------------------------------------------------------------------------------

    def wave(self, plan):
        from so101_demo.runtime.container_campaign.result_verifier import verify_wave_records
        from so101_demo.runtime.container_campaign.task_journal import read_task_journal

        index = plan['wave_index']
        wave_id = f'wave-{index}'
        launch_records = [record for record in self.records if record['launch']['wave_id'] == wave_id]
        instances = {record['launch']['launch_id']: dict(owner_root=record['launch']['owned_root'],
            worker_id=record['launch']['worker_id'], launch_generation=record['launch']['launch_generation'],
            wave_id=wave_id) for record in launch_records}
        try:
            journal = read_task_journal(self.run/'host'/wave_id/'task-journal', instances)
        except _RUN_ERRORS:
            self.reasons.add(f'WAVE_RECOMPUTE_INVALID:{index}')
            return None
        for task_id, item in journal.items():
            if item['failed'] is not None:
                self.reasons.add('TASK_FAILED:'+task_id)   # a faulted scene is a named reason; the wave is still verified
            elif item['collected'] is None:
                self.reasons.add('TASK_UNFINISHED:'+task_id)
        if any(item['collected'] is None and item['failed'] is None for item in journal.values()):
            return None
        try:
            manifest = _ref(self.run/'inputs'/'frozen'/'inputs-manifest.json')
            case_inputs = {scene: dict(scope=_ref(self.run/'inputs'/'scopes'/(scene+'.json')), inputs_manifest=dict(manifest))
                           for scene in plan['scene_ids']}
            return verify_wave_records(self.run, plan, launch_records, case_inputs, True,
                readback_workers=self.readback_workers, readback_timeout_s=self.readback_timeout_s)
        except _RUN_ERRORS as error:
            cause = str(error.__cause__ or '')
            for prefix in ('INSTANCE_SHORT', 'SURPLUS_BEFORE_RESERVED', 'RESERVED_COLLECTED_ELSEWHERE'):
                if cause.startswith(prefix+':'):
                    self.reasons.add(f'{prefix}:{wave_id}/{cause.split(":", 1)[1]}')
                    return None
            self.reasons.add(f'WAVE_RECOMPUTE_INVALID:{index}')
            return None

    def waves(self):
        self.wave_refs, self.verified = [], []
        for plan in self.plans:
            index = plan['wave_index']
            path = self.run/'host'/f'wave-{index}-verified.json'
            stored = _try_bytes(path)
            if stored is None:
                self.reasons.add(f'WAVE_VERIFIED_MISSING:{index}')
            else:
                self.wave_refs.append(_ref(path))
            verified = self.wave(plan)
            if verified is not None and stored is not None and canonical(verified) != stored:
                self.reasons.add(f'WAVE_RECORD_MISMATCH:{index}')
            self.verified.append(verified)
        complete = all(item is not None for item in self.verified)
        self.combined = self.combine() if complete else None
        for name, path in (('CAMPAIGN_RESULT', self.run/'host'/'campaign-result.json'),
                           ('FROZEN_INDEX', self.run/'collection-index.json')):
            stored = _try_bytes(path)
            if stored is None:
                self.reasons.add(name+'_MISSING')
            elif complete and self.campaign_id is not None and (self.combined is not None or not self.two_phase):
                from so101_demo.runtime.container_campaign.result_verifier import build_frozen_index

                if self.combined is not None:
                    from so101_demo.runtime.container_campaign.processing_verifier import build_campaign_result

                    document = (build_campaign_result(self.campaign_id, len(self.scenes), self.combined)
                                if name == 'CAMPAIGN_RESULT' else build_frozen_index(campaign_id=self.campaign_id,
                                    qualification=True, scene_count=len(self.scenes), combined=self.combined))
                else:
                    document = (dict(campaign_id=self.campaign_id, scene_count=len(self.scenes), waves=self.verified)
                                if name == 'CAMPAIGN_RESULT' else build_frozen_index(campaign_id=self.campaign_id,
                                    qualification=True, scene_count=len(self.scenes), waves=self.verified))
                if canonical(document) != stored:
                    self.reasons.add(name+'_MISMATCH')

    def combine(self):
        """The combined proof of both phases, recomputed from the phase-1 rows, the receipts, the processed results and the journal.

        A run is two-phase when a recomputed phase-1 proof is pending, a processor was launched or the processing record exists;
        a run without any of them is the inline form and is judged as before (`self.combined` stays None)."""
        rows = [row for wave in self.verified for row in wave['case_results']]
        self.two_phase = (any(row['proof'].get('processing') == 'PENDING' for row in rows) or bool(self.processors)
                          or (self.run/'host'/'processing-result.json').exists())
        if not self.two_phase:
            return None
        from so101_demo.runtime.container_campaign.processing_verifier import verify_processing

        try:
            combined = verify_processing(self.run, self.verified, self.scenes, readback_workers=self.readback_workers,
                                         readback_timeout_s=self.readback_timeout_s)
        except _RUN_ERRORS:
            self.reasons.add('PROCESSING_RECORD_INVALID')
            return None
        for item in combined['scenes']:
            if item['state'] == 'FAULT' and item['phase1'] is None:
                continue   # a phase-1 task fault: already named by `TASK_FAILED:<task>`
            if item['state'] == 'FAULT':
                self.reasons.add('PROCESSING_FAULT:'+item['scene_id'])
            elif item['state'] == 'MISSING':
                self.reasons.add(('PHASE1_NOT_RECORDED:' if item['phase1'] is None else 'PROCESSING_MISSING:')+item['scene_id'])
        return combined

    def scopes(self):
        if self.frozen_set is None:
            return
        from so101_demo.act.collection_scope import read_collection_scope

        for wave in self.verified:
            for row in (wave or {}).get('case_results', ()):
                try:
                    scope = read_collection_scope(row['scope_path'], expected_mode=self.frozen_set['mode'],
                                                  expected_inputs_sha256=self.frozen_set['inputs_sha256'])
                    if scope['scene_id'] != row['scene_id']:
                        raise ValueError('scene')
                except _RUN_ERRORS:
                    self.reasons.add('SCOPE_MISMATCH:'+row['scene_id'])

    def cleanup(self, registry):
        clear = False
        try:
            stored = {record['owner']['container_id']: record['exit_inspect'] for record in self.records
                      if record['owner'] is not None and record['exit_inspect'] is not None}
            clear = registry is not None and registry.all_terminated(lambda container_id: stored[container_id])
            document = read_document(self.run/'host'/'campaign-cleanup.json')
            keys = {'terminated', 'services', 'shards', 'stop_reason'} | ({'processors'} if self.processors else set())
            clear = (clear and set(document) == keys
                     and document['terminated'] is True and document['stop_reason'] == 'CAMPAIGN_CLOSING'
                     and document['services'].get('terminated') is True and len(document['shards']) == len(WAVES)*len(WORKERS)
                     and all(item.get('terminated') is True for item in document['shards'])
                     and sorted(item.get('launch_id') for item in document.get('processors', ())) == sorted(self.processors)
                     and all(item.get('terminated') is True for item in document.get('processors', ())))
        except _RUN_ERRORS:
            clear = False
        if not clear:
            self.reasons.add('CLEANUP_UNCONFIRMED')
        if (self.run/'host'/'dispatch-fault.json').exists() or (self.run/'host'/'dispatch-fault.json').is_symlink():
            self.reasons.add('DISPATCH_FAULT')

    # ---- quality -------------------------------------------------------------------------------------------------------------

    def scene_rows(self):
        """`(row, proof, processed)` per recorded scene and the scenes phase 1 never recorded.

        Two-phase: the proof is the phase-1 readback and `processed` the phase-2 readback record (None when processing did not deliver
        the scene). Inline: the proof is the whole sealed result and there is no phase 2."""
        if self.combined is not None:
            recorded = [(item, item['phase1'], item['phase2']) for item in self.combined['scenes'] if item['phase1'] is not None]
            return recorded, [item['scene_id'] for item in self.combined['scenes'] if item['phase1'] is None]
        return [(row, row['proof'], None) for wave in self.verified for row in (wave or {}).get('case_results', ())], []

    def quality(self):
        rows = {name: [] for name in QUALITY_ORDER}
        member = {}
        recorded, unrecorded = self.scene_rows()
        for row, proof, processed in recorded:
            scene = row['scene_id']
            try:
                verdicts, member[scene] = evaluate_scene(proof, processed)
            except _RUN_ERRORS:
                verdicts = {name: ('NO_EVIDENCE', None, 'EVIDENCE_INVALID') for name in QUALITY_ORDER}
                member[scene] = (True, None)
            for name in QUALITY_ORDER:
                outcome, source, error = verdicts[name]
                if error is not None:
                    self.reasons.add(f'EVIDENCE_INVALID:{name}:{scene}')
                rows[name].append(dict(scene_id=scene, task_id=row['task_id'], registration=file_ref(row['registration']),
                                       source=source, outcome=outcome))
        order = {scene: index for index, scene in enumerate(self.scenes)}
        complete = all(item is not None for item in self.verified)
        block = {}
        for name in QUALITY_ORDER:
            rule = self.rule[name]
            population = 'ALL_FROZEN_SCENES' if rule is None else rule['population']
            evidence = sorted(rows[name], key=lambda item: order[item['scene_id']])
            excluded = []
            if population == 'QC_VALID_EPISODES':
                # the named population of decision D2: the excluded scenes are listed with their reason, never skipped silently
                excluded = [dict(scene_id=item['scene_id'], reason=member[item['scene_id']][1]) for item in evidence
                            if not member[item['scene_id']][0]]
                evidence = [item for item in evidence if member[item['scene_id']][0]]
            # a scene phase 1 never recorded has no row to show, but it is in every denominator as no evidence, never as a pass
            outcomes = [item['outcome'] for item in evidence]+['NO_EVIDENCE']*len(unrecorded)
            passed = sum(1 for outcome in outcomes if outcome == 'PASS')
            if rule is None:
                verdict = 'UNDEFINED'
            elif not complete or len(evidence)+len(excluded)+len(unrecorded) != len(self.scenes):
                verdict = 'NOT_EVALUATED'
            else:
                passed, verdict = apply_rule(rule, outcomes)
                if verdict == 'FAIL':
                    self.reasons.add('QUALITY_GATE_FAILED:'+name)
            block[name] = dict(rule=_ref_of(self.contract['quality_rules'][name]), evidence=evidence,
                               result=dict(population=population, denominator=len(outcomes), passed=passed, verdict=verdict,
                                           excluded=excluded))
        return block


def _ref_of(reference):
    return dict(path=reference['path'], sha256=reference['sha256'])


def recompute(run_root, contract_path, *, readback_workers=None, readback_timeout_s=None):
    """The report document of the run: `status` QUALIFIED only with no reason. Raises when the run or contract cannot be read.

    `readback_workers` bounds the concurrent per-scene readbacks (None: the memory-derived default, 1: the serial path); the
    document does not depend on it."""
    run, layout = run_layout(run_root)
    raw, contract = contract_documents(contract_path)
    state = _Run(run, layout, contract_path, raw, contract, readback_workers, readback_timeout_s)
    try:
        state.plan()
    except _RUN_ERRORS as error:
        raise ValueError('QUALIFICATION_CONTRACT_UNREADABLE') from error
    state.rules()
    registry = None
    try:
        from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry

        registry = ContainerLaunchRegistry(run/'host'/'launches.sqlite3', create=False, read_only=True)
        state.records = registry.records()
    except _RUN_ERRORS:
        state.reasons.add('REGISTRY_UNREADABLE')
    try:
        state.topology(registry)
        state.specs()
        state.services()
        state.frozen()
        state.waves()
        state.scopes()
        state.cleanup(registry)
        quality = state.quality()
    finally:
        if registry is not None:
            registry.close()
    try:
        logs = [_ref(run/'host'/'resources.jsonl')]
    except _RUN_ERRORS:
        logs = []
    reasons = sorted(state.reasons)
    report = dict(schema_version=1, kind=KIND, status='NOT_QUALIFIED' if reasons else 'QUALIFIED',
        qualification_run_id=contract['qualification_run_id'], worker_count=8,
        controlled_identity=json.loads(canonical_json(contract['controlled_identity'])),
        contract=dict(path=str(Path(contract_path)), sha256=state.contract_sha), campaign_index=state.campaign_index,
        waves=state.wave_refs, quality=quality, resource_logs=logs, reasons=reasons)
    if state.environment() is not None:
        report['environment'] = state.environment()                # identity version 2: the GPU this host qualified on
    return report

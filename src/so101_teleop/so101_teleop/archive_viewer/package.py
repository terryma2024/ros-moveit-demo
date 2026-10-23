"""Collection projections keep recording, processing and commit facts distinct."""
from collections import OrderedDict
import threading
import hashlib
import statistics
from pathlib import Path
from .errors import invalid, refuse
from .manifest import ManifestIndex
from .models import (EpisodePage, EpisodeQuery, EpisodeRow, IdentityValue, Metric,
                     PackageStatistics, PackageView, SealView)
from .paths import read_json, resolve_package_path, open_readonly


class PackageSnapshot:
    def __init__(self, ref, records=None, records_lock=None):
        self._records = records if records is not None else OrderedDict()
        self._records_lock = records_lock or threading.RLock()
        self._cache_token = object()
        self.ref = ref
        self._manifest = None
        self.warnings = []
        self.scene_metadata = {}
        self.scenes = {}
        self.outputs = {}
        self.committed = set()
        self.rows = []
        self.identity = {}
        self.stats = None
        if ref.info.kind == 'collection':
            try:
                self._load_collection()
            except (TypeError, KeyError, AttributeError, ValueError) as error:
                invalid('collection documents', f'malformed structure: {type(error).__name__}')

    @property
    def manifest(self) -> ManifestIndex:
        if self._manifest is None:
            self._manifest = ManifestIndex(self.ref)
        return self._manifest

    def resolve(self, value: str, *, base: Path | None = None) -> Path:
        recorded = self.ref.recorded_root
        prefix = self.ref.source_root_prefix
        if prefix is not None and Path(value).is_relative_to(prefix):
            recorded = prefix
        return resolve_package_path(self.ref.path, recorded, value, base=base)

    def document(self, name: str, *, optional: bool = False) -> dict:
        path = self.resolve(name)
        if optional and not path.exists():
            self.warnings.append(f'{name}: unavailable')
            return {}
        return read_json(path, name, root=self.ref.path)

    def _load_collection(self):
        index = self.document('collection-index.json')
        if index.get('schema_version') not in (2, 3):
            invalid('collection-index.json', 'supported schema versions are 2 and 3')
        campaign = self.document('host/campaign-result.json', optional=True)
        frozen = self.document('inputs/frozen/inputs-manifest.json', optional=True)
        binding = frozen.get('scene_manifest')
        if binding:
            if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
                invalid('inputs-manifest.json', 'invalid scene manifest binding')
            path = self.resolve(binding['path'], base=self.ref.path/'inputs/frozen')
            if 'sha256' in binding:
                with open_readonly(self.ref.path, path) as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                if digest != binding['sha256']:
                    invalid('scene manifest', 'bound SHA256 mismatch')
            scenes = read_json(path, str(path.relative_to(self.ref.path)), root=self.ref.path).get('scenarios', [])
            if not isinstance(scenes, list):
                invalid('scene manifest', 'expected scenarios list')
            self.scene_metadata = self.scene_map(scenes, 'scene manifest')
        final_scenes = campaign.get('scenes', [])
        if not isinstance(final_scenes, list):
            invalid('campaign-result.json', 'expected scenes list')
        self.scenes = self.scene_map(final_scenes, 'host/campaign-result.json')
        committed = index.get('committed_episodes', [])
        if not isinstance(committed, list):
            invalid('collection-index.json', 'expected committed_episodes list')
        for entry in committed:
            scene_id = entry.get('scene_id')
            if not isinstance(scene_id, str) or scene_id in self.committed:
                invalid('collection-index.json', 'invalid or duplicate committed scene')
            self.committed.add(scene_id)
            output = entry.get('collection_evidence', {}).get('processing_output')
            if not isinstance(output, str):
                invalid('collection-index.json', 'processing_output missing')
            self.outputs[scene_id] = self.resolve(output)
        all_ids = set(self.scenes) | set(self.scene_metadata) | self.committed
        campaign_index = self.document('campaign-index.json', optional=True)
        for wave in campaign_index.get('waves', []):
            ids = wave.get('scene_ids', [])
            if not isinstance(ids, list) or any(not isinstance(value, str) or not value for value in ids):
                invalid('campaign-index.json', 'invalid scene ids')
            all_ids.update(ids)
        for item in index.get('collected_tasks', []):
            all_ids.add(item['scene_id'])
            if item.get('final', True) and item['scene_id'] not in self.scenes:
                self.scenes[item['scene_id']] = item
        if 'derived_sample' in index:
            sample = index['derived_sample']
            scope = sample.get('scenes') if isinstance(sample, dict) else None
            if (not isinstance(scope, list) or not scope
                    or any(not isinstance(scene, str) or not scene for scene in scope)
                    or len(set(scope)) != len(scope)
                    or type(index.get('scene_count')) is not int
                    or len(scope) != index['scene_count']
                    or not self.committed.issubset(scope)):
                invalid('collection-index.json', 'invalid derived sample scene scope')
            all_ids = set(scope)
            self.warnings.append(f'Derived sample ({len(scope)} scenes); campaign-level retry metadata may cover the full source campaign.')
        for scene_id in sorted(all_ids):
            row = self.scenes.get(scene_id, {})
            self.validate_attempts(row)
            attempts = self.recordings(row)
            output = self.outputs.get(scene_id)
            if output is None:
                processors = row.get('attempts', [])
                if processors and processors[-1].get('output_dir'):
                    output = self.resolve(processors[-1]['output_dir'])
                    self.outputs[scene_id] = output
            seal = {}; processed = {}
            size = None
            if output is not None:
                relative = output.relative_to(self.ref.path).as_posix()
                seal = self.document(relative+'/episode/seal.json', optional=True)
                processed = self.document(relative+'/processed-result.json', optional=True)
                size = sum(entry['bytes'] for entry in self.manifest.below(relative))
            count = seal.get('record_count')
            if count is not None and (type(count) is not int or count < 0):
                invalid('episode/seal.json', 'invalid record_count')
            outcome = self.outcome(row, processed, scene_id in self.committed)
            meta = self.scene_metadata.get(scene_id, {})
            phase1 = row.get('phase1') or (attempts[-1].get('phase1') if attempts else {}) or {}
            self.rows.append(EpisodeRow(
                scene_id=scene_id, split=meta.get('split'), collection_committed=scene_id in self.committed,
                outcome=outcome, reason=row.get('reason') or processed.get('act_data_reason'),
                recording_attempt_count=len(attempts), final_recording_round=row.get('recording_round', 0),
                record_count=count, duration_s=count/10 if count is not None else None, bytes=size,
                teacher_result=phase1.get('teacher_task_result') or row.get('teacher_task_result'),
                qc_status=processed.get('act_data_qc') or ('PASS' if seal.get('qc_passed') else None)))
        committed_rows = [r for r in self.rows if r.collection_committed]
        splits = {key: sum(r.split == key for r in committed_rows) for key in ('train', 'validation', 'offline_test')}
        outcomes = {key: sum(not r.collection_committed and r.outcome == key for r in self.rows) for key in ('FAULT', 'MISSING', 'INVALID')}
        recovered = {}
        for item in committed_rows:
            attempts = self.recordings(self.scenes.get(item.scene_id, {}))
            if item.final_recording_round > 0 and any(self.outcome(a, {}, False) == 'INVALID' for a in attempts[:-1]):
                key = str(item.final_recording_round)
                recovered[key] = recovered.get(key, 0) + 1
        retry = campaign.get('retry') or {}
        rounds_run = sum(d.get('status') == 'RUN' for d in retry.get('decisions', []))
        if not retry.get('decisions'):
            rounds_run = retry.get('rounds_run', len({r.final_recording_round for r in self.rows if r.final_recording_round > 0}))
        self.stats = PackageStatistics(planned=len(all_ids), committed=len(self.committed),
            committed_by_split=splits, non_committed_by_outcome=outcomes,
            retry_rounds_run=rounds_run, recovered=sum(recovered.values()), recovered_by_round=recovered,
            duration_rows=self.metric([r.record_count for r in committed_rows if r.record_count is not None]),
            duration_seconds=self.metric([r.duration_s for r in committed_rows if r.duration_s is not None]),
            episode_bytes=self.metric([r.bytes for r in committed_rows if r.bytes is not None]))
        self.identity = {key: IdentityValue() for key in ('campaign_id', 'source_commit', 'image_commit', 'image_digest', 'recording_cap', 'processor_count', 'retry_rounds', 'qualification_report_sha256', 'started_at', 'ended_at')}
        for key, value, source in [
            ('campaign_id', index.get('campaign_id') or campaign.get('campaign_id'), 'collection-index.json'),
            ('source_commit', frozen.get('source_commit'), 'inputs/frozen/inputs-manifest.json'),
            ('retry_rounds', retry.get('max_rounds'), 'host/campaign-result.json')]:
            self.identity[key] = IdentityValue(value=value, source=source if value is not None else None)
        provenance = self.document('host/teacher-provenance.json', optional=True)
        if provenance:
            self.identity['image_digest'] = IdentityValue(value=provenance.get('image_digest'), source='host/teacher-provenance.json')
            self.identity['image_commit'] = IdentityValue(value=provenance.get('provenance', {}).get('git_commit'), source='host/teacher-provenance.json')
            self.identity['started_at'] = IdentityValue(value=provenance.get('docker_started_at'), source='host/teacher-provenance.json (teacher start)')

    @staticmethod
    def validate_attempts(row):
        for key in ('attempts', 'recording_attempts'):
            values = row.get(key, [])
            if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
                invalid('host/campaign-result.json', f'invalid {key}')
        for recording in row.get('recording_attempts', []):
            PackageSnapshot.validate_attempts(recording)

    @staticmethod
    def scene_map(rows, document):
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('scene_id'), str) or not row['scene_id'] or row['scene_id'] in result:
                invalid(document, 'invalid or duplicate scene')
            result[row['scene_id']] = row
        return result

    @staticmethod
    def metric(values):
        return Metric(total=round(sum(values), 10), median=round(statistics.median(values), 10) if values else None)

    @staticmethod
    def recordings(row):
        return row.get('recording_attempts') or ([row] if row else [])

    @staticmethod
    def outcome(row, processed, committed):
        if row.get('state') in ('FAULT', 'MISSING'):
            return row['state']
        value = processed.get('act_data_status') or (row.get('verdict') or {}).get('act_data_status')
        attempts = row.get('attempts', [])
        value = value or (attempts[-1].get('outcome') if attempts else None) or row.get('act_data_status')
        if value in ('VALID', 'INVALID', 'FAULT', 'MISSING'):
            return value
        return 'VALID' if committed else 'MISSING'

    def view(self) -> PackageView:
        return PackageView(package=self.ref.info,
            seal=SealView(**{key: self.ref.seal[key] for key in SealView.model_fields if key in self.ref.seal}),
            identity=self.identity, statistics=self.stats, warnings=self.warnings)

    def episodes(self, query: EpisodeQuery) -> EpisodePage:
        if query.sort.lstrip('-') not in EpisodeRow.model_fields:
            invalid('sort', 'unknown episode sort column')
        rows = [r for r in self.rows if (not query.split or r.split == query.split) and
                (not query.outcome or r.outcome == query.outcome) and query.q.casefold() in r.scene_id.casefold()]
        key = query.sort.lstrip('-')
        present = [r for r in rows if getattr(r, key) is not None]
        absent = [r for r in rows if getattr(r, key) is None]
        present.sort(key=lambda r: r.scene_id)
        present.sort(key=lambda r: getattr(r, key), reverse=query.sort.startswith('-'))
        result = present + sorted(absent, key=lambda r: r.scene_id)
        return EpisodePage(episodes=result[query.offset:query.offset+query.limit], total=len(result))

    def episode(self, scene_id):
        from .episode import EpisodeSnapshot
        return EpisodeSnapshot(self, scene_id)

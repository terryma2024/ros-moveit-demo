"""Episode projections; only signal values and frame names survive records parsing."""
import hashlib
import json
import math
from .errors import invalid, refuse
from .files import read_file
from .models import ArchiveFile, AttemptView, EpisodeDetail, EpisodeSeries, SignalPoint
from .paths import read_json


class EpisodeSnapshot:
    def __init__(self, package, scene_id):
        self.package = package
        self.scene_id = scene_id
        self.output = package.outputs.get(scene_id)
        self.row = next((row for row in package.rows if row.scene_id == scene_id), None)
        if self.row is None:
            refuse('ARCHIVE_SCENE_NOT_FOUND', 'unknown scene id')

    def files(self):
        if self.output is None:
            return []
        prefix = self.output.relative_to(self.package.ref.path).as_posix()
        return [ArchiveFile(file_id=hashlib.sha256((self.package.ref.info.package_id+'\0'+entry['path']).encode()).hexdigest()[:24],
                            name=entry['path'], bytes=entry['bytes'], sha256=entry['sha256'])
                for entry in self.package.manifest.below(prefix)]

    def detail(self):
        seal = {}; processed = {}; qc = {}; warnings = []
        if self.output is not None:
            for name, target in [('episode/seal.json', seal), ('processed-result.json', processed)]:
                path = self.package.resolve(name, base=self.output)
                if path.exists():
                    target.update(read_json(path, name))
                else:
                    warnings.append(name+': unavailable')
            qc_path = processed.get('qc_report_path') or 'qc-report.json'
            if not isinstance(qc_path, str):
                invalid('processed-result.json', 'invalid qc_report_path')
            path = self.package.resolve(qc_path, base=self.output)
            if path.exists():
                qc = read_json(path, 'qc-report.json')
            else:
                warnings.append('qc-report.json: unavailable')
        attempts = []
        scene = self.package.scenes.get(self.scene_id, {})
        for recording in self.package.recordings(scene):
            common = dict(round=recording.get('recording_round'), wave=recording.get('wave_index'), shard=recording.get('worker_id'))
            attempts.append(AttemptView(kind='recording', **common, outcome=self.package.outcome(recording, {}, False), reason=recording.get('reason')))
            for proc in recording.get('attempts', []):
                attempts.append(AttemptView(kind='processing', **common, proc_attempt=proc.get('proc_attempt'), outcome=proc.get('outcome'), reason=proc.get('reason')))
        return EpisodeDetail(scene_id=self.scene_id, scene=self.package.scene_metadata.get(self.scene_id, {}),
                             collection_committed=self.row.collection_committed, seal=seal, processed_result=processed,
                             qc_summary=qc, attempts=attempts, files=self.files(), frame_count=len(self.records()), warnings=warnings)

    def records(self):
        key = (self.package._cache_token, self.scene_id)
        with self.package._records_lock:
            cached = self.package._records.pop(key, None)
            if cached is None:
                cached = self._read_records()
            self.package._records[key] = cached
            while len(self.package._records) > 2:
                self.package._records.popitem(last=False)
            return cached

    def _read_records(self):
        if self.output is None:
            return []
        path = self.package.resolve('episode/records.jsonl', base=self.output)
        if not path.exists():
            return []
        rows = []
        try:
            with path.open('rb') as stream:
                while raw := stream.readline(2*1024*1024+1):
                    if len(raw) > 2*1024*1024:
                        invalid('records.jsonl', 'record exceeds 2 MiB')
                    record = json.loads(raw); obs = record['observation']
                    point = SignalPoint(row=len(rows), t=obs['sim_time_s'], action=record['action'], state=obs['state'])
                    if len(point.action) != 6 or any(not math.isfinite(v) for v in [point.t, *point.action, *point.state]):
                        invalid('records.jsonl', 'invalid signal values')
                    rows.append((point, obs.get('head_png'), obs.get('wrist_png')))
        except (ValueError, KeyError, TypeError, UnicodeError):
            invalid('records.jsonl', 'invalid record structure')
        except OSError:
            refuse('ARCHIVE_FILE_NOT_FOUND', 'records not readable')
        return rows

    def series(self):
        rows = self.records()
        stride = max(1, math.ceil((len(rows)-1)/1999))
        indices = list(range(0, len(rows), stride))
        if rows and indices[-1] != len(rows)-1:
            indices.append(len(rows)-1)
        return EpisodeSeries(points=[rows[i][0] for i in indices], stride=stride, row_times_s=[r[0].t for r in rows])

    def frame(self, row, camera):
        if row < 0 or camera not in ('head', 'wrist'):
            invalid('frame', 'invalid row or camera')
        rows = self.records()
        if row >= len(rows):
            refuse('ARCHIVE_FRAME_NOT_FOUND', 'unknown frame row')
        value = rows[row][1 if camera == 'head' else 2]
        if not isinstance(value, str):
            refuse('ARCHIVE_FRAME_NOT_FOUND', 'frame is unavailable')
        path = self.package.resolve(value, base=self.output/'episode')
        frames = self.output/'episode/frames'
        if not path.is_relative_to(frames) or path.suffix != '.png':
            refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE', 'frame is outside episode frames', 409)
        # Both lexical and resolved identity must remain inside the manifest.
        relative = path.relative_to(self.package.ref.path).as_posix()
        if relative not in self.package.manifest.entries:
            refuse('ARCHIVE_PATH_OUTSIDE_PACKAGE', 'frame is not manifest-listed', 409)
        if not path.is_file():
            refuse('ARCHIVE_FRAME_NOT_FOUND', 'frame is missing')
        return path

    def file(self, file_id, offset=0, limit=100):
        entry = next((entry for entry in self.files() if entry.file_id == file_id), None)
        if entry is None:
            refuse('ARCHIVE_FILE_NOT_FOUND', 'unknown file id')
        return read_file(self.package.resolve(entry.name), offset=offset, limit=limit)

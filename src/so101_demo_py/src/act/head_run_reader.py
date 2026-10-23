"""Bounded, read-only file-v1 input reader. No execution dependencies."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

DEFAULT_EVIDENCE_ROOT = Path('/opt/data/work/so101-evidence' if sys.platform == 'darwin'
                             else '/data/work/so101-evidence')
MAX_EVENT_BYTES = 1024 * 1024
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64
MAX_EVENTS = 2_000_000
MAX_ARTIFACTS = 100_000
MAX_CORRELATIONS = 100_000
PROFILES = {
    ('63f3dc2b950c2d7b7be7f294db5b1b0b23184b40d55bf658a4a7d331452c17b5',
     'a5fb3450da59e2bfff452de5823efdf0bb070f71f7ff59a129b541e163a7fecc'): 'postflight-domain-key',
    ('780f1719d52af0df73ba3eebb4c70f493bf45b0571e2620b254d6eb189bdf993',
     '25f2bec71a0fee9288f019432335ce5cb788b5ac360510bbf1f47fefb72d7c95'): 'postflight-ros-domain-id-key',
}


class AuditToolError(RuntimeError):
    """Invalid access, resource limit or other incomplete tool operation (rc3)."""


class InvalidFormat(ValueError):
    """Untrusted structured input is malformed."""


def is_integer(value):
    return type(value) is int


def is_digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def strict_json(data):
    """Reject duplicate keys/nonfinite numbers and bound depth before decoding."""
    try:
        text = data.decode('utf-8', 'strict') if isinstance(data, bytes) else data
        depth = 0
        quoted = escaped = False
        for character in text:
            if quoted:
                if escaped:
                    escaped = False
                elif character == '\\':
                    escaped = True
                elif character == '"':
                    quoted = False
            elif character == '"':
                quoted = True
            elif character in '[{':
                depth += 1
                if depth > MAX_DEPTH:
                    raise AuditToolError('STRUCTURED_DEPTH_LIMIT')
            elif character in ']}':
                depth -= 1

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise InvalidFormat('DUPLICATE_JSON_KEY')
                result[key] = value
            return result

        def number(value):
            raise InvalidFormat('NONFINITE_JSON_NUMBER: ' + value)

        def floating(value):
            parsed = float(value)
            if not (-float('inf') < parsed < float('inf')):
                raise InvalidFormat('NONFINITE_JSON_NUMBER')
            return parsed

        return json.loads(text, object_pairs_hook=pairs, parse_constant=number, parse_float=floating)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise InvalidFormat(type(error).__name__) from error


def canonical_digest(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def strict_yaml(data):
    """Parse only bounded data mappings; reject duplicate keys and alias expansion."""
    import yaml

    class UniqueSafeLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            result = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise InvalidFormat('YAML_STRING_KEY_REQUIRED')
                if key in result:
                    raise InvalidFormat('DUPLICATE_YAML_KEY')
                result[key] = self.construct_object(value_node, deep=deep)
            return result

    try:
        depth = 0
        for event in yaml.parse(data, Loader=yaml.SafeLoader):
            if isinstance(event, yaml.events.AliasEvent):
                raise AuditToolError('YAML_ALIAS_EXPANSION_NOT_SUPPORTED')
            if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
                depth += 1
                if depth > MAX_DEPTH:
                    raise AuditToolError('STRUCTURED_DEPTH_LIMIT')
            elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
                depth -= 1
        value = yaml.load(data, Loader=UniqueSafeLoader)
        strict_json(json.dumps(value, allow_nan=False))
        return value
    except (yaml.YAMLError, TypeError, ValueError, RecursionError) as error:
        raise InvalidFormat(str(error)) from error


def normalized(path):
    if not Path(path).is_absolute():
        raise AuditToolError('ABSOLUTE_PATH_REQUIRED')
    return Path(os.path.normpath(os.fspath(path)))


@contextmanager
def open_regular(path):
    """Walk every original component without following links; never block on FIFO."""
    descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = Path(path).parts[1:]
        for part in parts[:-1]:
            next_descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                      dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        leaf = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                       dir_fd=descriptor)
        try:
            if not stat.S_ISREG(os.fstat(leaf).st_mode):
                raise AuditToolError('REGULAR_FILE_REQUIRED')
            with os.fdopen(leaf, 'rb', closefd=False) as stream:
                yield stream
        finally:
            os.close(leaf)
    except FileNotFoundError:
        raise
    except OSError as error:
        raise AuditToolError('INPUT_ACCESS_DENIED_OR_UNSAFE: ' + str(path)) from error
    finally:
        os.close(descriptor)


def file_identity(info):
    return dict(device=info.st_dev, inode=info.st_ino, size=info.st_size,
                mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns, links=info.st_nlink)


@contextmanager
def open_directory(path):
    descriptor=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in Path(path).parts[1:]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
        yield descriptor
    except FileNotFoundError:
        raise
    except OSError as error:
        raise AuditToolError('DIRECTORY_ACCESS_UNSAFE') from error
    finally:
        os.close(descriptor)


class RunReader:
    """Keep bounded metadata and document inputs, never a whole event stream."""

    def __init__(self, run_root, execution_receipt, execution_receipt_sha256, *, evidence_root=None):
        self.evidence_root = normalized(evidence_root or DEFAULT_EVIDENCE_ROOT)
        self.run_root = Path(run_root)
        self.execution_receipt = Path(execution_receipt)
        self.receipt_sha256 = execution_receipt_sha256
        if not is_digest(execution_receipt_sha256):
            raise AuditToolError('RECEIPT_SHA256_INVALID')
        self._check_scope(run_root)
        self._check_scope(execution_receipt)
        self.documents = {}
        self.external = {}
        self.files = {}
        self.tainted = set()
        self.findings = []
        self.seal = None
        self.profile = None
        self.initial_inventory = None
        self.event_count = 0
        self.passes = 0
        self.loaded = False

    def _check_scope(self, path):
        path = normalized(path)
        if not path.is_relative_to(self.evidence_root):
            raise AuditToolError('INPUT_ESCAPES_EVIDENCE_ROOT')
        return path

    def run_path(self, relative):
        if not isinstance(relative, str):
            raise AuditToolError('RUN_PATH_INVALID')
        parts = PurePosixPath(relative)
        if parts.is_absolute() or '..' in parts.parts or not parts.parts or '\\' in relative:
            raise AuditToolError('RUN_PATH_ESCAPES')
        return self.run_root / parts

    def finding(self, code, path=None, *, failure=False, line=None, observed=None):
        self.findings.append(dict(code=code, category='INTEGRITY' if failure else 'EVIDENCE_GAP',
            severity='ERROR' if failure else 'WARNING', affected_results=['integrity'],
            evidence=self.evidence(path, line=line), expected=code, observed=observed,
            calculation=None, identifiers={}))

    def evidence(self, path=None, *, line=None, sequence=None):
        p = str(normalized(path)) if path is not None else None
        entry = self.files.get(p, {})
        return dict(path=p, sha256=entry.get('sha256'), line=line, event_sequence=sequence)

    @property
    def integrity_status(self):
        if any(x['category'] == 'INTEGRITY' for x in self.findings):
            return 'FAIL'
        if any('integrity' in x['affected_results'] for x in self.findings):
            return 'INCOMPLETE'
        return 'PASS'

    def _record_stream(self, path, stream, expected=None, *, structured=False):
        before = file_identity(os.fstat(stream.fileno()))
        if structured and before['size'] > MAX_DOCUMENT_BYTES:
            raise AuditToolError('DOCUMENT_BYTES_LIMIT')
        sha = hashlib.sha256()
        body = bytearray() if structured else None
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
            if structured:
                if len(body) + len(chunk) > MAX_DOCUMENT_BYTES:
                    raise AuditToolError('DOCUMENT_BYTES_LIMIT')
                body.extend(chunk)
        after = file_identity(os.fstat(stream.fileno()))
        canonical = str(self._check_scope(path))
        entry = dict(original_path=str(path), path=canonical, size=after['size'],
                     sha256=sha.hexdigest(), identity=after)
        prior = self.files.get(canonical)
        self.files.setdefault(canonical, entry)
        if before != after or (prior is not None and (prior['identity'] != after or
                                                     prior['sha256'] != entry['sha256'])):
            self.tainted.add(canonical)
            self.finding('INPUT_CHANGED', path)
        if expected is not None:
            size = expected.get('size', expected.get('bytes'))
            if not is_digest(expected.get('sha256')) or (size is not None and
                                                       (not is_integer(size) or size < 0)):
                self.finding('FILE_REFERENCE_INVALID', path, failure=True)
            elif expected['sha256'] != entry['sha256'] or (size is not None and size != entry['size']):
                self.tainted.add(canonical)
                self.finding('FILE_DIGEST_OR_SIZE_MISMATCH', path, failure=True)
        return bytes(body) if structured else None

    def read_document(self, path, expected=None, *, yaml=False):
        self._check_scope(path)
        try:
            with open_regular(path) as stream:
                data = self._record_stream(path, stream, expected, structured=True)
            if yaml:
                value = strict_yaml(data)
            else:
                value = strict_json(data)
            if not isinstance(value, dict):
                raise InvalidFormat('DOCUMENT_OBJECT_REQUIRED')
            return value
        except FileNotFoundError:
            self.finding('INPUT_MISSING', path)
        except (InvalidFormat, ValueError) as error:
            self.tainted.add(str(normalized(path)))
            self.finding('DOCUMENT_FORMAT_INVALID', path, failure=self.seal is not None,
                         observed=str(error))
        return None

    def inventory(self):
        if not self.run_root.exists():
            return []
        result = []
        def walk(descriptor,prefix,depth):
            if depth>MAX_DEPTH:raise AuditToolError('RUN_DIRECTORY_DEPTH_LIMIT')
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    info=entry.stat(follow_symlinks=False)
                    if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                        raise AuditToolError('RUN_TREE_UNSAFE')
                    relative=prefix/entry.name
                    result.append(dict(path=str(relative),mode=stat.S_IFMT(info.st_mode),
                                       inode=info.st_ino,device=info.st_dev))
                    if len(result)>MAX_ARTIFACTS+16:raise AuditToolError('RUN_INVENTORY_LIMIT')
                    if stat.S_ISDIR(info.st_mode):
                        child=os.open(entry.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
                        try:walk(child,relative,depth+1)
                        finally:os.close(child)
        with open_directory(self.run_root) as descriptor:
            info=os.fstat(descriptor)
            result.append(dict(path='.',mode=stat.S_IFDIR,inode=info.st_ino,device=info.st_dev))
            walk(descriptor,PurePosixPath(),0)
        return sorted(result, key=lambda item: item['path'])

    def events(self):
        path = self.run_root / 'events.jsonl'
        self.passes += 1
        try:
            with open_regular(path) as stream:
                initial = file_identity(os.fstat(stream.fileno()))
                for line_number in range(1, MAX_EVENTS + 2):
                    line = stream.readline(MAX_EVENT_BYTES + 1)
                    if not line:
                        break
                    if line_number > MAX_EVENTS or len(line) > MAX_EVENT_BYTES:
                        raise AuditToolError('EVENT_COUNT_OR_LINE_LIMIT')
                    try:
                        if not line.endswith(b'\n'):
                            raise InvalidFormat('TRUNCATED_EVENT_TAIL')
                        event = strict_json(line)
                        if not isinstance(event, dict) or type(event.get('schema_version')) is not int or \
                                event['schema_version'] != 1 or \
                                not is_integer(event.get('sequence')) or event['sequence'] != line_number or \
                                not isinstance(event.get('record'), dict) or \
                                not isinstance(event.get('kind'), str) or \
                                not isinstance(event.get('run'), dict) or \
                                not isinstance(event.get('artifact_refs'), list):
                            raise InvalidFormat('EVENT_ENVELOPE_OR_SEQUENCE_INVALID')
                        version = event.get('record_schema_version')
                        if version is not None and (not is_integer(version) or version != 1):
                            raise InvalidFormat('RECORD_VERSION_INVALID')
                        for key in ('source_sha256', 'config_sha256', 'model_sha256'):
                            if not is_digest(event.get(key)):
                                raise InvalidFormat('EVENT_DIGEST_INVALID')
                        for key in ('occurrence_mono_ns', 'observed_mono_ns'):
                            if not is_integer(event.get(key)) or event[key] < 0:
                                raise InvalidFormat('EVENT_CLOCK_INVALID')
                        if event.get('source_stamp_ns') is not None and (not is_integer(event['source_stamp_ns'])
                                or event['source_stamp_ns']<0):
                            raise InvalidFormat('EVENT_SOURCE_CLOCK_INVALID')
                        if not is_integer(event['run'].get('generation')):
                            raise InvalidFormat('EVENT_GENERATION_INVALID')
                        event['_line'] = line_number
                        yield event
                    except InvalidFormat as error:
                        self.finding('EVENT_FORMAT_INVALID', path, failure=self.seal is not None,
                                     line=line_number, observed=str(error))
                if file_identity(os.fstat(stream.fileno())) != initial:
                    self.tainted.add(str(path))
                    self.finding('INPUT_CHANGED', path)
        except FileNotFoundError:
            self.finding('EVENT_STREAM_MISSING', path)

    def _external_ref(self, reference, label, *, yaml=False):
        if not isinstance(reference, dict) or not isinstance(reference.get('path'), str):
            self.finding('EXTERNAL_REFERENCE_MISSING: ' + label)
            return None
        value = self.read_document(Path(reference['path']), reference, yaml=yaml)
        self.external[label] = value
        return value

    def trusted_external(self, name):
        """Unverified external bytes cannot supply calculation parameters."""
        if name == 'execution_receipt':
            if str(normalized(self.execution_receipt)) in self.tainted:
                return None
        manifest = self.documents.get('manifest.json') or {}
        receipt = self.external.get('execution_receipt') or {}
        for source in (manifest, manifest.get('refs', {}), receipt.get('refs', {})):
            reference = source.get(name)
            if isinstance(reference, dict) and isinstance(reference.get('path'), str) and \
                    str(normalized(reference['path'])) in self.tainted:
                return None
        return self.external.get(name)

    def load(self):
        if self.loaded:
            raise AuditToolError('READER_ALREADY_LOADED')
        self.initial_inventory = self.inventory()
        self.seal = self.read_document(self.run_root / 'seal.json')
        if self.seal is None and not any(x['code'] == 'INPUT_MISSING' for x in self.findings):
            self.finding('SEAL_FORMAT_INVALID', self.run_root / 'seal.json', failure=True)
        expected = {}
        if self.seal is not None:
            entries = self.seal.get('files')
            if type(self.seal.get('file_protocol_version')) is not int or \
                    self.seal['file_protocol_version'] != 1 or not isinstance(entries, list):
                self.finding('SEAL_SCHEMA_INVALID', self.run_root / 'seal.json', failure=True)
                entries = []
            if len(entries) > MAX_ARTIFACTS + 3:
                raise AuditToolError('ARTIFACT_COUNT_LIMIT')
            for entry in entries:
                if not isinstance(entry, dict):
                    self.finding('SEAL_FILE_INVALID', failure=True)
                    continue
                relative = entry.get('path')
                path = self.run_path(relative)
                if relative in expected or relative == 'seal.json':
                    self.finding('SEAL_DUPLICATE_OR_SELF_REFERENCE', path, failure=True)
                expected[relative] = entry
                try:
                    with open_regular(path) as stream:
                        self._record_stream(path, stream, entry)
                except FileNotFoundError:
                    self.finding('SEALED_FILE_MISSING', path)
            actual_files = {x['path'] for x in self.initial_inventory if x['mode'] == stat.S_IFREG}
            if actual_files - {'seal.json'} - expected.keys():
                self.finding('UNLISTED_RUN_FILE', self.run_root / 'seal.json', failure=True)
            for name in ('manifest.json', 'events.jsonl', 'completion.json'):
                if name not in expected:
                    self.finding('REQUIRED_SEAL_ENTRY_MISSING', self.run_root / name)
            artifacts = sum(name.startswith('artifacts/') for name in expected)
            if not is_integer(self.seal.get('artifact_count')) or self.seal['artifact_count'] != artifacts:
                self.finding('ARTIFACT_COUNT_MISMATCH', self.run_root / 'seal.json', failure=True)
            counters = self.seal.get('counters', {})
            if not isinstance(counters, dict):
                self.finding('WRITER_COUNTERS_INVALID', failure=True)
            else:
                for name in ('drop_count', 'fault_count'):
                    if not is_integer(counters.get(name)) or counters[name] != 0:
                        self.finding('WRITER_LOSS_OR_FAULT', failure=True, observed=counters)
        else:
            # Missing sealing is an evidence gap. Available originals still
            # receive complete byte hashes and the same readback fence.
            for entry in self.initial_inventory:
                if entry['mode'] == stat.S_IFREG:
                    path = self.run_path(entry['path'])
                    try:
                        with open_regular(path) as stream:
                            self._record_stream(path, stream)
                    except FileNotFoundError:
                        self.finding('INPUT_MISSING', path)
        for name in ('manifest.json', 'completion.json'):
            self.documents[name] = self.read_document(self.run_root / name, expected.get(name))
        manifest = self.documents.get('manifest.json') or {}
        if manifest and (type(manifest.get('file_protocol_version')) is not int or
                         manifest['file_protocol_version'] != 1):
            self.finding('MANIFEST_PROTOCOL_INVALID', self.run_root / 'manifest.json', failure=True)
        run=manifest.get('run')
        if manifest and (not isinstance(run,dict) or not is_integer(run.get('generation'))
                         or run['generation']<=0 or any(not isinstance(run.get(key),str) or not run[key]
                         for key in ('run_id','epoch','session_id'))):
            self.finding('MANIFEST_RUN_FORMAT_INVALID',self.run_root/'manifest.json',failure=True)
        source = manifest.get('source_manifest', {})
        freeze = manifest.get('freeze_receipt', {})
        self.profile = PROFILES.get((source.get('sha256'), freeze.get('sha256')))
        for name in ('source_manifest', 'freeze_receipt', 'execution_inputs'):
            if name in manifest:
                self._external_ref(manifest[name], name)
        if str(normalized(self.run_root / 'manifest.json')) in self.tainted or any(
                self.trusted_external(name) is None for name in ('source_manifest', 'freeze_receipt')):
            self.profile = None
        refs = manifest.get('refs', {})
        if isinstance(refs, dict):
            for name in ('development_config', 'local_policy', 'camera_geometry', 'controller_config'):
                if name in refs:
                    self._external_ref(refs[name], name, yaml=name == 'controller_config')
        receipt = self.read_document(self.execution_receipt, {'sha256': self.receipt_sha256})
        self.external['execution_receipt'] = receipt
        if receipt is not None:
            receipt_refs = receipt.get('refs', {})
            if isinstance(receipt_refs, dict):
                for name in ('launcher', 'inputs', 'postflight', 'owned_postflight', 'seal', 'completion'):
                    if name in receipt_refs:
                        self._external_ref(receipt_refs[name], name)
        count = 0
        for event in self.events():
            count += 1
            for reference in event['artifact_refs']:
                if not isinstance(reference, dict):
                    self.finding('EVENT_ARTIFACT_REF_INVALID', failure=True, line=event['_line'])
                    continue
                relative = reference.get('path')
                path = self.run_path(relative)
                sealed = expected.get(relative)
                if sealed is None or sealed.get('sha256') != reference.get('sha256') or \
                        not is_integer(reference.get('size')) or sealed.get('size')!=reference['size']:
                    self.finding('EVENT_ARTIFACT_REF_UNSEALED', path, failure=self.seal is not None,
                                 line=event['_line'])
        self.event_count = count
        if self.seal is not None and str(normalized(self.run_root/'events.jsonl')) in self.files and \
                (not is_integer(self.seal.get('event_count')) or
                                     self.seal['event_count'] != count):
            self.finding('EVENT_COUNT_MISMATCH', self.run_root / 'seal.json', failure=True)
        if self.seal is not None and isinstance(self.seal.get('counters'),dict):
            counters=self.seal['counters']
            for name in ('event_count','artifact_count'):
                if not is_integer(counters.get(name)) or counters[name]!=self.seal.get(name):
                    self.finding('WRITER_COUNT_MISMATCH',self.run_root/'seal.json',failure=True)
        self.loaded = True
        return self

    def readback(self):
        changed = self.inventory() != self.initial_inventory
        for entry in list(self.files.values()):
            try:
                with open_regular(Path(entry['original_path'])) as stream:
                    before = file_identity(os.fstat(stream.fileno()))
                    sha = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        sha.update(block)
                    same = (before == file_identity(os.fstat(stream.fileno())) == entry['identity']
                            and sha.hexdigest() == entry['sha256'])
                if not same:
                    changed = True
                    self.tainted.add(entry['path'])
            except FileNotFoundError:
                changed = True
                self.tainted.add(entry['path'])
        if changed:
            self.finding('INPUT_CHANGED', self.run_root / 'manifest.json')
        return dict(unchanged=not changed, files=list(self.files.values()),
                    run_inventory_before=self.initial_inventory, run_inventory_after=self.inventory(),
                    tainted_files=sorted(self.tainted), stream_passes=self.passes)

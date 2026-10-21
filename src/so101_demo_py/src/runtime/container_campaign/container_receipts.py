"""Container termination receipts of a campaign run collected stage by stage.

A stage that finishes proves its own containers gone, because the next stage may not start while any container exists (the run script's
"no container" precondition). At the end of a completed stage the owner (1) inspects each container of the stage again, independently of
the settlement stored in the launch registry, and requires `exited` with an exit code, a finished-at time and the registered container
id, (2) removes the containers and (3) proves that none of them remains. The result is one receipt beside the stage record:

    host/containers-receipt-<NN>-<stage>.json     NN = 01, 02, ... in the order the stages ended

A receipt names the sha256 of the stage record it belongs to and of the receipt before it, so the receipts form a chain exactly as the
stage records do. A later stage and the finalize verify termination from these receipts and from the launch registry's stored settlement;
they never need a live container. A run that is not collected stage by stage writes no receipt.

Refusals: `STAGE_CONTAINER_RECEIPT_MISSING` (a completed stage has no receipt), `STAGE_CONTAINER_RECEIPT_INVALID` (not the receipt that was
written, a broken sha chain or sequence, or bound to another stage record), `STAGE_CONTAINER_RECEIPT_NOT_TERMINATED` (an entry does not show
exited, removed and absent) and `STAGE_CONTAINER_RECEIPT_COVERAGE` (a registered launch is covered by no receipt, or an entry disagrees
with the registry's settlement).
"""

import hashlib
import json
import os
from pathlib import Path
import re

from so101_demo.runtime.container_campaign import stage_records
from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
from so101_demo.runtime.parallel_ipc.frames import canonical_json

KIND = 'act_collection_stage_containers_receipt'
_NAME = re.compile(r'containers-receipt-([0-9]{2})-([a-z0-9-]+)\.json')
_ID = re.compile(r'[0-9a-f]{64}')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def document_sha256(document):
    return _sha(canonical_json(document))


def receipt_files(host):
    """`[(sequence, stage, path)]` of the receipts in `host`, in order."""
    found = []
    for path in Path(host).iterdir():
        match = _NAME.fullmatch(path.name)
        if match is not None:
            found.append((int(match.group(1)), match.group(2), path))
    return sorted(found)


def read_receipts(host):
    """Every receipt with its own sha256 added, in order. Refuses a receipt that is not the one written or a broken chain."""
    receipts, previous = [], None
    for index, (number, stage, path) in enumerate(receipt_files(host), start=1):
        raw = path.read_bytes()
        try:
            document = json.loads(raw)
            if (type(document) is not dict or document.get('kind') != KIND or document.get('schema_version') != 1
                    or document.get('stage') != stage or document.get('seq') != number or number != index
                    or raw != canonical_json(document) + b'\n' or type(document.get('containers')) is not list):
                raise ValueError
            link = document.get('previous_receipt')
            if link != (None if previous is None else dict(seq=previous['seq'], sha256=previous['sha256'])):
                raise ValueError
        except ValueError as error:
            raise ValueError('STAGE_CONTAINER_RECEIPT_INVALID') from error
        previous = dict(document, sha256=_sha(raw))
        receipts.append(previous)
    return receipts


def covered_launch_ids(host):
    return {entry['launch_id'] for receipt in read_receipts(host) for entry in receipt['containers']}


def has_receipt(host, stage):
    return any(item[1] == stage for item in receipt_files(host))


def write_receipt(host, *, stage, stage_record_sha256, containers):
    """Write the receipt of a completed stage once, durably, chained to the receipt before it."""
    host = Path(host)
    receipts = read_receipts(host)
    if any(item['stage'] == stage for item in receipts):
        raise ValueError('STAGE_CONTAINER_RECEIPT_ALREADY_WRITTEN')
    number = len(receipts) + 1
    document = dict(schema_version=1, kind=KIND, seq=number, stage=stage, stage_record_sha256=stage_record_sha256,
                    previous_receipt=None if not receipts else dict(seq=receipts[-1]['seq'], sha256=receipts[-1]['sha256']),
                    containers=containers)
    path = host / f'containers-receipt-{number:02d}-{stage}.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical_json(document) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(host, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return dict(document, sha256=_sha(path.read_bytes()))


def container_entry(record, observed):
    """The receipt entry of one container launch, from its registry record and the independent inspection `observed`."""
    launch = record['launch']
    state = observed.get('State') if type(observed) is dict else None
    if (type(state) is not dict or state.get('Status') != 'exited' or state.get('Running') is not False
            or type(state.get('ExitCode')) is not int or type(state.get('FinishedAt')) is not str or not state['FinishedAt']
            or observed.get('Id') != record['owner']['container_id']):
        raise ValueError('STAGE_CONTAINER_RECEIPT_NOT_TERMINATED')
    return dict(launch_id=launch['launch_id'], role=launch['role'], launcher='container', container_name=launch['container_name'],
                container_id=observed['Id'], status='exited', exit_code=state['ExitCode'], finished_at=state['FinishedAt'],
                inspect_sha256=document_sha256(observed), removed=False, absent_after_removal=False)


def native_entry(record):
    return dict(launch_id=record['launch']['launch_id'], role=record['launch']['role'], launcher='native', container_name=None,
                container_id=None, status=None, exit_code=None, finished_at=None,
                inspect_sha256=document_sha256(record['exit_inspect']), removed=None, absent_after_removal=None)


def _entry_terminated(entry):
    if type(entry) is not dict or entry.get('launcher') not in ('container', 'native') or type(entry.get('launch_id')) is not str:
        return False
    if entry['launcher'] == 'native':
        return entry.get('removed') is None and type(entry.get('inspect_sha256')) is str
    return (entry.get('status') == 'exited' and type(entry.get('exit_code')) is int and type(entry.get('finished_at')) is str
            and bool(entry['finished_at']) and type(entry.get('container_id')) is str
            and _ID.fullmatch(entry['container_id']) is not None
            and entry.get('removed') is True and entry.get('absent_after_removal') is True)


def _agrees(entry, record):
    """The entry is about the registered launch and states what the registry's stored settlement states."""
    launch, settled = record['launch'], record['exit_inspect']
    if entry['launcher'] != launch.get('launcher', 'container'):
        return False
    if entry['launcher'] == 'native':
        return entry['inspect_sha256'] == document_sha256(settled)
    state = settled.get('State', {}) if type(settled) is dict else {}
    return (entry['container_id'] == record['owner']['container_id'] == settled.get('Id')
            and entry['container_name'] == launch['container_name'] and entry['exit_code'] == state.get('ExitCode')
            and entry['finished_at'] == state.get('FinishedAt'))


def verify_receipts(host, last_record, registry_records):
    """The termination of every container started before the stage that continues from `last_record`, from the stored receipts alone.

    `registry_records` are `ContainerLaunchRegistry.records()` as they stand before that stage starts anything."""
    host = Path(host)
    receipts = read_receipts(host)
    stages, link = [], last_record
    while link is not None:
        stages.append(link)
        link = None if link['previous'] is None else stage_records.read_record(host, link['previous']['stage'])
    by_stage = {item['stage']: item for item in receipts}
    for record in stages:
        receipt = by_stage.get(record['stage'])
        if receipt is None:
            raise ValueError('STAGE_CONTAINER_RECEIPT_MISSING')
        if receipt['stage_record_sha256'] != record['sha256']:
            raise ValueError('STAGE_CONTAINER_RECEIPT_INVALID')
    entries = {}
    for receipt in receipts:
        for entry in receipt['containers']:
            if not _entry_terminated(entry):
                raise ValueError('STAGE_CONTAINER_RECEIPT_NOT_TERMINATED')
            if entry['launch_id'] in entries:
                raise ValueError('STAGE_CONTAINER_RECEIPT_COVERAGE')
            entries[entry['launch_id']] = entry
    for record in registry_records:
        entry = entries.get(record['launch']['launch_id'])
        if entry is None or record['owner'] is None or record['exit_inspect'] is None or not _agrees(entry, record):
            raise ValueError('STAGE_CONTAINER_RECEIPT_COVERAGE')
    return receipts


def covered_launches(host, registry_records):
    """The launch ids whose termination the receipts prove (every entry terminated, removed and agreeing with the registry's settlement).

    Raises `STAGE_CONTAINER_RECEIPT_*` for a receipt chain or entry that does not hold. A run without receipts covers nothing."""
    receipts = read_receipts(Path(host))
    by_launch = {record['launch']['launch_id']: record for record in registry_records}
    covered = set()
    for receipt in receipts:
        for entry in receipt['containers']:
            if not _entry_terminated(entry):
                raise ValueError('STAGE_CONTAINER_RECEIPT_NOT_TERMINATED')
            record = by_launch.get(entry['launch_id'])
            if (record is None or record['owner'] is None or record['exit_inspect'] is None or not _agrees(entry, record)
                    or entry['launch_id'] in covered):
                raise ValueError('STAGE_CONTAINER_RECEIPT_COVERAGE')
            covered.add(entry['launch_id'])
    return covered


def verify_for_admission(host, last_record):
    """`verify_receipts` against the run's launch registry, opened read-only (the CLI refuses before it takes any resource)."""
    registry = ContainerLaunchRegistry(Path(host) / 'launches.sqlite3', create=False, read_only=True)
    try:
        return verify_receipts(host, last_record, registry.records())
    finally:
        registry.close()

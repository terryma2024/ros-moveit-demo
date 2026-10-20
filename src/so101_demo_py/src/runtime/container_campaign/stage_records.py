"""The stage completion records of a campaign run collected stage by stage.

A run is phase 1 (`act_collect_parallel --stop-after-phase1`), phase 2, up to three retry rounds, and the finalize. Each stage leaves one
record under `host/`, written last and durably. A record names the previous record by name and sha256, so a stage starts only
from the exact record the earlier stage left; the logic document the run is bound to is in every record and may not change.

    host/phase1-complete.json  <- host/phase2-complete.json  <- host/retry-1-complete.json  ...  <- host/finalize-complete.json

The runtime values a stage used are written beside its record (`runtime-used-<stage>.json`) and are never compared.
"""

import hashlib
import json
import os
from pathlib import Path

from so101_demo.runtime.parallel_ipc.frames import canonical_json

KIND = 'act_collection_stage_complete'
PHASE1, PHASE2, FINALIZE = 'phase1', 'phase2', 'finalize'
MAX_RETRY_ROUNDS = 3


def retry_stage(number):
    return f'retry-{number}'


def record_path(host, stage):
    return Path(host) / f'{stage}-complete.json'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def previous_stage(stage):
    """The stage a stage continues from; phase 1 continues from nothing."""
    if stage == PHASE1:
        return None
    if stage == PHASE2:
        return PHASE1
    if stage == FINALIZE:
        return None                       # decided by the run: the last completed of phase 2 / the retry rounds
    number = int(stage.removeprefix('retry-'))
    return PHASE2 if number == 1 else retry_stage(number - 1)


def write_record(host, stage, body, *, previous=None):
    """Write the record of `stage` once. `previous` is the record this stage continued from, as returned by `read_record`."""
    document = dict(schema_version=1, kind=KIND, stage=stage, **body)
    document['previous'] = None if previous is None else dict(stage=previous['stage'], sha256=previous['sha256'])
    path = record_path(host, stage)
    if path.exists():
        raise ValueError('STAGE_ALREADY_COMPLETE')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(canonical_json(document) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return dict(document, sha256=_sha(path.read_bytes()))


def read_record(host, stage):
    """The record of `stage` with its own sha256 added; `STAGE_PREVIOUS_RECORD_MISSING` when there is none, `..._INVALID` when it is not one."""
    path = record_path(host, stage)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as error:
        raise ValueError('STAGE_PREVIOUS_RECORD_MISSING') from error
    try:
        document = json.loads(raw)
        if (type(document) is not dict or document.get('kind') != KIND or document.get('schema_version') != 1
                or document.get('stage') != stage or raw != canonical_json({k: v for k, v in document.items()}) + b'\n'):
            raise ValueError
    except ValueError as error:
        raise ValueError('STAGE_PREVIOUS_RECORD_INVALID') from error
    return dict(document, sha256=_sha(raw))


def require_previous(host, stage, *, logic):
    """The verified record a stage continues from. Refuses a missing or altered record, a changed logic document, or a stage already done.

    `logic` is the {path, sha256} of the campaign config the stage was started with: it must be the one every record names."""
    if record_path(host, stage).exists():
        raise ValueError('STAGE_ALREADY_COMPLETE')
    name = previous_stage(stage)
    if name is None:
        raise ValueError('STAGE_PREVIOUS_RECORD_MISSING')
    previous = read_record(host, name)
    if previous.get('campaign_config', {}).get('sha256') != logic.get('sha256'):
        raise ValueError('STAGE_LOGIC_DOCUMENT_CHANGED')
    link = previous
    while link['previous'] is not None:                      # every earlier record is the one its successor names
        earlier = read_record(host, link['previous']['stage'])
        if earlier['sha256'] != link['previous']['sha256']:
            raise ValueError('STAGE_PREVIOUS_RECORD_INVALID')
        link = earlier
    return previous


def last_completed(host):
    """The latest stage record of the run in order phase1, phase2, retry-1.., or None."""
    order = [PHASE1, PHASE2, *(retry_stage(number) for number in range(1, MAX_RETRY_ROUNDS + 1))]
    done = [stage for stage in order if record_path(host, stage).exists()]
    return None if not done else read_record(host, done[-1])

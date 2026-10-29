"""The stage completion records of a campaign run collected stage by stage.

A run is phase 1 (`act_collect_parallel --stop-after-phase1`), phase 2, up to three retry rounds, and the finalize. Each stage leaves one
record under `host/`, written last and durably. A record names the previous record by name and sha256, so a stage starts only
from the exact record the earlier stage left; the logic document the run is bound to is in every record and may not change.

    host/phase1-complete.json  <- host/phase2-complete.json  <- host/retry-1-complete.json  ...  <- host/finalize-complete.json

The runtime values a stage used are written beside its record (`runtime-used-<stage>.json`) and are never compared.

Attempts. A stage that failed after admission but proved its containers stopped may be run again as a new attempt (`next_attempt`).
Attempt 1 keeps the plain names. Attempt N >= 2 writes its once-only artefacts under an `.aN` name (`runtime-used-<stage>.aN.json`,
`campaign-cleanup-<stage>.aN.json`, `retry-round-N.aK.json`), its Teacher carries `-aN` in every name it owns, and its command id is
`collection-<campaign>-<stage>.aN`. Every earlier attempt's artefacts stay where they are. The completion record is still written once;
for N >= 2 it carries `attempt`, which is how a reader finds the artefacts of the attempt that completed (absent means 1).
"""

import hashlib
import json
import os
from pathlib import Path
import re

from so101_demo.runtime.parallel_ipc.frames import canonical_json

KIND = 'act_collection_stage_complete'
PHASE1, PHASE2, FINALIZE = 'phase1', 'phase2', 'finalize'
MAX_RETRY_ROUNDS = 3
MAX_ATTEMPTS = 5


def attempt_suffix(attempt):
    """The file-name suffix of an attempt: none for the first, `.aN` after."""
    if type(attempt) is not int or not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError('STAGE_ATTEMPT_INVALID')
    return '' if attempt == 1 else f'.a{attempt}'


def attempt_tag(stage, attempt):
    """The name a stage attempt carries in container, launch and receipt names (no dot): `retry-1`, `retry-1-a2`."""
    attempt_suffix(attempt)
    return stage if attempt == 1 else f'{stage}-a{attempt}'


def failed_attempt_tag(stage, attempt):
    """The receipt name of the containers a failed attempt left: always carries the attempt (`retry-1-a1`), so it never collides with the
    receipt of the attempt that completes the stage."""
    attempt_suffix(attempt)
    return f'{stage}-a{attempt}'


def runtime_used_path(host, stage, attempt=1):
    return Path(host) / f'runtime-used-{stage}{attempt_suffix(attempt)}.json'


def cleanup_path(host, stage, attempt=1):
    return Path(host) / f'campaign-cleanup-{stage}{attempt_suffix(attempt)}.json'


def retry_decision_path(host, number, attempt=1):
    return Path(host) / f'retry-round-{number}{attempt_suffix(attempt)}.json'


def record_attempt(record):
    """The attempt that completed the stage: `attempt` in the record, 1 for a record without it (every run before attempts)."""
    return record.get('attempt', 1)


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


def write_record(host, stage, body, *, previous=None, attempt=1):
    """Write the record of `stage` once. `previous` is the record this stage continued from, as returned by `read_record`.

    `attempt` is stored only when it is above 1, so a first attempt writes the bytes it always wrote."""
    document = dict(schema_version=1, kind=KIND, stage=stage, **body)
    if attempt != 1:
        attempt_suffix(attempt)
        document['attempt'] = attempt
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
    return verify_chain(host, read_record(host, name), logic=logic)


def check_before_admission(host, stage, *, logic):
    """What a stage needs from the records before it takes any resource: the CLI refuses here, the owner checks again.

    A retry round needs its predecessor (`STAGE_PREVIOUS_RECORD_MISSING`, `STAGE_PREVIOUS_RECORD_INVALID`, `STAGE_LOGIC_DOCUMENT_CHANGED`)
    and the finalize the latest record after phase 1; a stage with a record is `STAGE_ALREADY_COMPLETE`."""
    if stage != FINALIZE:
        return require_previous(host, stage, logic=logic)
    if record_path(host, stage).exists():
        raise ValueError('STAGE_ALREADY_COMPLETE')
    last = last_completed(host)
    if last is None or last['stage'] == PHASE1:
        raise ValueError('STAGE_PREVIOUS_RECORD_MISSING')
    return verify_chain(host, last, logic=logic)


def verify_chain(host, record, *, logic):
    """`record` (the latest the run holds) is bound to this logic document and every earlier record is the one its successor names."""
    if record.get('campaign_config', {}).get('sha256') != logic.get('sha256'):
        raise ValueError('STAGE_LOGIC_DOCUMENT_CHANGED')
    link = record
    while link['previous'] is not None:                      # every earlier record is the one its successor names
        earlier = read_record(host, link['previous']['stage'])
        if earlier['sha256'] != link['previous']['sha256']:
            raise ValueError('STAGE_PREVIOUS_RECORD_INVALID')
        link = earlier
    return record


def last_completed(host):
    """The latest stage record of the run in order phase1, phase2, retry-1.., or None."""
    order = [PHASE1, PHASE2, *(retry_stage(number) for number in range(1, MAX_RETRY_ROUNDS + 1))]
    done = [stage for stage in order if record_path(host, stage).exists()]
    return None if not done else read_record(host, done[-1])


_ATTEMPT_FILE = re.compile(r'(?:runtime-used|campaign-cleanup)-(?P<stage>[a-z0-9-]+?)(?:\.a(?P<attempt>[0-9]+))?\.json')


def attempts_started(host, stage):
    """The attempt numbers of `stage` that left a runtime-used or cleanup file in `host`, sorted (the plain name is attempt 1)."""
    found = set()
    for path in Path(host).iterdir():
        match = _ATTEMPT_FILE.fullmatch(path.name)
        if match is not None and match.group('stage') == stage:
            found.add(1 if match.group('attempt') is None else int(match.group('attempt')))
    return sorted(found)


def outputs_left(host, stage):
    """The stage-specific outputs a failed attempt left behind. A stage that already produced them cannot start over."""
    host = Path(host)
    if stage == PHASE2:
        names = [host / 'processing-journal.jsonl', host / 'processing-result.json']
    elif stage == FINALIZE:
        names = [host / 'campaign-result.json', host.parent / 'collection-index.json']
    else:
        number = int(stage.removeprefix('retry-'))
        names = [host / f'retry-{number}', host / f'retry-{number}-waves.json']
    return [path for path in names if path.exists() or path.is_symlink()]


def _attempt_cleanup(host, stage, attempt):
    """The cleanup document of a finished attempt, or None when it left none or one that is not a proof of termination."""
    try:
        document = json.loads(cleanup_path(host, stage, attempt).read_bytes())
    except (OSError, ValueError):
        return None
    if type(document) is not dict or document.get('terminated') is not True:
        return None
    if document.get('shards') or document.get('processors'):
        return None                       # shards or processors were launched: their wave and processing numbers are spent
    return document


def next_attempt(host, stage):
    """The attempt number a stage runs as: 1 when it never ran, else the one after the last, only if every earlier attempt is a proven stop.

    Refuses (nothing is admitted yet) a stage that is complete (`STAGE_ALREADY_COMPLETE`, RUN and ABORTED alike), an earlier attempt
    that left no cleanup record proving its containers stopped (`STAGE_ATTEMPT_PREVIOUS_UNPROVEN`), that launched shards or processors, or
    that left outputs of the stage (`STAGE_ATTEMPT_OUTPUTS_LEFT`), and the sixth attempt (`STAGE_ATTEMPTS_EXCEEDED`)."""
    if record_path(host, stage).exists():
        raise ValueError('STAGE_ALREADY_COMPLETE')
    started = attempts_started(host, stage)
    if not started:
        return 1
    if started != list(range(1, started[-1] + 1)):
        raise ValueError('STAGE_ATTEMPT_PREVIOUS_UNPROVEN')
    for attempt in started:
        if _attempt_cleanup(host, stage, attempt) is None:
            raise ValueError(f'STAGE_ATTEMPT_PREVIOUS_UNPROVEN: attempt {attempt} of {stage} has no cleanup record proving a stop')
    left = outputs_left(host, stage)
    if left:
        raise ValueError('STAGE_ATTEMPT_OUTPUTS_LEFT: ' + ', '.join(path.name for path in left))
    if started[-1] >= MAX_ATTEMPTS:
        raise ValueError('STAGE_ATTEMPTS_EXCEEDED')
    return started[-1] + 1

"""Original collection clocks retained by the sole audit writer; no command authority."""

import base64
import hashlib
import json

from .contracts import fields, finite, identifier, integer, sha256, vector
from .native_endpoints import validate_source_clock

#: the stages every collection retains, once each: QC and the formal audit coverage both require exactly these
COLLECTION_BOUNDARY_STAGES = ('verified_reset', 'capture_start', 'initial_capture', 'normal_stop', 'final_capture')


def validate_verified_reset(document, *, identity=None):
    """The V3 verified reset: the FIRST evidence of this session and epoch the Recorder itself retained.

    Its clock is the evidence producer's own: the sample's simulation time and the producer's monotonic interval of that
    physics step, never a receipt time. The Recorder runs before the Teacher, so this boundary precedes the capture start and
    the Teacher's first command on both clocks; the Teacher's `reset_complete` event is a later, consistent claim
    (`teacher_collection.validate_reset_complete_matches`). Version 2 (the Teacher's receipt time) is never accepted.
    """
    fields(document, {'kind', 'schema_version', 'session_id', 'attempt_id', 'reset_epoch', 'source_clock',
                      'physical_source'})
    if (document['kind'] != 'ACT_VERIFIED_RESET_BOUNDARY' or type(document['schema_version']) is not int
            or document['schema_version'] != 3):
        raise ValueError('COLLECTION_RESET_VERSION_INVALID')
    for key in ('session_id', 'attempt_id'):
        identifier(document[key])
    integer(document['reset_epoch'], minimum=1)
    clock = validate_source_clock(document['source_clock'])
    physical = document['physical_source']
    fields(physical, {'session_id', 'reset_epoch', 'simulation_step', 'publisher_sequence', 'simulation_time_s',
                      'received_wall_s'})
    if (physical['session_id'] != document['session_id'] or type(physical['reset_epoch']) is not int
            or physical['reset_epoch'] != document['reset_epoch']):
        raise ValueError('COLLECTION_RESET_SOURCE_INVALID')
    integer(physical['simulation_step'])
    integer(physical['publisher_sequence'])
    finite(physical['simulation_time_s'], nonnegative=True)
    if round(physical['simulation_time_s'] * 1e9) != clock['sim_time_ns']:
        raise ValueError('COLLECTION_RESET_SIM_CLOCK_INVALID')
    received = finite(physical['received_wall_s'], nonnegative=True)
    # The producer's interval of that step ends before the Recorder received the evidence. There is no upper bound: the world
    # topic is transient-local, so a record the Recorder received when it joined may be seconds older than its receipt (L2
    # 6062afd8 refused the replayed records at 0.5 s and started the capture 8 s late). The receipt is metadata only.
    if received - clock['end_monotonic_ns'] / 1e9 < 0:
        raise ValueError('COLLECTION_RESET_RECEIPT_INVALID')
    if identity is not None and any(document[key] != identity[key]
            for key in ('session_id', 'attempt_id', 'reset_epoch')):
        raise ValueError('COLLECTION_RESET_SCOPE_INVALID')
    return document


def validate_collection_boundary(document, *, identity=None):
    fields(document, {'kind', 'schema_version', 'stage', 'value'})
    if (document['kind'] != 'ACT_COLLECTION_BOUNDARY' or type(document['schema_version']) is not int
            or document['schema_version'] != 2):
        raise ValueError('COLLECTION_BOUNDARY_VERSION_INVALID')
    if document['stage'] == 'verified_reset':
        validate_verified_reset(document['value'], identity=identity)
    elif document['stage'] == 'capture_start':
        validate_source_clock(document['value'])
    elif document['stage'] == 'normal_stop':
        from .native_endpoints import validate_normal_stop_boundary
        validate_normal_stop_boundary(document['value'], identity=identity if identity is not None else dict(
            session_id=document['value']['epoch']['session_id'], reset_epoch=document['value']['epoch']['reset_epoch']))
    elif document['stage'] in ('initial_capture','final_capture'):
        from .native_endpoints import validate_world_source
        value=document['value']
        fields(value,{'source_clock','world_source'})
        clock=validate_source_clock(value['source_clock'])
        source=value['world_source']
        scope=identity if identity is not None else dict(session_id=source['physics']['simulation_session_id'],
            reset_epoch=source['physics']['reset_epoch'])
        world=validate_world_source(source,identity=scope)
        if (not 0<=clock['sim_time_ns']-round(world.simulation_time_s*1e9)<=100_000_000
                or clock['begin_monotonic_ns']<max(source['received_monotonic_ns'],source['scene_received_monotonic_ns'])):
            raise ValueError('COLLECTION_ENDPOINT_CAPTURE_CLOCK_INVALID')
    else:
        raise ValueError('COLLECTION_BOUNDARY_STAGE_INVALID')
    return document


def boundary_clock(document):
    if document['stage'] in ('verified_reset', 'initial_capture', 'final_capture', 'normal_stop'):
        return document['value']['source_clock']
    return document['value']


def world_source_digest(source):
    from .scene_association import canonical
    return hashlib.sha256(canonical(source)).hexdigest()


def claim_collection_boundary(event, *, identity, seen, world_hashes=None):
    document = validate_collection_boundary(event['payload']['collection_boundary'], identity=identity)
    clock = boundary_clock(document)
    if (event['sim_time_s'] != clock['sim_time_ns'] / 1e9
            or event['monotonic_ns'] < clock['end_monotonic_ns']):
        raise ValueError('COLLECTION_BOUNDARY_EVENT_CLOCK_INVALID')
    if document['stage'] in seen:
        raise ValueError('COLLECTION_BOUNDARY_REPEATED')
    if document['stage'] in ('initial_capture','final_capture'):
        source=document['value']['world_source']
        if (world_hashes is None or world_hashes.get(source['physics']['publisher_sequence'])
                !=world_source_digest(source)):
            raise ValueError('COLLECTION_ENDPOINT_ORIGINAL_REQUIRED')
    seen.add(document['stage'])
    return document

"""Offline validation of native paired camera originals for Head campaigns.

This module never renders post-integration qpos, invokes a detector or supplies
truth to a controller. ROS imports occur only when decoding declared originals.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_FIXTURE_FIELDS = {'schema_version', 'case_id', 'seed', 'condition_class', 'anchor',
                   'scene_sha256', 'reset_free_bodies', 'lighting', 'truth_manifest', 'injection'}
_TRUTH_FIELDS = {'model_sha256', 'render_config_sha256', 'camera_name', 'capture_identity',
                 'simulation_session_id', 'reset_epoch', 'width', 'height', 'frame_id',
                 'qpos_count', 'qvel_count', 'instances'}


def _require(condition, reason):
    if not condition:
        raise ValueError('HEAD_CAMPAIGN_TRUTH_' + reason)


def _read_ref(reference, *, maximum_bytes=64*1024*1024):
    _require(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'REF_SCHEMA')
    declared, digest = reference['path'], reference['sha256']
    _require(type(declared) is str and type(digest) is str and _SHA.fullmatch(digest), 'REF_IDENTITY')
    path = Path(declared)
    _require(path.is_absolute() and '..' not in path.parts, 'REF_PATH')
    _require(not any(part.is_symlink() for part in (path, *path.parents)), 'REF_SYMLINK')
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum_bytes, 'REF_SIZE')
            raw = stream.read(maximum_bytes+1)
    except OSError as error:
        raise ValueError('HEAD_CAMPAIGN_TRUTH_REF_UNREADABLE') from error
    _require(len(raw) <= maximum_bytes and hashlib.sha256(raw).hexdigest() == digest, 'REF_SHA')
    return raw


def _json_ref(reference):
    try:
        return json.loads(_read_ref(reference, maximum_bytes=1024*1024))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('HEAD_CAMPAIGN_TRUTH_JSON') from error


def _source_ns(header):
    return header.stamp.sec*1_000_000_000 + header.stamp.nanosec


def _positive_int(value):
    return type(value) is int and value > 0


def validate_native_reference(envelope, expected=None):
    """Validate V2's initial-only reference while retaining the outer original.

    This checks transport structure. The initial condition builder separately
    verifies compiled light coefficients and visible/amodal cup evidence.
    """
    from sensor_msgs.msg import Image
    frame=envelope.original
    _require(envelope.schema_version==2 and envelope.reference_kind in (0,1,2),'V2_SCHEMA')
    first=frame.record_type==frame.FRAME and frame.frame_sequence==1
    kind=envelope.reference_kind
    if not first or kind==0:
        _require(kind==0 and envelope.reference==Image() and
            not envelope.scene_light_model_ids and not envelope.hidden_geom_ids and
            not envelope.reference_light_diffuse and not envelope.reference_light_specular and
            not envelope.frozen_cameras and not envelope.scene_restored and
            envelope.initial_render_elapsed_ns==0,'V2_REFERENCE_EMPTY')
        if first and expected is not None:
            _require(expected['kind']=='none','V2_REFERENCE_MISSING')
        return
    image=envelope.reference
    channels=3 if kind==1 else 8
    _require(image.header==frame.rgb.header and image.width==frame.rgb.width and
        image.height==frame.rgb.height and image.encoding==('rgb8' if kind==1 else '32SC2') and
        not image.is_bigendian and image.step==image.width*channels and
        len(image.data)==image.width*image.height*channels and image.width>0 and image.height>0,
        'V2_REFERENCE_LAYOUT')
    _require(envelope.scene_restored and 0<envelope.initial_render_elapsed_ns<100000000 and
        len(envelope.frozen_cameras)==32 and all(math.isfinite(x) for x in envelope.frozen_cameras),
        'V2_REFERENCE_FROZEN_SCENE')
    lights=list(envelope.scene_light_model_ids)
    _require(len(lights)<=100 and len(lights)==len(set(lights)) and
        all(-1<=x<100 for x in lights),'V2_REFERENCE_LIGHT_MAP')
    if kind==1:
        diffuse=list(envelope.reference_light_diffuse);specular=list(envelope.reference_light_specular)
        _require(not envelope.hidden_geom_ids and 0<len(diffuse)==len(specular)<=300 and
            len(diffuse)%3==0 and all(math.isfinite(x) and x>=0 for x in diffuse+specular),
            'V2_REFERENCE_LIGHT_COEFFICIENTS')
    else:
        hidden=list(envelope.hidden_geom_ids)
        _require(not envelope.reference_light_diffuse and not envelope.reference_light_specular and
            0<len(hidden)<=2000 and len(hidden)==len(set(hidden)) and all(x>=0 for x in hidden),
            'V2_REFERENCE_OCCLUDERS')
        allowed=set(zip(frame.object_ids,frame.object_types))|{(-1,-1)}
        _require(all(pixel in allowed for pixel in struct.iter_unpack('<ii',bytes(image.data))),
                 'V2_REFERENCE_UNMAPPED_PIXEL')
    if expected is not None:
        _require(expected['kind']==('normal_light' if kind==1 else 'amodal_cup') and
            list(envelope.hidden_geom_ids)==expected['hidden_geom_ids'] and
            list(envelope.reference_light_diffuse)==expected['baseline_diffuse'] and
            list(envelope.reference_light_specular)==expected['baseline_specular'],
            'V2_REFERENCE_CONFIG_CONFLICT')


def _physics_join(state_refs, truth, source_ns):
    from rclpy.serialization import deserialize_message
    from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
    _require(type(state_refs) is list and state_refs, 'PHYSICS_MISSING')
    previous_chunk = previous_step = None
    matches = []
    for reference in state_refs:
        try:
            chunk = deserialize_message(_read_ref(reference), PhysicsStepEvidenceChunk)
        except Exception as error:
            raise ValueError('HEAD_CAMPAIGN_TRUTH_PHYSICS_DECODE') from error
        _require(not chunk.evidence_loss and chunk.failed_publish_attempts == 0, 'PHYSICS_LOSS')
        _require(chunk.simulation_session_id == truth['simulation_session_id'] and
                 chunk.reset_epoch == truth['reset_epoch'], 'PHYSICS_IDENTITY')
        _require(previous_chunk is None or chunk.chunk_sequence == previous_chunk+1, 'CHUNK_GAP')
        previous_chunk = chunk.chunk_sequence
        _require(bool(chunk.samples), 'CHUNK_EMPTY')
        _require(chunk.first_physics_step == chunk.samples[0].physics_step and
                 chunk.last_physics_step == chunk.samples[-1].physics_step and
                 chunk.first_simulation_time_s == chunk.samples[0].simulation_time_s and
                 chunk.last_simulation_time_s == chunk.samples[-1].simulation_time_s, 'CHUNK_BOUNDS')
        for sample in chunk.samples:
            _require(sample.simulation_session_id == truth['simulation_session_id'] and
                     sample.reset_epoch == truth['reset_epoch'], 'SAMPLE_IDENTITY')
            _require(sample.physics_step > 0 and
                     (previous_step is None or sample.physics_step == previous_step+1), 'STEP_GAP')
            previous_step = sample.physics_step
            _require(math.isfinite(sample.simulation_time_s) and sample.simulation_time_s >= 0 and
                     len(sample.model_qpos) == truth['qpos_count'] and
                     len(sample.model_qvel) == truth['qvel_count'] and
                     all(math.isfinite(v) for v in (*sample.model_qpos, *sample.model_qvel)), 'FULL_STATE')
            # Native camera uses llround, never Python's ties-to-even round.
            if math.floor(sample.simulation_time_s*1e9+.5) == source_ns:
                matches.append(dict(physics_step=sample.physics_step, state_ref=dict(reference)))
    _require(len(matches) == 1, 'EXACT_STATE_NOT_UNIQUE')
    return matches[0]


def _new_output(path):
    root = Path(path)
    _require(root.is_absolute() and '..' not in root.parts and not root.exists() and
             not root.is_symlink() and not any(p.is_symlink() for p in root.parents), 'OUTPUT_COLLISION')
    return root


def _write_new(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}


def _validated_paired_original(doc, truth, reference_expected=None):
    keys = {'schema_version', 'kind', 'cdr', 'production_rgb', 'production_info',
            'received_utc_ns', 'received_monotonic_ns'}
    _require(type(doc) is dict and set(doc) == keys and type(doc['schema_version']) is int and
             doc['schema_version']==2 and doc['kind']=='paired_camera_truth_original' and
             _positive_int(doc['received_utc_ns']) and _positive_int(doc['received_monotonic_ns']), 'FRAME_SCHEMA')
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image, CameraInfo
    try:
        from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
        envelope=deserialize_message(_read_ref(doc['cdr']),CameraTruthFrameV2)
        frame=envelope.original
        validate_native_reference(envelope,reference_expected)
    except Exception as error:
        raise ValueError('HEAD_CAMPAIGN_TRUTH_FRAME_DECODE') from error
    _require(frame.schema_version == 1 and frame.record_type == frame.FRAME and
             frame.frame_sequence > 0 and not frame.loss_latched and frame.dropped_count == 0,
             'FRAME_WATERMARK')
    _require(1 <= frame.enqueued_count <= frame.generated_count and
             frame.frame_sequence <= frame.last_enqueued_sequence <= frame.generated_count and
             frame.published_count == frame.last_published_sequence == frame.frame_sequence-1 and
             frame.last_dropped_sequence == 0, 'FRAME_COUNTS')
    for key in ('model_sha256','render_config_sha256','capture_identity','camera_name'):
        _require(getattr(frame,key) == truth[key], 'FRAME_' + key.upper())
    _require(frame.render_phase == 'frozen_mjv_scene_after_original_rgb', 'RENDER_PHASE')
    rgb, info, instances = frame.rgb, frame.camera_info, frame.instances
    try:
        production_rgb = deserialize_message(_read_ref(doc['production_rgb']), Image)
        production_info = deserialize_message(_read_ref(doc['production_info']), CameraInfo)
    except Exception as error:
        raise ValueError('HEAD_CAMPAIGN_TRUTH_PRODUCTION_DECODE') from error
    # CDR alignment padding is not message content and is not stable on a new
    # serialization. Retain each original CDR SHA; compare every decoded field
    # plus the actual image bytes without reserializing either original.
    _require(rgb == production_rgb and bytes(rgb.data) == bytes(production_rgb.data) and
             info == production_info, 'PRODUCTION_BYTES')
    _require(rgb.header == info.header == instances.header and
             rgb.header.frame_id == truth['frame_id'] and _source_ns(rgb.header) > 0, 'HEADERS')
    width, height = truth['width'], truth['height']
    for image, encoding, channels in ((rgb,'rgb8',3), (instances,'32SC2',8)):
        _require(image.width == width and image.height == height and
                 image.encoding == encoding and not image.is_bigendian and
                 image.step == width*channels and len(image.data) == width*height*channels, 'IMAGE_LAYOUT')
    _require(info.width == width and info.height == height and
             all(math.isfinite(v) for v in (*info.k,*info.r,*info.p,*info.d)), 'CAMERA_INFO')
    source_ns = _source_ns(rgb.header)
    _require(len(frame.segmentation_ids) == len(frame.object_ids) == len(frame.object_types) <= 2000 and
             len(set(frame.segmentation_ids)) == len(frame.segmentation_ids) and
             all(0 <= v < 2000 for v in frame.segmentation_ids), 'SEGMENTATION_MAP')
    allowed = set(zip(frame.object_ids, frame.object_types)) | {(-1,-1)}
    pixels = list(struct.iter_unpack('<ii', bytes(instances.data)))
    _require(all(pixel in allowed for pixel in pixels), 'UNMAPPED_PIXEL')
    return frame,envelope,pixels


def build_frame_truth(frame_ref, state_refs, fixture_ref, output_root):
    """Validate actual paired CDR, production bytes and exact native identity.

    Refusal creates no output. Successful masks refer to the actual paired
    instance image, with no geometric reconstruction or timestamp interpolation.
    """
    root = _new_output(output_root)
    fixture = _json_ref(fixture_ref)
    _require(type(fixture) is dict and set(fixture) == _FIXTURE_FIELDS and
             type(fixture['schema_version']) is int and fixture['schema_version'] == 1, 'FIXTURE_SCHEMA')
    truth = fixture['truth_manifest']
    _require(type(truth) is dict and set(truth) == _TRUTH_FIELDS, 'TRUTH_SCHEMA')
    _require(all(_positive_int(truth[k]) for k in ('width','height','qpos_count','qvel_count','reset_epoch'))
             and truth['width'] <= 4096 and truth['height'] <= 4096, 'TRUTH_DIMENSIONS')
    _require(all(type(truth[k]) is str and _SHA.fullmatch(truth[k])
                 for k in ('model_sha256','render_config_sha256')), 'TRUTH_DIGESTS')
    doc = _json_ref(frame_ref)
    expected=None
    if fixture['lighting'].get('render_config_ref'):
        render_ref=fixture['lighting']['render_config_ref']
        _require(render_ref['sha256']==truth['render_config_sha256'],'RENDER_CONFIG_SHA')
        expected=_json_ref(render_ref)['initial_reference']
    frame,envelope,pixels=_validated_paired_original(doc,truth,expected)
    source_ns=_source_ns(frame.rgb.header)
    width,height=truth['width'],truth['height']
    state=_physics_join(state_refs,truth,source_ns)
    declaration = truth['instances']
    _require(type(declaration) is list and bool(declaration), 'INSTANCES_MISSING')
    names, geoms, masks = set(), set(), []
    for instance in declaration:
        _require(type(instance) is dict and set(instance) == {'instance_id','kind','geom_ids'}, 'INSTANCE_SCHEMA')
        name, ids = instance['instance_id'], instance['geom_ids']
        _require(type(name) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name) and
                 name not in names and instance['kind'] in ('cup','distractor','support','occluder') and
                 type(ids) is list and bool(ids) and all(type(v) is int and v >= 0 for v in ids) and
                 len(ids) == len(set(ids)) and not (geoms & set(ids)), 'INSTANCE_IDENTITY')
        names.add(name)
        geoms.update(ids)
        mask = bytes(int(kind == 5 and obj in ids) for obj,kind in pixels)
        masks.append((instance,mask))
    result = dict(schema_version=1, status='PASS', source_ns=source_ns, frame_sequence=frame.frame_sequence,
                  simulation_session_id=truth['simulation_session_id'], reset_epoch=truth['reset_epoch'],
                  width=width,height=height, frame_ref=frame_ref, fixture_ref=fixture_ref, exact_state=state,
                  received_utc_ns=doc['received_utc_ns'],received_monotonic_ns=doc['received_monotonic_ns'],
                  instances=[])
    if envelope is not None:
        result.update(original_message_schema_version=2,native_outer_cdr=dict(doc['cdr']))
    root.mkdir(parents=True, exist_ok=False)
    for instance,mask in masks:
        ref = _write_new(root/(instance['instance_id']+'.mask'),mask)
        result['instances'].append(dict(instance_id=instance['instance_id'],kind=instance['kind'],
                                        visible_pixels=sum(mask),mask=ref))
    _write_new(root/'truth.json',json.dumps(result,sort_keys=True,indent=2).encode()+b'\n')
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
    return result


def build_initial_condition_reference(initial_ref, fixture_ref, output_root):
    """Verify a paused reset exposure and its native condition counterfactual.

    Step zero is accepted only here. This result is never a moving-frame mask,
    an actual production image, or admission for a campaign.
    """
    import numpy as np
    from types import SimpleNamespace
    from so101_demo.adapters.act.head_execution_scene import load_scene_safety
    root=_new_output(output_root)
    fixture=_json_ref(fixture_ref)
    _require(type(fixture) is dict and set(fixture)==_FIXTURE_FIELDS and
             type(fixture['schema_version']) is int and fixture['schema_version']==1,'FIXTURE_SCHEMA')
    truth=fixture['truth_manifest']
    _require(type(truth) is dict and set(truth)==_TRUTH_FIELDS,'TRUTH_SCHEMA')
    render_ref=fixture['lighting']['render_config_ref']
    _require(render_ref['sha256']==truth['render_config_sha256'],'RENDER_CONFIG_SHA')
    render=_json_ref(render_ref)
    _require(render.get('truth_schema_version')==2 and render['model_sha256']==truth['model_sha256'],
             'INITIAL_RENDER_CONFIG')
    doc=_json_ref(initial_ref)
    keys={'schema_version','kind','cdr','production_rgb','production_info',
          'received_utc_ns','received_monotonic_ns','reset_original'}
    _require(type(doc) is dict and set(doc)==keys and type(doc['schema_version']) is int and
             doc['schema_version']==2 and doc['kind']=='initial_paired_camera_truth_original',
             'INITIAL_SCHEMA')
    pair={key:value for key,value in doc.items() if key!='reset_original'}
    pair['kind']='paired_camera_truth_original'
    frame,envelope,pixels=_validated_paired_original(pair,truth,render['initial_reference'])
    reset=doc['reset_original']
    _require(type(reset) is dict and reset.get('paused') is True and
        type(reset.get('simulation_step')) is int and reset['simulation_step']==0 and
        frame.frame_sequence==1 and type(reset.get('reset_epoch')) is int and
        reset['reset_epoch']==truth['reset_epoch'] and
        reset.get('simulation_session_id')==truth['simulation_session_id'] and
        reset.get('model_sha256')==truth['model_sha256'],'INITIAL_RESET_IDENTITY')
    source=reset.get('simulation_time_s')
    _require(type(source) in (int,float) and math.isfinite(source) and source>0 and
             math.floor(source*1e9+.5)==_source_ns(frame.rgb.header),'INITIAL_RESET_SOURCE')
    qpos,qvel=reset.get('qpos'),reset.get('qvel')
    _require(type(qpos) is list and type(qvel) is list and len(qpos)==truth['qpos_count'] and
        len(qvel)==truth['qvel_count'] and
        all(type(x) in (int,float) and math.isfinite(x) for x in qpos+qvel) and
        all(abs(x)<=1e-9 for x in qvel),'INITIAL_FULL_STATE')
    scene_refs=fixture['lighting']['scene_safety_refs']
    safety=load_scene_safety(SimpleNamespace(refs=scene_refs))
    model=safety.checker.model
    _require(model.nq==len(qpos) and model.nv==len(qvel) and
        safety.checker.model_sha256==truth['model_sha256'] and
        scene_refs['scene']['sha256']==fixture['scene_sha256']==render['scene_sha256'],'INITIAL_MODEL')
    pose=render['development_pose']
    for name,value in zip(('1','2','3','4','5','6','neck_yaw_joint'),
                          (*pose['arm_rad'],pose['neck_rad']),strict=True):
        _require(abs(qpos[safety.joint_map[name]['qpos']]-value)<=1e-9,'INITIAL_JOINT_POSE')
    _require(set(fixture['reset_free_bodies'])==set(safety.free_body_map),'INITIAL_FREE_BODY_SET')
    for name,row in fixture['reset_free_bodies'].items():
        address=safety.free_body_map[name]['qpos']
        _require(all(abs(a-b)<=1e-9 for a,b in zip(qpos[address:address+7],
            (*row['xyz'],*row['quat_wxyz']),strict=True)),'INITIAL_FREE_BODY_POSE')
    condition=fixture['condition_class']
    kind={'low_light':1,'partial_occlusion':2}.get(condition,0)
    _require(envelope.reference_kind==kind,'INITIAL_CONDITION_KIND')
    result=dict(schema_version=1,status='PASS',condition_class=condition,initial_ready=True,
        condition_applied=True if kind else None,dynamic_truth=False,campaign_admission=False,
        original_message_schema_version=2,native_outer_cdr=dict(doc['cdr']),
        initial_ref=initial_ref,fixture_ref=fixture_ref,render_config_ref=render_ref,
        source_ns=_source_ns(frame.rgb.header),frame_sequence=1,
        simulation_session_id=truth['simulation_session_id'],reset_epoch=truth['reset_epoch'],
        received_utc_ns=doc['received_utc_ns'],received_monotonic_ns=doc['received_monotonic_ns'],
        reference_source='native_counterfactual_from_same_frozen_exposure',
        initial_render_elapsed_ns=envelope.initial_render_elapsed_ns)
    visible=amodal=None
    if kind:
        lights=[int(i) for i in range(model.nlight) if model.light_active[i]]
        if model.vis.headlight.active:lights.append(-1)
        _require(sorted(envelope.scene_light_model_ids)==sorted(lights),'INITIAL_LIGHT_MAPPING')
    if kind==1:
        baseline=render['initial_reference']
        for name,values in [('light_diffuse',baseline['baseline_diffuse']),
                            ('light_specular',baseline['baseline_specular'])]:
            expected=(np.asarray(values,dtype=np.float64)*.35).astype(np.float32)
            _require(np.array_equal(getattr(model,name).ravel(),expected),'INITIAL_LOW_LIGHT_COEFFICIENT')
        _require(fixture['lighting']['scale']==.35 and
            np.array_equal(model.light_ambient.ravel(),render['baseline_light_ambient']),
            'INITIAL_LOW_LIGHT_AMBIENT')
        for name,value in render['baseline_headlight'].items():
            _require(np.array_equal(getattr(model.vis.headlight,name),value),'INITIAL_LOW_LIGHT_HEADLIGHT')
        actual=np.asarray(frame.rgb.data,dtype=np.uint8).reshape(-1,3)
        reference=np.asarray(envelope.reference.data,dtype=np.uint8).reshape(-1,3)
        weights=np.asarray([.2126,.7152,.0722])
        mean=float((actual@weights).mean());normal=float((reference@weights).mean())
        _require(mean<normal,'INITIAL_LOW_LIGHT_LUMINANCE')
        result.update(actual_mean_luminance=mean,reference_mean_luminance=normal)
    elif kind==2:
        primary=[row for row in truth['instances'] if row['instance_id']=='plastic_cup' and row['kind']=='cup']
        _require(len(primary)==1,'INITIAL_PRIMARY_CUP')
        cup_ids=set(primary[0]['geom_ids'])
        occluders={geom for row in truth['instances'] if row['kind']=='occluder' for geom in row['geom_ids']}
        _require(set(envelope.hidden_geom_ids)<=occluders and not (cup_ids&occluders),'INITIAL_OCCLUDER_SCOPE')
        visible=np.asarray([kind==5 and obj in cup_ids for obj,kind in pixels],dtype=np.uint8)
        amodal=np.asarray([kind==5 and obj in cup_ids for obj,kind in
                           struct.iter_unpack('<ii',bytes(envelope.reference.data))],dtype=np.uint8)
        visible_count,amodal_count=int(visible.sum()),int(amodal.sum())
        _require(amodal_count>0 and bool(np.all(visible<=amodal)),'INITIAL_OCCLUSION_SUBSET')
        fraction=1-visible_count/amodal_count
        _require(0<fraction<1,'INITIAL_OCCLUSION_FRACTION')
        result.update(visible_pixels=visible_count,amodal_pixels=amodal_count,occluded_fraction=fraction)
    root.mkdir(parents=True,exist_ok=False)
    if kind:
        result['extracted_reference_payload']=_write_new(root/'reference.pixels',bytes(envelope.reference.data))
        result['extracted_reference_payload_kind']='decoded_bytes_from_retained_outer_CDR'
    if visible is not None:
        result['visible_mask']=_write_new(root/'visible.mask',visible.tobytes())
        result['amodal_mask']=_write_new(root/'amodal.mask',amodal.tobytes())
    _write_new(root/'condition.json',json.dumps(result,sort_keys=True,indent=2,allow_nan=False).encode()+b'\n')
    for directory in (root,root.parent):
        descriptor=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(descriptor)
        finally:os.close(descriptor)
    return result


def attribute_locked_frames(frames, detections):
    """Attribute three original bboxes by pixel centers inside half-open bounds.

    A unique nonzero maximum must name the same actual cup in all three frames.
    Proven conflicting cups/non-cups fail; incomplete originals remain UNKNOWN.
    """
    result=dict(schema_version=1,status='UNKNOWN',instance_id=None,wrong_locks=None,frames=[])
    try:
        _require(type(frames) is list and type(detections) is list and
                 len(frames)==len(detections)==3,'LOCK_FRAME_COUNT')
        previous_source=previous_sequence=0
        identity=None
        assignments=[]
        for frame,detection in zip(frames,detections,strict=True):
            _require(type(frame) is dict and frame.get('status')=='PASS' and
                     type(detection) is dict,'LOCK_INPUT')
            width,height=frame['width'],frame['height']
            source,sequence=frame['source_ns'],frame['frame_sequence']
            _require(_positive_int(width) and _positive_int(height) and max(width,height)<=4096 and
                     _positive_int(source) and _positive_int(sequence) and source>previous_source and
                     sequence>previous_sequence and type(detection.get('source_ns')) is int and
                     detection['source_ns']==source,'LOCK_FRAME_ORDER')
            previous_source,previous_sequence=source,sequence
            actual=(frame['simulation_session_id'],frame['reset_epoch'])
            _require(type(actual[0]) is str and actual[0] and _positive_int(actual[1]) and
                     (identity is None or actual==identity),'LOCK_NATIVE_IDENTITY')
            identity=actual
            bbox=detection.get('bbox_xyxy')
            _require(type(bbox) is list and len(bbox)==4 and
                     all(type(v) in (int,float) and math.isfinite(v) for v in bbox),'LOCK_BBOX')
            x1,y1,x2,y2=bbox
            _require(0<=x1<x2<=width and 0<=y1<y2<=height,'LOCK_BBOX_BOUNDS')
            columns=range(max(0,math.ceil(x1-.5)),min(width,math.ceil(x2-.5)))
            rows=range(max(0,math.ceil(y1-.5)),min(height,math.ceil(y2-.5)))
            counts=[]
            names=set()
            _require(type(frame['instances']) is list and frame['instances'],'LOCK_MASKS')
            for instance in frame['instances']:
                name=instance['instance_id']
                _require(type(name) is str and name and name not in names and
                         instance['kind'] in ('cup','distractor','support','occluder'),'LOCK_INSTANCE')
                names.add(name)
                mask=_read_ref(instance['mask'],maximum_bytes=4096*4096)
                _require(len(mask)==width*height and all(pixel in (0,1) for pixel in mask) and
                         type(instance['visible_pixels']) is int and
                         sum(mask)==instance['visible_pixels'],'LOCK_MASK_LAYOUT')
                intersection=sum(mask[y*width+x] for y in rows for x in columns)
                counts.append((intersection,name,instance['kind']))
            greatest=max(row[0] for row in counts)
            winners=[row for row in counts if row[0]==greatest]
            _require(greatest>0 and len(winners)==1,'LOCK_INTERSECTION_NOT_UNIQUE')
            pixels,name,kind=winners[0]
            assignments.append((name,kind))
            result['frames'].append(dict(source_ns=source,frame_sequence=sequence,
                instance_id=name,kind=kind,intersection_pixels=pixels))
        if len(set(assignments))!=1 or assignments[0][1]!='cup':
            result.update(status='FAIL',wrong_locks=1,reason='LOCK_WRONG_INSTANCE')
        else:
            result.update(status='PASS',instance_id=assignments[0][0],wrong_locks=0,reason=None)
    except (ValueError,KeyError,TypeError,OverflowError) as error:
        result['reason']=str(error)
    return result

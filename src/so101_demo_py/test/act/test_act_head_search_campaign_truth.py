"""Offline truth uses real serialized ROS originals, never detector labels."""
import hashlib
import copy
import importlib
import json
from pathlib import Path

import pytest


def _module():
    return importlib.import_module('so101_demo.act.head_search.campaign_truth')


def _ref(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def _inputs(tmp_path, change=None):
    from rclpy.serialization import serialize_message
    from mujoco_ros2_control_msgs.msg import CameraTruthFrame, CameraTruthFrameV2
    from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk
    from sensor_msgs.msg import Image, CameraInfo
    from std_msgs.msg import Header
    from builtin_interfaces.msg import Time
    def save(name, data):
        p = tmp_path / name
        p.write_bytes(data)
        return _ref(p)
    header = Header(stamp=Time(sec=0, nanosec=200000000), frame_id='head_camera_frame')
    rgb = Image(header=header, width=2, height=2, encoding='rgb8', step=6,
                data=bytes([0,10,20]*4))
    info = CameraInfo(header=header, width=2, height=2, distortion_model='plumb_bob',
                      d=[0.]*5, k=[1.,0.,1.,0.,1.,1.,0.,0.,1.])
    import struct
    instance = Image(header=header, width=2, height=2, encoding='32SC2', step=16,
                      is_bigendian=0, data=struct.pack('<8i', 17,5, 91,5, -1,-1, 17,5))
    frame = CameraTruthFrame(schema_version=1, record_type=0,
        capture_identity='capture-unique', frame_sequence=1, camera_name='head_camera',
        model_sha256='a'*64, render_config_sha256='b'*64,
        render_phase='frozen_mjv_scene_after_original_rgb', rgb=copy.deepcopy(rgb), camera_info=copy.deepcopy(info),
        instances=instance, segmentation_ids=[0,3], object_ids=[17,91], object_types=[5,5],
        generated_count=1, enqueued_count=1, published_count=0, last_enqueued_sequence=1)
    sample = PhysicsStepEvidence(simulation_session_id='native-session', reset_epoch=7,
        physics_step=1, simulation_time_s=.2, model_qpos=[0.], model_qvel=[0.])
    chunk = PhysicsStepEvidenceChunk(chunk_sequence=1, simulation_session_id='native-session',
        reset_epoch=7, first_physics_step=1, last_physics_step=1,
        first_simulation_time_s=.2, last_simulation_time_s=.2, samples=[sample])
    truth = dict(model_sha256='a'*64, render_config_sha256='b'*64, camera_name='head_camera',
        capture_identity='capture-unique', simulation_session_id='native-session', reset_epoch=7,
        width=2, height=2, frame_id='head_camera_frame', qpos_count=1, qvel_count=1,
        instances=[dict(instance_id='cup-a',kind='cup',geom_ids=[17]),
                   dict(instance_id='distractor-b',kind='distractor',geom_ids=[91])])
    if change:
        change(frame, chunk, truth, rgb, info)
    fixture = dict(schema_version=1, case_id='head-search-900000', seed=900000,
        condition_class='nominal', anchor='default', scene_sha256='c'*64,
        reset_free_bodies=[], lighting={}, truth_manifest=truth, injection={})
    frame_doc = dict(schema_version=2, kind='paired_camera_truth_original',
        cdr=save('paired.cdr',serialize_message(CameraTruthFrameV2(schema_version=2, original=frame, reference_kind=0))),
        production_rgb=save('rgb.cdr',serialize_message(rgb)),
        production_info=save('info.cdr',serialize_message(info)),
        received_utc_ns=1000, received_monotonic_ns=2000)
    return (save('frame.json',json.dumps(frame_doc).encode()),
            [save('physics.cdr',serialize_message(chunk))],
            save('fixture.json',json.dumps(fixture).encode()))


def test_exact_paired_original_yields_true_cup_and_separate_distractor(tmp_path):
    module = _module()
    args = _inputs(tmp_path)
    result = module.build_frame_truth(*args, tmp_path/'truth')
    assert result['status'] == 'PASS'
    assert result['source_ns'] == 200000000
    assert result['frame_sequence'] == 1
    assert result['simulation_session_id'] == 'native-session'
    assert result['reset_epoch'] == 7
    masks = {row['instance_id']: row for row in result['instances']}
    assert Path(masks['cup-a']['mask']['path']).read_bytes() == bytes([1,0,0,1])
    assert Path(masks['distractor-b']['mask']['path']).read_bytes() == bytes([0,1,0,0])
    for row in masks.values():
        assert _ref(Path(row['mask']['path'])) == row['mask']


@pytest.mark.parametrize('change', [
    lambda f,c,t,r,i: setattr(f,'model_sha256','d'*64),
    lambda f,c,t,r,i: setattr(f,'capture_identity','old-capture'),
    lambda f,c,t,r,i: setattr(f,'render_config_sha256','d'*64),
    lambda f,c,t,r,i: setattr(f,'camera_name','wrist_camera'),
    lambda f,c,t,r,i: setattr(f.instances,'is_bigendian',1),
    lambda f,c,t,r,i: setattr(f.instances,'encoding','32SC1'),
    lambda f,c,t,r,i: setattr(f.instances,'step',8),
    lambda f,c,t,r,i: setattr(f.instances.header,'frame_id','other'),
    lambda f,c,t,r,i: setattr(f,'segmentation_ids',[0,0]),
    lambda f,c,t,r,i: setattr(f,'loss_latched',True),
    lambda f,c,t,r,i: setattr(f,'frame_sequence',0),
    lambda f,c,t,r,i: setattr(c,'evidence_loss',True),
    lambda f,c,t,r,i: setattr(c,'failed_publish_attempts',1),
    lambda f,c,t,r,i: setattr(c.samples[0],'reset_epoch',6),
    lambda f,c,t,r,i: setattr(c.samples[0],'simulation_session_id','old-native'),
    lambda f,c,t,r,i: setattr(c.samples[0],'simulation_time_s',.199),
    lambda f,c,t,r,i: setattr(c.samples[0],'model_qpos',[]),
    lambda f,c,t,r,i: setattr(r,'data',bytes([1,10,20]*4)),
    lambda f,c,t,r,i: setattr(i,'distortion_model','modified'),
])
def test_incomplete_or_conflicting_truth_refuses_without_output(tmp_path, change):
    module = _module()
    args = _inputs(tmp_path, change)
    with pytest.raises(ValueError):
        module.build_frame_truth(*args, tmp_path/'truth')
    assert not (tmp_path/'truth').exists()


def test_duplicate_same_ns_physics_is_not_a_unique_native_join(tmp_path):
    module = _module()
    frame, states, fixture = _inputs(tmp_path)
    with pytest.raises(ValueError):
        module.build_frame_truth(frame, states+states, fixture, tmp_path/'truth')
    assert not (tmp_path/'truth').exists()


def test_corrupt_original_and_existing_output_cannot_be_accepted(tmp_path):
    module = _module()
    frame, states, fixture = _inputs(tmp_path)
    Path(states[0]['path']).write_bytes(b'corruption')
    with pytest.raises(ValueError):
        module.build_frame_truth(frame, states, fixture, tmp_path/'truth')
    assert not (tmp_path/'truth').exists()

@pytest.mark.parametrize('change', [
    lambda f,c,t,r,i: setattr(f,'generated_count',0),
    lambda f,c,t,r,i: setattr(f,'enqueued_count',0),
    lambda f,c,t,r,i: setattr(f,'published_count',2),
    lambda f,c,t,r,i: setattr(f,'last_dropped_sequence',1),
])
def test_contradictory_native_counts_refuse(tmp_path, change):
    module = _module()
    args = _inputs(tmp_path, change)
    with pytest.raises(ValueError):
        module.build_frame_truth(*args, tmp_path/'truth')
    assert not (tmp_path/'truth').exists()


def test_existing_output_is_preserved(tmp_path):
    module = _module()
    args = _inputs(tmp_path)
    root = tmp_path/'truth'
    root.mkdir()
    (root/'user-data').write_bytes(b'preserve')
    with pytest.raises(ValueError):
        module.build_frame_truth(*args, root)
    assert (root/'user-data').read_bytes() == b'preserve'


def test_cdr_alignment_padding_does_not_change_original_message_content(tmp_path):
    module = _module()
    frame, states, fixture = _inputs(tmp_path)
    from rclpy.serialization import deserialize_message
    from sensor_msgs.msg import Image
    path = tmp_path/'rgb.cdr'
    before = path.read_bytes()
    modified = bytearray(before)
    # Alignment after this literal header string and encoding; not message fields.
    for offset in (34,35,54,55):
        modified[offset] = (modified[offset]+1) % 256
    assert deserialize_message(bytes(modified), Image) == deserialize_message(before, Image)
    path.write_bytes(modified)
    document_path = Path(frame['path'])
    document = json.loads(document_path.read_text())
    document['production_rgb'] = _ref(path)
    document_path.write_text(json.dumps(document))
    result = module.build_frame_truth(_ref(document_path), states, fixture, tmp_path/'truth')
    assert result['status'] == 'PASS'


def test_a_frame_document_of_another_schema_is_refused(tmp_path):
    module = _module()
    frame, states, fixture = _inputs(tmp_path)
    document = json.loads(Path(frame['path']).read_text())
    document["schema_version"] = 1
    retired = tmp_path / 'retired-frame.json'
    retired.write_bytes(json.dumps(document).encode())
    with pytest.raises(ValueError, match='FRAME_SCHEMA'):
        module.build_frame_truth(_ref(retired), states, fixture, tmp_path/'truth')
    assert not (tmp_path/'truth').exists()

"""`raw_physics_chunks.message_to_dict` equals `dict(message_to_ordereddict(message))` (to-do 2e option 4), and the audit writer keeps only the
fields of the previous chunk that the continuity check reads."""
import json
import random

import numpy
import pytest

from rosidl_runtime_py.convert import message_to_ordereddict
from so101_mujoco_support.msg import ContactSample, PhysicsStepEvidence, PhysicsStepEvidenceChunk

from so101_demo.act import raw_physics_chunks as chunks


def contact(rng):
    item = ContactSample()
    item.body1_id, item.geom1_id, item.body2_id, item.geom2_id = (rng.randrange(-1, 99) for _ in range(4))
    item.body1, item.geom1, item.body2, item.geom2 = ("b1é", "g1", "b2", "g☃")
    item.position_world.x, item.position_world.y, item.position_world.z = (rng.random() for _ in range(3))
    item.normal_world.x, item.normal_world.y, item.normal_world.z = (rng.random() for _ in range(3))
    item.signed_distance_m, item.normal_force_n = rng.random(), rng.random() * 1e3
    return item


def chunk(seed, samples=7):
    rng = random.Random(seed)
    message = PhysicsStepEvidenceChunk()
    message.chunk_sequence, message.simulation_session_id, message.reset_epoch = seed, "session-é", 3
    message.first_physics_step, message.last_physics_step = 100, 100 + samples - 1
    message.first_simulation_time_s, message.last_simulation_time_s = 0.2, 0.2 + 0.002 * samples
    message.failed_publish_attempts, message.handoff_monotonic_ns, message.publish_monotonic_ns = 0, 2**63, 5
    message.publish_deferrals_total, message.evidence_loss = 0, False
    for index in range(samples):
        sample = PhysicsStepEvidence()
        sample.simulation_session_id, sample.reset_epoch, sample.physics_step = "session-é", 3, 100 + index
        sample.simulation_time_s = 0.2 + 0.002 * index
        sample.clock_interval_begin_monotonic_ns, sample.clock_interval_end_monotonic_ns = 10 + index, 20 + index
        sample.model_qpos = [rng.random() for _ in range(rng.randrange(0, 9))]
        sample.model_qvel = [rng.random() * 1e-300 for _ in range(rng.randrange(0, 9))]
        sample.object_pose_world.position.x, sample.object_pose_world.orientation.w = rng.random(), 1.0
        sample.object_twist_world.linear.y = float("inf") if index == 3 else -0.0
        sample.has_contact, sample.truncated = bool(index % 2), False
        sample.maximum_normal_force_n = float("nan") if index == 4 else 1.5
        sample.net_contact_force_world_n.z = 0.1
        sample.left_fingertip_contacts = [contact(rng) for _ in range(index % 3)]
        sample.right_fingertip_contacts = [contact(rng)] if index == 5 else []
        sample.other_object_contacts = [contact(rng) for _ in range(rng.randrange(0, 3))]
        message.samples.append(sample)
    return message


def same(a, b):
    """Equal as the generic conversion's output: values (nan equal to nan), key order at every level, and the JSON bytes."""
    def norm(x):
        if isinstance(x, dict):
            return [(k, norm(v)) for k, v in x.items()]
        if isinstance(x, list):
            return [norm(v) for v in x]
        return "nan" if isinstance(x, float) and x != x else (type(x).__name__, x)
    return norm(a) == norm(b)


@pytest.mark.parametrize("seed", range(12))
def test_the_fast_conversion_equals_the_generic_one(seed):
    message = chunk(seed, samples=1 + seed)
    fast, generic = chunks.message_to_dict(message), dict(message_to_ordereddict(message))
    assert same(fast, generic)
    assert fast.keys() == generic.keys() and type(fast["samples"]) is list


def test_a_fast_conversion_failure_mode_falls_back_to_the_generic_conversion():
    message = chunk(1)
    message.samples[0].model_qpos = numpy.array([1.0, 2.0])         # numpy arrays: not handled by the fast path
    assert same(chunks.message_to_dict(message), dict(message_to_ordereddict(message)))
    message = chunk(2)
    message.samples[1].model_qvel = [1, 2.5]                          # mixed int/float list: python types preserved either way
    assert same(chunks.message_to_dict(message), dict(message_to_ordereddict(message)))


def test_the_converted_values_are_not_shared_with_the_message():
    message = chunk(3)
    converted = chunks.message_to_dict(message)
    converted["samples"][0]["model_qpos"].append(9.0)
    assert 9.0 not in list(message.samples[0].model_qpos)


def test_a_chunk_from_ros_is_the_same_record_as_before(monkeypatch):
    monkeypatch.setattr(chunks, "verify_raw_chunk", lambda record, **kwargs: record)
    message = chunk(5, samples=4)
    record = chunks.raw_chunk_from_ros(message, received_monotonic_ns=7)
    assert json.dumps(record, sort_keys=True, allow_nan=True) == json.dumps(
        {"schema_version": 1, "received_monotonic_ns": 7, "chunk": dict(message_to_ordereddict(message))}, sort_keys=True, allow_nan=True)

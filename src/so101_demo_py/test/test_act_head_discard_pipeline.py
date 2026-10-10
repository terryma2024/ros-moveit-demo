"""Real stopped exposure → owned inference thread → search recovery contract."""
from types import SimpleNamespace
import hashlib
import threading
import time

import pytest

from so101_demo.act.head_feedback import FeedbackPolicy
from so101_demo.adapters.act.head_inference_owner import HeadInferenceOwner
from so101_demo.adapters.act.head_live_exposure import HeadLiveExposures
from test_act_head_local_search_loop import loop_driver
from test_act_head_local_stopped_exposure import FakeBuffer
from test_act_search import BOX


def await_row(owner, sequence):
    deadline = time.monotonic() + 2.
    while time.monotonic() < deadline:
        row = owner.next_completed_observation(sequence - 1)
        if row is not None:
            return row
        time.sleep(.001)
    pytest.fail('real inference owner did not finish the observation')


@pytest.mark.parametrize('outcome', ['EXPIRED', 'SHORT_DROP'])
@pytest.mark.parametrize('block_completion_return', [False, True])
def test_real_discard_pipeline_recovers_on_next_admitted_exposure(outcome, block_completion_return):
    c = loop_driver()
    c.port = c.search.port
    payload = bytes(640 * 480 * 3)
    scope = c.state.scope
    c.search.controller.config.update(session_id=scope['session_id'], attempt_id=scope['epoch'])
    c.port.monotonic = lambda: c.clock[0]
    c.port.stop_velocity = .01
    c.port.feedback_policy = FeedbackPolicy.parse(c.policy.feedback_values(),
                                                 simulation_policy=c.policy)

    def snapshot():
        sample = dict(c.port._head_samples[-1])
        return dict(sample=sample, decision=dict(sim_ns=round(c.clock[0] * 1e9),
                    sim_s=c.clock[0], wall_before_s=c.clock[0], wall_after_s=c.clock[0]))

    c.port.original_feedback_snapshot = snapshot
    c.port.feedback_snapshot = lambda: dict(snapshot()['sample'], decision=snapshot()['decision'])
    primary = SimpleNamespace(port=c.port, ready=True, failed=False, retirement_confirmed=True,
        epoch=SimpleNamespace(epoch=scope['epoch'], generation=scope['generation'],
            session_id=scope['session_id'], policy_hash=scope['policy_sha256'], inventory={}),
        observer=SimpleNamespace(camera_frame='head_camera_frame',
            camera_age=c.policy.perception_max_age_s, _simulation_policy=c.policy),
        _simulation_policy=c.policy, dispatch_guard=lambda: True,
        inference_deadline=lambda value: True, fault=lambda *args: c.faults.append(args))

    class Detector:
        calls = 0

        def reset(self):
            pass

        def detect(self, pixels, **scope):
            self.calls += 1
            return [dict(BOX)]

    class Buffer(FakeBuffer):
        def lookup_transform(self, *args):
            tf = super().lookup_transform(*args)
            tf.transform.rotation = SimpleNamespace(x=0., y=2**-.5, z=-2**-.5, w=0.)
            return tf

    detector = Detector()
    owner = HeadInferenceOwner(factory=lambda: dict(runtime=detector, runtime_device='cuda'),
        fault_callback=primary.fault, simulation_policy=c.policy)
    live = None
    published, release_return = threading.Event(), threading.Event()

    def feed_pair(source):
        source_ns = round(source * 1e9)
        live.observe('IMAGE', dict(source_ns=source_ns, wall_s=source, frame_id=live.frame,
            valid=True, width=640, height=480, step=1920, encoding='rgb8', is_bigendian=0,
            payload_bytes=len(payload), payload_sha256=hashlib.sha256(payload).hexdigest()),
            payload=payload)
        live.observe('INFO', dict(source_ns=source_ns, wall_s=source, frame_id=live.frame,
            valid=True, k=[400., 0., 320., 0., 400., 240., 0., 0., 1.], d=[0.] * 5))

    def feed_joints(*sources):
        with c.port._lock:
            for source in sources:
                c.port._head_samples.append(dict(sequence=len(c.port._head_samples) + 1,
                    valid=True, source_ns=round(source * 1e9), wall_s=source,
                    positions=[0.], velocities=[0.]))

    try:
        owner.configuration(timeout_s=2.)
        owner.bind_live(lambda runtime: HeadLiveExposures(port=c.port, buffer=Buffer(),
            detector=runtime, primary=primary, monitor=None, camera_skew_s=.02,
            emit=lambda *args, **kwargs: None), timeout_s=2.)
        live = owner._live
        if block_completion_return:
            original_infer = live.infer

            def blocked_infer(**kwargs):
                result = original_infer(**kwargs)
                if result is not None and result['observation_sequence'] == 1:
                    published.set()
                    if not release_return.wait(2.):
                        raise TimeoutError('test completion-return barrier was not released')
                return result

            live.infer = blocked_infer
        owner.activate_live()
        c.search.owner = owner
        feed_joints(1.)
        assert c.search.tick() is None
        feed_joints(1.01, 1.02, 1.03)
        feed_pair(1.04)
        c.clock[0] = 1.35 if outcome == 'EXPIRED' else 1.05
        feed_joints(c.clock[0])
        if outcome == 'SHORT_DROP':
            # Replace the real pending camera frame at the actual job guard.
            original_guard = live._guard
            replaced = threading.Event()

            def guard(deadline):
                original_guard(deadline)
                if live._stopped_candidate is not None and not replaced.is_set():
                    replaced.set()
                    feed_pair(1.045)

            live._guard = guard
        if block_completion_return:
            assert published.wait(2.)
            before = c.state.search_state
            assert c.search.tick() is None
            assert c.state.search_state == before
            assert c.search.pending_observation_request['observation_sequence'] == 1
            assert c.search.observation_budget['reobservations_total'] == 0
            assert c.faults == [] and c.sent == []
            release_return.set()
        row = await_row(owner, 1)
        assert row['sequence'] is None and row['observation_sequence'] == 1
        assert row['observation_outcome'] == outcome and detector.calls == 0
        before = c.state.search_state
        assert c.search.tick() is None
        assert c.state.search_state == before and c.search.controller.lock_count == 0
        assert c.search.pending_observation_request['observation_sequence'] == 2
        assert c.search.observation_budget['reobservations_total'] == 1
        feed_joints(1.37, 1.38, 1.39)
        feed_pair(1.40)
        c.clock[0] = 1.41
        feed_joints(1.41)
        row = await_row(owner, 2)
        assert row['sequence'] == 1 and row['observation_sequence'] == 2
        assert row['observation_outcome'] == 'VALID' and detector.calls == 1
        assert c.search.tick() is None
        assert c.search.controller.lock_count == 1
        assert c.search.observations[0]['source_ns'] == 1_400_000_000
        assert c.search.tick() is None
        assert c.search.pending_observation_request['observation_sequence'] == 3
        assert c.sent == [] and c.faults == []
    finally:
        release_return.set()
        assert owner.close(timeout_s=2.)['retired'] is True

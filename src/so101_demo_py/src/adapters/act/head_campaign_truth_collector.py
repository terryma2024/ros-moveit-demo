"""Capture native campaign originals through the existing bounded file-v1 writer.

No truth is sent to perception or motion. ROS attachment is optional and owned
by the campaign provider; ordinary Head providers never construct this object.
"""
from __future__ import annotations

import copy
import threading
import time
import math


def create_campaign_truth_collector(*,node,inputs,writer):
    """Attach only the sealed opt-in fixture before its owned stack starts."""
    if ('scenario_fixture' not in inputs.refs
            or inputs.document.get('campaign_truth_enabled', True) is False):
        return None
    if inputs.document.get('event_log_enabled',True) is not True:
        raise ValueError('HEAD_TRUTH_LOGS_REQUIRED')
    import copy
    import json
    import yaml
    from so101_demo.act.head_search.campaign_scene import load_case_fixture
    from so101_demo.act.head_search.campaign_truth import _read_ref
    from .head_execution_scene import load_scene_safety
    safety=load_scene_safety(inputs)
    fixture=load_case_fixture(inputs,safety)
    truth=fixture['truth_manifest']
    if (truth['capture_identity']!=inputs.run['run_id'] or
            truth['simulation_session_id']!=inputs.run['session_id']):
        raise ValueError('HEAD_TRUTH_RUN_IDENTITY_CONFLICT')
    render_ref=fixture['lighting']['render_config_ref']
    render=json.loads(_read_ref(render_ref))
    if (render_ref['sha256']!=truth['render_config_sha256'] or
            render['model_sha256']!=truth['model_sha256'] or
            render['frame_id']!=truth['frame_id']):
        raise ValueError('HEAD_TRUTH_RENDER_CONFIG_CONFLICT')
    plugin=yaml.safe_load(_read_ref(inputs.refs['mujoco_plugin']))
    parameters=plugin['/**']['ros__parameters']
    cameras=parameters['mujoco_plugins']['mujoco_camera_plugin']
    camera=cameras['head_camera']
    required=dict(truth_enabled=True,truth_topic='/head_campaign/paired_truth',
        truth_capture_identity=truth['capture_identity'],truth_model_sha256=truth['model_sha256'],
        truth_render_config_sha256=truth['render_config_sha256'],frame_name=truth['frame_id'])
    if render.get('truth_schema_version')!=2:
        raise ValueError('HEAD_TRUTH_NATIVE_CONFIG_CONFLICT')
    reference=render.get('initial_reference')
    required.update(truth_schema_version=2,truth_reference_kind=reference['kind'],
        truth_baseline_diffuse=reference['baseline_diffuse'],
        truth_baseline_specular=reference['baseline_specular'],
        truth_hidden_geom_ids=reference['hidden_geom_ids'])
    if any(type(camera.get(key)) is not type(value) or camera[key]!=value
           for key,value in required.items()):
        raise ValueError('HEAD_TRUTH_NATIVE_CONFIG_CONFLICT')
    original=copy.deepcopy(cameras)
    for key in required:
        if key.startswith('truth_'):
            original['head_camera'].pop(key)
    if (original!=render['rgb_plugin'] or cameras.get('camera_publish_rate')!=10. or
            parameters.get('physics_step_buffer_capacity',5000)!=render['physics_step_buffer_capacity'] or
            parameters.get('physics_step_chunk_size',5)!=render['physics_step_chunk_size'] or
            parameters.get('physics_step_topic','/so101/simulation/physics_step_chunks')!=render['physics_step_topic']):
        raise ValueError('HEAD_TRUTH_ORIGINAL_CONFIG_CONFLICT')
    recorder=FrameOriginalRecorder(writer=writer,**{key:truth[key] for key in (
        'capture_identity','camera_name','model_sha256','render_config_sha256')},
        expected_native_identity=dict(simulation_session_id=truth['simulation_session_id'],
                                      reset_epoch=truth['reset_epoch']),
        expected_image=dict(width=truth['width'],height=truth['height'],frame_id=truth['frame_id']),
        expected_reference=reference)
    return HeadCampaignTruthCollector(node=node,recorder=recorder,truth_topic=camera['truth_topic'],
        rgb_topic=camera['image_topic'],info_topic=camera['info_topic'],
        physics_topic=render['physics_step_topic'])


class FrameOriginalRecorder:
    """Save actual CDR before validation, then maintain sticky receive watermarks."""

    def __init__(self, *, writer, capture_identity, camera_name, model_sha256,
                 render_config_sha256, expected_native_identity=None, expected_image=None,
                 expected_reference=None):
        from so101_demo.act.head_run_evidence import HeadRunEvidence
        if type(writer) is not HeadRunEvidence:
            raise ValueError('HEAD_TRUTH_WRITER_REQUIRED')
        self.writer = writer
        self.expected = dict(capture_identity=capture_identity, camera_name=camera_name,
                             model_sha256=model_sha256, render_config_sha256=render_config_sha256)
        self.frame_watermark = 0
        self.source_watermark = 0
        self.failure = None
        self.final_received = False
        self.production_watermarks = dict(rgb=0, info=0)
        self.native_identity = None
        self.expected_native_identity = expected_native_identity
        self.expected_image = expected_image
        self.expected_reference=copy.deepcopy(expected_reference)
        self._lock = threading.RLock()
        # Preparation keeps one paired RGB/Info and one latest production pair.
        # These bounded copies are released before activation, never frame history.
        self._first_frame = None
        self._initial_production = {}
        self._initial_started = self._initial_consumed = False
        self._initial_receipt = None

    def _fail(self, reason):
        self.failure = self.failure or reason
        raise ValueError(self.failure)

    def _save(self, kind, message, record, source_ns, received_utc_ns, received_monotonic_ns):
        from rclpy.serialization import serialize_message
        if (type(received_utc_ns) is not int or received_utc_ns <= 0 or
                type(received_monotonic_ns) is not int or received_monotonic_ns <= 0):
            self._fail('HEAD_TRUTH_RECEIPT_INVALID')
        try:
            ref = self.writer.add_artifact(serialize_message(message),
                                           media_type='application/vnd.ros2.cdr', suffix='cdr')
            saved = dict(schema_version=1, **record, cdr_ref=ref,
                         source_ns=source_ns, received_utc_ns=received_utc_ns,
                         received_monotonic_ns=received_monotonic_ns)
            self.writer.append(kind,saved,source_stamp_ns=source_ns,
                               observed_mono_ns=received_monotonic_ns,
                               occurrence_mono_ns=received_monotonic_ns, artifact_refs=[ref])
        except Exception:
            self.failure = self.failure or 'HEAD_TRUTH_ORIGINAL_SAVE_FAILED'
            raise
        return saved

    def bind_reset(self, receipt):
        with self._lock:
            if (self.native_identity is not None or receipt.get('paused') is not True or
                    type(receipt.get('simulation_step')) is not int or receipt['simulation_step'] != 0 or
                    type(receipt.get('reset_epoch')) is not int or receipt['reset_epoch'] <= 0 or
                    not receipt.get('simulation_session_id') or
                    receipt.get('model_sha256') != self.expected['model_sha256'] or
                    self.expected_native_identity is not None and
                    any(receipt.get(key)!=value for key,value in self.expected_native_identity.items())):
                self._fail('HEAD_TRUTH_RESET_IDENTITY_INVALID')
            self.native_identity = dict(simulation_session_id=receipt['simulation_session_id'],
                                        reset_epoch=receipt['reset_epoch'])
            self.writer.append('TRUTH_NATIVE_RESET_BOUND', dict(schema_version=1,**self.native_identity),
                source_stamp_ns=None,observed_mono_ns=time.monotonic_ns(),occurrence_mono_ns=time.monotonic_ns())

    def wait_initial_reset_frame(self, receipt, *, deadline):
        """Require the original paused reset exposure within its existing deadline.

        Only this preparation record may use step-zero state. Later truth still
        requires actual physics chunks, never these initialization coordinates.
        A saver holding the recorder lock cannot extend the caller's budget.
        """
        now=time.monotonic()
        if (type(deadline) not in (int,float) or not math.isfinite(deadline)
                or not 0<deadline-now<=5.):
            raise TimeoutError('HEAD_TRUTH_INITIAL_FRAME_DEADLINE')
        if not self._lock.acquire(timeout=max(0.,deadline-time.monotonic())):
            raise TimeoutError('HEAD_TRUTH_INITIAL_FRAME_SAVER_BUSY')
        try:
            if self._initial_started:
                raise PermissionError('HEAD_TRUTH_INITIAL_FRAME_REUSED')
            self._initial_started=True
            simulation_time=receipt.get('simulation_time_s')
            if (type(simulation_time) not in (int,float) or
                    not math.isfinite(simulation_time) or simulation_time<=0):
                self._fail('HEAD_TRUTH_INITIAL_RESET_TIME_INVALID')
            source_ns=math.floor(simulation_time*1e9+.5)
            self.bind_reset(receipt)
        finally:
            self._lock.release()
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not self._lock.acquire(timeout=max(0.,remaining)):
                raise TimeoutError('HEAD_TRUTH_INITIAL_FRAME_TIMEOUT')
            try:
                if self.failure:
                    raise ValueError(self.failure)
                if self.final_received:
                    self._fail('HEAD_TRUTH_INITIAL_FRAME_AFTER_FINAL')
                first=self._first_frame
                if first is not None:
                    paired,rgb,info=first
                    if paired['frame_sequence']!=1 or paired['source_ns']!=source_ns:
                        self._fail('HEAD_TRUTH_INITIAL_RESET_SOURCE_INVALID')
                    production=self._initial_production
                    if all(channel in production for channel in ('rgb','info')):
                        if any(production[channel][0]['source_ns']>source_ns
                               for channel in ('rgb','info')):
                            self._fail('HEAD_TRUTH_INITIAL_PRODUCTION_MISSING')
                        if all(production[channel][0]['source_ns']==source_ns
                               for channel in ('rgb','info')):
                            if (production['rgb'][1]!=rgb or production['info'][1]!=info):
                                self._fail('HEAD_TRUTH_INITIAL_PRODUCTION_BYTES_INVALID')
                            proof=dict(schema_version=1,ready=True,source_ns=source_ns,
                                frame_sequence=1,reset_original=copy.deepcopy(receipt),
                                paired_original=copy.deepcopy(paired),
                                production_rgb=copy.deepcopy(production['rgb'][0]),
                                production_info=copy.deepcopy(production['info'][0]))
                            occurrence=time.monotonic_ns()
                            self.writer.append('TRUTH_INITIAL_RESET_FRAME',proof,
                                source_stamp_ns=source_ns,observed_mono_ns=occurrence,
                                occurrence_mono_ns=occurrence,
                                artifact_refs=[row['cdr_ref'] for row in
                                    (paired,production['rgb'][0],production['info'][0])])
                            if time.monotonic()>=deadline:
                                raise TimeoutError('HEAD_TRUTH_INITIAL_FRAME_TIMEOUT')
                            self._initial_receipt=proof
                            self._initial_consumed=True
                            self._first_frame=None
                            self._initial_production.clear()
                            return copy.deepcopy(proof)
            finally:
                self._lock.release()
            time.sleep(min(.005,max(0.,deadline-time.monotonic())))

    def record_frame(self, frame, *, received_utc_ns, received_monotonic_ns):
        from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
        original=frame
        if type(frame) is not CameraTruthFrameV2:
            self._fail('HEAD_TRUTH_MESSAGE_TYPE_INVALID')
        extra=dict(message_schema_version=2,reference_kind=frame.reference_kind)
        frame=frame.original
        with self._lock:
            final = frame.record_type == frame.FINAL_WATERMARK
            source = None if final else self._source(frame.rgb)
            counts = dict(generated=frame.generated_count,enqueued=frame.enqueued_count,
                          published=frame.published_count,dropped=frame.dropped_count,
                          last_enqueued=frame.last_enqueued_sequence,
                          last_published=frame.last_published_sequence,
                          last_dropped=frame.last_dropped_sequence,loss=frame.loss_latched)
            saved = self._save('TRUTH_CAMERA_FINAL' if final else 'TRUTH_CAMERA_PAIRED', original,
                dict(frame_sequence=frame.frame_sequence, counts=counts,**extra,
                     **{key:getattr(frame,key) for key in self.expected}),source,
                received_utc_ns,received_monotonic_ns)
            if self.failure:
                raise ValueError(self.failure)
            from so101_demo.act.head_search.campaign_truth import validate_native_reference
            try:validate_native_reference(original,self.expected_reference)
            except ValueError as error:self._fail(str(error))
            if frame.schema_version != 1 or any(getattr(frame,k) != v for k,v in self.expected.items()):
                self._fail('HEAD_TRUTH_FRAME_IDENTITY_INVALID')
            if frame.loss_latched or frame.dropped_count or frame.last_dropped_sequence:
                self._fail('HEAD_TRUTH_FRAME_LOSS')
            if self.final_received:
                self._fail('HEAD_TRUTH_FRAME_AFTER_FINAL')
            if final:
                if not (frame.generated_count == frame.enqueued_count == frame.published_count ==
                        frame.last_enqueued_sequence == frame.last_published_sequence ==
                        frame.frame_sequence == self.frame_watermark):
                    self._fail('HEAD_TRUTH_FINAL_RECEIVER_LOSS')
                self.final_received = True
            else:
                if (frame.record_type != frame.FRAME or frame.frame_sequence != self.frame_watermark+1 or
                        source <= self.source_watermark or frame.rgb.header != frame.camera_info.header or
                        frame.rgb.header != frame.instances.header or
                        frame.render_phase != 'frozen_mjv_scene_after_original_rgb'):
                    self._fail('HEAD_TRUTH_FRAME_ORDER_OR_HEADERS_INVALID')
                if not (1<=frame.enqueued_count<=frame.generated_count and
                        frame.frame_sequence<=frame.last_enqueued_sequence<=frame.generated_count and
                        frame.published_count==frame.last_published_sequence==frame.frame_sequence-1):
                    self._fail('HEAD_TRUTH_FRAME_COUNTS_INVALID')
                width,height=frame.rgb.width,frame.rgb.height
                if not (0<width<=4096 and 0<height<=4096):
                    self._fail('HEAD_TRUTH_FRAME_DIMENSIONS_INVALID')
                for message,encoding,size in ((frame.rgb,'rgb8',3),(frame.instances,'32SC2',8)):
                    if (message.width!=width or message.height!=height or message.encoding!=encoding or
                            message.is_bigendian or message.step!=width*size or
                            len(message.data)!=width*height*size):
                        self._fail('HEAD_TRUTH_FRAME_LAYOUT_INVALID')
                info=frame.camera_info
                if (info.width!=width or info.height!=height or
                        not all(math.isfinite(v) for v in (*info.k,*info.r,*info.p,*info.d))):
                    self._fail('HEAD_TRUTH_FRAME_INFO_INVALID')
                if (self.expected_image is not None and
                        (width!=self.expected_image['width'] or height!=self.expected_image['height'] or
                         frame.rgb.header.frame_id!=self.expected_image['frame_id'])):
                    self._fail('HEAD_TRUTH_FRAME_CAMERA_INVALID')
                if not (len(frame.segmentation_ids)==len(frame.object_ids)==len(frame.object_types)<=2000 and
                        len(set(frame.segmentation_ids))==len(frame.segmentation_ids) and
                        all(0<=value<2000 for value in frame.segmentation_ids)):
                    self._fail('HEAD_TRUTH_FRAME_MAPPING_INVALID')
                self.frame_watermark, self.source_watermark = frame.frame_sequence, source
                if frame.frame_sequence==1 and not self._initial_consumed:
                    self._first_frame=(copy.deepcopy(saved),copy.deepcopy(frame.rgb),
                                       copy.deepcopy(frame.camera_info))
            return saved

    @staticmethod
    def _source(message):
        return message.header.stamp.sec*1_000_000_000 + message.header.stamp.nanosec

    def record_production(self, channel, message, *, received_utc_ns, received_monotonic_ns):
        from sensor_msgs.msg import Image, CameraInfo
        if channel not in ('rgb','info') or type(message) is not (Image if channel == 'rgb' else CameraInfo):
            self._fail('HEAD_TRUTH_PRODUCTION_TYPE_INVALID')
        with self._lock:
            source = self._source(message)
            saved = self._save('TRUTH_CAMERA_PRODUCTION',message,dict(channel=channel),source,
                               received_utc_ns,received_monotonic_ns)
            if source <= self.production_watermarks[channel]:
                self._fail('HEAD_TRUTH_PRODUCTION_ORDER_INVALID')
            self.production_watermarks[channel] = source
            if not self._initial_consumed:
                self._initial_production[channel]=(copy.deepcopy(saved),copy.deepcopy(message))
            return saved

    def record_physics(self, chunk, *, received_utc_ns, received_monotonic_ns):
        from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
        if type(chunk) is not PhysicsStepEvidenceChunk:
            self._fail('HEAD_TRUTH_PHYSICS_TYPE_INVALID')
        with self._lock:
            saved = self._save('TRUTH_PHYSICS_CHUNK', chunk,
                dict(chunk_sequence=chunk.chunk_sequence,simulation_session_id=chunk.simulation_session_id,
                     reset_epoch=chunk.reset_epoch,first_physics_step=chunk.first_physics_step,
                     last_physics_step=chunk.last_physics_step,evidence_loss=chunk.evidence_loss,
                     failed_publish_attempts=chunk.failed_publish_attempts),None,
                received_utc_ns,received_monotonic_ns)
            if chunk.evidence_loss or chunk.failed_publish_attempts:
                self._fail('HEAD_TRUTH_PHYSICS_LOSS')
            if (self.native_identity is not None and any(getattr(chunk,k) != v
                                                        for k,v in self.native_identity.items())):
                self._fail('HEAD_TRUTH_PHYSICS_RESET_CONFLICT')
            return saved

    def receipt(self):
        with self._lock:
            return dict(schema_version=1,frame_watermark=self.frame_watermark,
                source_watermark=self.source_watermark,final_received=self.final_received,
                failure=self.failure,native_identity=self.native_identity,
                initial_reset_frame=copy.deepcopy(self._initial_receipt),
                production_watermarks=dict(self.production_watermarks),
                complete=self.failure is None and self.final_received and self.native_identity is not None
                         and (not self._initial_started or self._initial_consumed))


class HeadCampaignTruthCollector:
    """Four owned subscriptions; retirement does not substitute for native exit."""

    def __init__(self, *, node, recorder, truth_topic,
                 rgb_topic='/head_camera/color', info_topic='/head_camera/camera_info',
                 physics_topic='/so101/simulation/physics_step_chunks'):
        from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
        from sensor_msgs.msg import Image, CameraInfo
        from mujoco_ros2_control_msgs.msg import CameraTruthFrameV2
        frame_type=CameraTruthFrameV2
        from so101_mujoco_support.msg import PhysicsStepEvidenceChunk
        self.node, self.recorder = node, recorder
        self.subscriptions = []
        self._closed = False
        self._closing = False
        self._active_callbacks = 0
        self._callback_condition = threading.Condition()
        qos = QoSProfile(depth=10, history=HistoryPolicy.KEEP_LAST,
                         reliability=ReliabilityPolicy.BEST_EFFORT)
        def callback(operation):
            def capture(message):
                with self._callback_condition:
                    if self._closing:
                        return
                    self._active_callbacks += 1
                utc, monotonic = time.time_ns(), time.monotonic_ns()
                try:
                    operation(message,received_utc_ns=utc,received_monotonic_ns=monotonic)
                except Exception:
                    # The primary writer retains its own fault callback/Stop path.
                    # Refuse truth without letting an optional callback kill the executor.
                    with recorder._lock:
                        recorder.failure = recorder.failure or 'HEAD_TRUTH_CALLBACK_FAILED'
                finally:
                    with self._callback_condition:
                        self._active_callbacks -= 1
                        self._callback_condition.notify_all()
            return capture
        try:
            for cls, topic, operation in (
                (frame_type, truth_topic, recorder.record_frame),
                (Image, rgb_topic, lambda message,**times: recorder.record_production('rgb',message,**times)),
                (CameraInfo, info_topic, lambda message,**times: recorder.record_production('info',message,**times)),
                (PhysicsStepEvidenceChunk,physics_topic,recorder.record_physics)):
                self.subscriptions.append(node.create_subscription(cls,topic,callback(operation),qos))
        except Exception:
            self.close()
            raise

    def collect_frame_state_originals(self):
        return self.recorder.receipt()

    def close(self):
        deadline = time.monotonic()+.05
        with self._callback_condition:
            self._closing = True
            while self._active_callbacks:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    # The saver may hold recorder._lock. Do not wait on its
                    # receipt or destroy subscriptions underneath the callback.
                    return dict(closed=False,failures=['truth_callback_retirement_pending'],truth=None)
                self._callback_condition.wait(remaining)
        if self._closed:
            return dict(closed=not self.subscriptions,truth=self.recorder.receipt())
        failures = []
        for subscription in tuple(self.subscriptions):
            try:
                if self.node.destroy_subscription(subscription) is not True:
                    failures.append('subscription_destroy_unconfirmed')
                else:
                    self.subscriptions.remove(subscription)
            except Exception as error:
                failures.append(type(error).__name__)
        self._closed = not failures
        return dict(closed=not failures,failures=failures,truth=self.recorder.receipt())

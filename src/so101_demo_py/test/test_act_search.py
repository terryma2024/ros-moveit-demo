"""Bounded RGB search must use actual optical rays and fresh scoped evidence."""

import math
import numpy as np
import pytest

from so101_demo.act.bearing import bearing, optical_ray_base
from so101_demo.act.search import HeadSearchController


def config(**changes):
    result = dict(attempt_id="a", session_id="s", search_start_rad=0.,
        horizontal_fov_rad=1.2, coarse_step_rad=.5, search_timeout_s=30.,
        max_age_s=.15, max_skew_s=.02, settle_velocity_rad_s=.01,
        goal_tolerance_rad=.01, center_deadband_px=8., vertical_bounds_px=(100.,400.),
        min_area_px2=100., min_confidence=.7, max_fine_corrections=3,
        max_fine_total_rad=.5, frame_id="head_camera_frame",
        ray_origin_frame_id="head_camera_frame")
    result.update(changes); return result


def evidence(t, q=0., detections=()):
    # Optical +Z points base -Y; pixels are not simulator object positions.
    rotation=np.array([[-1.,0.,0.],[0.,0.,-1.],[0.,-1.,0.]])
    frame=dict(session_id="s", attempt_id="a", sim_time_s=t,
        received_wall_s=t, detections=list(detections), k=(400.,0.,320.,0.,400.,240.,0.,0.,1.),
        distortion=(0.,0.,0.,0.,0.), rotation_optical_to_base=rotation,
        frame_id="head_camera_frame")
    feedback=dict(session_id="s",attempt_id="a",sim_time_s=t, received_wall_s=t,
        neck_yaw_rad=q,neck_velocity_rad_s=0.,safe_observe=True)
    return frame,feedback


BOX = dict(xyxy=(300.,200.,340.,280.), confidence=.9,class_id=0,track_id="cup1")


def test_actual_ray_and_distortion_geometry():
    assert bearing((0.,1.,-1.))==pytest.approx(math.pi/2)
    assert bearing((-1.,0.,0.))==pytest.approx(-math.pi)
    with pytest.raises(ValueError): bearing((0.,0.,-1.))
    f,_=evidence(1.)
    ray=optical_ray_base((320.,240.),f["k"],f["distortion"],f["rotation_optical_to_base"])
    assert bearing(ray)==pytest.approx(-math.pi/2)
    with pytest.raises(ValueError): optical_ray_base((320.,240.),f["k"],f["distortion"],np.zeros((3,3)))


def test_lock_requires_three_fresh_same_target_frames():
    search=HeadSearchController(config())
    for t in (1.,1.1): assert "found" not in search.tick(*evidence(t,detections=(BOX,)),t)
    result=search.tick(*evidence(1.2,detections=(BOX,)),1.2)
    assert result["found"] and result["status"]=="TARGET_LOCKED"
    assert result["bearing_rad"]==pytest.approx(-math.pi/2)
    search.reset(config(attempt_id="new"))
    with pytest.raises(ValueError): search.tick(*evidence(2.,detections=(BOX,)),2.)


def test_ambiguity_invalidates_bearing_and_one_revolution_is_terminal():
    search=HeadSearchController(config())
    other=dict(BOX,track_id="cup2",xyxy=(100.,200.,140.,280.))
    result=search.tick(*evidence(1.,detections=(BOX,other)),1.)
    assert result["status"]=="TARGET_AMBIGUOUS" and result["bearing_rad"] is None
    search=HeadSearchController(config())
    yaw=0.
    for index in range(20):
        result=search.tick(*evidence(1.+index*.1,q=yaw),1.+index*.1)
        if "found" in result: break
        yaw=result["neck_target_rad"]
    assert result["status"]=="TARGET_NOT_FOUND"
    assert yaw==pytest.approx(2*math.pi)


def test_stale_input_stops_and_search_clock_cannot_refresh():
    search=HeadSearchController(config(search_timeout_s=1.))
    f,q=evidence(1.); search.tick(f,q,1.)
    result=search.tick(f,q,1.3)
    assert result["stop"]
    result=search.tick(*evidence(2.),2.)
    assert result["status"]=="SEARCH_TIMEOUT" and result["bearing_rad"] is None
    with pytest.raises(ValueError): HeadSearchController(config(coarse_step_rad=.7))


def test_detector_spatial_identity_and_rgb_shape_filter_are_attempt_scoped():
    from so101_demo.adapters.act.detector import HeadRgbDetector, detect_head
    from so101_demo.core.detection import DetectionCandidate, DetectionBatch
    class Detector:
        boxes=((300.,200.,340.,280.),(290.,267.,390.,340.))
        def detect(self, frame, query):
            return DetectionBatch("candidate", "a"*64, "cpu", 1., 640,480,
                tuple(DetectionCandidate(str(index),"plastic_cup",.95,box,
                    np.ones((480,640),dtype=bool),frame.source_stamp_ns,frame.source_frame_id,640,480)
                    for index,box in enumerate(self.boxes)))
    detector=Detector()
    runtime=HeadRgbDetector(detector,model_id="candidate",weights_sha256="a"*64,
                            tracking_iou=.5,min_bbox_aspect=1.)
    bundle=dict(runtime=runtime,session_id="s",attempt_id="a",source_stamp_ns=1,
                source_frame_id="head_camera_frame")
    pixels=np.zeros((480,640,3),np.uint8)
    first=detect_head(pixels,bundle)
    assert len(first)==1
    bundle["source_stamp_ns"]=2
    second=detect_head(pixels,bundle)
    assert first[0]["track_id"]==second[0]["track_id"]
    detector.boxes=((100.,200.,140.,280.),)
    bundle["source_stamp_ns"]=3
    assert detect_head(pixels,bundle)[0]["track_id"]!=first[0]["track_id"]
    bundle["source_stamp_ns"]=4; bundle["attempt_id"]="new"
    with pytest.raises(ValueError): detect_head(pixels,bundle)
    runtime.reset()
    assert len(detect_head(pixels,bundle))==1
    bundle["depth"]=object()
    with pytest.raises(ValueError): detect_head(pixels,bundle)


def test_head_rgb_boundary_converts_ultralytics_array_channel_order():
    from so101_demo.adapters.act.detector import RgbHeadModel
    class Model:
        names={0:"plastic_cup"}
        def predict(self, *, source, **kwargs):
            assert source[0,0].tolist()==[10,20,250]
            assert kwargs=={"verbose":False}
            return ["real-result"]
    wrapper=RgbHeadModel(Model())
    rgb=np.zeros((480,640,3),np.uint8); rgb[0,0]=[250,20,10]
    assert wrapper.names=={0:"plastic_cup"}
    assert wrapper.predict(source=rgb,verbose=False)==["real-result"]
    assert rgb[0,0].tolist()==[250,20,10]


def adapter_fixture(monkeypatch,*,with_inputs=False,tf_missing=False,stop_confirmed=True):
    from types import SimpleNamespace
    from sensor_msgs.msg import Image,CameraInfo,JointState
    from so101_demo.adapters.act import ros_search
    clock=[10.];calls=[]
    class Node:
        def create_subscription(self,*args):return None
    class Neck:
        def stop_and_confirm(self):calls.append('stop');return stop_confirmed
        def command_neck(self,*args,**kwargs):calls.append('command')
    class TF:
        def lookup_transform(self,*args):
            if tf_missing:raise RuntimeError('transform unavailable')
            return SimpleNamespace(transform=SimpleNamespace(rotation=SimpleNamespace(x=0.,y=0.,z=0.,w=1.)))
    runtime=SimpleNamespace(reset=lambda:None)
    search=HeadSearchController(config(search_timeout_s=1.))
    adapter=ros_search.RosSearchAdapter(Node(),search,runtime,Neck(),tf_buffer=TF(),monotonic=lambda:clock[0])
    adapter.reset(config(search_timeout_s=1.),source_floor_s=0.)
    if with_inputs:
        image=Image(width=640,height=480,step=1920,encoding='rgb8',data=bytes(640*480*3))
        info=CameraInfo(k=[400.,0.,320.,0.,400.,240.,0.,0.,1.],d=[0.]*5)
        joints=JointState(name=['neck_yaw_joint'],position=[0.],velocity=[0.])
        for msg in (image,info,joints):msg.header.stamp.sec=1;msg.header.frame_id='head_camera_frame'
        adapter._image(image);adapter._info(info);adapter._joints(joints)
    monkeypatch.setattr(ros_search,'detect_head',lambda *args:[])
    return adapter,clock,calls,ros_search


@pytest.mark.parametrize('tf_missing',(False,True))
def test_adapter_deadline_runs_without_rgb_or_transform(monkeypatch,tf_missing):
    adapter,clock,calls,_=adapter_fixture(monkeypatch,with_inputs=tf_missing,tf_missing=tf_missing)
    first=adapter.tick(safe_observe=True)
    assert first['stop'] and not 'command' in calls
    clock[0]=11.
    result=adapter.tick(safe_observe=True)
    assert not result['found'] and result['status']=='SEARCH_TIMEOUT' and result['bearing_rad'] is None
    assert adapter.search.started_wall_s==10. and not 'command' in calls


def test_detector_latency_counts_toward_search_deadline(monkeypatch):
    adapter,clock,calls,module=adapter_fixture(monkeypatch,with_inputs=True)
    import threading
    completed=threading.Event()
    def slow_detector(*args):clock[0]+=2.;completed.set();return []
    monkeypatch.setattr(module,'detect_head',slow_detector)
    first=adapter.tick(safe_observe=True)
    assert completed.wait(.5)
    result=first if first.get('status')=='SEARCH_TIMEOUT' else adapter.tick(safe_observe=True)
    assert not result['found'] and result['status']=='SEARCH_TIMEOUT'
    assert not 'command' in calls


def test_search_cannot_return_success_or_command_after_unconfirmed_stop(monkeypatch):
    adapter,clock,calls,_=adapter_fixture(monkeypatch,stop_confirmed=False)
    with pytest.raises(RuntimeError,match='SEARCH_STOP_UNCONFIRMED'):adapter.tick(safe_observe=True)
    assert not 'command' in calls
    assert adapter.search.terminal['found'] is False


def test_hung_head_detector_does_not_block_tick_or_deadline(monkeypatch):
    import threading
    adapter,clock,calls,module=adapter_fixture(monkeypatch,with_inputs=True)
    begun=threading.Event();release=threading.Event();done=threading.Event();returned=[]
    def hung_detector(*args):
        begun.set();assert release.wait(2);return []
    monkeypatch.setattr(module,'detect_head',hung_detector)
    def tick():
        try:returned.append(adapter.tick(safe_observe=True))
        finally:done.set()
    thread=threading.Thread(target=tick);thread.start()
    try:
        assert begun.wait(.5)
        assert done.wait(.2),'RGB inference must not block the monotonic search tick'
        clock[0]=11.
        result=adapter.tick(safe_observe=True)
        assert result['status']=='SEARCH_TIMEOUT' and not result['found']
        assert not 'command' in calls
    finally:release.set();thread.join(2)


@pytest.mark.parametrize('box,sign',(((240.,200.,280.,280.),1),((360.,200.,400.,280.),-1)))
def test_left_right_corrections_use_actual_mounted_axes(box,sign):
    search=HeadSearchController(config())
    detection=dict(BOX,xyxy=box)
    result=search.tick(*evidence(1.,detections=(detection,)),1.)
    assert result['neck_target_rad']*sign>0 and search.fine_count==1


def test_fine_budget_and_lost_target_keep_unspent_coarse_budget():
    search=HeadSearchController(config(max_fine_corrections=1,max_fine_total_rad=.5))
    offcenter=dict(BOX,xyxy=(240.,200.,280.,280.))
    first=search.tick(*evidence(1.,detections=(offcenter,)),1.)
    assert search.coarse_angle==0. and search.fine_count==1
    coarse=search.tick(*evidence(1.1,q=first['neck_target_rad']),1.1)
    assert coarse['neck_target_rad']==.5 and search.coarse_angle==.5
    refused=search.tick(*evidence(1.2,q=.5,detections=(offcenter,)),1.2)
    assert not refused['found'] and refused['status']=='TARGET_NOT_CENTERED'
    assert search.fine_count==1 and search.coarse_angle==.5


def test_neck_scan_crosses_pi_without_restarting_cumulative_budget():
    start=math.pi-.1;search=HeadSearchController(config(search_start_rad=start))
    result=search.tick(*evidence(1.,q=start),1.)
    assert result['neck_target_rad']==pytest.approx(start+.5)
    assert search.coarse_angle==.5
    search.reset(config(search_start_rad=-math.pi+.1,attempt_id='new'))
    assert search.terminal is None and search.coarse_angle==0. and search.started_wall_s is None


def test_reset_during_hung_inference_defers_detector_reset_and_discards_old_job(monkeypatch):
    import threading,time
    adapter,clock,calls,module=adapter_fixture(monkeypatch,with_inputs=True)
    begun=threading.Event();release=threading.Event();reset_calls=[]
    adapter.detector_runtime.reset=lambda:reset_calls.append('reset')
    def detector(*args):begun.set();assert release.wait(2);return [BOX]
    monkeypatch.setattr(module,'detect_head',detector)
    first=adapter.tick(safe_observe=True);assert first['status']=='INPUT_PENDING' and begun.wait(.5)
    old=adapter._pending_detection
    try:
        adapter.reset(config(search_timeout_s=1.,attempt_id='new'),source_floor_s=1.)
        assert reset_calls==[]
        current=adapter.tick(safe_observe=True)
        assert current['status']=='INPUT_PENDING' and not 'command' in calls
        assert adapter._pending_detection is old
    finally:release.set()
    until=time.monotonic()+.5
    while not old['future'].done() and time.monotonic()<until:time.sleep(.001)
    assert old['future'].done()
    current=adapter.tick(safe_observe=True)
    assert current['status']=='INPUT_STALE' and adapter.last_detections_stamp is None
    assert adapter.search.lock_count==0 and reset_calls==['reset'] and adapter._pending_detection is None

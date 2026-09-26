"""Task 6 camera samples remain causal, lossless and unqualified."""

import hashlib
import json
import threading
import time
from types import SimpleNamespace

from PIL import Image as PillowImage
import pytest

from so101_demo.act.joints import ACT_JOINTS
from so101_demo.adapters.act.task6_capture import Task6FrameRecorder


def stamp(value):
    sec = int(value)
    return SimpleNamespace(sec=sec, nanosec=round((value - sec) * 1e9))


def header(value, frame):
    return SimpleNamespace(stamp=stamp(value), frame_id=frame)


def image(value, frame, color):
    raw = bytes(color) * (640 * 480)
    return SimpleNamespace(header=header(value, frame), encoding="rgb8", width=640,
                           height=480, step=1920, data=raw)


def info(value, frame):
    return SimpleNamespace(header=header(value, frame), width=640, height=480,
                           k=[400., 0., 320., 0., 400., 240., 0., 0., 1.],
                           d=[0.] * 5, distortion_model="plumb_bob")


def joints(value):
    return SimpleNamespace(header=header(value, "base"), name=list(ACT_JOINTS),
                           position=[0.] * 7, velocity=[0.] * 7)


def world(value=1., *, epoch=2, session="task6-299", step=500):
    return SimpleNamespace(simulation_time_s=value, simulation_session_id=session,
                           reset_epoch=epoch, simulation_step=step, paused=False,
                           truncated=False,
                           object_state=SimpleNamespace(position_world=(.02, -.28, .165),
                                                        orientation_xyzw=(0., 0., 0., 1.)))


def prepared(tmp_path, *, include_info=True, image_time=.99, joint_time=.985):
    recorder = Task6FrameRecorder(
        tmp_path / "capture", session_id="task6-299", reset_epoch=2,
        source_floor_s=.5, max_age_s=.05, max_skew_s=.03,
    )
    recorder.accept_image("head", image(image_time, "head_camera_frame", (10, 20, 30)))
    recorder.accept_image("wrist", image(image_time, "wrist_camera_frame", (40, 50, 60)))
    if include_info:
        recorder.accept_info("head", info(image_time, "head_camera_frame"))
        recorder.accept_info("wrist", info(image_time, "wrist_camera_frame"))
    recorder.accept_joints(joints(joint_time))
    return recorder


def test_causal_sample_preserves_both_rgb_images_and_joint_provenance(tmp_path):
    recorder = prepared(tmp_path)
    row = recorder.capture(world())
    summary = recorder.finish()
    assert summary["status"] == "RECORDED_UNQUALIFIED"
    assert summary["samples"] == 1
    assert row["simulation_session_id"] == "task6-299"
    assert row["reset_epoch"] == 2 and row["simulation_step"] == 500
    assert row["joint_positions_rad"] == [0.] * 7
    assert row["joint_stamp_s"] == pytest.approx(.985)
    assert row["head"]["image_stamp_s"] == row["head"]["info_stamp_s"]
    assert row["wrist"]["image_stamp_s"] == row["wrist"]["info_stamp_s"]
    for label, rgb in (("head", bytes((10, 20, 30))), ("wrist", bytes((40, 50, 60)))):
        path = tmp_path / "capture" / row[label]["png_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == row[label]["png_sha256"]
        with PillowImage.open(path) as decoded:
            decoded.load()
            assert decoded.tobytes() == rgb * (640 * 480)
    saved = [json.loads(line) for line in (tmp_path / "capture/frames.jsonl").read_text().splitlines()]
    assert saved == [row]


def test_wrong_epoch_and_reused_images_never_create_a_second_sample(tmp_path):
    recorder = prepared(tmp_path)
    with pytest.raises(ValueError, match="TASK6_WORLD_SCOPE_INVALID"):
        recorder.capture(world(epoch=3))
    recorder.capture(world())
    with pytest.raises(ValueError, match="TASK6_SOURCE_STALE"):
        recorder.capture(world(1.1, step=550))
    assert recorder.finish()["samples"] == 1


def test_new_images_cannot_reuse_old_joint_feedback(tmp_path):
    recorder = prepared(tmp_path)
    recorder.capture(world())
    for camera, rgb in (("head", (1, 2, 3)), ("wrist", (4, 5, 6))):
        recorder.accept_image(camera, image(1.005, f"{camera}_camera_frame", rgb))
        recorder.accept_info(camera, info(1.005, f"{camera}_camera_frame"))
    with pytest.raises(ValueError, match="TASK6_SOURCE_STALE"):
        recorder.capture(world(1.01, step=501))
    assert recorder.finish()["samples"] == 1


def test_missing_camera_info_and_future_image_refuse_without_file_rows(tmp_path):
    recorder = prepared(tmp_path, include_info=False)
    with pytest.raises(ValueError, match="TASK6_CAMERA_INFO_MISSING"):
        recorder.capture(world())
    assert recorder.finish()["samples"] == 0
    future = prepared(tmp_path / "other", image_time=1.01)
    with pytest.raises(ValueError, match="TASK6_SOURCE_STALE"):
        future.capture(world())
    assert future.finish()["samples"] == 0


def test_malformed_rgb_and_source_skew_refuse(tmp_path):
    recorder = prepared(tmp_path)
    bad = image(1.01, "head_camera_frame", (1, 2, 3))
    bad.data = bad.data[:-1]
    with pytest.raises(ValueError, match="TASK6_RGB_INVALID"):
        recorder.accept_image("head", bad)
    recorder.finish()
    skewed = prepared(tmp_path / "other", joint_time=.955)
    with pytest.raises(ValueError, match="TASK6_SOURCE_SKEW"):
        skewed.capture(world())
    assert skewed.finish()["samples"] == 0


def test_paused_or_truncated_physics_never_becomes_a_camera_sample(tmp_path):
    recorder = prepared(tmp_path)
    paused = world()
    paused.paused = True
    with pytest.raises(ValueError, match="TASK6_WORLD_SCOPE_INVALID"):
        recorder.capture(paused)
    lost = world()
    lost.truncated = True
    with pytest.raises(ValueError, match="TASK6_WORLD_SCOPE_INVALID"):
        recorder.capture(lost)
    assert recorder.finish()["samples"] == 0


def test_cli_rejects_unscoped_output_before_ros_initialization(tmp_path):
    from so101_demo.cli.act_capture_task6 import main

    with pytest.raises(ValueError, match="TASK6_CAPTURE_SCOPE_INVALID"):
        main(["--evidence-root", str(tmp_path), "--run-id", "../outside",
              "--session-id", "task6-299", "--reset-epoch", "2",
              "--source-floor-s", ".5", "--max-age-s", ".05",
              "--max-skew-s", ".03", "--duration-s", "1"])
    assert not (tmp_path / "experiments").exists()


def test_cli_drains_atomic_callbacks_during_a_slow_png_write(tmp_path, monkeypatch):
    import rclpy
    from rclpy import executors
    from so101_demo.backends.mujoco import observer as world_module
    from so101_demo.cli import act_capture_task6 as cli

    (tmp_path / "experiments").mkdir()
    ticks = [0]
    recorders = []

    class Node:
        def __init__(self, name):
            self.name = name

        def create_subscription(self, *_args):
            return object()

        def destroy_node(self):
            pass

    class Executor:
        def __init__(self):
            self.stop = threading.Event()
            self.node = None

        def add_node(self, node):
            self.node = node

        def spin(self):
            while not self.stop.is_set():
                if self.node.name.endswith("_world"):
                    ticks[0] += 1
                time.sleep(.001)

        def spin_once(self, timeout_sec):
            if self.node.name.endswith("_world"):
                ticks[0] += 1
            time.sleep(timeout_sec)

        def shutdown(self, timeout_sec):
            self.stop.set()

    class Recorder:
        def __init__(self, *_args, **_kwargs):
            self.samples = 0
            self.rejections = []
            recorders.append(self)

        def capture(self, _world):
            before = ticks[0]
            time.sleep(.03)
            assert ticks[0] >= before + 2, "atomic callback stalled during PNG write"
            self.samples += 1

        def record_rejection(self, reason):
            self.rejections.append(reason)

        def finish(self):
            return {"samples": self.samples}

    class Observer:
        def __init__(self, *_args, **_kwargs):
            pass

        def recent_with_receipts(self):
            return (SimpleNamespace(evidence=object()),)

    monkeypatch.setattr(rclpy, "init", lambda: None)
    monkeypatch.setattr(rclpy, "ok", lambda: False)
    monkeypatch.setattr(rclpy, "create_node", lambda name, **_kwargs: Node(name))
    monkeypatch.setattr(executors, "SingleThreadedExecutor", Executor)
    monkeypatch.setattr(world_module, "MujocoWorldObserver", Observer)
    monkeypatch.setattr(cli, "Task6FrameRecorder", Recorder)
    result = cli.main([
        "--evidence-root", str(tmp_path), "--run-id", "capture",
        "--session-id", "task6-302", "--reset-epoch", "1",
        "--source-floor-s", "0", "--max-age-s", ".12",
        "--max-skew-s", ".05", "--duration-s", ".21",
    ])
    assert result == 0
    assert recorders[0].samples >= 2

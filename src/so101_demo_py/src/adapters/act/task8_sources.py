"""Task 8 ROS evidence subscriptions over one activated compiled MuJoCo model."""

from __future__ import annotations

import queue
import threading

import mujoco

from so101_demo.act.synchronizer import RgbObservationSynchronizer
from so101_demo.backends.mujoco.observer import MujocoWorldObserver
from .contact_evidence import RobotContactObserver, RosRobotContactAdapter
from .physics import model_sha256
from .ros_observation import RosObservationAdapter
from .scene_state import SceneStateObserver, RosSceneStateAdapter
from .task8_contact_pairs import Task8ContactPairs
from .task8_readback import Task8PhysicalReadback


class Task8RosEvidence:
    """Join physical sources; ROS callbacks only enqueue stop requests."""

    def __init__(
        self, node, broker, *, model: mujoco.MjModel,
        contact_pairs: Task8ContactPairs, session_id: str,
        max_wall_age_s: float, max_source_skew_s: float, max_sim_gap_s: float,
        joint_tolerance_rad: float, cup_pose_tolerance_m: float,
        cup_orientation_tolerance: float,
    ) -> None:
        if (not isinstance(model, mujoco.MjModel)
                or not isinstance(contact_pairs, Task8ContactPairs)
                or model_sha256(model) != contact_pairs.model_sha256
                or not isinstance(session_id, str) or not session_id):
            raise ValueError("TASK8_SOURCE_MODEL_INVALID")
        self.session_id = session_id
        self.contact_pairs = contact_pairs
        self._hazards: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.reset_epoch: int | None = None
        self.phase: str | None = None

        self.world = MujocoWorldObserver(
            node, session_id, max_age_s=max_wall_age_s,
            on_hazard=self._enqueue_hazard,
        )
        self.scene = SceneStateObserver(
            model_sha256=contact_pairs.model_sha256, nq=model.nq, nv=model.nv,
            max_age_s=max_wall_age_s,
        )
        self.contacts = RobotContactObserver(
            known_geoms=contact_pairs.known_geoms, allowed_pairs=set(),
            max_age_s=max_wall_age_s, max_sim_gap_s=max_sim_gap_s,
        )
        self.rgb = RgbObservationSynchronizer(
            max_age_s=max_wall_age_s, max_skew_s=max_source_skew_s,
        )
        self.scene_adapter = RosSceneStateAdapter(
            node, self.scene, on_hazard=self._enqueue_hazard,
        )
        self.contact_adapter = RosRobotContactAdapter(
            node, self.contacts, on_hazard=self._enqueue_hazard,
        )
        self.rgb_adapter = RosObservationAdapter(node, self.rgb)
        self.readback = Task8PhysicalReadback(
            self.world, self.scene, self.contacts, self.rgb, broker,
            model=model, expected_model_sha256=contact_pairs.model_sha256,
            expected_mujoco_version=mujoco.mj_versionString(),
            max_source_skew_s=max_source_skew_s, max_wall_age_s=max_wall_age_s,
            joint_tolerance_rad=joint_tolerance_rad,
            cup_pose_tolerance_m=cup_pose_tolerance_m,
            cup_orientation_tolerance=cup_orientation_tolerance,
        )

    def _enqueue_hazard(self, reason: str) -> None:
        self._hazards.put_nowait(reason)

    def take_hazard(self) -> str | None:
        try:
            return self._hazards.get_nowait()
        except queue.Empty:
            return None

    def arm(self, phase: str) -> int:
        try:
            reset = self.world.recent_with_receipts()[-1].evidence
        except Exception as error:
            raise ValueError("TASK8_RESET_UNAVAILABLE") from error
        if (reset.simulation_session_id != self.session_id or reset.paused is not True
                or reset.simulation_step != 0 or type(reset.reset_epoch) is not int
                or reset.reset_epoch < 1):
            raise ValueError("TASK8_RESET_UNAVAILABLE")
        allowed = self.contact_pairs.for_phase(phase)
        self.contact_adapter.replace_allowed_pairs(allowed)
        self.scene_adapter.arm(reset)
        self.contact_adapter.arm(reset)
        self.rgb_adapter.reset(self.session_id, source_floor_s=reset.simulation_time_s)
        self.reset_epoch = reset.reset_epoch
        self.phase = phase
        return reset.reset_epoch

    def set_phase(self, phase: str) -> None:
        if self.reset_epoch is None:
            raise ValueError("TASK8_RESET_UNAVAILABLE")
        self.contact_adapter.replace_allowed_pairs(self.contact_pairs.for_phase(phase))
        self.phase = phase

    def capture(self, attempt_id: str, *, after_step: int | None = None) -> dict:
        if self.reset_epoch is None:
            raise ValueError("TASK8_RESET_UNAVAILABLE")
        return self.readback.capture(
            self.session_id, attempt_id, self.reset_epoch, after_step=after_step,
        )


class Task8HazardDispatcher:
    """Cancel owned action goals away from the single-threaded ROS executor."""

    def __init__(self, sources: Task8RosEvidence, broker, cancelled: threading.Event,
                 *, command_broker=None) -> None:
        self._sources = sources
        self._broker = broker
        self._command_broker = command_broker
        self._cancelled = cancelled
        self._closing = threading.Event()
        self.finished = threading.Event()
        self.reason: str | None = None
        self.error: BaseException | None = None
        self.confirmed = False
        self._thread = threading.Thread(
            target=self._run, name="act-task8-hazard-stop", daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._closing.is_set():
                reason = self._sources.take_hazard()
                if reason is None:
                    self._closing.wait(0.005)
                    continue
                self.reason = reason
                self._cancelled.set()
                if self._command_broker is None:
                    self._broker.stop_all("TASK8_EVIDENCE_HAZARD")
                else:
                    self._command_broker.ownership.revoke("TASK8_EVIDENCE_HAZARD")
                    self._command_broker.tick()
                while not self._closing.is_set():
                    if self._command_broker is None:
                        self._broker.refresh_stop()
                    else:
                        self._command_broker.tick()
                    if self._broker.stopped():
                        self.confirmed = True
                        return
                    self._closing.wait(0.005)
                return
        except BaseException as error:
            self.error = error
        finally:
            self.finished.set()

    def close(self) -> None:
        self._closing.set()
        if self._thread.ident is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                raise RuntimeError("TASK8_HAZARD_DISPATCHER_NOT_STOPPED")

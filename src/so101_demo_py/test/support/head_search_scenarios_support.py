"""Fakes and helpers shared by the Head search scenario tests."""

from __future__ import annotations

import math

WIDTH_PX = 640


HEIGHT_PX = 480


FOCAL_PX = 415.69219381653056


PRINCIPAL_X_PX = WIDTH_PX / 2.0


PRINCIPAL_Y_PX = HEIGHT_PX / 2.0


TIMESTEP_S = 0.002


CONTROL_STEPS = 5


ROTATION_OPTICAL_TO_BASE = (
    (-1.0, 0.0, 0.0),
    (0.0, 0.6, -0.8),
    (0.0, -0.8, -0.6),
)


GAIN_PX_PER_RAD = 0.8 * FOCAL_PX


VERTICAL_BOUNDS_PX = (191.699852915671, 272.6768492617673)


FRAME_PERIOD_S = 0.1


CONDITION_CLASSES = [
    "nominal",
    "left_anchor",
    "forward_anchor",
    "distractor_present",
    "two_cups",
    "no_cup",
    "low_light",
    "partial_occlusion",
    "fast_interruption",
    "reacquire_after_stop",
]


ANCHORS = ["default", "left", "forward"]


def _partition_items(count: int = 40) -> list[dict]:
    """The declared qualification list, built with the tracked document's own rotation of classes."""

    items = []
    for index in range(count):
        condition_class = CONDITION_CLASSES[index % len(CONDITION_CLASSES)]
        items.append(
            {
                "seed": 900000 + index,
                "scene_group_id": f"scene-{900000 + index:09d}",
                "condition_class": condition_class,
                "anchor": ANCHORS[index % len(ANCHORS)],
            }
        )
    return items


def _project(yaw_rad: float, cup_yaw_rad: float) -> float:
    """The pixel column a cup at `cup_yaw_rad` lands on while the neck holds `yaw_rad`."""

    return PRINCIPAL_X_PX - GAIN_PX_PER_RAD * math.tan(cup_yaw_rad - yaw_rad)


class FakePlant:
    """A yaw-only plant that commands a target, moves exactly there and renders one frame per stop.

    The plant holds the neck to the declared frame boundary exactly as the sealed MuJoCo plant does, so
    every stop advances the simulation clock by one frame period and the recorded stop is settled: the
    interval between two frames is that period, which is the contract the cadence check proves.
    """

    def __init__(
        self,
        *,
        cup_yaw_rad: float,
        yaw_rad: float = 0.0,
        follow_gain: float = 1.0,
        quiet_steps: int = 5,
        frame_period_s: float = FRAME_PERIOD_S,
        settled: bool = True,
        reached: bool = True,
        hold_velocity_rad_s: float = 0.0,
    ) -> None:
        self.cup_yaw_rad = float(cup_yaw_rad)
        self.yaw_rad = float(yaw_rad)
        self.follow_gain = float(follow_gain)
        self.quiet_steps = int(quiet_steps)
        self.frame_period_s = float(frame_period_s)
        self.settled = bool(settled)
        self.reached = bool(reached)
        self.hold_velocity_rad_s = float(hold_velocity_rad_s)
        self.simulation_timestep_s = TIMESTEP_S
        self.time_s = 0.0
        self.frames_rendered = 0
        self.stops: list[dict] = []
        self.commands: list[float] = []
        self.target_rad = float(yaw_rad)

    def settle_to(self, target_rad: float) -> dict:
        self.commands.append(float(target_rad))
        start_sim, start_rad = self.time_s, self.yaw_rad
        self.target_rad = float(target_rad)
        self.yaw_rad = start_rad + self.follow_gain * (float(target_rad) - start_rad)
        self.time_s += self.frame_period_s
        steps = int(round(self.frame_period_s / TIMESTEP_S))
        stop = {
            "index": None,
            "kind": "plan",
            "target_rad": float(target_rad),
            "start_rad": start_rad,
            "sim_start_s": start_sim,
            "sim_end_s": self.time_s,
            "steps": steps,
            "settle_s": self.time_s - start_sim,
            "settled": self.settled,
            "reached": self.reached,
            "final_velocity_rad_s": (
                self.hold_velocity_rad_s
                if abs(float(target_rad) - start_rad) <= 1e-12
                else 0.0
            ),
            "final_position_error_rad": float(target_rad) - self.yaw_rad,
            "quiet_steps": self.quiet_steps,
            "time_base": "simulation",
        }
        self.stops.append(stop)
        return dict(stop)

    @property
    def velocity_rad_s(self) -> float:
        return 0.0

    @property
    def frame_stamp_ns(self) -> int:
        return int(round(self.time_s * 1e9))

    def render_frame(self):
        self.frames_rendered += 1
        return {"frame": self.frames_rendered, "yaw_rad": self.yaw_rad}

    def optical_geometry(self) -> dict:
        return {
            "k": (FOCAL_PX, 0.0, PRINCIPAL_X_PX, 0.0, FOCAL_PX, PRINCIPAL_Y_PX, 0.0, 0.0, 1.0),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": ROTATION_OPTICAL_TO_BASE,
        }


class FakeDetector:
    """A detector that projects the plant's own yaw, with a declared per-frame pixel jitter."""

    def __init__(self, plant, *, jitter_px=(), cups=1, fail_at=()) -> None:
        self.plant = plant
        self.jitter_px = tuple(jitter_px)
        self.cups = int(cups)
        self.fail_at = tuple(fail_at)
        self.calls = 0
        self.resets = 0

    def reset(self) -> None:
        self.calls = 0
        self.resets += 1

    def __call__(self, image, stamp_ns):
        index = self.calls
        self.calls += 1
        if index in self.fail_at:
            raise RuntimeError("DETECTOR_FAILED")
        if self.cups == 0:
            return []
        jitter = self.jitter_px[index % len(self.jitter_px)] if self.jitter_px else 0.0
        column = _project(float(image["yaw_rad"]), self.plant.cup_yaw_rad) + jitter
        if column - 30.0 < 0.0 or column + 30.0 > WIDTH_PX:
            return []
        return [
            {
                "xyxy": (column - 30.0, PRINCIPAL_Y_PX - 30.0, column + 30.0, PRINCIPAL_Y_PX + 30.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": f"head-cup-{cup}",
            }
            for cup in range(self.cups)
        ]


def _clock(start=1000.0, step=0.001):
    state = {"now": start}

    def clock() -> float:
        state["now"] += step
        return state["now"]

    return clock

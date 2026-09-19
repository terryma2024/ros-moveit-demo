"""One cumulative revolution with independently bounded RGB centering."""

import math

from .bearing import bearing, optical_ray_base
from .contracts import fields, finite, identifier, integer, validate_search_result, vector


class HeadSearchController:
    def __init__(self, config):
        self.reset(config)

    def reset(self, config):
        keys = ("attempt_id", "session_id", "search_start_rad", "horizontal_fov_rad",
                "coarse_step_rad", "search_timeout_s", "max_age_s", "max_skew_s",
                "settle_velocity_rad_s", "goal_tolerance_rad", "center_deadband_px",
                "vertical_bounds_px", "min_area_px2", "min_confidence", "max_fine_corrections",
                "max_fine_total_rad", "frame_id", "ray_origin_frame_id")
        fields(config, keys)
        self.config = dict(config)
        for key in ("attempt_id", "session_id", "frame_id", "ray_origin_frame_id"):
            identifier(config[key])
        for key in keys:
            if key not in ("attempt_id", "session_id", "frame_id", "ray_origin_frame_id",
                           "vertical_bounds_px", "max_fine_corrections"):
                finite(config[key], nonnegative=key != "search_start_rad")
        integer(config["max_fine_corrections"], minimum=1)
        vertical = vector(config["vertical_bounds_px"], 2)
        if (not 0 < config["coarse_step_rad"] <= config["horizontal_fov_rad"] / 2 < math.pi
                or config["search_timeout_s"] <= 0 or config["max_age_s"] <= 0
                or not 0 <= config["min_confidence"] <= 1
                or not 0 <= vertical[0] < vertical[1] <= 480):
            raise ValueError("SEARCH_CONFIG_INVALID")
        self.target = config["search_start_rad"]
        self.coarse_angle = self.fine_angle = 0.
        self.fine_count = self.lock_count = 0
        self.track = None
        self.started_wall_s = self.last_wall_s = self.last_frame_s = None
        self.motion_source_s = None
        self.terminal = None
        self.last_feedback = None
        self.state = "SAFE_OBSERVE"

    def _result(self, status, feedback, stamp, *, found=False, ray=None, confidence=None):
        self.terminal = validate_search_result(dict(found=found, status=status,
            bearing_rad=bearing(ray) if found else None, frame_id=self.config["frame_id"],
            ray_origin_frame_id=self.config["ray_origin_frame_id"],
            neck_yaw_rad=feedback["neck_yaw_rad"], confidence=confidence if found else None,
            timestamp=stamp, attempt_id=self.config["attempt_id"]))
        return dict(self.terminal)

    def _command(self, *, stop=False, feedback=None, status=None):
        return dict(neck_target_rad=feedback["neck_yaw_rad"] if stop else self.target,
                    stop=stop, status=status or self.state)

    def advance_deadline(self, now_wall_s):
        now=finite(now_wall_s,nonnegative=True)
        if self.last_wall_s is not None and now<self.last_wall_s:raise ValueError("SEARCH_CLOCK_INVALID")
        self.last_wall_s=now
        if self.started_wall_s is None:self.started_wall_s=now
        if self.terminal is not None:return dict(self.terminal)
        if now-self.started_wall_s>=self.config["search_timeout_s"]:
            return self.fail("SEARCH_TIMEOUT")
        return None

    def fail(self,status):
        return self._result(status,self.last_feedback or {"neck_yaw_rad":None},self.last_frame_s or 0.)

    def tick(self, frame, feedback, now_wall_s):
        now = finite(now_wall_s, nonnegative=True)
        for value in (frame, feedback):
            if (value["session_id"], value["attempt_id"]) != (
                    self.config["session_id"], self.config["attempt_id"]):
                raise ValueError("SEARCH_IDENTITY_INVALID")
        terminal=self.advance_deadline(now)
        if terminal is not None:return terminal
        yaw = finite(feedback["neck_yaw_rad"])
        velocity = finite(feedback["neck_velocity_rad_s"])
        stamp = finite(frame["sim_time_s"], nonnegative=True)
        feedback_stamp = finite(feedback["sim_time_s"], nonnegative=True)
        self.last_feedback=dict(feedback)
        if feedback["safe_observe"] is not True:
            return self._result("SEARCH_UNSAFE", feedback, stamp)
        fresh = all(0 <= now - finite(value["received_wall_s"], nonnegative=True)
                    <= self.config["max_age_s"] for value in (frame, feedback))
        if (not fresh or frame["frame_id"] != self.config["frame_id"]
                or not 0 <= stamp - feedback_stamp <= self.config["max_skew_s"]
                or (self.last_frame_s is not None and stamp <= self.last_frame_s)):
            self.lock_count = 0
            return self._command(stop=True, feedback=feedback, status="INPUT_STALE")
        if abs(yaw - self.target) > self.config["goal_tolerance_rad"] or abs(velocity) > self.config["settle_velocity_rad_s"]:
            return self._command()
        if self.motion_source_s is not None and stamp <= self.motion_source_s:
            return self._command(stop=True, feedback=feedback, status="INPUT_STALE")
        self.last_frame_s = stamp
        self.state = "SEARCH_CUP"
        candidates = []
        for detection in frame["detections"]:
            fields(detection, ("xyxy", "confidence", "class_id", "track_id"))
            box = vector(detection["xyxy"], 4)
            confidence = finite(detection["confidence"])
            integer(detection["class_id"]); identifier(detection["track_id"])
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= 640 and 0 <= y1 < y2 <= 480 and 0 <= confidence <= 1):
                raise ValueError("DETECTION_INVALID")
            if confidence >= self.config["min_confidence"] and (x2-x1)*(y2-y1) >= self.config["min_area_px2"]:
                candidates.append((detection, ((x1+x2)/2, (y1+y2)/2)))
        if len(candidates) > 1: return self._result("TARGET_AMBIGUOUS", feedback, stamp)
        if candidates:
            detection, center = candidates[0]
            ray = optical_ray_base(center, frame["k"], frame["distortion"], frame["rotation_optical_to_base"])
            if self.track != detection["track_id"]:
                self.track, self.lock_count = detection["track_id"], 0
            vertical = self.config["vertical_bounds_px"]
            horizontal_error = center[0] - frame["k"][2]
            if abs(horizontal_error) <= self.config["center_deadband_px"] and vertical[0] <= center[1] <= vertical[1]:
                self.lock_count += 1
                self.state = "CENTER_CUP"
                if self.lock_count >= 3:
                    return self._result("TARGET_LOCKED", feedback, stamp, found=True,
                                        ray=ray, confidence=detection["confidence"])
                return self._command()
            self.lock_count = 0
            # Infer correction from the calibrated optical axis, including mounting pitch/yaw.
            axis = optical_ray_base((frame["k"][2], frame["k"][5]), frame["k"],
                                    frame["distortion"], frame["rotation_optical_to_base"])
            correction = (bearing(ray)-bearing(axis)+math.pi) % (2*math.pi)-math.pi
            if (self.fine_count >= self.config["max_fine_corrections"]
                    or self.fine_angle + abs(correction) > self.config["max_fine_total_rad"]
                    or abs(correction) < 1e-9):
                return self._result("TARGET_NOT_CENTERED", feedback, stamp)
            self.fine_count += 1; self.fine_angle += abs(correction)
            self.target = yaw + correction; self.motion_source_s = stamp; self.state = "CENTER_CUP"
            return self._command()
        self.lock_count, self.track = 0, None
        if self.coarse_angle >= 2*math.pi - 1e-9:
            return self._result("TARGET_NOT_FOUND", feedback, stamp)
        step = min(self.config["coarse_step_rad"], 2*math.pi-self.coarse_angle)
        self.coarse_angle += step
        self.target = self.config["search_start_rad"] + self.coarse_angle
        self.motion_source_s = stamp
        return self._command()

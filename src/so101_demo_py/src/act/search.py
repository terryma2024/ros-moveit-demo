"""One cumulative revolution with independently bounded RGB centering."""

import math

from .bearing import bearing, optical_ray_base
from .contracts import fields, finite, identifier, integer, validate_search_result, vector
from .head_search_domain import TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL, bounded_search_stops
from .head_feedback import FeedbackPolicy, nanoseconds
from .head_evidence_identity import canonical_bytes
from .head_simulation_policy import HeadSimulationPolicy


class HeadSearchController:
    def __init__(self, config, *, simulation_policy=None):
        self._simulation_policy=(None if simulation_policy is None else HeadSimulationPolicy.parse(
            simulation_policy.readback() if type(simulation_policy) is HeadSimulationPolicy else simulation_policy))
        self.reset(config)

    def reset(self, config):
        if self._simulation_policy is not None:
            policy=self._simulation_policy
            if (type(config) is not dict or not {'required_search_domain_rad','lock_valid_neck_rad'}<=set(config)
                    or 'required_domain_rad' in config
                    or any(type(config.get(name)) not in (int,float) or config[name]!=value for name,value in
                        (('max_age_s',policy.perception_max_age_s),('search_timeout_s',policy.search_timeout_s)))):
                raise ValueError('HEAD_SEARCH_SIMULATION_CONFIG_INVALID')
            for name in ('required_search_domain_rad','lock_valid_neck_rad'):
                interval=config[name]
                if (type(interval) not in (list,tuple) or len(interval)!=2
                        or any(type(v) not in (int,float) or not math.isfinite(v) for v in interval)):
                    raise ValueError('HEAD_SEARCH_SIMULATION_DOMAIN_INVALID')
        keys = (
            "attempt_id",
            "session_id",
            "search_start_rad",
            "horizontal_fov_rad",
            "coarse_step_rad",
            "search_timeout_s",
            "max_age_s",
            "max_skew_s",
            "settle_velocity_rad_s",
            "goal_tolerance_rad",
            "center_deadband_px",
            "vertical_bounds_px",
            "min_area_px2",
            "min_confidence",
            "max_fine_corrections",
            "max_fine_total_rad",
            "frame_id",
            "ray_origin_frame_id",
        )
        # the sealed domain is optional: a config without it keeps the legacy revolution behaviour.
        # The seal spells the declaration `required_search_domain_rad`, while `required_domain_rad`
        # is the legacy spelling the controller shipped with; both name the same required interval
        optional = {
            key: config[key]
            for key in ("required_search_domain_rad", "required_domain_rad", "lock_valid_neck_rad")
            if key in config
        }
        fields({key: value for key, value in config.items() if key not in optional}, keys)
        self.config = dict(config)
        for key in ("attempt_id", "session_id", "frame_id", "ray_origin_frame_id"):
            identifier(config[key])
        for key in keys:
            if key not in (
                "attempt_id",
                "session_id",
                "frame_id",
                "ray_origin_frame_id",
                "vertical_bounds_px",
                "max_fine_corrections",
            ):
                finite(config[key], nonnegative=key != "search_start_rad")
        integer(config["max_fine_corrections"], minimum=1)
        vertical = vector(config["vertical_bounds_px"], 2)
        if (
            not 0 < config["coarse_step_rad"] <= config["horizontal_fov_rad"] / 2 < math.pi
            or config["search_timeout_s"] <= 0
            or config["max_age_s"] <= 0
            or not 0 <= config["min_confidence"] <= 1
            or not 0 <= vertical[0] < vertical[1] <= 480
        ):
            raise ValueError("SEARCH_CONFIG_INVALID")
        self.target = config["search_start_rad"]
        self.coarse_angle = self.fine_angle = 0.0
        self.fine_count = self.lock_count = 0
        self.track = None
        self.previous_horizontal_error = None
        self.centering_gain = 1.0
        self.started_wall_s = self.last_wall_s = self.last_frame_s = None
        self.motion_source_s = None
        self.terminal = None
        self.last_feedback = None
        self.state = "SAFE_OBSERVE"
        # when the config carries the declared required domain the controller walks the bounded plan
        # instead of accumulating a full revolution, which could command angles past the safe bound
        self.plan = None
        self.plan_index = 0
        required_domain = optional.get(
            "required_search_domain_rad", optional.get("required_domain_rad")
        )
        if required_domain is not None:
            # without a declared safe interval the required domain itself bounds the sweep, so a
            # plan that spells the domain only in the seal still cannot walk past it
            safe_interval = optional.get("lock_valid_neck_rad")
            if safe_interval is None:
                # a clamped endpoint is commanded as `current + direction * travel`, which can land
                # one float ulp short of the bound; the 1e-12 allowance absorbs only that round-off,
                # so a domain the stops do cover still earns the clean negative, not a refusal
                safe_interval = (
                    float(required_domain[0]) - 1e-12,
                    float(required_domain[1]) + 1e-12,
                )
            self.plan = bounded_search_stops(
                anchor_rad=config["search_start_rad"],
                required_domain_rad=required_domain,
                safe_interval_rad=safe_interval,
                horizontal_fov_rad=config["horizontal_fov_rad"],
                coarse_step_rad=config["coarse_step_rad"],
            )

    def _result(self, status, feedback, stamp, *, found=False, ray=None, confidence=None):
        self.terminal = validate_search_result(
            dict(
                found=found,
                status=status,
                bearing_rad=bearing(ray) if found else None,
                frame_id=self.config["frame_id"],
                ray_origin_frame_id=self.config["ray_origin_frame_id"],
                neck_yaw_rad=feedback["neck_yaw_rad"],
                confidence=confidence if found else None,
                timestamp=stamp,
                attempt_id=self.config["attempt_id"],
            )
        )
        return dict(self.terminal)

    def _command(self, *, stop=False, feedback=None, status=None):
        return dict(
            neck_target_rad=feedback["neck_yaw_rad"] if stop else self.target,
            stop=stop,
            status=status or self.state,
        )

    def advance_deadline(self, now_wall_s):
        now = finite(now_wall_s, nonnegative=True)
        if self.last_wall_s is not None and now < self.last_wall_s:
            raise ValueError("SEARCH_CLOCK_INVALID")
        self.last_wall_s = now
        if self.started_wall_s is None:
            self.started_wall_s = now
        if self.terminal is not None:
            return dict(self.terminal)
        if now - self.started_wall_s >= self.config["search_timeout_s"]:
            return self.fail("SEARCH_TIMEOUT")
        return None

    def next_target(self):
        """The next stop of the bounded plan, or None once every stop has been commanded."""

        if self.plan is None or self.plan_index >= len(self.plan.targets_rad):
            return None
        target = self.plan.targets_rad[self.plan_index]
        self.plan_index += 1
        return target

    def fail(self, status):
        return self._result(
            status, self.last_feedback or {"neck_yaw_rad": None}, self.last_frame_s or 0.0
        )

    def tick(self, frame, feedback, now_wall_s, *, joint_context=None):
        now = finite(now_wall_s, nonnegative=True)
        for value in (frame, feedback):
            if (value["session_id"], value["attempt_id"]) != (
                self.config["session_id"],
                self.config["attempt_id"],
            ):
                raise ValueError("SEARCH_IDENTITY_INVALID")
        terminal = self.advance_deadline(now)
        if terminal is not None:
            return terminal
        yaw = finite(feedback["neck_yaw_rad"])
        velocity = finite(feedback["neck_velocity_rad_s"])
        stamp = finite(frame["sim_time_s"], nonnegative=True)
        feedback_stamp = finite(feedback["sim_time_s"], nonnegative=True)
        self.last_feedback = dict(feedback)
        if feedback["safe_observe"] is not True:
            return self._result("SEARCH_UNSAFE", feedback, stamp)
        if joint_context is None:
            fresh = all(
                0 <= now - finite(value["received_wall_s"], nonnegative=True)
                <= self.config["max_age_s"] for value in (frame, feedback)
            )
        else:
            # The source-bound historical JointState supplies the exposure's
            # pose. Current motion freshness belongs to a separately measured
            # original JointState/dual-clock decision, never the camera age.
            try:
                fields(joint_context,("session_id","attempt_id","sample","decision","policy"))
                if (joint_context['session_id'],joint_context['attempt_id']) != (
                        self.config['session_id'],self.config['attempt_id']):
                    raise ValueError('SEARCH_JOINT_CONTEXT_IDENTITY_INVALID')
                policy=FeedbackPolicy.parse(joint_context['policy']);decision=joint_context['decision']
                if self._simulation_policy is not None and (policy._bound_simulation_policy is None
                        or canonical_bytes(policy._bound_simulation_policy.readback())
                            !=canonical_bytes(self._simulation_policy.readback())):
                    raise ValueError('HEAD_SEARCH_SIMULATION_FEEDBACK_MISMATCH')
                fields(decision,('wall_before_s','wall_after_s','sim_ns','sim_s'))
                if (type(decision['sim_ns']) is not int or decision['sim_ns']<=0
                        or nanoseconds(decision['sim_s'])!=decision['sim_ns']
                        or not nanoseconds(decision['wall_before_s'])<=nanoseconds(decision['wall_after_s'])
                        or not 0<=nanoseconds(now)-nanoseconds(decision['wall_after_s'])
                        <=math.floor(policy.watchdog_reaction_limit_s*1e9)):
                    raise ValueError('SEARCH_JOINT_CONTEXT_CLOCK_INVALID')
                policy.check_joint(joint_context['sample'],decision)
                if not (0<=nanoseconds(now)-nanoseconds(joint_context['sample']['wall_s'])
                        <=math.floor(policy.joint_max_receipt_age_s*1e9)):
                    raise ValueError('HEAD_FEEDBACK_RECEIPT_STALE')
                fresh=(0<=now-finite(frame['received_wall_s'],nonnegative=True)<=self.config['max_age_s']
                    and 0<=now-finite(feedback['received_wall_s'],nonnegative=True))
            except (ValueError,KeyError,TypeError):
                self.lock_count=0
                raise
        if (
            not fresh
            or frame["frame_id"] != self.config["frame_id"]
            or not 0 <= stamp - feedback_stamp <= self.config["max_skew_s"]
            or (self.last_frame_s is not None and stamp <= self.last_frame_s)
        ):
            self.lock_count = 0
            return self._command(stop=True, feedback=feedback, status="INPUT_STALE")
        if (
            abs(yaw - self.target) > self.config["goal_tolerance_rad"]
            or abs(velocity) > self.config["settle_velocity_rad_s"]
        ):
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
            integer(detection["class_id"])
            identifier(detection["track_id"])
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= 640 and 0 <= y1 < y2 <= 480 and 0 <= confidence <= 1):
                raise ValueError("DETECTION_INVALID")
            if (
                confidence >= self.config["min_confidence"]
                and (x2 - x1) * (y2 - y1) >= self.config["min_area_px2"]
            ):
                candidates.append((detection, ((x1 + x2) / 2, (y1 + y2) / 2)))
        if len(candidates) > 1:
            return self._result("TARGET_AMBIGUOUS", feedback, stamp)
        if candidates:
            detection, center = candidates[0]
            ray = optical_ray_base(
                center, frame["k"], frame["distortion"], frame["rotation_optical_to_base"]
            )
            if self.track != detection["track_id"]:
                self.track, self.lock_count = detection["track_id"], 0
                self.previous_horizontal_error = None
                self.centering_gain = 1.0
            vertical = self.config["vertical_bounds_px"]
            horizontal_error = center[0] - frame["k"][2]
            if (
                abs(horizontal_error) <= self.config["center_deadband_px"]
                and vertical[0] <= center[1] <= vertical[1]
            ):
                self.lock_count += 1
                self.state = "CENTER_CUP"
                if self.lock_count >= 3:
                    return self._result(
                        "TARGET_LOCKED",
                        feedback,
                        stamp,
                        found=True,
                        ray=ray,
                        confidence=detection["confidence"],
                    )
                return self._command()
            self.lock_count = 0
            # Infer correction from the calibrated optical axis, including mounting pitch/yaw.
            axis = optical_ray_base(
                (frame["k"][2], frame["k"][5]),
                frame["k"],
                frame["distortion"],
                frame["rotation_optical_to_base"],
            )
            correction = (bearing(ray) - bearing(axis) + math.pi) % (2 * math.pi) - math.pi
            if self._simulation_policy is not None:
                previous_error = self.previous_horizontal_error
                # A large improvement can cross center without oscillating. Reduce
                # gain only for a same-track reversal that retains most of its error.
                if (previous_error is not None and horizontal_error * previous_error < 0
                        and abs(horizontal_error) >= 0.8 * abs(previous_error)):
                    self.centering_gain *= 0.5
                self.previous_horizontal_error = horizontal_error
                correction *= self.centering_gain
            if (
                self.fine_count >= self.config["max_fine_corrections"]
                or self.fine_angle + abs(correction) > self.config["max_fine_total_rad"]
                or abs(correction) < 1e-9
            ):
                return self._result("TARGET_NOT_CENTERED", feedback, stamp)
            self.fine_count += 1
            self.fine_angle += abs(correction)
            self.target = yaw + correction
            self.motion_source_s = stamp
            self.state = "CENTER_CUP"
            return self._command()
        self.lock_count, self.track = 0, None
        self.previous_horizontal_error = None
        self.centering_gain = 1.0
        if self.plan is not None:
            target = self.next_target()
            if target is None:
                if self._simulation_policy is not None:
                    return self._result(TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL if self.plan.coverage_complete
                        else 'SEARCH_COVERAGE_INCOMPLETE',feedback,stamp)
                # a bound was reached first, so this is not a clean negative
                return self._result(
                    self.plan.not_found_status(reached_bound=not self.plan.coverage_complete),
                    feedback,
                    stamp,
                )
            self.target = target
            self.motion_source_s = stamp
            return self._command()
        if self.coarse_angle >= 2 * math.pi - 1e-9:
            return self._result(TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL, feedback, stamp)
        step = min(self.config["coarse_step_rad"], 2 * math.pi - self.coarse_angle)
        self.coarse_angle += step
        self.target = self.config["search_start_rad"] + self.coarse_angle
        self.motion_source_s = stamp
        return self._command()

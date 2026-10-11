"""The runtime readback of the eleven measured calibration parameters.

Seventeen values enter the bundle. Six of them - the field of view, the safe neck interval and the four
perception values - are declared by the run and read back by their producers (ledger HS-311). The other
eleven are *measured*: phase 6 computes the sweep step, the search timeout, the deadband, the vertical
bounds and the two fine-correction budgets, and phase 7 computes the freshness bound, the skew bound, the
submission lead, the stop velocity and the stop latency. Until now those eleven were recorded with
`verified: false`, because nothing queried a running component for them (ledger HS-311, inference ten).

This module is that query. For every one of the eleven it **constructs the production component that
consumes the value with the recorded value and records what it observes**:

* the installed ``so101_demo.act.search.HeadSearchController`` for the eight configuration keys its
  ``tick`` reads - ``coarse_step_rad`` (also read off the bounded stop plan the controller builds, which
  is the step every neck target of the plan is anchored to), ``search_timeout_s``, ``center_deadband_px``,
  ``vertical_bounds_px``, ``max_fine_corrections``, ``max_fine_total_rad``, ``max_age_s`` and
  ``max_skew_s``;
* the installed ``so101_demo.adapters.act.ros_neck.RosNeckSearchPort`` for the three values its search
  path reads - the submission lead (``.lead``, used as the goal's header stamp offset), the stop timeout
  (``.stop_timeout``, the value the recorded ``stop_latency_s`` becomes for the neck port) and the
  freshness bound (``.max_age``, the staleness check before every command);
* the installed ``so101_demo.adapters.act.ros_execution.RosControllerPort`` - the stop criterion the
  measurement harness of HS-304..308 already drives - for ``stop_velocity_rad_s`` (``.stop_velocity``,
  the bound every monitored joint's measured velocity is compared against).

Three of the eight controller values are *also* observed behaviourally, at the exact float boundary the
component applies: the search deadline (a tick exactly at ``search_timeout_s`` reports ``SEARCH_TIMEOUT``
and one ulp earlier does not), the frame freshness bound (a frame exactly ``max_age_s`` old is fresh; one
ulp older is ``INPUT_STALE``) and the stamp skew bound (the same, for ``max_skew_s``). The other eight
observations are the values the constructed components hold under the keys their own code reads.

Two rules keep the record honest:

* a value whose component was **queried and disagreed** is recorded with the value that was actually
  observed, so the phase that consumes this record refuses with ``CAL_EFFECTIVE_VALUE_MISMATCH``
  (plan section 2b) instead of certifying a running system that uses another value;
* a value whose component **could not be queried at all** is recorded as ``not_observable`` with the
  reason and the recorded value, and stays ``verified: false``. No observation is invented: the reason
  is the exception that stopped the query, verbatim.

Nothing here commands motion, starts ROS, MuJoCo or a detector, reads a file or writes one. The
components are the installed ones; only the transport they are built on is the harness's, exactly as the
stop measurement's own harness documents it (``ControllerFeedbackTransport``), and the stand-ins are
recorded in every readback that used them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_measured_readback"
PHASE = "measured_parameter_readback"

#: this module's own refusal: a readback that was asked for something that is not a measured parameter
CAL_MEASURED_READBACK_INCOMPLETE = "CAL_MEASURED_READBACK_INCOMPLETE"
REFUSAL_CODES = (CAL_MEASURED_READBACK_INCOMPLETE,)

#: the eleven measured parameters, in the order design section 7.1 lists them. The first six are phase
#: 6's, the last five are phase 7's; `coarse_step_rad` is phase 6's sixth
MEASURED_PARAMETERS = (
    "coarse_step_rad",
    "search_timeout_s",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)

#: the eight values the installed search controller reads out of the configuration it validated
CONTROLLER_PARAMETERS = (
    "coarse_step_rad",
    "search_timeout_s",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
)

#: the values the installed neck search port reads; the freshness bound is read by both components
NECK_PORT_PARAMETERS = ("submit_lead_s", "stop_latency_s", "max_age_s")

#: the value the installed stop criterion reads, and the freshness bound it also takes
STOP_CRITERION_PARAMETERS = ("stop_velocity_rad_s", "max_age_s")

#: the observation of a value read off a component this module constructed
CONSTRUCTED_OBSERVATION = "constructed_production_component"
#: the observation of a value whose component could not be queried; the reason is recorded with it
NOT_OBSERVABLE = "not_observable"

#: the two observations this module records, and the ones a phase keeps verbatim: either of them means
#: the value was taken off a running component (or its absence from one was established), so the phase
#: must not relabel the record as a caller's report
OBSERVED_OBSERVATIONS = (CONSTRUCTED_OBSERVATION, NOT_OBSERVABLE)

#: the installed components, named as the record cites them
CONTROLLER_MODULE = "so101_demo.act.search"
CONTROLLER_CLASS = "HeadSearchController"
NECK_PORT_MODULE = "so101_demo.adapters.act.ros_neck"
NECK_PORT_CLASS = "RosNeckSearchPort"
STOP_CRITERION_MODULE = "so101_demo.adapters.act.ros_execution"
STOP_CRITERION_CLASS = "RosControllerPort"

#: the harness's own inputs, none of them one of the seventeen. The neck port is constructed for its
#: attributes, not to command anything: the goal duration is a stand-in the port only validates, the
#: command guard always allows, and the transport is the subscription stand-in the installed criterion
#: documents. They are recorded in every readback that used them so the record names its own harness
HARNESS_GOAL_DURATION_S = 1.0
HARNESS_COMMAND_GUARD = "always_true"
HARNESS_TRANSPORT = "subscription stand-in"
#: the identity the components are constructed under; a readback is not a flight, so it is not a generation
READBACK_IDENTITY = "measured-parameter-readback"

#: the two clock thresholds whose probe is exact: an order statistic of a sample would not be
FRESHNESS_PROBE_PARAMETER = "max_age_s"
SKEW_PROBE_PARAMETER = "max_skew_s"
DEADLINE_PROBE_PARAMETER = "search_timeout_s"

#: the statuses the installed controller reports when the observed frame is refused as stale
INPUT_STALE = "INPUT_STALE"
SEARCH_TIMEOUT = "SEARCH_TIMEOUT"


class CalibrationMeasuredReadbackRefused(CalibrationInputsRefused):
    """A readback refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(detail: str) -> CalibrationMeasuredReadbackRefused:
    return CalibrationMeasuredReadbackRefused(CAL_MEASURED_READBACK_INCOMPLETE, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


class _SubscriptionStandIn:
    """The node the installed neck port registers its joint-state subscription on.

    The port is the installed one and only its transport is the harness's, exactly as
    `head_search_stop_measurement.ControllerFeedbackTransport` documents for the stop criterion: nothing
    is published, and no ROS node, context or executor is created.
    """

    def __init__(self) -> None:
        self.topic = None
        self.message_type = None
        self.callback = None

    def create_subscription(self, topic, message_type, callback, qos_profile):
        self.topic, self.message_type, self.callback = topic, message_type, callback
        return None


class _NeckClientStandIn:
    """The action client the neck port holds; the readback never sends a goal through it."""

    def send_goal_async(self, message):  # pragma: no cover - the readback never commands a goal
        raise RuntimeError("the measured readback constructs the port and never sends a goal")


class _ControllerPortStandIn:
    """An injected controller port: a client and the feedback policy, so no graph is needed."""

    def __init__(self, feedback_policy) -> None:
        self.client = _NeckClientStandIn()
        self.feedback_policy = feedback_policy


#: the default scheduling policy the port is constructed under for the readback
READBACK_FEEDBACK_POLICY = {
    "joint_max_receipt_age_s": 0.25,
    "joint_max_source_age_s": 0.05,
    "camera_interarrival_deadline_s": 0.11,
    "camera_max_source_age_s": 0.11,
    "clock_interarrival_deadline_s": 0.25,
    "watchdog_period_s": 0.002,
    "watchdog_reaction_limit_s": 0.010,
    "revoker_connection_deadline_s": 0.002,
}


def _controller_configuration(values, configuration) -> dict:
    """The installed controller's configuration: the declared one, with the measured keys replaced.

    The declared configuration is the flat configuration the run's controller is constructed with, so it
    is exactly the key set `HeadSearchController` validates. Only the eight keys that controller reads are
    overridable here; a measured value outside them is the neck port's or the stop criterion's.
    """

    if not isinstance(configuration, Mapping):
        raise _refuse("the readback needs the configuration the running controller is constructed with")
    checked = dict(configuration)
    for name in CONTROLLER_PARAMETERS:
        if name in values:
            checked[name] = values[name]
    return checked


def _build_controller(configuration, factory):
    if factory is None:
        from so101_demo.act.search import HeadSearchController

        factory = HeadSearchController
    return factory(dict(configuration))


def _port_configuration(values, configuration) -> dict:
    """The configuration the neck port and the stop criterion are constructed with.

    Both take the four timing and stop values; a value the caller neither recorded nor declared is left
    absent on purpose, so the construction fails and the readback records why instead of inventing one.
    """

    checked = dict(configuration)
    checked.update({name: values[name] for name in values})
    return checked


def _required(configuration, name: str):
    if name not in configuration:
        raise KeyError(f"{name} is neither recorded nor declared, so the component cannot be constructed")
    return configuration[name]


def _build_neck_port(configuration, factory):
    if factory is None:
        from so101_demo.adapters.act.ros_neck import RosNeckSearchPort

        factory = RosNeckSearchPort
    from so101_demo.act.head_feedback import FeedbackPolicy

    policy = FeedbackPolicy.parse(dict(READBACK_FEEDBACK_POLICY))
    return factory(
        _SubscriptionStandIn(),
        session_id=READBACK_IDENTITY,
        attempt_id=READBACK_IDENTITY,
        goal_duration_s=HARNESS_GOAL_DURATION_S,
        submit_lead_s=_required(configuration, "submit_lead_s"),
        stop_timeout_s=_required(configuration, "stop_latency_s"),
        stop_velocity_rad_s=_required(configuration, "stop_velocity_rad_s"),
        max_age_s=_required(configuration, "max_age_s"),
        command_guard=lambda current_rad, target_rad: True,
        feedback_policy=policy,
        controller_port=_ControllerPortStandIn(policy),
    )


def _default_stop_criterion(configuration):
    """The installed stop criterion, over the harness's own subscription stand-in."""

    from so101_demo.act.head_search_stop_measurement.flights import controller_stop_criterion

    port, _transport, _clock = controller_stop_criterion(
        stop_velocity_rad_s=_required(configuration, "stop_velocity_rad_s"),
        max_age_s=_required(configuration, "max_age_s"),
    )
    return port


def _build_stop_criterion(configuration, factory):
    if factory is None:
        factory = _default_stop_criterion
    return factory(dict(configuration))


def _harness() -> dict:
    return {
        "goal_duration_s": HARNESS_GOAL_DURATION_S,
        "command_guard": HARNESS_COMMAND_GUARD,
        "transport": HARNESS_TRANSPORT,
        "readback_identity": READBACK_IDENTITY,
    }


def _frame(configuration, *, stamp_s, received_wall_s, detections=()) -> dict:
    return {
        "session_id": configuration["session_id"],
        "attempt_id": configuration["attempt_id"],
        "frame_id": configuration["frame_id"],
        "sim_time_s": stamp_s,
        "received_wall_s": received_wall_s,
        "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0],
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        "rotation_optical_to_base": [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]],
        "detections": list(detections),
    }


def _feedback(configuration, *, stamp_s, received_wall_s) -> dict:
    return {
        "session_id": configuration["session_id"],
        "attempt_id": configuration["attempt_id"],
        "sim_time_s": stamp_s,
        "received_wall_s": received_wall_s,
        "neck_yaw_rad": configuration["search_start_rad"],
        "neck_velocity_rad_s": 0.0,
        "safe_observe": True,
    }


def _tick_status(
    configuration, factory, *, received_wall_s, stamp_s, now_wall_s, feedback_stamp_s=None
) -> str | None:
    """One tick of a freshly constructed controller, and the status it reported.

    The frame's own stamp and the feedback's are separate arguments because the controller's skew gate is
    the difference between them: a probe that handed the same stamp to both could never reach it.
    """

    controller = _build_controller(configuration, factory)
    controller.advance_deadline(0.0)
    result = controller.tick(
        _frame(configuration, stamp_s=stamp_s, received_wall_s=received_wall_s),
        _feedback(
            configuration,
            stamp_s=stamp_s if feedback_stamp_s is None else feedback_stamp_s,
            received_wall_s=received_wall_s,
        ),
        now_wall_s,
    )
    return result.get("status") if isinstance(result, Mapping) else None


def _deadline_probe(configuration, factory) -> dict:
    """Where the controller's own timeout verdict flips, at the exact float the value names."""

    timeout = float(_required(configuration, "search_timeout_s"))
    controller = _build_controller(configuration, factory)
    controller.advance_deadline(0.0)
    just_before = controller.advance_deadline(math.nextafter(timeout, 0.0))
    at = controller.advance_deadline(timeout)
    status = at.get("status") if isinstance(at, Mapping) else None
    verified = just_before is None and status == SEARCH_TIMEOUT
    return {
        "probe": "search_deadline",
        "threshold_s": timeout,
        "just_before_threshold": None if just_before is None else just_before.get("status"),
        "at_threshold": status,
        "observed_value": timeout if verified else None,
        "verified": verified,
    }


def _clock_probe_skip(configuration, threshold_s: float) -> str | None:
    """Why a clock-threshold probe cannot isolate its own threshold, or None when it can."""

    timeout = float(_required(configuration, "search_timeout_s"))
    if threshold_s >= timeout:
        return (
            f"the search deadline {timeout} s fires before the {threshold_s} s threshold can be "
            f"observed on its own"
        )
    return None


def _freshness_probe(configuration, factory) -> dict:
    """A frame exactly `max_age_s` old is fresh; one ulp older is `INPUT_STALE`."""

    threshold = float(_required(configuration, "max_age_s"))
    body = {"probe": "frame_freshness", "threshold_s": threshold}
    skip = _clock_probe_skip(configuration, threshold)
    if skip is not None:
        return {**body, "skipped": skip, "observed_value": None, "verified": None}
    at = _tick_status(
        configuration, factory, received_wall_s=0.0, stamp_s=0.0, now_wall_s=threshold
    )
    beyond = _tick_status(
        configuration,
        factory,
        received_wall_s=0.0,
        stamp_s=0.0,
        now_wall_s=math.nextafter(threshold, math.inf),
    )
    verified = at != INPUT_STALE and beyond == INPUT_STALE
    return {
        **body,
        "at_threshold": "fresh" if at != INPUT_STALE else at,
        "just_beyond_threshold": beyond,
        "observed_value": threshold if verified else None,
        "verified": verified,
    }


def _skew_probe(configuration, factory) -> dict:
    """A frame whose stamps differ by exactly `max_skew_s` is accepted; one ulp more is stale."""

    threshold = float(_required(configuration, "max_skew_s"))
    age = float(_required(configuration, "max_age_s"))
    body = {"probe": "frame_skew", "threshold_s": threshold}
    if threshold > age:
        return {
            **body,
            "skipped": (
                f"a {threshold} s stamp skew is older than the {age} s freshness bound, so the "
                f"freshness refusal would hide the skew refusal"
            ),
            "observed_value": None,
            "verified": None,
        }
    skip = _clock_probe_skip(configuration, threshold)
    if skip is not None:
        return {**body, "skipped": skip, "observed_value": None, "verified": None}
    at = _tick_status(
        configuration,
        factory,
        received_wall_s=0.0,
        stamp_s=threshold,
        feedback_stamp_s=0.0,
        now_wall_s=threshold,
    )
    beyond = _tick_status(
        configuration,
        factory,
        received_wall_s=0.0,
        stamp_s=math.nextafter(threshold, math.inf),
        feedback_stamp_s=0.0,
        now_wall_s=threshold,
    )
    verified = at != INPUT_STALE and beyond == INPUT_STALE
    return {
        **body,
        "at_threshold": "fresh" if at != INPUT_STALE else at,
        "just_beyond_threshold": beyond,
        "observed_value": threshold if verified else None,
        "verified": verified,
    }


#: the three probes by the parameter they observe
PROBES = {
    DEADLINE_PROBE_PARAMETER: _deadline_probe,
    FRESHNESS_PROBE_PARAMETER: _freshness_probe,
    SKEW_PROBE_PARAMETER: _skew_probe,
}


def _record(
    *,
    name,
    value,
    observations,
    failures,
    configuration,
    extra=None,
    harness=None,
) -> dict:
    """One parameter's readback: the value a component was queried for, or the reason it was not.

    A value that was observed is recorded with the value the component actually holds, even when another
    consumer of the same value could not be queried: the record then carries the observation it took and
    the reason the proof is withheld. Only a value no component could be queried for is recorded with the
    value the phase computed, and then as `not_observable` - an observation is never invented.
    """

    base = {
        "configuration": dict(configuration),
        "configuration_sha256": canonical_sha256(configuration),
        **({} if harness is None else {"harness": dict(harness)}),
        **({} if not extra else dict(extra)),
    }
    if not observations:
        reason = "; ".join(failures) if failures else (
            f"{name} has no production component this readback can query"
        )
        return {
            "observed_value": value,
            "observation": NOT_OBSERVABLE,
            "verified": False,
            "component": None,
            "source": None,
            "reason": reason,
            **base,
        }
    primary = observations[0]
    record = {
        "observed_value": primary["value"],
        "observation": CONSTRUCTED_OBSERVATION,
        # a single unqueried consumer withholds the proof: the run must never certify a value one of the
        # components that reads it could not be asked about
        "verified": not failures and all(observation["value"] == value for observation in observations),
        "component": primary["component"],
        "source": primary["source"],
        **base,
    }
    also = {observation["source"]: observation["value"] for observation in observations[1:]}
    if also:
        record["also_observed"] = also
    if failures:
        record["reason"] = "; ".join(failures)
    return record


def observe_measured_readbacks(
    *,
    values,
    configuration,
    controller_factory=None,
    neck_port_factory=None,
    stop_criterion_factory=None,
) -> dict:
    """Observe the recorded measured values off the production components that consume them.

    `values` is the mapping of measured parameter names to the values the phases computed and the caller
    wants proven; `configuration` is the flat configuration the running controller is constructed with.
    Only the recorded keys are observed, so phase 6 can ask about its six while phase 7 asks about its
    five. Every observation is taken by constructing the installed component with the recorded value and
    reading the attribute its own code reads; the three factories exist so a test can put another
    component in the way, and a production caller leaves all three alone.

    A component that cannot be constructed leaves the values it would have observed unverified, with the
    exception recorded verbatim - never with an invented observation. A component that *is* constructed
    but holds another value is recorded with the value it actually holds, so the phase that consumes this
    record refuses the run with `CAL_EFFECTIVE_VALUE_MISMATCH`.
    """

    if not isinstance(values, Mapping) or not values:
        raise _refuse("the readback observes the measured values the phases computed, and none was given")
    unknown = sorted(set(values) - set(MEASURED_PARAMETERS))
    if unknown:
        raise _refuse(
            f"{unknown} are not among the eleven measured parameters, so no production component of this "
            f"readback consumes them"
        )

    controller_configuration = _controller_configuration(values, configuration)
    port_configuration = _port_configuration(values, configuration)
    observations: dict[str, list] = {name: [] for name in values}
    failures: dict[str, list] = {name: [] for name in values}
    harness = _harness()

    controller_parameters = [name for name in MEASURED_PARAMETERS if name in values and name in CONTROLLER_PARAMETERS]
    controller = None
    if controller_parameters:
        try:
            controller = _build_controller(controller_configuration, controller_factory)
        except Exception as error:  # noqa: BLE001 - an unobservable value is recorded, never faked
            reason = (
                f"the installed controller {CONTROLLER_MODULE}.{CONTROLLER_CLASS} could not be "
                f"constructed with the recorded values: {type(error).__name__}: {error}"
            )
            for name in controller_parameters:
                failures[name].append(reason)
        else:
            for name in controller_parameters:
                observations[name].append(
                    {
                        "component": f"{CONTROLLER_MODULE}.{CONTROLLER_CLASS}",
                        "source": f"{CONTROLLER_CLASS}(...).config[{name!r}]",
                        "value": controller.config[name],
                    }
                )
            if "coarse_step_rad" in controller_parameters:
                plan = getattr(controller, "plan", None)
                if plan is not None:
                    observations["coarse_step_rad"].append(
                        {
                            "component": f"{CONTROLLER_MODULE}.{CONTROLLER_CLASS}",
                            "source": "plan.coarse_step_rad",
                            "value": float(plan.coarse_step_rad),
                        }
                    )

    neck_parameters = [name for name in MEASURED_PARAMETERS if name in values and name in NECK_PORT_PARAMETERS]
    if neck_parameters:
        try:
            port = _build_neck_port(port_configuration, neck_port_factory)
        except Exception as error:  # noqa: BLE001 - an unobservable value is recorded, never faked
            reason = (
                f"the installed neck search port {NECK_PORT_MODULE}.{NECK_PORT_CLASS} could not be "
                f"constructed with the recorded values: {type(error).__name__}: {error}"
            )
            for name in neck_parameters:
                failures[name].append(reason)
        else:
            attributes = {
                "submit_lead_s": "lead",
                "stop_latency_s": "stop_timeout",
                "max_age_s": "max_age",
            }
            for name in neck_parameters:
                attribute = attributes[name]
                observations[name].append(
                    {
                        "component": f"{NECK_PORT_MODULE}.{NECK_PORT_CLASS}",
                        "source": f"neck_port.{attribute}",
                        "value": float(getattr(port, attribute)),
                    }
                )

    criterion_parameters = [
        name for name in MEASURED_PARAMETERS if name in values and name in STOP_CRITERION_PARAMETERS
    ]
    if criterion_parameters:
        try:
            criterion = _build_stop_criterion(port_configuration, stop_criterion_factory)
        except Exception as error:  # noqa: BLE001 - an unobservable value is recorded, never faked
            reason = (
                f"the installed stop criterion {STOP_CRITERION_MODULE}.{STOP_CRITERION_CLASS} could not "
                f"be constructed with the recorded values: {type(error).__name__}: {error}"
            )
            for name in criterion_parameters:
                failures[name].append(reason)
        else:
            attributes = {"stop_velocity_rad_s": "stop_velocity", "max_age_s": "max_age"}
            for name in criterion_parameters:
                attribute = attributes[name]
                observations[name].append(
                    {
                        "component": f"{STOP_CRITERION_MODULE}.{STOP_CRITERION_CLASS}",
                        "source": f"stop_criterion.{attribute}",
                        "value": float(getattr(criterion, attribute)),
                    }
                )

    probes: dict[str, dict] = {}
    for name, probe in PROBES.items():
        if name not in values:
            continue
        try:
            probes[name] = probe(controller_configuration, controller_factory)
        except Exception as error:  # noqa: BLE001 - an unrun probe is recorded, never faked
            probes[name] = {
                "probe": name,
                "skipped": f"{type(error).__name__}: {error}",
                "observed_value": None,
                "verified": None,
            }
        if probes[name].get("verified") is False:
            failures[name].append(f"the {probes[name]['probe']} probe did not observe the value")

    readbacks = {}
    for name in MEASURED_PARAMETERS:
        if name not in values:
            continue
        extra = {}
        probe = probes.get(name)
        if probe is not None:
            extra["behavioural"] = probe
        controller_record = name in CONTROLLER_PARAMETERS
        readbacks[name] = _record(
            name=name,
            value=values[name],
            observations=observations[name],
            failures=failures[name],
            configuration=(controller_configuration if controller_record else port_configuration),
            extra=extra,
            harness=(None if controller_record else harness),
        )
    return readbacks

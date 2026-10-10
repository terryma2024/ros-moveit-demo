"""RED: the neck sweep must be the bounded stop-point sequence of the plan's required domain.

HS-286 pins the violation: `HeadSearchController` still walks a forward-cumulative revolution - the
`2 * math.pi` branch of `src/act/search.py` - whenever the sealed plan is not handed to it in the exact
opt-in key pair the controller happens to recognise. The design (section 7, "coarse sweep trajectory")
fixes the trajectory instead: per anchor, first to the NEARER endpoint of `required_search_domain_rad`,
then one reversal to the other endpoint, with `coarse_step_rad` never carrying a stop past the endpoint.
Coverage is the union of the stops' field-of-view intervals, never an accumulated angle of `2*pi`, and the
outcome is the clean `TARGET_NOT_FOUND` only once that coverage is complete (design section 8.2).

Nothing here touches hardware, ROS or MuJoCo: the controller is a pure state machine driven with settled
feedback and an empty detection list.
"""

from __future__ import annotations

from so101_demo.act.head_search_domain import TARGET_NOT_FOUND
from so101_demo.act.search import HeadSearchController

#: the seal tolerance: a stop that reaches an endpoint may be a rounding error away from it
TOL = 1e-9
#: the shipped seal values this fixture is built from; the required domain is the one the exit test uses
ANCHORS = {"default": 0.1, "left": -0.4, "forward": 0.35}
ANCHOR = "default"
REQUIRED_DOMAIN = (-0.29145679447786704, 0.540419500270584)
HORIZONTAL_FOV_RAD = 1.3121067481206794
#: 0.2 rad does not divide either leg of the required domain (0.3915 rad and 0.8319 rad), so the last stop
#: of each leg is exactly the endpoint: a cumulative `coarse_angle += step` would overshoot it instead
COARSE_STEP_RAD = 0.2
#: narrower than the required domain at the low end, so the clamp - not luck - keeps every stop valid
LOCK_VALID_NECK_RAD = (-0.15, 1.35)
#: the name the controller reads today (see test_act_head_search_domain.py); the seal spells the same
#: declaration `required_search_domain_rad`, which test 06 pins as additionally accepted
DOMAIN_KEY = "required_domain_rad"
SEALED_DOMAIN_KEY = "required_search_domain_rad"


def _plan(*, with_safe_interval: bool = False) -> dict:
    """The sealed plan for one anchor: the anchors it declares and the required search domain."""

    plan = {
        "anchor": ANCHOR,
        "anchors": {name: {"neck_rad": value} for name, value in ANCHORS.items()},
        "required_search_domain_rad": list(REQUIRED_DOMAIN),
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "coarse_step_rad": COARSE_STEP_RAD,
    }
    if with_safe_interval:
        plan["lock_valid_neck_rad"] = list(LOCK_VALID_NECK_RAD)
    return plan


def _anchor_rad(plan: dict) -> float:
    return plan["anchors"][plan["anchor"]]["neck_rad"]


def _nearer_endpoint_first(plan: dict) -> tuple[float, float]:
    """The required-domain endpoints in the order the design's trajectory visits them."""

    low, high = plan["required_search_domain_rad"]
    anchor = _anchor_rad(plan)
    return (low, high) if abs(anchor - low) <= abs(high - anchor) else (high, low)


def _config(plan: dict, *, domain_key: str = DOMAIN_KEY) -> dict:
    """The controller config for the plan: the declared anchor plus the declared required domain."""

    config = {
        "attempt_id": "attempt",
        "session_id": "session",
        "search_start_rad": _anchor_rad(plan),
        "horizontal_fov_rad": plan["horizontal_fov_rad"],
        "coarse_step_rad": plan["coarse_step_rad"],
        "search_timeout_s": 60.0,
        "max_age_s": 0.1,
        "max_skew_s": 0.05,
        "settle_velocity_rad_s": 0.1,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 20.0,
        "vertical_bounds_px": [100.0, 380.0],
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 3,
        "max_fine_total_rad": 0.5,
        "frame_id": "camera",
        "ray_origin_frame_id": "base",
        domain_key: list(plan["required_search_domain_rad"]),
    }
    if "lock_valid_neck_rad" in plan:
        config["lock_valid_neck_rad"] = list(plan["lock_valid_neck_rad"])
    return config


def _emitted_stops(
    plan: dict, *, domain_key: str = DOMAIN_KEY, max_ticks: int = 200
) -> tuple[list[float], dict | None]:
    """Drive the production loop and collect the neck stops it commands.

    The feedback follows the last commanded stop and reports zero velocity, so the next tick is settled and
    the state machine advances; no detection is ever offered, so the search can only sweep or terminate.
    """

    controller = HeadSearchController(_config(plan, domain_key=domain_key))
    yaw = _anchor_rad(plan)
    stops: list[float] = []
    terminal = None
    now = 0.0
    for _ in range(max_ticks):
        now += 0.05
        stamp = 1.0 + now
        frame = {
            "session_id": "session",
            "attempt_id": "attempt",
            "frame_id": "camera",
            "sim_time_s": stamp,
            "received_wall_s": now,
            "detections": [],
            "k": [320.0, 240.0, 320.0, 240.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
            "rotation_optical_to_base": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0],
        }
        feedback = {
            "session_id": "session",
            "attempt_id": "attempt",
            "sim_time_s": stamp,
            "received_wall_s": now,
            "neck_yaw_rad": yaw,
            "neck_velocity_rad_s": 0.0,
            "safe_observe": True,
        }
        out = controller.tick(frame, feedback, now)
        if "neck_target_rad" not in out:
            terminal = out
            break
        commanded = out["neck_target_rad"]
        if out["stop"] is not True and (not stops or abs(commanded - stops[-1]) > TOL):
            stops.append(commanded)
            yaw = commanded
    return stops, terminal


def test_01_every_emitted_target_stays_inside_the_required_search_domain() -> None:
    """A coarse step must never carry a stop past the endpoint the plan declared."""

    plan = _plan()
    low, high = plan["required_search_domain_rad"]
    stops, _ = _emitted_stops(plan)

    assert stops, "the controller never commanded a stop"
    outside = [stop for stop in stops if not low - TOL <= stop <= high + TOL]
    assert not outside, (
        f"the sweep left the required domain ({low}, {high}) with coarse_step_rad="
        f"{plan['coarse_step_rad']}: {len(outside)} of {len(stops)} stops are outside it, "
        f"first {outside[0]} and furthest {max(outside, key=lambda stop: abs(stop - low))}"
    )


def test_02_the_first_stop_moves_to_the_nearer_endpoint_then_reverses_once() -> None:
    """The sequence is two monotone legs: anchor -> nearer endpoint -> farther endpoint."""

    plan = _plan()
    anchor = _anchor_rad(plan)
    nearer, farther = _nearer_endpoint_first(plan)
    stops, _ = _emitted_stops(plan)

    assert stops, "the controller never commanded a stop"
    assert abs(stops[0] - nearer) < abs(anchor - nearer), (
        f"the first stop {stops[0]} does not move from the anchor {anchor} toward the nearer endpoint "
        f"{nearer} (the other endpoint is {farther})"
    )
    reached = next(
        (index for index, stop in enumerate(stops) if abs(stop - nearer) <= TOL), None
    )
    assert reached is not None, (
        f"the sweep never reached the nearer endpoint {nearer}; it commanded {stops}"
    )
    first_leg, second_leg = stops[: reached + 1], stops[reached:]
    assert first_leg == sorted(first_leg) or first_leg == sorted(first_leg, reverse=True), (
        f"the first leg is not monotone toward the nearer endpoint {nearer}: {first_leg}"
    )
    assert second_leg == sorted(second_leg), (
        f"the reversal at {nearer} is not monotone toward the farther endpoint {farther}: {second_leg}"
    )
    assert abs(second_leg[-1] - farther) <= TOL, (
        f"after reversing at {nearer} the sweep ended at {second_leg[-1]}, not at the farther endpoint "
        f"{farther}"
    )


def test_03_two_constructions_emit_the_same_deterministic_stop_sequence() -> None:
    """The same plan must always produce the same stops, in the same order."""

    first, first_terminal = _emitted_stops(_plan())
    second, second_terminal = _emitted_stops(_plan())

    assert first == second, f"two constructions of the same plan disagree: {first} != {second}"
    assert (first_terminal or {}).get("status") == (second_terminal or {}).get("status")


def test_04_a_covered_domain_without_a_candidate_reports_not_found() -> None:
    """Only a complete coverage earns the clean negative; the sweep must not run on past the domain."""

    plan = _plan()
    low, high = plan["required_search_domain_rad"]
    stops, terminal = _emitted_stops(plan)

    assert terminal is not None, (
        f"the search never terminated; it was still commanding at {stops[-1]} after {len(stops)} stops"
    )
    assert terminal["found"] is False
    assert terminal["status"] == TARGET_NOT_FOUND, (
        f"a domain the stops cover must end in {TARGET_NOT_FOUND}, not {terminal['status']}: the sweep "
        f"commanded {len(stops)} stops from {stops[0]} to {stops[-1]}, while the required domain is "
        f"({low}, {high})"
    )
    assert min(stops) >= low - TOL and max(stops) <= high + TOL, (
        f"the not-found verdict came after leaving the required domain ({low}, {high}): "
        f"the sweep ran from {min(stops)} to {max(stops)}"
    )


def test_05_every_emitted_target_satisfies_the_declared_valid_neck_interval() -> None:
    """When the plan declares `lock_valid_neck_rad`, no stop may leave it."""

    plan = _plan(with_safe_interval=True)
    low, high = plan["required_search_domain_rad"]
    safe_low, safe_high = plan["lock_valid_neck_rad"]
    stops, _ = _emitted_stops(plan)

    assert stops, "the controller never commanded a stop"
    outside = [stop for stop in stops if not safe_low - TOL <= stop <= safe_high + TOL]
    assert not outside, (
        f"stops left the declared valid neck interval ({safe_low}, {safe_high}): {outside}"
    )
    assert all(low - TOL <= stop <= high + TOL for stop in stops), (
        f"a stop inside the safe interval still left the required domain ({low}, {high}): {stops}"
    )


def test_06_the_controller_accepts_the_sealed_plan_declaration() -> None:
    """The seal declares the domain as `required_search_domain_rad`; that declaration must be honoured."""

    plan = _plan(with_safe_interval=True)
    sealed, _ = _emitted_stops(plan, domain_key=SEALED_DOMAIN_KEY)
    existing, _ = _emitted_stops(plan, domain_key=DOMAIN_KEY)

    assert sealed == existing, (
        f"the sealed declaration {SEALED_DOMAIN_KEY} and {DOMAIN_KEY} produce different sweeps: "
        f"{sealed} != {existing}"
    )

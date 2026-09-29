"""A nine-phase case through the PORT, driven by the production runner.

The only substituted layer is the boundary underneath the port - the ROS/MuJoCo/controller surface - which is where
every other test in this batch draws the line: the port, the phase routing, the validators and the runner's own verifier
are production code, and the boundary supplies the runtime seams (a planning scene, a controller stop, a tool pose, a
retreat axis and an IK solver) plus the readback.

This file grows one phase at a time on purpose. SEARCH first, because every later phase's documents are stamped against
the case scope the port binds here; then the other eight, each with the run's own verifier as the judge.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_act_pick_place_approach_path_screen import physical_inputs  # noqa: E402
from test_act_task8_case_documents import _case  # noqa: E402
from test_act_task8_search_port import (  # noqa: E402
    ATTEMPT, SESSION, bind, fixture, request as port_request,
)

from so101_demo.act.pick_place_runner import PickPlaceRunner  # noqa: E402

from so101_demo.adapters.act.pick_place_search_boundary import PickPlaceSearchBoundary  # noqa: E402
from so101_demo.adapters.act.pick_place_search_port import (  # noqa: E402
    PickPlaceSearchPhasePort,
)
from so101_demo.ports.evidence import PoseEvidence  # noqa: E402

#: every production method the port may call on the boundary when the runtime is substituted
_BOUND = ("_checked_aggregates", "sequence_facts", "sequence_phase", "execute_approach", "_close_facts",
          "_motion_facts", "_release_facts", "_gripper_open_rad", "set_down", "release_preflight",
          "run_retreat_segment", "planning_attached", "detach_moveit", "current_readback")


def _receipt(prefix, ticket):
    """A real receipt from the production issuing authority: the prover checks its type, not its shape."""

    from so101_demo.act.prefix_source import SOURCE_KEYS, PrefixSourceAuthority

    authority = PrefixSourceAuthority(ticket_guard=lambda item: None, max_observation_age_s=10.0,
                                      max_prefix_age_s=10.0, monotonic=lambda: 1.36)
    source = {"session_id": ticket[3], "attempt_id": ticket[4], "reset_epoch": 2, "phase": "SEARCH",
              "physics_step": 9, "simulation_time_s": prefix["observation_time_s"],
              "observation_sha256": "ae" * 32, "source_received_wall_s": {key: 1.0 for key in SOURCE_KEYS}}
    return authority.issue(ticket=ticket, prefix=prefix, source=source, source_kind="EXPERT_ROUTE",
                           source_artifact_sha256="ac" * 32, contact_policy_fingerprint="ad" * 32)


def _boundary(*, session_id, attempt_id):
    """The substituted runtime, carrying the REAL boundary methods.

    The distinction matters: the seams below are the ROS/MuJoCo/controller surface, and everything the port asks for on
    top of them is production code, so a nine-phase run cannot agree with itself about what a phase's evidence is.
    """

    boundary, calls, _capture, _request = _case()
    boundary._gate_facts = PickPlaceSearchBoundary._gate_facts      # staticmethod: assigned
    for name in _BOUND:
        setattr(boundary, name, MethodType(getattr(PickPlaceSearchBoundary, name), boundary))
    boundary.reset.sources.session_id = session_id
    boundary.reset.sources.phase = "SEARCH"
    boundary.reset_epoch = boundary.reset.receipt.new_epoch
    boundary.reset.release_epoch = 0
    boundary.calls = calls
    return boundary


def test_the_scaffold_binds_every_production_method_the_port_calls():
    """A guard for the file itself: a missing binding would show up as a refusal in a later phase, not here."""

    boundary = _boundary(session_id="session-1", attempt_id="attempt-1")
    boundary._gate_facts = PickPlaceSearchBoundary._gate_facts   # a staticmethod: assigned, not bound
    for name in _BOUND:
        assert callable(getattr(boundary, name)), name
    assert isinstance(boundary, SimpleNamespace)


def test_the_port_is_the_object_under_test_not_a_double():
    boundary = _boundary(session_id="session-1", attempt_id="attempt-1")
    port = PickPlaceSearchPhasePort.__new__(PickPlaceSearchPhasePort)
    for name in ("_boundary_capability", "_support_distance", "set_down", "release_preflight", "run_retreat_segment",
                 "detach_moveit", "planning_attached"):
        setattr(port, name, MethodType(getattr(PickPlaceSearchPhasePort, name), port))
    port.boundary = boundary
    port._support_distance_max_m = 0.02
    port._motion_template, port._motion_duration_s = object(), 0.4
    # every delegation reaches the boundary rather than re-implementing it
    port.planning_attached({"session_id": "session-1", "attempt_id": "attempt-1"})


def test_the_runner_drives_the_real_port_through_the_search_phase():
    """The first phase end to end: the runner's own request keys, the port's own begin, the port's SEARCH path.

    Nothing here is new machinery - the SEARCH port fixture already builds a working port against a substituted
    boundary, and this test puts the production RUNNER on top of it. If the runner and the port disagree about the
    request shape or the evidence keys, that disagreement is what this asserts against.
    """

    port, events = fixture()
    bind(port)
    runner = PickPlaceRunner(port)
    request = dict(port_request())
    result = runner.run({
        # a phase-prefix case is a FULL_RESTART by the runner's own rule: a prefix may not be run against a stack that
        # someone else's case left in an unknown state
        "mode": "phase_prefix", "stop_after": "SEARCH", "lifecycle": "FULL_RESTART",
        "scenario_id": request["scenario_id"] if "scenario_id" in request else "scenario-1",
        "session_id": SESSION, "attempt_id": ATTEMPT,
        "deadline_ns": runner.clock_ns() + 60_000_000_000,
    })
    print("[probe] runner result:", {key: str(value)[:60] for key, value in result.items()}
          if isinstance(result, dict) else type(result).__name__)
    assert isinstance(result, dict) and result, "the runner returns a case result, not an empty document"


from so101_demo.adapters.act.visible_approach_expert_route import VisibleApproachExpertRoute  # noqa: E402


class _World:
    """The substituted world, which REMEMBERS what the phases did to it.

    A stand-in that returns the same readback for every phase is refused by the validators, and correctly so: a real
    world changes when a gripper closes, an arm lifts and a gripper opens. This one models exactly that and nothing
    more - on the table, grasped, lifted, released - and it classifies a gripper command by comparing its target
    against the two values the case admits (the closed position and the model's own open limit), never by magnitude.
    """

    def __init__(self, *, closed_rad, open_rad, template=None):
        self.template = template
        self.stage = "on_table"
        self.lift_m = 0.0
        self._closed_rad, self._open_rad = closed_rad, open_rad

    def note_dispatch(self, kind, goal):
        if kind == "gripper":
            target = goal["positions"][1][0]
            if target == self._closed_rad:
                self.stage = "grasped"
            elif target == self._open_rad:
                self.stage = "released"
        elif kind == "arm" and self.stage == "grasped":
            self.stage = "lifted"

    @property
    def grasped(self):
        return self.stage in ("grasped", "lifted")

    @property
    def released(self):
        return self.stage == "released"


class _Route(VisibleApproachExpertRoute):
    """The expert route, substituted but of the REAL type: the port checks `isinstance` when it builds one.

    An instance is made without running the production constructor (`object.__new__`), because the constructor's job is
    to admit a candidate from a pinned manifest - which is the seal's business, not this run's - while the type is what
    the port's own check demands and what keeps the substitution honest about which layer is replaced.
    """

    manifest = {"policy_fingerprint": "ad" * 32, "candidate_profile_sha256": "af" * 32,
                "contact_scope_sha256": "ba" * 32, "checker_sha256": "bb" * 32, "expected_samples": 51}

    def __init__(self, prefix):
        self._prefix = prefix

    def prepare(self, observed, *, selected_source, owner_ticket, active_policy_fingerprint):
        return {"kind": "VISIBLE_APPROACH_EXPERT_PREPARATION", "prefix": self._prefix,
                "selected_source": selected_source, "owner_ticket": owner_ticket,
                "source_artifact_sha256": "ac" * 32, "policy_fingerprint": "ad" * 32,
                "command_authority": False, "eligible_for_collection": False}

    def qualify(self, prepared, proof, *, current_snapshot):
        return {"ok": True, "kind": prepared["kind"], "status": proof.status}


class _PrefixExecutor:
    """The broker's paired execution, substituted: approve, submit, wait, and the two documents it owns."""

    def __init__(self, prefix, proof_snapshot):
        self._prefix = prefix
        self._snapshot = proof_snapshot
        self.approvals = []

    def approve_with_source(self, ticket, prefix, receipt):
        self.approvals.append((ticket, receipt.source_kind))
        return "PERMIT"

    def submit(self, ticket, prefix, permit):
        return 42

    def wait_for(self, ticket, goal_id):
        return None

    def time_axis(self, ticket, goal_id):
        """The two times the path's axis needs, taken from the prefix being EXECUTED.

        P1-4 piece 4: they used to be the literals `1.30`/`1.32` while the case's clock now runs to about 1.7 s, so the
        observed axis `bridge <= observation < start < first target` could not hold - a fixed value for a quantity that
        belongs to the run. Reading them from the plan keeps the axis true by construction.
        """

        origin = self._prefix.get("observation_time_s") if isinstance(self._prefix, dict) else None
        if not isinstance(origin, (int, float)) or isinstance(origin, bool):
            return {"bridge_time_s": 1.30, "start_time_s": 1.32}
        return {"bridge_time_s": origin - 0.05, "start_time_s": origin + 0.05}

    def snapshot(self, ticket, goal_id):
        """The document the checker hashes, with the two times taken from the SAME plan the axis reports.

        P1-4 piece 4: the checker refuses a snapshot whose `controller_start_time_s` / `controller_bridge.time_s`
        differ from the request's axis (`PATH_SOURCE_TIME_CHANGED`) - and those were the literals 1.32 / 1.30 while the
        case's clock now runs past 1.7 s. Two hardcoded times for quantities that belong to the run: they come from
        the plan here, exactly as `time_axis` does, so the two cannot disagree.
        """

        origin = self._prefix.get("observation_time_s") if isinstance(self._prefix, dict) else None
        if not isinstance(origin, (int, float)) or isinstance(origin, bool):
            return self._snapshot
        document = dict(self._snapshot)
        document["controller_start_time_s"] = origin + 0.05
        bridge = dict(document.get("controller_bridge") or {})
        bridge["time_s"] = origin - 0.05
        document["controller_bridge"] = bridge
        return document


def _proof_snapshot(checker):
    """The snapshot the prover hashes - the paired execution's own document, shaped as path_proof reads it."""

    return {"model_sha256": checker.model_sha256,
            "model_qpos": [0.0] * checker.model.nq, "model_qvel": [0.0] * checker.model.nv,
            "phase": "APPROACH", "holding_state": "EMPTY", "cup_in_gripper_transform": None,
            "controller_start_time_s": 1.32,
            "controller_start_positions": [0.0] * 6, "controller_start_velocities": [0.0] * 6,
            "controller_bridge": {"time_s": 1.30,
                                  "point": {"positions": [0.0] * 6, "velocities": [0.0] * 6,
                                            "accelerations": [0.0] * 6}}}


#: the case's own identity, which the runner's request carries and the window must agree with
SCENARIO = "scenario-1"


def _case_window(tmp_path, *, case_id):
    """The live-evidence window bound to THIS case's identity.

    The window is not interchangeable between cases: its identity is what the port's feed is checked against, so a
    helper that hardcodes one case's identity would be the wrong thing to borrow (the mismatch it produces is the
    system working).
    """

    from so101_demo.act.task8_live_evidence import LiveEvidenceWindow, Task8LiveEvidenceRecorder

    recorder = Task8LiveEvidenceRecorder(case_id=case_id, evidence_root=tmp_path,
                                         session_id=SESSION, attempt_id=ATTEMPT)
    window = LiveEvidenceWindow(
        recorder,
        identity={"case_id": case_id, "session_id": SESSION, "attempt_id": ATTEMPT,
                  # P1-4: the identity is the epoch the case ENDS in. The samples span 0 (before RELEASE) and 1
                  # (after it), which the recorder's rule allows; the identity is the terminal one.
                  "reset_epoch": 2, "release_epoch": 1},
        period_s=0.1, tolerance_s=0.01)
    return recorder, window


def _wide_prefix(prefix):
    # The contract puts every target on a grid: `t == observation_time_s + delay + interval * (i + 1)`. Widening the
    # window therefore means DECLARING the wider interval, not inventing a free-standing time - a target of 60.0 s
    # is refused by name (PREFIX_TIME_GRID_INVALID) because it is not on the grid the document implies.
    # the delay is a fixed convention (0.1 s exactly - any other value is PREFIX_FIRST_TARGET_DELAY_INVALID), and the
    # target sits on the declared grid: origin + delay + interval * 1
    interval, delay = 0.002, 0.1
    # P1-4 piece 4: the window must cover the CASE, because the capture clock is now monotonic and is no longer
    # wrapped to stay inside it. The contract puts every target on the declared grid and refuses more than 600 of
    # them (`PREFIX_SAMPLE_BUDGET`), so 600 is the widest window this contract allows - 0.1 + 1.2 = 1.3 s.
    count = 600
    origin = prefix["observation_time_s"]
    # and the POSITIONS must match the times row for row: widening the window without widening the rows is
    # `PREFIX_INVALID`, which the APPROACH path reported as a wrapped "execution" failure until the cause was read
    rows = tuple(prefix["positions"])
    if not rows:
        raise ValueError("the fixture's prefix carries no positions to widen")
    return {**prefix, "target_interval_s": interval, "first_target_delay_s": delay,
            "target_times_s": tuple(origin + delay + interval * (index + 1) for index in range(count)),
            "positions": tuple(rows[index % len(rows)] for index in range(count))}

def _open_limit(screen):
    """The gripper's open position, read from the model's own joint range - the same source the boundary uses."""

    import mujoco

    from so101_demo.act.joints import ARM_JOINTS

    model = screen.path_checker.model
    joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, ARM_JOINTS[5])
    low, high = (float(value) for value in model.jnt_range[joint])
    return high if abs(high) >= abs(low) else low


def _issue_prefix_source(*, ticket, prefix, source, **kwargs):
    """Refresh the prefix to THIS plan's observation, sign it, and freeze it.

    The two requirements meet here and nowhere else: the receipt names `prefix_sha256(checked)`, so the prefix must not
    move after signing - and the header stamp (the readback's `sim_time_s`) must fall inside the prefix's ~0.102 s
    window, so the prefix must be current AT signing. The boundary hands down the case's frozen selected source, built
    from the SEARCH observation, so its own time is the plan's observation: refreshing from it and then signing is what
    production does (a plan is prepared, its prefix signed, and executed), and it is the only shape that satisfies both.
    """

    # the prefix was refreshed by the last readback (with a LEAD, so the window can contain the header the boundary
    # takes from its OWN next capture); this seam therefore does not move it again - it signs what will be executed
    receipt = _receipt(prefix, ticket if isinstance(ticket, tuple) else (7, "owner-key", "act", SESSION, ATTEMPT))
    _case_capture.prefix_signed = True
    return receipt


def _full_case_port(tmp_path):
    """ONE case's runtime: the real model and its readback, plus the four members the SEARCH path needs.

    The earlier version stapled two fixtures together and the validators refused it - correctly, because a case has one
    model, one session and one epoch (CP-1541). Here the model and the readback come from the batch's own fixture (whose
    scope checks already pass), and only the SEARCH entry points are borrowed from the port suite's pattern, because
    they are the ROS surface: begin, search, safe_stop, and the neck sweep checker.
    """

    boundary, calls, _capture, _request = _case()
    screen, prefix, _goals, _checks, sources, _driver, _owner, _events, _qpos, _qvel = physical_inputs()
    # P1-4 piece 4: ONE construction site for the plan. The executor (which reports the path's time axis), the route
    # (which executes it) and the readback (which refreshes it) must all hold the SAME object - building it twice left
    # the executor on a copy that the refresh never reached, which is how a shared quantity turns into two.
    wide_prefix = _wide_prefix(prefix)
    _reset_case_clock()          # this case gets its own sequence, not the previous test's
    from test_act_task8_search_port import observation

    observed = observation()
    # the SEARCH observation's readback is the document the port validates, and it must be THIS case's: the fixture's
    # RGB frames and search result describe the geometry, while the physical readback comes from the case's own capture
    # - real model digest, real qpos/qvel, this session and epoch. The earlier version patched three keys of another
    # fixture's readback, which is how a stand-in ends up describing a world nobody is running.
    digest = screen.path_checker.model_sha256
    model = screen.path_checker.model
    capture = _case_capture(sources, prefix, boundary)
    readback = observed.physical_readback
    # the two documents are NOT the same document: SEARCH's raw carries SEVEN wall receipts (world, scene, contact and
    # the four sensor streams), while a sequence phase's snapshot carries the four RGB stamps the phase validator
    # compares. Overwriting one with the other is what produced "physical receipt schema" - so the receipts stay as
    # SEARCH's own and only the readback's physical members are replaced.
    # The rule, read rather than guessed: the RGB stamps must satisfy `0 <= world_time - stamp <= skew`, so they belong
    # to the READBACK's clock and must advance with it - while `source_received_wall_s` is SEARCH's own seven-key wall
    # receipt map and must be left alone. Excluding both is what kept a stale 1.2 stamp against a 1.31 world clock.
    readback.update({key: value for key, value in capture.items() if key != "source_received_wall_s"})
    readback["scene"] = {**capture["scene"], "model_sha256": digest,
                         "qpos": tuple(float(value) for value in model.qpos0),
                         "qvel": (0.0,) * model.nv}
    readback["world"] = capture["world"]

    # the case manifest the port selects its candidate from: one FULL case, matching the runner's own request, with a
    # non-default anchor so the route comes from the factory (a "default" anchor would require a trusted source port)
    boundary.reset.manifest = {
        # the case-level policy fingerprint the route's own manifest must agree with, and the candidate list the port
        # selects from: one FULL case matching this request, with a non-default anchor so the factory builds the route
        "contact_policy_fingerprint": "ad" * 32,
        "prefix_cases": (),
        "full_cases": ({"case_id": SCENARIO, "mode": "full", "stop_after": None, "lifecycle": "FULL_RESTART",
                        "contact_policy_fingerprint": "ad" * 32, "anchor": "route"},),
    }
    boundary.begin = lambda item: {"session_id": item["session_id"], "attempt_id": item["attempt_id"],
                                   "reset_epoch": 2, "release_epoch": 0, "full_restart": False}
    boundary.search = lambda item: observed
    boundary.safe_stop = lambda reason, item: True
    # the sweep checker needs the neck joint's index as well as its step: the port reads `neck_qpos` to decide which
    # joint it is sweeping, exactly as the port suite's own sweep double supplies it
    boundary.neck_sweep_checker = SimpleNamespace(step_s=0.002, neck_qpos=0,
                                                  check=lambda *args, **kwargs: True)
    boundary.reset.sources.contact_pairs.fingerprint = "ad" * 32
    boundary.reset.sources.capture = lambda *args, **kwargs: _case_capture(sources, prefix, boundary)
    # The grid's rule is that consecutive samples are exactly one period apart, and the port feeds it once per phase -
    # so the substituted world's clock advances one period per READBACK, which the boundary owns.
    clock = {"count": 0, "base": None}

    def _current_readback(request):
        # the counter advances BEFORE the capture: `_case_capture` reads it to stamp the readback, so advancing it
        # afterwards meant two phases saw the same instant (measured: step 4 -> 7 with `sim_time_s` fixed at 1.4,
        # which the grid refuses as a regression)
        clock["count"] += 1
        _case_clock["count"] += 1
        raw = _case_capture(sources, prefix, boundary)
        # P1-4 piece 4: ONE clock. This readback used to compute its own - `0.002 * (1 + count % 40)`, wrapping every
        # 40 readbacks - while `_case_capture` advanced a different one and the grid wanted 0.1 s per sample. **Three
        # clocks, and the fixture's own comment called two of them "on purpose".** The readback now carries the time
        # `_case_capture` produced, so the source clock, the grid's cadence and the plan's window are one sequence.
        moment = raw["world"].simulation_time_s      # the instant this sample carries, from the one sequence
        stamps = {name: moment for name in ("head", "wrist", "arm", "neck")}
        return {**raw,
                "world": dataclasses.replace(raw["world"], simulation_time_s=moment),
                "scene": {**raw["scene"], "simulation_time_s": moment},
                "contact": {**raw["contact"], "simulation_time_s": moment},
                "observation": {**raw["observation"], "sim_time_s": moment},
                "reference": {**raw["reference"], "requested_sim_time_s": moment},
                "source_stamps_s": stamps, "source_received_wall_s": dict(stamps)}

    boundary.current_readback = _current_readback
    # and on the boundary the PORT actually holds: the probe showed `PickPlaceSearchBoundary.current_readback` (the
    # production method) being called instead, which returned a cached readback - so the clock never advanced and two
    # phases reported one instant (`GRID_REGRESSION`). One object, named once (CP-1699's family again).
    # the readback's own tolerance and skew: the substituted runtime supplies them, as the port suite's own double does
    boundary.reset.sources.readback.joint_tolerance = 0.002
    boundary.reset.sources.readback.max_skew = 0.02
    # the monotonic clock must be LATER than the wall receipts the readback carries (the fixture stamps them at 10 s),
    # or a receipt that arrives in the future is refused - "RGB source skew" was exactly that
    boundary.reset.sources.monotonic = lambda: 100.0
    boundary.reset.sources.session_id = SESSION
    # the prover reports the checker's step and clearance, so the substituted checker supplies them as the fixture's
    # own does in the path-screen suite
    screen.path_checker.step, screen.path_checker.clearance = 0.002, 0.01
    boundary.approach_screen = screen
    # the planning scene is STATEFUL, like the world: it holds the cup until the run detaches it, and the detach is
    # readable - the set-down document must report an attachment, and the release must happen without one
    _scene = {"attached": True}
    boundary.planning_scene = SimpleNamespace(is_attached=lambda: _scene["attached"],
                                              detach=lambda: _scene.update(attached=False))
    boundary.controller_stop = lambda request: True
    boundary.tool_pose = lambda request: PoseEvidence((0.2, -0.2, 0.2), (0.0, 0.0, 0.0, 1.0))
    boundary.retreat_axis = lambda direction: {"radial": (1.0, 0.0, 0.0), "vertical": (0.0, 0.0, 1.0)}[direction]
    boundary.motion_target_joints = lambda target: (0.5,) * 5
    # the substituted world is told about every command, which is what makes it a faithful stand-in: the phases change
    # it, and the readback they are judged against reflects that change
    from test_dynamic_pick import _template as _case_template

    _world = _World(closed_rad=0.2, open_rad=_open_limit(screen), template=_case_template())
    _case_capture.world = _world
    boundary.reset.broker = SimpleNamespace(
        dispatch=lambda ticket, kind, goal: (_world.note_dispatch(kind, goal), 7)[1],
        driver=SimpleNamespace(wait=lambda gid: None),
        ownership=SimpleNamespace(ticket=lambda *parts: (7, "owner-key", "act", SESSION, ATTEMPT)),
        # the WIDENED prefix, the same object the route executes against: the executor reads its time axis from the plan
        # it is running, and handing it the narrow one made it fall back to fixed literals (P1-4 piece 4)
        prefix_executor=_PrefixExecutor(wide_prefix, _proof_snapshot(screen.path_checker)),
        _prefix_source_port=SimpleNamespace(register=lambda *args, **kwargs: None),
        # the receipt is issued against the prefix the caller actually passes down: signing a different (narrower)
        # prefix is what raised PATH_SOURCE_RECEIPT_INVALID, because the prover compares the digest it is handed
        # P1-4 piece 4: signing the prefix FREEZES it. The receipt names `prefix_sha256(checked)`, so a prefix that
        # moves after the signature stops matching the prefix being executed - `PATH_SOURCE_RECEIPT_INVALID` - and the
        # refresh below is therefore bounded by this moment, exactly as production bounds it (a plan is prepared, its
        # prefix signed, and then executed).
        issue_prefix_source=_issue_prefix_source)
    boundary.reset.act_context = {"lease_token": "lease-1"}
    boundary.reset.receipt = SimpleNamespace(new_epoch=2)
    boundary.screen = screen
    boundary.prefix = prefix
    boundary._release_epoch, boundary._set_down_step = 0, None

    from so101_demo.adapters.act.pick_place_readback import capture_evidence_fields

    boundary.canonical_evidence = lambda captured, *, support_distance_max_m, raw_records: capture_evidence_fields(
        captured, support_distance_max_m=support_distance_max_m, raw_records=raw_records,
        end_effector_position_m=boundary.tool_pose({}).position_m)
    boundary._gate_facts = PickPlaceSearchBoundary._gate_facts   # a staticmethod: assigned, not bound
    for name in _BOUND:
        setattr(boundary, name, MethodType(getattr(PickPlaceSearchBoundary, name), boundary))

    # The factory is the route source for a "default" anchor ONLY (the port's own condition), so a non-default anchor -
    # which is what this case declares - takes its route by direct assignment, and `begin` does not replace it: the only
    # other assignment is in `begin`'s failure path. That distinction cost two rounds and is now written down.
    # the RECORDER goes in at construction because the seal goes through it; the WINDOW is bound afterwards
    recorder, window = _case_window(tmp_path, case_id=SCENARIO)
    port = PickPlaceSearchPhasePort(boundary, evidence_recorder=recorder)
    port.bind_startup_receipt({"schema_version": 1, "session_id": SESSION,
                               "stack_owner": {"pid": 1}, "child_owner": {"pid": 2}})
    route = _Route.__new__(_Route)
    # the prefix's window is the trajectory's timing, and this case's clock advances one period per sample so
    # the grid can satisfy the recorder: a window ending at 1.4 s falls behind the case's own clock and every
    # APPROACH goal stamp is refused (APPROACH_HEADER_STAMP_INVALID). This opens it wide enough for the run.

    route.__init__(wide_prefix)
    # and THIS is the object a case executes against: the widened prefix the route holds, not the narrow one it came
    # from - refreshing the wrong dict was why the header stamp kept failing (the check reads the prefix it is given)
    _case_capture.prefix = wide_prefix
    port._expert_route = route
    # the WINDOW is bound here, and with it the case's admitted support distance: the distance
    # travels with the evidence attachment, not with the case targets (CP-1550)
    port.bind_live_evidence(window, support_distance_max_m=0.02, raw_records_root=tmp_path)
    # THE GRID'S CLOCK, defined here because this fixture owns the substituted world's time: the recorder requires
    # consecutive samples to be exactly one period apart, so the sample's stamp is set from the window's own count. In a
    # real case that clock is MuJoCo's, and it has to satisfy the same rule - which is a property of the recorder, not
    # of this fixture.
    # P1-4 piece 4: the add_grid wrapper is GONE. It stamped every sample one period apart because the port produced
    # one sample per phase from a clock that could not advance; the port now samples at the frozen period from the
    # readback's own monotonic clock, so the cadence is a property of the acquisition and nothing is rewritten here.
    # (the widened registration above is the one that matters: this line used to overwrite it with
    #  the narrow prefix, so the refresh updated a dict no route executes against)
    port.boundary.current_readback = _current_readback
    return port, calls, boundary, prefix


#: one clock for the whole case: `count` advances once per capture, `capture_base` is set from the
#: first readback's own simulated time (P1-4 piece 4)
_case_clock = {"count": 0}


def _case_capture(sources, prefix, boundary):
    """The readback for THIS case, at the world's current state.

    What changes with the state is exactly what the phases' predicates are about: whether the fingers touch the cup,
    whether the cup is still resting on the table (its signed distance against the case's admitted support threshold),
    and - once released - whether it is at the place target the policy names.
    """

    world_state = _case_capture.world
    readings = _case_capture.readings
    index = len(readings)
    readings.append(index)
    raw = sources.capture(prefix["attempt_id"], after_step=0)
    # `_case_clock` is ONE accumulator for the case: the world's own simulated time advances by whatever the physics
    # did, while the frozen grid requires consecutive samples exactly one period apart - so the capture clock is this
    # sequence, and the readback's other fields follow the world as before.
    if "capture_base" not in _case_clock:
        _case_clock["capture_base"] = raw["world"].simulation_time_s
    moment_index = _case_clock["count"]      # advanced by the SAMPLING readback, not by every capture
    step = raw["world"].simulation_step + 1 + index
    # P1-4 piece 4: ONE monotonically increasing source clock, and no rewriting. The capture's time advances by the
    # frozen period per sample, for the whole case - the prefix window is widened to cover it instead of the clock
    # being wrapped to fit the window, which is what made the cadence a property of the fixture rather than of the run.
    moment = _case_clock["capture_base"] + (0.1 * (1 + moment_index))
    # and the PREFIX is re-issued with every readback, because that is what a prefix IS: a plan issued from the
    # current observation. The contract fixes its window at `observation_time_s + 0.1 + 0.002` (~0.102 s), and the
    # header stamp must fall strictly inside it - so a plan left behind by a case that has since run for a second is
    # refused by name (`APPROACH_HEADER_STAMP_INVALID`). Re-issuing is what production does; this keeps the plan fresh
    # instead of wrapping the clock to fit an old one.
    prefix_document = getattr(_case_capture, "prefix", None)
    if isinstance(prefix_document, dict) and not getattr(_case_capture, "prefix_signed", False):
        # the CURRENT instant: the boundary takes the header from its own capture, which reports this same moment (the
        # counter is advanced by the sampling readback before the capture runs). Projecting one step ahead put the
        # window's start PAST the header - measured: origin 1.45 against header 1.40 - so the plan is placed around the
        # instant it will actually be executed at.
        origin = moment - 0.05
        prefix_document["observation_time_s"] = origin
        prefix_document["target_times_s"] = tuple(
            origin + 0.1 + 0.002 * (index + 1) for index in range(len(prefix_document["target_times_s"])))

    from so101_demo.core.simulation.types import ContactEvidence

    state = raw["world"].object_state
    position = tuple(float(value) for value in state.position_world)
    contacts = ()
    held = world_state is not None and world_state.grasped
    if held:
        def _grasp(side):
            return ContactEvidence(body1_id=state.body_id, geom1_id=state.body_id, body1=state.body,
                                   geom1=f"cup_{side}_geom", body2_id=991, geom2_id=992,
                                   body2=f"gripper_{side}", geom2=f"{side}_pad",
                                   position_world=(0.0, 0.0, 0.0), normal_world=(0.0, 0.0, 1.0),
                                   # the world requires the aggregate to BE the contacts' own minimum, so the contact
                                   # distance is the same value the aggregate reports
                                   signed_distance_m=0.5, normal_force_n=1.0)

        contacts = (_grasp("left"), _grasp("right"))
        # a grasped cup that the arm has lifted is NOT supported: HOLDING means held and clear of the table, which is
        # the meaning the aggregate rules give it and the one the runner's predicates for CLOSE and beyond require
        distance = 0.5
    else:
        # the world's own rule: with no contacts the distance aggregate must be exactly zero, and zero is still
        # "supported" against any positive threshold
        distance = 0.0
        if world_state is not None and world_state.released:
            # released means where it was PUT: the place target's own cup pose, with the grasp transform undone
            from so101_demo.core.dynamic_pick import compose_pose, inverse_pose

            template = world_state.template
            placed = compose_pose(template.place_tcp_world, inverse_pose(template.cup_to_tcp_grasp))
            position = tuple(float(value) for value in placed.values[:3])
            state = dataclasses.replace(state, position_world=position)

    world = dataclasses.replace(raw["world"], simulation_step=step, simulation_time_s=moment,
                                simulation_session_id=SESSION, reset_epoch=2, object_state=state,
                                left_fingertip_contacts=contacts[:1], right_fingertip_contacts=contacts[1:],
                                other_object_contacts=(), minimum_signed_distance_m=distance,
                                has_contact=bool(contacts),
                                maximum_normal_force_n=1.0 if contacts else 0.0)
    stamps = {name: moment for name in ("head", "wrist", "arm", "neck")}
    return {**raw, "world": world, "source_stamps_s": stamps, "source_received_wall_s": dict(stamps),
            "scene": {**raw["scene"], "simulation_step": step, "simulation_time_s": moment,
                      "simulation_session_id": SESSION, "reset_epoch": 2},
            "contact": {**raw["contact"], "physics_step": step, "simulation_time_s": moment,
                        "simulation_session_id": SESSION, "reset_epoch": 2},
            "observation": {**raw["observation"], "sim_time_s": moment},
            "reference": {**raw["reference"], "requested_sim_time_s": moment}}


_case_capture.readings = []
_case_capture.world = None
# the one sequence is per CASE, not per process: module-level state carried this case's clock into the next one,
# which is why a single case sealed cleanly while the suite failed (measured: one case -> ten samples exactly one
# period apart and `sealed fine`; the same case inside the suite -> TASK8_LIVE_EVIDENCE_GRID_GAP)
_case_clock["count"] = 0


def _reset_case_clock():
    """Start a fresh sequence for the case that is about to run."""

    _case_clock.clear()
    _case_clock["count"] = 0        # `clear()` alone left the reader below with no key at all (KeyError: 'count')
    _case_capture.readings = []


def test_the_runner_runs_the_whole_case_and_reports_which_phases_completed(tmp_path):
    """The milestone: nine phases, the runner driving, the port routing, and one verdict at the end."""

    from test_dynamic_pick import _template

    port, _events, boundary, _prefix = _full_case_port(tmp_path)
    # the closed position is a positive joint value (the port refuses zero by name): closing moves the gripper joint
    # towards its closed limit, it does not mean "no value"
    _route = _Route.__new__(_Route)
    _route.__init__(_wide_prefix(boundary.prefix))
    port._expert_route = _route
    port.bind_case_targets(gripper_closed_rad=0.2, close_duration_s=0.4,
                           motion_template=_template(), motion_duration_s=0.4)
    runner = PickPlaceRunner(port)
    result = runner.run({
        # the runner's own full-case mode: no stop_after, and a FULL_RESTART lifecycle
        "mode": "full", "stop_after": None, "lifecycle": "FULL_RESTART", "scenario_id": SCENARIO,
        "session_id": SESSION, "attempt_id": ATTEMPT, "deadline_ns": runner.clock_ns() + 600_000_000_000,
    })
    print("[probe] full-case result:", {key: str(value)[:80] for key, value in result.items()}
          if isinstance(result, dict) else type(result).__name__)
    assert isinstance(result, dict) and result

# SO-101 MuJoCo Approved Policy and Outcomes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the disabled placeholder contact calibration and hard-coded physical decisions with a fingerprint-bound, explicitly approved policy and deterministic grasp, carry, and final-placement evaluators.

**Architecture:** Add one typed `TaskPolicy` loader over the motion and contact YAML artifacts, keep calibration proposal generation separate from approval, and make every physical decision a ROS-free pure evaluator. The existing qualified subprocess runtime temporarily consumes these policy objects so live behavior fails closed before Projects B and C replace its orchestration.

**Tech Stack:** Python 3.12, ROS 2 Jazzy/rclpy, PyYAML, pytest, Ruff, MuJoCo atomic `SimulationEvidence`, MoveIt Planning Scene readback, zsh/colcon.

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2` on `codex/so101-mujoco-ros2-teleop`.
- This work is simulation-only. It does not authorize real-robot motion.
- MuJoCo physical evidence is the cup-motion truth; MoveIt attachment is only the Planning Scene collision shadow.
- Do not use weld, equality, adhesion, mocap, object teleport, direct object-state writes, or hidden retries.
- Do not modify protected `src/so101_gazebo_demo_py`; parity tests may read its checked-in YAML.
- Preserve existing CLI inputs; execute must fail before motion when policy approval or fingerprints are invalid.
- Existing user changes and unrelated tmux/ROS processes must be preserved.
- Use standard Git against Gitee `origin`; do not use `gh`.
- Do not run `ament_uncrustify --reformat`.
- Use Bun for `so101_teleop` web commands.
- Follow `.agents/skills/so101-dev/SKILL.md`: one hypothesis per experiment, persistent ledger entries before live actions, unique `/tmp` evidence roots, fresh installed provenance, exact process ownership, and RED→GREEN evidence.
- Contact-policy activation requires a separate user response approving the exact generated `proposal_sha256`; the architecture/design approval is not threshold approval.

---

### Task 1: Establish the remediation experiment ledger

**Files:**
- Create: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`
- Reference: `docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- Reference: `docs/superpowers/specs/2026-08-12-so101-mujoco-maintainability-remediation-design.md`

**Interfaces:**
- Consumes: published migration checkpoint `CP-156`, implementation baseline `579db0fd1b8b418731957a8f83feb724419eed30`, fork commit `f42b7b3d77288c2fee750fe53b0258e0a3d18194`.
- Produces: the sole persistent ledger for Projects A–D and experiment IDs beginning at `EXP-001`.

- [ ] **Step 1: Capture the live baseline without changing processes**

Run:

```zsh
hostname
pwd
git branch --show-current
git rev-parse HEAD
git status --short
git submodule status third_party/mujoco_ros2_control
tmux list-sessions 2>/dev/null || true
pgrep -af 'mujoco|move_group|rviz2|pick_place_state_machine|ros2_control_node' || true
source /opt/ros/jazzy/setup.zsh
ros2 node list 2>/dev/null | sort || true
```

Expected: `AI-STATION-001`; target worktree/branch; no task-owned ROS stack; unrelated tmux sessions remain untouched.

- [ ] **Step 2: Create the ledger with a concrete header and checkpoint**

Use this exact initial structure, replacing only `current_commit` if Task 1 starts from a later reviewed commit:

```yaml
task_id: so101-mujoco-maintainability-remediation
goal: Replace migration experiment scaffolding with approved policy-driven state-machine production runtime and requalify it.
success_contract: All seven audit findings pass automated gates plus independent FULL_RESTART and RESET_WORLD physical qualification.
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2-teleop
base_commit: 70bece06e008b27da8f0923472668e95a369309e
current_commit: 579db0fd1b8b418731957a8f83feb724419eed30
evidence_root: /tmp/so101-debug-mujoco-maintainability-remediation/
confirmed_conclusions:
  - CP-156: prior implementation passed the published 5 FULL_RESTART plus 5 RESET_WORLD simulation qualification.
  - AUDIT-001: contact_calibration.yaml is PLANNED/disabled while production phases hard-code contact limits.
  - AUDIT-002: execute bypasses StateMachineRunner and ignores public checkpoint controls.
disproven_routes:
  - Treating the prior 857-result colcon summary as a clean three-package result; it included 240 stale Gazebo tests.
open_hypotheses:
  - A fresh seven-regime fixed-fingerprint campaign can produce non-overlapping deterministic thresholds for the current model and motion policy.
latest_checkpoint: MNT-CP-001
next_experiment: EXP-001
```

Append `MNT-CP-001` with `owned_processes: NONE`, the exact dirty paths, and the next command from Task 2.

- [ ] **Step 3: Verify the ledger is the only change and commit it**

Run:

```zsh
git diff --check
git status --short
git add -- docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md
git commit -m "docs(so101_mujoco): start maintainability remediation ledger"
```

Expected: one ledger file committed; no runtime process started.

---

### Task 2: Add one typed task-policy loader

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/task_policy.py`
- Create: `src/so101_mujoco_demo_py/test/test_task_policy.py`
- Modify: `src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_mujoco_demo_py/test/test_motion_policy_contract.py`

**Interfaces:**
- Consumes: motion policy schema v1 and `PhysicalOutcomePolicy` / `PlanningShadowPolicy` from `physical_outcome.py`.
- Produces: `TaskPolicyFingerprint`, `GripperActions`, `MotionStatePolicy`, `TaskPolicy`, and `load_task_policy(motion_path: Path) -> TaskPolicy`.

- [ ] **Step 1: Write the failing typed-policy tests**

Create tests using literal expected values, including:

```python
def test_loads_single_source_motion_and_final_outcome_policy() -> None:
    policy = load_task_policy(MOTION_POLICY)
    assert policy.policy_id == "light_cup_wall_pick"
    assert policy.gripper.grasp_close_q6 == -0.047608632840292
    assert policy.states["MOVE_ABOVE_PLACE"].velocity_scaling == 0.10
    assert policy.physical_outcome.final_target_min_xy_m == (-0.090, -0.260)
    assert policy.physical_outcome.final_target_max_xy_m == (-0.070, -0.240)
    assert len(policy.fingerprint.motion_policy_sha256) == 64


def test_rejects_unknown_keys_and_invalid_motion_dimensions(tmp_path: Path) -> None:
    document = yaml.safe_load(MOTION_POLICY.read_text())
    document["states"]["LIFT"]["waypoints"][0] = [0.0] * 4
    document["unreviewed"] = True
    candidate = tmp_path / "invalid.yaml"
    candidate.write_text(yaml.safe_dump(document, sort_keys=False))
    with pytest.raises(ValueError, match="unreviewed|five arm joints"):
        load_task_policy(candidate)
```

Also assert finite values, scaling in `(0, 1]`, ordered min/max bounds, positive durations/counts, exact state names, and immutable tuple/mapping outputs.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
source install/setup.zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_task_policy.py
```

Expected: collection/import failure because `task_policy.py` does not exist.

- [ ] **Step 3: Add the final-outcome section to the motion policy**

Add this exact policy data; no production Python literal may repeat it:

```yaml
physical_outcome:
  intended_support_collision: table_collision
  minimum_support_signed_distance_m: -0.0000001
  final_target_region:
    kind: axis_aligned_box
    min_xy_m: [-0.090, -0.260]
    max_xy_m: [-0.070, -0.240]
  support_height_range_m: [0.155, 0.175]
  max_upright_tilt_rad: 0.08726646259971647
  max_linear_speed_m_s: 0.001
  max_angular_speed_rad_s: 0.05
  consecutive_samples: 5
  minimum_stable_duration_s: 0.20
  sample_interval_s: 0.05
  settle_timeout_s: 2.0
  max_observation_age_s: 0.10
  max_telemetry_samples: 40
  catastrophic_workspace_bounds_m: [-0.21, -0.46, 0.12, 0.21, 0.06, 0.30]
  max_relative_position_drift_m: 0.005
  max_relative_orientation_drift_rad: 0.070
  planning_shadow:
    max_position_divergence_m: 0.005
    max_orientation_divergence_rad: 0.070
    max_pair_age_s: 0.10
```

Move `maximum_diagnostic_force_n: 11.60` to a top-level `safety_limits` mapping and make the calibration/staged sections reference the typed value rather than owning independent copies during Task 7.

- [ ] **Step 4: Implement the typed loader**

Use frozen dataclasses with these public shapes:

```python
@dataclass(frozen=True, slots=True)
class TaskPolicyFingerprint:
    motion_policy_sha256: str
    contact_policy_sha256: str | None


@dataclass(frozen=True, slots=True)
class GripperActions:
    preopen_q6: float
    grasp_close_q6: float
    seating_preload_rad: float
    release_q6: float


@dataclass(frozen=True, slots=True)
class MotionStatePolicy:
    logical_start: tuple[float, ...]
    waypoints: tuple[tuple[float, ...], ...]
    require_waypoint_ladder: bool
    require_axial_path_validation: bool
    gripper_q6: float
    velocity_scaling: float
    acceleration_scaling: float


@dataclass(frozen=True, slots=True)
class TaskPolicy:
    policy_id: str
    object_id: str
    planning_group: str
    tcp_link: str
    gripper_joint: str
    all_joints: tuple[str, ...]
    arm_joints: tuple[str, ...]
    gripper: GripperActions
    states: Mapping[str, MotionStatePolicy]
    physical_outcome: PhysicalOutcomePolicy
    maximum_diagnostic_force_n: float
    fingerprint: TaskPolicyFingerprint
```

Keep YAML validation helpers private. Reject extra keys at each newly typed mapping. Compute SHA-256 from the exact file bytes, not a reserialized mapping.

- [ ] **Step 5: Run focused tests to GREEN**

Run:

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_task_policy.py \
  src/so101_mujoco_demo_py/test/test_motion_policy_contract.py \
  src/so101_mujoco_demo_py/test/test_physical_outcome.py
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit the typed policy boundary**

```zsh
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/task_policy.py \
  src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml \
  src/so101_mujoco_demo_py/test/test_task_policy.py \
  src/so101_mujoco_demo_py/test/test_motion_policy_contract.py
git commit -m "feat(so101_mujoco): add typed task policy"
```

---

### Task 3: Version calibration proposals and enforce explicit approval

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_policy.py`
- Create: `src/so101_mujoco_demo_py/test/test_contact_policy.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration_collector.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/task_policy.py`
- Modify: `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- Modify: `src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py`
- Modify: `src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py`
- Modify: `src/so101_mujoco_demo_py/test/test_task_policy.py`
- Modify: `src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py`

**Interfaces:**
- Consumes: schema-v1 archived raw calibration matrices for read compatibility and schema-v2 raw matrices from `ContactCalibrationCollector`.
- Produces: schema-v2 raw matrices and disabled proposals, `ApprovalRecord`, `ApprovedContactPolicy`, `proposal_sha256(document) -> str`, `approve_proposal(document, approval) -> dict[str, object]`, `load_approved_contact_policy(path, expected_fingerprint) -> ApprovedContactPolicy`, and `load_task_policy(motion_path: Path, contact_path: Path | None = None, expected_contact_fingerprint: ContactPolicyFingerprint | None = None, *, require_approved_contact: bool = False) -> TaskPolicy`.

- [ ] **Step 1: Write RED tests for proposal identity**

Add literal-behavior tests:

```python
def test_proposal_hash_excludes_only_approval_envelope() -> None:
    proposal = valid_disabled_proposal()
    first = proposal_sha256(proposal)
    proposal["approval"] = {
        "enabled": False,
        "approved": False,
        "approved_by": None,
        "approved_at": None,
        "proposal_sha256": first,
    }
    assert proposal_sha256(proposal) == first
    proposal["thresholds"]["minimum_bilateral_force_n"] += 0.01
    assert proposal_sha256(proposal) != first


def test_approval_requires_exact_hash_and_complete_identity() -> None:
    proposal = valid_disabled_proposal()
    with pytest.raises(ValueError, match="proposal hash mismatch"):
        approve_proposal(
            proposal,
            ApprovalRecord("0" * 64, "user", "2026-08-12T12:00:00+08:00"),
        )
```

Add rejection cases for disabled/unapproved policy loading, missing raw evidence hash,
changed model/scene/motion-policy hash, invalid timestamp, zero/placeholder hash,
non-finite thresholds, overlapping min/max, and modification after approval.

- [ ] **Step 2: Run and verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_contact_policy.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py \
  src/so101_mujoco_demo_py/test/test_task_policy.py
```

Expected: import failure for `contact_policy` and schema-v2 assertions fail.

- [ ] **Step 3: Define the schema-v2 public types**

Implement:

```python
@dataclass(frozen=True, slots=True)
class ContactThresholds:
    minimum_bilateral_force_n: float
    maximum_compression_distance_m: float
    maximum_safe_force_n: float
    maximum_hold_linear_speed_m_s: float
    minimum_stable_hold_duration_s: float


@dataclass(frozen=True, slots=True)
class ContactEvaluationPolicy:
    maximum_observation_age_s: float
    minimum_consecutive_samples: int


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    proposal_sha256: str
    approved_by: str
    approved_at: str


@dataclass(frozen=True, slots=True)
class ContactPolicyFingerprint:
    dependency_commit: str
    model_sha256: str
    scene_sha256: str
    motion_policy_sha256: str
    source_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovedContactPolicy:
    policy_id: str
    thresholds: ContactThresholds
    evaluation: ContactEvaluationPolicy
    allowed_other_contact_bodies: frozenset[str]
    fingerprint: ContactPolicyFingerprint
    approval: ApprovalRecord
```

Canonical proposal bytes are UTF-8 JSON with sorted keys and separators
`(',', ':')`, excluding the entire `approval` mapping. The policy file stores
the computed hash inside `approval.proposal_sha256`.

- [ ] **Step 4: Upgrade analyzer output and the checked-in template**

Schema v2 contains literal `schema_version: 2`, policy ID
`light_cup_wall_pick-contact`, calibration status, allowed other
contact bodies, calibrated thresholds, fixed evaluation controls
`maximum_observation_age_s` and `minimum_consecutive_samples`, statistics, and
an approval envelope containing `enabled`, `approved`, approval identity/time,
and `proposal_sha256`. Its
fingerprint contains the recorded source/dependency commits and the exact
model, scene, motion-policy, and source-evidence SHA-256 values. The checked-in
pre-campaign file records hashes computed from the then-current repository
artifacts, keeps `source_evidence_sha256` and thresholds null, and remains
`PLANNED`, disabled, and unapproved. No dummy all-zero or example hash is
permitted.

Extend `CollectionRequest`, its CLI arguments, and the raw-matrix serializer
with `scene_sha256` and `motion_policy_sha256`. New collection output is raw
schema v2 and records all five artifact identities; the analyzer retains an
explicit read-only adapter for archived schema-v1 matrices. Tests prove the
collector rejects malformed or changing fingerprints before appending a
sample.

`analyze_bytes()` emits `VALID`, disabled, unapproved proposals and inserts the
computed proposal hash. `--validate` accepts both disabled proposals and exact
approved policies but never changes approval. Extend `load_task_policy` only
after `ApprovedContactPolicy` exists: it loads the contact file, compares all
expected physical-artifact hashes, attaches the approved policy to
`TaskPolicy.contact`, and rejects missing approval when
`require_approved_contact=True`.

- [ ] **Step 5: Add an explicit approval CLI path**

Extend the analyzer entry point:

```text
analyze_contact_calibration --approve proposal.yaml \
  --proposal-sha256 "$proposal_sha" \
  --approved-by user \
  --approved-at 2026-08-12T12:00:00+08:00 \
  --output contact_calibration.yaml
```

It calls `approve_proposal`, atomically writes only when the supplied hash
matches, and refuses to overwrite an approved file with a different hash.

- [ ] **Step 6: Run focused tests to GREEN**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_contact_policy.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py \
  src/so101_mujoco_demo_py/test/test_task_policy.py
```

Expected: all selected tests pass; checked-in policy remains disabled.

- [ ] **Step 7: Commit proposal/approval separation**

```zsh
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_policy.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/contact_calibration_collector.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/task_policy.py \
  src/so101_mujoco_demo_py/config/contact_calibration.yaml \
  src/so101_mujoco_demo_py/test/test_contact_policy.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_collector.py \
  src/so101_mujoco_demo_py/test/test_task_policy.py \
  src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py
git commit -m "feat(so101_mujoco): require exact contact policy approval"
```

---

### Task 4: Implement the deterministic grasp evaluator

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/grasp_outcome.py`
- Create: `src/so101_mujoco_demo_py/test/test_grasp_outcome.py`

**Interfaces:**
- Consumes: `tuple[ReceivedSimulationEvidence, ...]`, `ApprovedContactPolicy`, expected session/epoch, action boundary sequence, and current monotonic time.
- Produces: `GraspOutcome` and `evaluate_grasp(...) -> GraspOutcome` with stable failure codes and metrics.

- [ ] **Step 1: Write the RED decision-matrix tests**

Define literal samples and cover this precedence:

```python
def test_accepts_fresh_bilateral_window_inside_approved_bounds() -> None:
    result = evaluate_grasp(
        samples=five_bilateral_samples(),
        policy=approved_policy(),
        expected_session_id="session-a",
        expected_reset_epoch=3,
        action_boundary_sequence=99,
        now_monotonic_s=10.25,
    )
    assert result.success
    assert result.failure_code is None
    assert result.metrics["minimum_left_force_n"] == pytest.approx(0.61)
    assert result.metrics["minimum_right_force_n"] == pytest.approx(0.62)
```

Add one test per failure: `GRASP_STALE_EVIDENCE`,
`GRASP_PROVENANCE_MISMATCH`, `GRASP_TRUNCATED_CONTACTS`,
`GRASP_FORBIDDEN_CONTACT`, `GRASP_LEFT_CONTACT_MISSING`,
`GRASP_RIGHT_CONTACT_MISSING`, `GRASP_FORCE_TOO_LOW`,
`GRASP_FORCE_TOO_HIGH`, `GRASP_OVER_COMPRESSED`, `GRASP_SLIPPING`, and
`GRASP_DWELL_TOO_SHORT`. Combine two failures in one case to assert the declared
precedence, rather than the order of test fixtures.

- [ ] **Step 2: Run and verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_grasp_outcome.py
```

Expected: import failure because `grasp_outcome.py` does not exist.

- [ ] **Step 3: Implement the immutable result and evaluator**

```python
@dataclass(frozen=True, slots=True)
class GraspOutcome:
    success: bool
    failure_code: str | None
    sample_count: int
    duration_s: float
    metrics: Mapping[str, float]
    telemetry: tuple[ReceivedSimulationEvidence, ...]


def evaluate_grasp(
    samples: tuple[ReceivedSimulationEvidence, ...],
    policy: ApprovedContactPolicy,
    expected_session_id: str,
    expected_reset_epoch: int,
    action_boundary_sequence: int,
    now_monotonic_s: float,
) -> GraspOutcome:
    eligible = tuple(
        item
        for item in samples
        if item.evidence.publisher_sequence > action_boundary_sequence
    )
    return _evaluate_grasp_window(
        eligible,
        policy,
        expected_session_id,
        expected_reset_epoch,
        now_monotonic_s,
    )
```

Only samples newer than the action boundary are eligible. Require strictly
increasing publisher sequence/simulation time/receipt time, freshness within
`policy.evaluation.maximum_observation_age_s`, at least
`policy.evaluation.minimum_consecutive_samples` continuous bilateral samples,
per-side summed normal
force above the approved minimum, aggregate force below the approved maximum,
compression below the approved maximum, speed below the approved hold maximum,
and duration at least the approved dwell. Reject `other_object_contacts` whose
`body2`/`geom2` names are not in `allowed_other_contact_bodies`.
`_evaluate_grasp_window` performs those checks in the failure-code precedence
declared by the tests and always returns immutable telemetry/metrics; it never
reads ROS state or wall-clock time itself.

- [ ] **Step 4: Run to GREEN and mutation-check branches**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_grasp_outcome.py
```

Expected: all evaluator tests pass. Manually confirm each realistic mutation
(wrong comparison direction, missing side, ignored epoch, ignored forbidden
contact) breaks at least one named test.

- [ ] **Step 5: Commit the grasp evaluator**

```zsh
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/grasp_outcome.py \
  src/so101_mujoco_demo_py/test/test_grasp_outcome.py
git commit -m "feat(so101_mujoco): evaluate approved physical grasp"
```

---

### Task 5: Implement causal micro-lift and transport evaluators

**Files:**
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/grasp_outcome.py`
- Create: `src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py`
- Create: `src/so101_mujoco_demo_py/test/test_transport_outcome.py`
- Modify: `src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/task_policy.py`

**Interfaces:**
- Consumes: approved contact policy plus typed TCP/cup/contact samples.
- Produces: `CarrySample`, `CarryOutcome`, `CarryPolicy`, `evaluate_micro_lift(samples, contact_policy, carry_policy, expected_session_id, expected_reset_epoch, action_boundary_sequence, now_monotonic_s)`, and `evaluate_transport(samples, contact_policy, carry_policy, expected_session_id, expected_reset_epoch, action_boundary_sequence, now_monotonic_s)`.

- [ ] **Step 1: Add policy data and RED micro-lift tests**

Add under `physical_outcome`:

```yaml
micro_lift:
  minimum_cup_lift_m: 0.0015
  maximum_cup_lift_m: 0.0035
  minimum_tcp_lift_m: 0.0015
  maximum_lateral_drift_m: 0.001
  maximum_relative_position_drift_m: 0.001
  minimum_stable_duration_s: 0.30
transport:
  maximum_relative_position_drift_m: 0.005
  maximum_relative_orientation_drift_rad: 0.070
  minimum_table_clearance_m: 0.001
```

Write positive and negative literal windows for cup teleport, table-supported
false positive, gripper/TCP motion without cup motion, cup motion without TCP
motion, lateral drift, contact loss, slip, excessive force, stale receipt,
session/reset crossing, and catastrophic workspace exit.

- [ ] **Step 2: Run micro-lift tests and verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py
```

Expected: missing `CarrySample` / `evaluate_micro_lift` failure.

- [ ] **Step 3: Implement carry types and micro-lift evaluation**

```python
@dataclass(frozen=True, slots=True)
class CarrySample:
    simulation_session_id: str
    reset_epoch: int
    publisher_sequence: int
    simulation_time_s: float
    received_monotonic_s: float
    cup_pose_xyz_xyzw: Pose
    tcp_pose_xyz_xyzw: Pose
    table_contact: bool
    left_force_n: float
    right_force_n: float
    maximum_force_n: float
    forbidden_contact: bool


@dataclass(frozen=True, slots=True)
class CarryOutcome:
    success: bool
    failure_code: str | None
    sample_count: int
    metrics: Mapping[str, float]
    telemetry: tuple[CarrySample, ...]


@dataclass(frozen=True, slots=True)
class MicroLiftPolicy:
    minimum_cup_lift_m: float
    maximum_cup_lift_m: float
    minimum_tcp_lift_m: float
    maximum_lateral_drift_m: float
    maximum_relative_position_drift_m: float
    minimum_stable_duration_s: float


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    maximum_relative_position_drift_m: float
    maximum_relative_orientation_drift_rad: float
    minimum_table_clearance_m: float


@dataclass(frozen=True, slots=True)
class CarryPolicy:
    micro_lift: MicroLiftPolicy
    transport: TransportPolicy
    max_observation_age_s: float
    catastrophic_workspace_bounds_m: tuple[float, ...]
```

`evaluate_micro_lift` derives cup/TCP deltas independently, checks correlated
direction and bounded relative displacement, requires table contact to clear,
and reuses approved bilateral/force/provenance gates. It does not trust a
Planning Scene attached flag as physical evidence.

Extend `TaskPolicy` with `carry: CarryPolicy`, parsed from the two YAML mappings
plus the existing physical-outcome freshness/workspace fields, with strict-key,
finite-number, positive-bound, six-dimensional workspace, and ordered-range
validation.

- [ ] **Step 4: Run micro-lift tests to GREEN**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py
```

Expected: all micro-lift cases pass.

- [ ] **Step 5: Write RED transport-window tests**

Assert stable relative cup/TCP pose through named `LIFT`, `MOVE_ABOVE_PLACE`,
and `DESCEND_TO_PLACE` segments. Include failures for missing segment,
non-monotonic evidence, table recontact before placement, orientation drift,
position drift, bilateral loss, forbidden contact, reset crossing, and
catastrophic bounds.

- [ ] **Step 6: Run transport tests and verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test/test_transport_outcome.py
```

Expected: missing `evaluate_transport` or unimplemented segment validation.

- [ ] **Step 7: Implement transport evaluation and run GREEN**

Add `segment: str` to `CarrySample`; accept only the three policy segment names;
require at least two fresh samples per segment and preserve the first physical
failure as primary.

Run:

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py \
  src/so101_mujoco_demo_py/test/test_transport_outcome.py \
  src/so101_mujoco_demo_py/test/test_task_policy.py
```

Expected: all selected tests pass.

- [ ] **Step 8: Commit causal carry evaluation**

```zsh
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/grasp_outcome.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/task_policy.py \
  src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml \
  src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py \
  src/so101_mujoco_demo_py/test/test_transport_outcome.py
git commit -m "feat(so101_mujoco): prove causal cup transport"
```

---

### Task 6: Make final placement and cross-backend parity policy-driven

**Files:**
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/release_retreat.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py`
- Modify: `src/so101_mujoco_demo_py/test/test_physical_outcome.py`
- Modify: `src/so101_mujoco_demo_py/test/test_live_runtime_contract.py`
- Create: `src/so101_mujoco_demo_py/test/test_backend_policy_parity.py`
- Read only: `src/so101_gazebo_demo_py/config/validation_policies/light_cup_wall_pick.yaml`

**Interfaces:**
- Consumes: `TaskPolicy.physical_outcome`.
- Produces: no production target-region literals outside YAML and one repository test that rejects Gazebo/MuJoCo semantic drift.

- [ ] **Step 1: Write RED tests that expose both duplicate target sources**

Change the final-placement fixture boundary to the approved 10 mm region and
assert `x=-0.089` succeeds while `x=-0.091` fails. Inject a `TaskPolicy` into
`_validate_final_release` and assert it obeys the injected bounds rather than
module constants.

Add parity assertions for these semantic fields:

```python
assert mujoco.final_target_min_xy_m == tuple(gazebo_region["min_xy_m"])
assert mujoco.final_target_max_xy_m == tuple(gazebo_region["max_xy_m"])
assert mujoco.support_height_range_m == tuple(gazebo_outcome["support_height_range_m"])
assert mujoco.max_upright_tilt_rad == gazebo_outcome["max_upright_tilt_rad"]
assert mujoco.max_linear_speed_m_s == gazebo_outcome["max_linear_speed_m_s"]
assert mujoco.max_angular_speed_rad_s == gazebo_outcome["max_angular_speed_rad_s"]
```

- [ ] **Step 2: Run and verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_physical_outcome.py \
  src/so101_mujoco_demo_py/test/test_live_runtime_contract.py \
  src/so101_mujoco_demo_py/test/test_backend_policy_parity.py
```

Expected: old ±5 mm expectation or missing policy injection/parity test fails.

- [ ] **Step 3: Remove production literals and load the typed policy**

Delete `outcome_policy()` from `release_retreat.py`. Its `main()` loads one
`TaskPolicy` and passes `task_policy.physical_outcome` to final evaluation.
Change `_validate_final_release(document, policy)` to call the same pure
`evaluate_final_placement` function after strictly deserializing the recorded
final sample window. It accepts the document only when the recomputed outcome
is successful and the existing ACM/Planning Scene readback predicates pass; it
must not trust a serialized success boolean or compare x/y literals itself.

- [ ] **Step 4: Run selected tests to GREEN**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_task_policy.py \
  src/so101_mujoco_demo_py/test/test_physical_outcome.py \
  src/so101_mujoco_demo_py/test/test_live_runtime_contract.py \
  src/so101_mujoco_demo_py/test/test_backend_policy_parity.py
```

Expected: all selected tests pass without changing Gazebo files.

- [ ] **Step 5: Commit single-source final outcome policy**

```zsh
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/release_retreat.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py \
  src/so101_mujoco_demo_py/test/test_physical_outcome.py \
  src/so101_mujoco_demo_py/test/test_live_runtime_contract.py \
  src/so101_mujoco_demo_py/test/test_backend_policy_parity.py
git commit -m "fix(so101_mujoco): unify physical outcome policy"
```

---

### Task 7: Fail live execute closed and remove contact-limit literals

**Files:**
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/cli.py`
- Modify: `src/so101_mujoco_demo_py/launch/so101_pick_place.launch.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/contact_hold.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/micro_lift.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/policy_lift_waypoint1.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/remaining_lift.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/transport.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/descend.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/place_alignment.py`
- Modify: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/release_retreat.py`
- Modify: `src/so101_mujoco_demo_py/test/test_pick_place_cli.py`
- Modify: `src/so101_mujoco_demo_py/test/test_live_runtime_contract.py`

**Interfaces:**
- Consumes: `load_task_policy(..., require_approved_contact=True)` and pure evaluators.
- Produces: execute preflight error `CONTACT_POLICY_NOT_APPROVED` / `POLICY_FINGERPRINT_MISMATCH`, `LiveRuntimeConfig.contact_policy`, and no repeated `11.60`/`0.50` contact constants in phase modules.

- [ ] **Step 1: Write RED preflight and injection tests**

Assert execute with the checked-in disabled template performs zero command-runner
calls and returns `CONTACT_POLICY_NOT_APPROVED`. Assert an approved fixture with
wrong model/scene/motion hash returns `POLICY_FINGERPRINT_MISMATCH`. Assert every
phase receives one already loaded `TaskPolicy`/approved policy fixture and uses
its changed force value in observable acceptance/rejection behavior.

- [ ] **Step 2: Run and verify RED**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_pick_place_cli.py \
  src/so101_mujoco_demo_py/test/test_live_runtime_contract.py
```

Expected: execute currently enters phase orchestration without validating
approval; changed fixture values do not control hard-coded phase decisions.

- [ ] **Step 3: Add the contact-policy argument and preflight**

Add `--contact-policy` to CLI/launch and `contact_policy: Path` to
`LiveRuntimeConfig`. `run_live_workflow` loads the `TaskPolicy` before resume or
subprocess creation and returns a typed failure manifest on any approval or
fingerprint error.

During the temporary subprocess implementation, pass only the paths and
expected hashes in the child environment. Each child loads the same immutable
policy and calls the pure evaluator. Do not serialize thresholds into environment
variables.

- [ ] **Step 4: Remove duplicated contact-limit literals**

Delete `MAX_FORCE_N`, `MIN_SIDE_NORMAL_FORCE_N`, and target-region literals from
all listed phase modules. Replace comparisons with typed policy fields and
replace ad-hoc bilateral/hold checks with `evaluate_grasp`,
`evaluate_micro_lift`, or `evaluate_transport`. Keep motion target literals for
Project B, which deletes the phase implementation after state-action parity.

- [ ] **Step 5: Run focused tests to GREEN**

```zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_contact_policy.py \
  src/so101_mujoco_demo_py/test/test_grasp_outcome.py \
  src/so101_mujoco_demo_py/test/test_micro_lift_outcome.py \
  src/so101_mujoco_demo_py/test/test_transport_outcome.py \
  src/so101_mujoco_demo_py/test/test_pick_place_cli.py \
  src/so101_mujoco_demo_py/test/test_live_runtime_contract.py
```

Expected: all selected tests pass; execute remains deliberately unavailable
until Task 9 activates an exact proposal.

- [ ] **Step 6: Verify literal removal semantically**

Run:

```zsh
rg -n 'MAX_FORCE_N|MIN_SIDE_NORMAL_FORCE_N|-0\.085|-0\.255|-0\.075|-0\.245' \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py
```

Expected: no matches. This search is a maintenance check; behavior remains
proved by the fixture-injection tests.

- [ ] **Step 7: Commit fail-closed policy consumption**

```zsh
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_runtime.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/cli.py \
  src/so101_mujoco_demo_py/launch/so101_pick_place.launch.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/contact_hold.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/micro_lift.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/policy_lift_waypoint1.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/remaining_lift.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/transport.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/descend.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/place_alignment.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/live_phases/release_retreat.py \
  src/so101_mujoco_demo_py/test/test_pick_place_cli.py \
  src/so101_mujoco_demo_py/test/test_live_runtime_contract.py
git diff --cached --stat
git commit -m "fix(so101_mujoco): enforce approved live policy"
```

Before committing, inspect the staged stat and unstage any path outside this
explicit list.

---

### Task 8: Run the fresh seven-regime calibration campaign

**Files:**
- Modify: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`
- Create outside repository: `/tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/`
- Generate outside repository: `contact-calibration-raw.json`, `contact-calibration-proposal.yaml`, logs, and hashes.

**Interfaces:**
- Consumes: installed Task 7 collector/analyzer, current model/scene/motion hashes, one isolated MuJoCo stack, minimum 20 valid samples per regime.
- Produces: one schema-v2 disabled proposal and its exact `proposal_sha256`; it does not modify checked-in approval state.

- [ ] **Step 1: Build a clean isolated overlay and verify provenance**

Use unique bases beneath the evidence root and build exactly the MuJoCo support/demo packages. Source in this order:

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
project_a_build=/tmp/so101-debug-mujoco-maintainability-remediation/project-a-build
test ! -e "$project_a_build"
mkdir -p "$project_a_build"
colcon --log-base "$project_a_build/log" build \
  --base-paths src \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --build-base "$project_a_build/build" \
  --install-base "$project_a_build/install" \
  --symlink-install
source "$project_a_build/install/setup.zsh"
ros2 pkg prefix so101_mujoco_demo_py
ros2 pkg prefix so101_mujoco_support
python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
```

Expected: package prefixes point to the new isolated install; fork packages
point to the pinned fork overlay; validation errors are empty.

- [ ] **Step 2: Pre-register seven experiments before any live action**

Create `EXP-001` through `EXP-007`, one for each ordered regime:
`no_contact`, `left_only`, `right_only`, `bilateral_touch`,
`over_compression`, `micro_lift_slip`, `stable_hold`.

Each record freezes one source commit, dependency/model/scene/motion hashes,
one `ROS_DOMAIN_ID`, one `GZ_PARTITION`, one session/reset epoch, exact command,
single active motion/contact variable, safety aborts (`11.60 N`, `3 mm`
pre-contact displacement, stale/truncated/reset mismatch), and minimum 25 raw
samples so the modulo-five split leaves at least 20 calibration samples.

- [ ] **Step 3: Start one owned isolated stack and collect regimes in order**

Use a tmux-held stack with exact PID/process-group ownership. For each regime:

1. read a fresh atomic sample and record the initial cup/TCP/q6 state;
2. change only the preregistered contact/motion variable;
3. invoke installed `collect_contact_calibration` with
   `--sample-count 25`, the same output matrix, and exact fingerprints;
4. save command exit code and partial evidence on any abort;
5. mark the experiment `VALID` or `INVALID` before proceeding.

The regime labels must be physically created and independently checked:

- `no_contact`: table-only pre-close and post-release negative controls;
- `left_only` and `right_only`: exactly one fingertip side, never inferred from
  a missing callback;
- `bilateral_touch`: both sides with light contact while the cup remains
  table-supported;
- `over_compression`: bilateral contact beyond the acceptable compression/force
  distribution but below the diagnostic hazard ceiling;
- `micro_lift_slip`: commanded TCP lift with bilateral contact but rejected
  causal cup carry;
- `stable_hold`: successful causal micro-lift followed by stable bilateral hold.

If the current geometry cannot produce a required regime without crossing a
safety abort, record a `VALID` behavioral failure and stop. Do not manufacture
samples or relabel another regime.

- [ ] **Step 4: Analyze the immutable raw matrix**

Run the installed analyzer, then independently validate it:

```zsh
ros2 run so101_mujoco_demo_py analyze_contact_calibration \
  --input /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw.json \
  --output /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal.yaml
ros2 run so101_mujoco_demo_py analyze_contact_calibration \
  --validate /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal.yaml
sha256sum /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-raw.json \
  /tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal.yaml
```

Expected: `calibration_status: VALID`, `approval.enabled: false`,
`approval.approved: false`, at least 25 samples per regime, zero evaluation
misclassifications, positive safety margins, and a non-placeholder
`approval.proposal_sha256`.

- [ ] **Step 5: Stop only the owned stack and checkpoint the evidence**

Use the exact process group, wait for ordered shutdown, verify no owned residual
processes/nodes, and update the ledger with observed distributions, hashes,
proposal path/hash, invalid runs, and the next step `USER_APPROVAL_REQUIRED`.

Do not copy raw evidence into the repository and do not modify
`contact_calibration.yaml` yet.

---

### Task 9: Obtain exact user approval and activate the policy

**Files:**
- Modify after approval: `src/so101_mujoco_demo_py/config/contact_calibration.yaml`
- Modify: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`

**Interfaces:**
- Consumes: Task 8 disabled proposal and exact `proposal_sha256`.
- Produces: one checked-in enabled schema-v2 policy whose approval envelope references the exact hash.

- [ ] **Step 1: Present the approval packet and stop**

Report one table with every threshold, unit, calibration/evaluation sample count,
p05/p50/p95 per regime, safety margin, confusion matrix, false-positive/negative
count, model/scene/motion hashes, raw evidence SHA-256, proposal file SHA-256,
and `proposal_sha256`.

Ask the user to type the fixed prefix `批准 contact proposal ` followed
immediately by the exact 64-hex `proposal_sha256` displayed in the packet.

Do not infer approval from earlier design messages. Do not continue this task
until that exact hash is approved.

- [ ] **Step 2: Apply the exact approval through the CLI**

After the exact response, use `approved_by=user` and the current ISO-8601
Asia/Shanghai timestamp:

```zsh
proposal_path=/tmp/so101-debug-mujoco-maintainability-remediation/project-a-calibration/contact-calibration-proposal.yaml
proposal_sha=$(python3 -c 'import sys, yaml; print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))["approval"]["proposal_sha256"])' "$proposal_path")
approved_at=$(date --iso-8601=seconds)
ros2 run so101_mujoco_demo_py analyze_contact_calibration \
  --approve "$proposal_path" \
  --proposal-sha256 "$proposal_sha" \
  --approved-by user \
  --approved-at "$approved_at" \
  --output src/so101_mujoco_demo_py/config/contact_calibration.yaml
```

Before running the approval command, print `proposal_sha` and verify it is
byte-for-byte identical to the hash in the user's response. If it differs,
stop without writing the checked-in policy. `approved_at` comes from the
command-time clock and is recorded in the ledger.

- [ ] **Step 3: Validate approval and fingerprint rejection**

Run:

```zsh
python3 src/so101_mujoco_demo_py/scripts/analyze_contact_calibration.py \
  --validate src/so101_mujoco_demo_py/config/contact_calibration.yaml
PYTHONNOUSERSITE=1 python3 -m pytest -q \
  src/so101_mujoco_demo_py/test/test_contact_policy.py \
  src/so101_mujoco_demo_py/test/test_contact_calibration_contract.py \
  src/so101_mujoco_demo_py/test/test_pick_place_cli.py
```

Expected: exact policy validates and execute preflight tests accept it; mutation
fixtures still reject every fingerprint change.

- [ ] **Step 4: Commit the approved artifact and ledger reference**

```zsh
git add -- \
  src/so101_mujoco_demo_py/config/contact_calibration.yaml \
  docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md
git commit -m "feat(so101_mujoco): activate approved contact policy"
```

---

### Task 10: Verify Project A automatically and with one physical cycle

**Files:**
- Modify: `docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md`
- No production changes unless a new RED regression reproduces a failure.

**Interfaces:**
- Consumes: exact approved policy commit from Task 9.
- Produces: Project A completion checkpoint and an immutable physical acceptance manifest for Project B.

- [ ] **Step 1: Run focused and package gates**

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
source install/setup.zsh
PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_mujoco_demo_py/test
ruff check src/so101_mujoco_demo_py
ruff format --check src/so101_mujoco_demo_py
zsh src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --check
```

Expected: all tests/gates pass. Ruff format is check-only.

- [ ] **Step 2: Rebuild an isolated installed runtime**

Run:

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_moveit/.worktrees/ws_mujoco_ros2_control_fork/install/setup.zsh
acceptance_build=/tmp/so101-debug-mujoco-maintainability-remediation/project-a-acceptance-build
test ! -e "$acceptance_build"
mkdir -p "$acceptance_build"
colcon --log-base "$acceptance_build/log" build \
  --base-paths src \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --build-base "$acceptance_build/build" \
  --install-base "$acceptance_build/install" \
  --symlink-install
source "$acceptance_build/install/setup.zsh"
ros2 pkg prefix so101_mujoco_demo_py
ros2 pkg prefix so101_mujoco_support
python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
python3 src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml \
  --check-only
```

Expected: build and both checks exit zero; package prefixes resolve to the
fresh acceptance install and fork dependencies resolve to the pinned overlay.

- [ ] **Step 3: Pre-register and run one FULL_RESTART policy acceptance**

Create the next ledger experiment with one unique domain/partition/session and
exact approved policy/model hashes. Run the existing production workflow once.
It must prove:

- controller/action success and joint/TCP convergence;
- approved fresh bilateral grasp;
- causal micro-lift and stable transport without hidden aid;
- MoveIt collision-shadow attach/detach readback;
- release-epoch settle and final target/support/twist success;
- ordered shutdown, exit code zero, and no owned residual process.

This is an A-stage acceptance, not part of the final Project D 5+5 qualification.

- [ ] **Step 4: Record Project A checkpoint and commit docs**

Write hashes, exact commands/exit codes, evidence paths, observed outcome, and
remaining Project B risk to the ledger. Set the next command to create the
Project B implementation plan from the approved design.

```zsh
git add -- docs/experiments/so101-mujoco-maintainability-remediation-experiment-ledger.md
git commit -m "test(so101_mujoco): qualify approved outcome policy"
```

Expected: Project A is independently reviewable; the goal remains active for
Projects B, C, and D.

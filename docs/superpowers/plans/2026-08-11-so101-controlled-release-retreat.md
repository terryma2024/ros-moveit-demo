# SO-101 Controlled Release Retreat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the continuous physical pick-place strategy use a preflighted, selectively constrained world-Z Cartesian retreat after opening the gripper, with guaranteed MoveIt Planning Scene restoration.

**Architecture:** Extend the existing Planning Scene shadow client with an explicit temporary `omit` state. Use one injectable helper for the pre-open plan-only check and another for post-open execution/restoration, so the existing post-open/pre-retreat outcome epoch remains intact. The live strategy uses the Cartesian helper as its only final-retreat path; fixed-joint `RETREAT` waypoints are not used as fallback.

**Tech Stack:** Python 3.10, ROS 2, MoveIt 2 actions/services, Gazebo physical-contact backend, pytest, colcon.

## Global Constraints

- Work only in `/data/work/ws_moveit/.worktrees/so101-physical-five-success` on branch `codex/so101-physical-five-success`.
- Experiments use `RESET_WORLD`; never use `FULL_RESTART`.
- Cartesian target is world Z `+0.035 m`; orientation tolerances are relative X/Z `0.005 rad` and relative Y `0.060 rad`.
- The controlled Cartesian route is the default and only continuous final-retreat path; no fixed-joint waypoint fallback.
- Always restore `plastic_cup` as a world object from the latest available Gazebo pose after opening, including failure paths.
- Preserve all pre-existing dirty changes. Do not stage or commit overlapping implementation files as whole files.

---

### Task 1: Planning Scene Temporary Omission

**Files:**
- Modify: `src/so101_gazebo_demo_py/src/live_execute.py` (`PlanningSceneShadowClient.apply`)
- Test: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`

**Interfaces:**
- Consumes: `PlanningSceneShadowClient.apply(operation: str, object_pose: tuple[float, ...] | None = None) -> dict`
- Produces: `apply("omit") -> {"world_objects": ..., "attached_objects": ...}` with `plastic_cup` absent from both lists.

- [ ] **Step 1: Write the failing omission contract test**

Add a source-contract test requiring an explicit `omit` branch that sends both an attached-object REMOVE and a world-object REMOVE, followed by the existing apply-plus-readback path:

```python
def test_moveit_shadow_can_temporarily_omit_cup_for_release_retreat() -> None:
    source = LIVE_EXECUTE.read_text()
    apply_body = source[source.index("    def apply("):source.index("\n\ndef run_live_plan_only")]
    assert 'elif operation == "omit":' in apply_body
    assert "scene.robot_state.attached_collision_objects=[remove]" in apply_body
    assert "scene.world.collision_objects=[world]" in apply_body
    assert "world.operation=CollisionObject.REMOVE" in apply_body
```

- [ ] **Step 2: Run the focused test and verify RED**

Run from the package directory:

```bash
pytest -q test/test_live_physical_outcome_contract.py::test_moveit_shadow_can_temporarily_omit_cup_for_release_retreat
```

Expected: FAIL because `operation == "omit"` is absent.

- [ ] **Step 3: Implement the minimal `omit` scene diff**

Add this branch before `detach`:

```python
elif operation == "omit":
    remove=AttachedCollisionObject()
    remove.object.id="plastic_cup"
    remove.object.operation=CollisionObject.REMOVE
    scene.robot_state.attached_collision_objects=[remove]
    world=CollisionObject()
    world.id="plastic_cup"
    world.header.frame_id="world"
    world.operation=CollisionObject.REMOVE
    scene.world.collision_objects=[world]
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the same pytest command. Expected: PASS.

### Task 2: Injectable Preflight and Controlled Retreat Helpers

**Files:**
- Modify: `src/so101_gazebo_demo_py/src/live_execute.py`
- Test: `src/so101_gazebo_demo_py/test/test_outcome_first_continuation.py`
- Test: `src/so101_gazebo_demo_py/test/test_main_strategy_parity.py`

**Interfaces:**
- Produces: `_moveit_world_z_execute(..., execute_trajectory: bool = True)`; when false, return planning metadata without calling `/execute_trajectory`.
- Produces: `preflight_controlled_release_retreat(backend, apply_scene, plan_retreat) -> dict`.
- Produces: `execute_controlled_release_retreat(backend, apply_scene, released, execute_retreat) -> dict`.
- Preflight result contains `planned_points`, `omitted_scene`, and `restored_scene`; execution result contains `execution_points`, `retreated`, `omitted_scene`, and `restored_scene`.

- [ ] **Step 1: Write failing orchestration tests**

Use fake samples, event lists, and injected callables. Require the two helper orders below and confirm the exact selective tolerances in the real wrapper:

```python
assert preflight_events == ["omit", "plan", "attach"]
assert execution_events == ["omit", "execute", "detach"]
assert "orientation_tolerances_rad=(0.005,0.060,0.005)" in live_execute_source
```

Add a second test where `execute_retreat` raises; require `detach` after the exception and require the re-raised error to preserve the execution failure. Add a third test where planning fails; require `attach` restoration. The live source-contract test in Task 3 proves the preflight call precedes `open_gripper_from_bilateral_release`.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
pytest -q \
  test/test_outcome_first_continuation.py -k controlled_release_retreat \
  test/test_main_strategy_parity.py::test_controlled_release_retreat_uses_selective_pitch_tolerance
```

Expected: FAIL because the helper and plan-only execution switch do not exist.

- [ ] **Step 3: Add plan-only support without changing the existing default**

Extend `_moveit_world_z_execute`:

```python
def _moveit_world_z_execute(..., execute_trajectory: bool = True):
    # existing planning logic
    if not execute_trajectory:
        node.destroy_subscription(subscription)
        node.destroy_node()
        rclpy.shutdown()
        return points,transform.transform.translation.z
    # existing ExecuteTrajectory logic
```

Keep `execute_trajectory=True` as the default so all current micro-lift and alignment callers retain their behavior.

- [ ] **Step 4: Implement both orchestration helpers**

Implement the helpers with this control structure:

```python
def preflight_controlled_release_retreat(backend, apply_scene, plan_retreat):
    omitted_scene=apply_scene("omit")
    primary_error=None
    try:
        planned_points=plan_retreat()
    except Exception as error:
        primary_error=error
    finally:
        latest=backend.sample()
        try:
            restored_scene=apply_scene(
                "attach", (*latest.object_xyz,*latest.object_xyzw),
            )
        except Exception as restore_error:
            if primary_error is not None:
                raise RuntimeError(
                    f"preflight failed: {primary_error}; restore failed: {restore_error}"
                ) from restore_error
            raise
    if primary_error is not None:
        raise primary_error
    return {
        "planned_points":planned_points,
        "omitted_scene":omitted_scene,
        "restored_scene":restored_scene,
    }

def execute_controlled_release_retreat(
    backend, apply_scene, released, execute_retreat,
):
    omitted_scene=None
    primary_error=None
    try:
        omitted_scene=apply_scene("omit")
        execution_points=execute_retreat()
        retreated=backend.sample()
    except Exception as error:
        primary_error=error
        retreated=None
    finally:
        try:
            latest=backend.sample()
        except Exception:
            latest=released
        restored_scene=apply_scene(
            "detach", (*latest.object_xyz,*latest.object_xyzw),
        )
    if primary_error is not None:
        raise primary_error
    return {
        "retreated":retreated,
        "execution_points":execution_points,
        "omitted_scene":omitted_scene,
        "restored_scene":restored_scene,
    }
```

If both the primary action and restoration fail, raise one `RuntimeError` containing both error strings so neither failure disappears from evidence.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 pytest command. Expected: all selected tests PASS.

### Task 3: Continuous Strategy Integration and Verification

**Files:**
- Modify: `src/so101_gazebo_demo_py/src/live_execute.py` (`_run_live_execute_with_scene` release section)
- Modify: `src/so101_gazebo_demo_py/test/test_live_physical_outcome_contract.py`
- Modify: `docs/experiments/so101-physical-five-success-v2-experiment-ledger.md`

**Interfaces:**
- Consumes: `preflight_controlled_release_retreat(...)` and `execute_controlled_release_retreat(...)` from Task 2.
- Produces: continuous policy telemetry for preflight points, execution points, omitted scene, restored scene, and final released/retreated samples.

- [ ] **Step 1: Replace obsolete source-contract assertions with failing controlled-path assertions**

Require the release section to call `preflight_controlled_release_retreat` before `open_gripper_from_bilateral_release`, call `execute_controlled_release_retreat` from the existing immediate-retreat callback, require `_moveit_world_z_execute` with `0.035` and `(0.005,0.060,0.005)`, and forbid `backend.move_arm(retreat_policy.waypoints, ...)` between opening and final outcome collection.

- [ ] **Step 2: Run the release-contract tests and verify RED**

Run:

```bash
pytest -q test/test_live_physical_outcome_contract.py -k 'release or retreat'
```

Expected: FAIL on the old fixed-joint retreat assertions.

- [ ] **Step 3: Wire the helper into the continuous strategy**

Pass these callables while retaining `collect_final_outcome_after_immediate_retreat`, so its pre-retreat epoch occurs after opening and before execution:

```python
plan_retreat=lambda:_moveit_world_z_execute(
    0.035,
    orientation_tolerances_rad=(0.005,0.060,0.005),
    execute_trajectory=False,
)[0]
execute_retreat=lambda:_moveit_world_z_execute(
    0.035,
    orientation_tolerances_rad=(0.005,0.060,0.005),
)[0]
```

Set `scene_membership` from `restored_scene`. Keep `collect_final_outcome_after_immediate_retreat`: it collects the existing pre-retreat epoch after opening, invokes `execute_controlled_release_retreat` through `immediate_retreat`, then collects the post-retreat epoch. Remove the direct joint-waypoint retreat from this release path.

- [ ] **Step 4: Run targeted and package verification**

Run:

```bash
pytest -q \
  test/test_live_physical_outcome_contract.py \
  test/test_outcome_first_continuation.py \
  test/test_main_strategy_parity.py
colcon build --base-paths . --packages-select so101_gazebo_demo_py
source install/setup.zsh
colcon test --base-paths . --packages-select so101_gazebo_demo_py --event-handlers console_direct+
colcon test-result --test-result-base build/so101_gazebo_demo_py --verbose
```

Expected: targeted tests PASS; package tests report zero failures and zero errors. Record commands, exit codes, and SHA-256 hashes in the ledger.

- [ ] **Step 5: Run one RESET_WORLD full sample**

Use the existing `ROS_DOMAIN_ID=189` and `GZ_PARTITION=so101_phy5_v2_r0_001` stack. Reset with the repository `RESET_WORLD` CLI, then run exactly one unchanged full continuous policy sample. Do not use `FULL_RESTART`.

Acceptance evidence:

```text
gripper q6 reaches configured open position
TCP world-Z delta is approximately +35 mm
last contact window contains no robot-cup contact
Planning Scene final attached_objects excludes plastic_cup
Planning Scene final world_objects includes plastic_cup
```

Record success or valid failure without counting it toward five consecutive successes unless every existing physical-outcome criterion also passes.

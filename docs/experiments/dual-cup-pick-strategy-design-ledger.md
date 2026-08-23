# Dual Cup Pick Strategy Design Ledger

```yaml
task_id: dual-cup-pick-strategy-design-20260823
goal: Document an implementation-ready, fail-closed dual strategy design for fixed and perception-driven cup pick-place.
worktree: /Users/matianyi/Projects/robot_demo_001/moveit-demo
branch: main
base_commit: e34bf2b8eea55c44b24b32ff6521887cad0abca4
current_commit: e34bf2b8eea55c44b24b32ff6521887cad0abca4
evidence_root: /tmp/so101-debug-dual-cup-pick-design-20260823
runtime_executable: NONE; documentation-only task
install_overlay: /Users/matianyi/Projects/robot_demo_001/moveit-demo/install/so101_demo_py
ros_domain_id: unset
gz_partition: unset
confirmed_conclusions:
  - V1 fixed waypoints and V2 perception-driven TCP planning must remain separate public strategies.
  - V2 must not fall back to fixed waypoints after a cup-pose failure.
disproven_routes:
  - Treating an external cup Pose as a direct replacement for the existing fixed joint waypoint YAML.
open_hypotheses:
  - Dynamic world-frame plan-only can establish a safe first runtime boundary before dynamic execute qualification.
latest_checkpoint: DCP-DESIGN-001
next_experiment: NONE; implementation requires a new PLANNED experiment before runtime actions.
```

```yaml
checkpoint_id: DCP-DESIGN-001
recorded_at: 2026-08-23 Asia/Shanghai
status: VALID
single_variable: documentation of fixed and dynamic public strategy separation
lifecycle: REUSE_STACK
owned_processes: NONE
preserved_processes: all existing ROS, Gazebo, MoveIt, RViz, tmux, and user-owned processes
observed:
  - The current fixed policy requires complete state waypoint ladders.
  - The current cup_pose_subscriber is a separate continuous listener and cannot pass a frozen Pose to pick_place.
  - RobotControlPort already defines TcpMotionRequest as the dynamic planning seam.
artifacts:
  - docs/superpowers/specs/2026-08-23-dual-cup-pick-strategy-design.md
  - docs/superpowers/plans/2026-08-23-dual-cup-pick-strategy-implementation.md
validation:
  - documentation-only; no ROS process started and no motion command issued
  - git diff --no-index --check: PASS for all three new documents
decision: KEEP
retained_runs:
  - /tmp/so101-debug-dual-cup-pick-design-20260823
archived_runs: []
deletion_candidates:
  - /tmp/so101-debug-dual-cup-pick-design-20260823
```

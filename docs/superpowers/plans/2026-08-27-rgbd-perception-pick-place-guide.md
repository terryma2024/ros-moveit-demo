# RGB-D Perception Pick Place Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-linked Chinese tutorial that explains how MuJoCo RGB-D data becomes a `world`-frame `/cup_pose` and drives the existing dynamic SO-101 pick-place workflow.

**Architecture:** The guide complements `docs/so101-dynamic-cup-pick-place-source-guide.md`: it concentrates on the perception and launch-composition half, then hands off to the existing guide for motion-target derivation and state-machine details. Component inventory, ROS communication, algorithms, runnable commands, fail-closed behavior, and the four-preset macOS qualification are derived from current source and the registered experiment ledger.

**Tech Stack:** ROS 2 Jazzy, tf2, Open3D, NumPy, MoveIt 2, ros2_control, MuJoCo, Markdown.

**Spec:** `docs/so101-dynamic-cup-pick-place-source-guide.md` plus the user-approved outline in this task.

## Global Constraints

- Do not alter runtime behavior or product source.
- Preserve the existing untracked macOS four-preset experiment ledger.
- Describe `rgbd_point_cloud` as a one-shot teaching/debug executable and `rgbd_cup_pose` as the production launch component.
- Keep source, installed-runtime, physical, visual, and publication evidence boundaries explicit.
- Reuse the task evidence root `/tmp/so101-debug-mac-four-preset-post-reconcile-20260827`; do not create another root.

---

### Task 1: Write and verify the RGB-D perception tutorial

**Files:**
- Create: `docs/so101-rgbd-perception-pick-place-source-guide.md`
- Preserve: `docs/experiments/macos-four-preset-post-reconcile-experiment-ledger.md`

**Interfaces:**
- Consumes: camera topics `/task_camera/camera_info`, `/task_camera/color`, `/task_camera/depth`; TF chain `world -> base -> camera_link -> task_camera_frame`; output `/cup_pose`; MoveIt services/actions; controller trajectory actions; MuJoCo evidence.
- Produces: one source-linked guide containing an architecture diagram, component inventory, communication table, algorithm walkthrough, launch procedure, four-preset verification table, failure diagnosis, and self-check questions.

- [x] **Step 1: Map the current implementation**

Read the launch composition, camera TF contract, RGB-D point-cloud builder, cup-pose node, dynamic pose source, controller configuration, MJCF keyframes, and experiment ledger. Record only interfaces proven by those files.

- [x] **Step 2: Write the guide**

Create `docs/so101-rgbd-perception-pick-place-source-guide.md`. Link each major behavior to its owning source file and link downstream motion details to `docs/so101-dynamic-cup-pick-place-source-guide.md` instead of duplicating that guide.

- [x] **Step 3: Verify source facts and Markdown links**

Run:

```bash
python3 -c 'import pathlib,re,sys; p=pathlib.Path("docs/so101-rgbd-perception-pick-place-source-guide.md"); t=p.read_text(); links=re.findall(r"\[[^]]+\]\(([^)#]+)(?:#[^)]+)?\)",t); missing=[x for x in links if "://" not in x and not (p.parent/x).resolve().exists()]; print(f"relative_links={len(links)} missing={len(missing)}"); sys.exit(bool(missing))'
rg -n 'rgbd_point_cloud|rgbd_cup_pose|/cup_pose|task_camera_frame|arm_controller|gripper_controller' docs/so101-rgbd-perception-pick-place-source-guide.md
```

Expected: every relative target exists, the production/debug distinction is present, and all required interfaces are covered.

- [x] **Step 4: Run related and package-level tests**

Run the repository's existing perception, launch-composition, dynamic-input, and package test command from the active project environment.

Expected: zero failures; if the local environment cannot execute a layer, report it as unavailable rather than claiming it passed.

- [x] **Step 5: Review the final patch**

Run:

```bash
git diff --check
git status --short
git diff -- docs/so101-rgbd-perception-pick-place-source-guide.md docs/superpowers/plans/2026-08-27-rgbd-perception-pick-place-guide.md
```

Expected: no whitespace errors, only the requested documentation plus the preserved experiment ledger and this plan are present, and no runtime source is modified.

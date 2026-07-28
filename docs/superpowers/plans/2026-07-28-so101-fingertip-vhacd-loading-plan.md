# SO101 Fingertip VHACD Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-finger box and 64-piece moving-jaw collision set with two accurate, low-count offline fingertip VHACD sets, and cache prepared SDF output so Bullet starts materially faster.

**Architecture:** A deterministic generator extracts a bounded fingertip region from each visual STL, emits binary convex STL pieces and a hash manifest, and the Xacro names every installed piece. Model preparation validates both manifests, marks only those meshes as convex hulls, and reuses a digest-addressed prepared-SDF cache. Existing contact observation and attach gates migrate to stable fixed/moving prefixes and remain fail-closed.

**Tech Stack:** Python 3.12, trimesh, VHACD, Xacro, SDFormat 1.11, ROS 2 Jazzy launch, Gazebo Harmonic, Bullet Featherstone, pytest, CTest.

## Global Constraints

- Preserve `wrist_roll_follower_so101_v1.stl` and `moving_jaw_so101_v1.stl` as complete visual meshes.
- Preserve the Coke mass at `0.05 kg` and inertia at `0.0002647 / 0.0002647 / 0.0000953 kg m^2`.
- Preserve `gz-physics-bullet-featherstone-plugin`, the existing state-machine order, and the current wrist orientation.
- Start with eight convex pieces per fingertip; no fingertip may exceed twelve and total pieces may not exceed twenty-four.
- Preserve bilateral contact, sidewall-height, and `0.002 m` maximum-penetration gates.
- Preserve all unrelated staged, unstaged, and untracked files. Every commit command must name only the files in its task.
- Run GUI processes only in `so101-moveit` after `source ~/gui-env.zsh`; never hard-code `DISPLAY` or `XAUTHORITY`.

---

### Task 1: Capture the 64-piece startup baseline

**Files:**
- Create: `src/so101_gazebo_demo/scripts/benchmark_gazebo_startup.py`
- Create: `src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

**Interfaces:**
- Consumes: `ros2 launch so101_gazebo_demo so101_gazebo.launch.py headless:=true` and `ros2 control list_controllers`.
- Produces: `measure_runs(command: list[str], runs: int, timeout: float, domain_start: int, partition_prefix: str) -> dict` and JSON with `durations_seconds`, `median_seconds`, `piece_count`, and `success`.

- [ ] **Step 1: Write the failing parser and statistics tests**

```python
def test_active_controller_evidence_requires_all_three():
    text = 'joint_state_broadcaster active\narm_controller active\ngripper_controller active\n'
    assert module.controllers_ready(text)
    assert not module.controllers_ready('arm_controller active\n')


def test_summary_uses_median_and_records_piece_count():
    result = module.summarize([12.0, 9.0, 10.0], piece_count=64)
    assert result == {
        'durations_seconds': [12.0, 9.0, 10.0],
        'median_seconds': 10.0,
        'piece_count': 64,
        'success': True,
    }
```

- [ ] **Step 2: Run the test and verify RED**

Run: `python3 -m pytest -q src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py`

Expected: FAIL because `benchmark_gazebo_startup.py` and its functions do not exist.

- [ ] **Step 3: Implement the minimal benchmark utility**

Use `time.monotonic()`, a unique `ROS_DOMAIN_ID` and `GZ_PARTITION` per run, `start_new_session=True`, polling `ros2 control list_controllers`, and `os.killpg(..., signal.SIGINT)` cleanup. The CLI must accept `--runs`, `--timeout`, `--domain-start`, `--partition-prefix`, `--piece-count`, and `--output`. A timed-out run exits non-zero and records no successful median.

- [ ] **Step 4: Register and run the test**

Add `ament_add_pytest_test(test_benchmark_gazebo_startup test/test_benchmark_gazebo_startup.py)` and run the focused pytest again.

Expected: `2 passed`.

- [ ] **Step 5: Measure and retain the baseline before changing collision assets**

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
python3 src/so101_gazebo_demo/scripts/benchmark_gazebo_startup.py \
  --runs 3 --timeout 180 --domain-start 130 \
  --partition-prefix so101_vhacd_baseline --piece-count 64 \
  --output /tmp/so101-vhacd-baseline.json
```

Expected: three successful durations and a finite positive median. Keep the JSON until final comparison.

- [ ] **Step 6: Commit only the benchmark utility and test**

```bash
git add -- src/so101_gazebo_demo/scripts/benchmark_gazebo_startup.py \
  src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py \
  src/so101_gazebo_demo/CMakeLists.txt
git commit --only -- src/so101_gazebo_demo/scripts/benchmark_gazebo_startup.py \
  src/so101_gazebo_demo/test/test_benchmark_gazebo_startup.py \
  src/so101_gazebo_demo/CMakeLists.txt \
  -m 'test: measure SO101 Gazebo startup latency'
```

### Task 2: Generate deterministic fingertip convex sets and manifests

**Files:**
- Create: `src/so101_gazebo_demo/scripts/generate_fingertip_convex_collision.py`
- Create: `src/so101_gazebo_demo/test/test_generate_fingertip_convex_collision.py`
- Retain as compatibility wrapper: `src/so101_gazebo_demo/scripts/generate_jaw_convex_collision.py`

**Interfaces:**
- Consumes: source STL, `Roi(minimum, maximum)`, prefix, hull limit, voxel resolution.
- Produces: `extract_roi(mesh: trimesh.Trimesh, roi: Roi) -> trimesh.Trimesh`, `generate_collision_set(...) -> dict`, binary STL files, and `manifest.json` schema version 1.

- [ ] **Step 1: Write failing unit tests with synthetic meshes**

Test that ROI extraction excludes triangles outside the bounds, empty ROI raises `ValueError('fingertip ROI is empty')`, eight-piece budget is passed to VHACD, STL output begins with an 80-byte binary header rather than `solid`, and two identical fixture runs produce identical ordered manifest fields and hashes.

The manifest assertion must require:

```python
{
  'schema_version': 1,
  'prefix': 'fixed_finger_contact_convex',
  'source_sha256': '<64 lowercase hex characters>',
  'roi_min': [-0.031, -0.012, 0.060],
  'roi_max': [-0.012, 0.012, 0.106],
  'max_convex_hulls': 8,
  'voxel_resolution': 400000,
  'pieces': [{'filename': 'fixed_finger_contact_convex_000.stl', 'sha256': '<hash>'}],
}
```

- [ ] **Step 2: Run the generator tests and verify RED**

Run: `python3 -m pytest -q src/so101_gazebo_demo/test/test_generate_fingertip_convex_collision.py`

Expected: FAIL because the generic generator is absent.

- [ ] **Step 3: Implement ROI extraction, VHACD, binary export, and atomic manifest output**

Use these initial source-mesh ROIs:

- fixed finger: min `[-0.031, -0.012, 0.060]`, max `[-0.012, 0.012, 0.106]` from `wrist_roll_follower_so101_v1.stl`;
- moving jaw: min `[-0.0125, -0.0825, -0.0245]`, max `[0.0105, -0.0350, 0.0245]` from `moving_jaw_so101_v1.stl`.

Select faces whose triangle bounds intersect the ROI, remove unreferenced vertices, repair normals, run `convex_decomposition(maxConvexHulls=8, resolution=400000, minimumVolumePercentErrorAllowed=0.05, maxRecursionDepth=15, maxNumVerticesPerCH=64, shrinkWrap=True)`, sort pieces by centroid and volume before naming, export with `trimesh.exchange.stl.export_stl`, and atomically replace the output directory.

- [ ] **Step 4: Convert the old jaw script into a compatibility wrapper**

The wrapper calls the new CLI with prefix `moving_jaw_contact_convex` and the exact moving-jaw ROI above. It must print a deprecation message but retain the old positional source/output arguments.

- [ ] **Step 5: Run tests and commit only generator files**

Expected: all generator tests pass and `git diff --check` is clean.

### Task 3: Generate and inspect the real eight-piece assets

**Files:**
- Create: `src/so101_gazebo_demo/meshes/so101/collision/fixed_finger_contact/manifest.json`
- Create: `src/so101_gazebo_demo/meshes/so101/collision/fixed_finger_contact/fixed_finger_contact_convex_*.stl`
- Create: `src/so101_gazebo_demo/meshes/so101/collision/moving_jaw_contact/manifest.json`
- Create: `src/so101_gazebo_demo/meshes/so101/collision/moving_jaw_contact/moving_jaw_contact_convex_*.stl`

**Interfaces:**
- Consumes: Task 2 CLI and the two source STLs.
- Produces: two checked-in collision sets whose manifests each contain between one and eight pieces.

- [ ] **Step 1: Generate both real collision sets**

Run the new CLI twice with the exact ROIs, `--max-convex-hulls 8`, and `--voxel-resolution 400000`.

- [ ] **Step 2: Verify geometry before wiring it into Xacro**

Run a read-only inspection that prints each piece's convexity, bounds, triangle count, and total size. Fail if a piece is empty or non-convex, either manifest has more than eight pieces, total pieces exceed sixteen, or either directory exceeds 260 KB.

- [ ] **Step 3: Render fixed and moving pieces over their visual STL for inspection**

Create `/tmp/so101-fixed-finger-collision-preview.png` and `/tmp/so101-moving-jaw-collision-preview.png` with trimesh scene rendering. Confirm the fixed set covers the load-bearing fixed fingertip and excludes the housing; confirm the moving set covers the inner fingertip and excludes the hinge.

- [ ] **Step 4: Commit only the two generated directories**

Use `git add --` and `git commit --only --` with the two exact directories; do not include the old 64-piece directory in this commit.

### Task 4: Replace the box and 64-piece Xacro profile

**Files:**
- Modify: `src/so101_gazebo_demo/urdf/so101_base.xacro`
- Modify: `src/so101_gazebo_demo/test/test_configuration_contract.py`
- Modify: `src/so101_gazebo_demo/test/test_so101_pick_place_world.py`

**Interfaces:**
- Consumes: Task 3 filenames.
- Produces: stable collision prefixes `fixed_finger_contact_convex_` on link `gripper` and `moving_jaw_contact_convex_` on link `jaw`.

- [ ] **Step 1: Change configuration tests first**

Require both Gazebo links to contain mesh collisions, forbid `fixed_finger_contact` box geometry, require each prefix count to match its manifest, require one through eight pieces per prefix and no more than sixteen total, and require each collision origin to equal its link's visual origin.

- [ ] **Step 2: Run the focused configuration test and verify RED**

Run: `python3 -m pytest -q src/so101_gazebo_demo/test/test_configuration_contract.py -k gazebo_contact_profile`

Expected: FAIL because the fixed finger is still a box and the moving jaw still has 64 old names.

- [ ] **Step 3: Add generic Xacro mesh-collision macros and list the manifest pieces**

Use the gripper visual transform `xyz="5.55112e-17 -0.000218214 0.000949706" rpy="-3.14159 -5.55112e-17 -9.17912e-24"` for fixed pieces and retain the moving-jaw visual transform. Remove the fixed box and all 64 old macro calls only after both new lists are present.

- [ ] **Step 4: Run configuration and world static tests**

Expected: focused configuration test passes; `python3 -m pytest -q src/so101_gazebo_demo/test/test_so101_pick_place_world.py -k 'not runtime'` remains green.

- [ ] **Step 5: Commit only Xacro and its two tests**

Use an exact-path `git commit --only`.

### Task 5: Validate manifests and cache the prepared SDF

**Files:**
- Modify: `src/so101_gazebo_demo/scripts/prepare_simulation_model.py`
- Modify: `src/so101_gazebo_demo/test/test_prepare_simulation_model.py`
- Modify: `src/so101_gazebo_demo/launch/so101_gazebo.launch.py`
- Modify: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`

**Interfaces:**
- Consumes: Xacro, both manifest paths, `base_height`, and cache directory.
- Produces: `load_manifest(path: Path) -> dict`, `model_cache_key(...) -> str`, `enable_fingertip_convex_hulls(sdf_text: str, manifests: list[dict]) -> str`, and an atomic cached SDF copy at the requested spawn path.

- [ ] **Step 1: Replace the hard-coded preparation tests with failing manifest/cache tests**

Cover both prefixes, exact name/count agreement, missing and duplicate collision rejection, piece hash mismatch rejection, total count over twenty-four rejection, cache miss invoking Xacro and `gz sdf`, cache hit invoking neither, and Xacro/manifest/base-height changes producing a different key.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python3 -m pytest -q src/so101_gazebo_demo/test/test_prepare_simulation_model.py`

Expected: FAIL because manifest-driven validation and cache functions are absent.

- [ ] **Step 3: Implement manifest validation and convex-hull tagging**

Remove `DEFAULT_MAX_CONVEX_HULLS` from runtime preparation. Validate SHA-256 against installed piece files before parsing SDF. Set `optimization="convex_hull"` on exactly the collision meshes listed by both manifests and remove any nested runtime `convex_decomposition` elements.

- [ ] **Step 4: Implement the digest cache**

Default cache root is `${XDG_CACHE_HOME:-$HOME/.cache}/so101_gazebo_demo/prepared_sdf`. The cache key includes Xacro bytes, both manifest bytes and referenced piece hashes, base height, collision mode, and schema version. Write cache entries atomically, then copy the valid cached entry to the PID-specific output requested by launch.

- [ ] **Step 5: Update launch arguments and tests**

Replace `--max-convex-hulls` and `--voxel-resolution` with two `--manifest` arguments. Keep preparation-before-spawn event ordering. Reduce `INITIAL_DETACH_TIMEOUT_SECONDS` only after measured post-change startup data supports the new value; otherwise retain 120 seconds.

- [ ] **Step 6: Run focused tests and commit exact files**

Expected: preparation and launch contract tests pass; `git diff --check` is clean.

### Task 6: Migrate contact classification without weakening attach safety

**Files:**
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_gazebo_attachment.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`

**Interfaces:**
- Consumes: new fixed/moving collision prefixes.
- Produces: unchanged `gazebo_coke_fixed_finger_contact`, `gazebo_coke_moving_jaw_contact`, height ranges, collision-name set, and maximum depth facts.

- [ ] **Step 1: Add failing contact-name tests**

Feed contacts named `so101::gripper::fixed_finger_contact_convex_003` and `so101::jaw::moving_jaw_contact_convex_005`; require independent fixed/moving evidence. Require an unrelated gripper housing collision not to satisfy either side.

- [ ] **Step 2: Run focused CTest and verify RED**

Run the two named test executables with filters for the new collision names.

- [ ] **Step 3: Replace broad substring rules with stable-prefix classification**

Classify only the two approved prefixes. Preserve contact heights, maximum penetration, freshness handling, bilateral gate, top-edge rejection, and 2 mm limit.

- [ ] **Step 4: Run all six focused attachment/gripper/state-machine CTests**

Expected: 6/6 pass.

- [ ] **Step 5: Commit only observer and two tests**

Use an exact-path `git commit --only`.

### Task 7: Build, compare startup performance, and perform GUI acceptance

**Files:**
- Runtime evidence: `/tmp/so101-vhacd-baseline.json`
- Runtime evidence: `/tmp/so101-vhacd-optimized.json`
- Runtime logs: `/tmp/so101-fingertip-vhacd-*.log`
- GUI captures: `assets/captures/ai-station/<timestamp>/`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: fresh build/test output, three-run performance comparison, contact metrics, complete state trace or first physical failure, and screenshots.

- [ ] **Step 1: Build and run automated regression**

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
source install/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
ctest --test-dir build/so101_gazebo_demo -R '^(test_so101_gazebo_attachment|test_so101_attachment_contracts|test_so101_fixed_motion_targets|test_so101_joint_motion_adapter|test_so101_gripper_state|test_so101_task3_runtime)$' --output-on-failure
python3 -m pytest -q src/so101_gazebo_demo/test/test_configuration_contract.py src/so101_gazebo_demo/test/test_prepare_simulation_model.py src/so101_gazebo_demo/test/test_so101_launch_contract.py
git diff --check
```

Expected: build exits zero, 6/6 CTests pass, all named pytest files pass, and diff check is empty.

- [ ] **Step 2: Measure three optimized headless starts under the same conditions**

Run the Task 1 benchmark with `--partition-prefix so101_vhacd_optimized`, `--piece-count` equal to the two manifest totals, and output `/tmp/so101-vhacd-optimized.json`.

- [ ] **Step 3: Compare medians**

Calculate `improvement = 1 - optimized_median / baseline_median`. Acceptance requires `improvement >= 0.40`; otherwise inspect whether time remains in Bullet collision construction, reduce only the failing ROI's hull budget, regenerate, and rerun Tasks 3 through 7 without weakening contact gates.

- [ ] **Step 4: Restart the GUI in the existing session**

Use `so101-moveit`, source `~/gui-env.zsh`, source ROS/workspace, and set the confirmed `ROS_DOMAIN_ID` and `GZ_PARTITION`. Start with `headless:=false`; do not create a replacement GUI session.

- [ ] **Step 5: Run reset and full state-machine acceptance**

Record Bullet plugin loading, both manifest counts, absence of mesh construction/resource errors, fixed and moving collision names, contact heights/normals, maximum penetration, q6 target/observation/controller error, RTF after settling, attach state, MoveIt membership, LIFT, detach, and recovery. If the run fails, report the first physical/state failure rather than only a later recovery failure.

- [ ] **Step 6: Capture and inspect the actual GUI**

Use the repository ai-station capture workflow from the tmux GUI environment. The screenshot must show both fingertips relative to Coke and confirm that the fixed fingertip does not visibly penetrate the cylinder.

- [ ] **Step 7: Final verification and handoff**

Report exact pass/fail counts, baseline and optimized medians, improvement percentage, piece counts, penetration, RTF, and state trace. Do not claim complete grasp success unless attach, LIFT, detach, and cross-world state checks all have fresh evidence.

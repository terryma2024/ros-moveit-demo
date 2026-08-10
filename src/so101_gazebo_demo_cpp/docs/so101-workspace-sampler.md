# SO-101 TCP 6D workspace sampler

This ai-station-only offline tool samples arm joints 1–5, calculates the actual `so101_tcp`
position and orientation with MoveIt FK, and classifies the fixed canonical `q6_preopen` state
against a process-local Planning Scene containing only `base_pedestal` and `table`. It does not
start or query move_group, Gazebo, controllers, RViz, or a live Planning Scene.

Run the quick profile:

```bash
ros2 launch so101_gazebo_demo_cpp so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-quick profile:=quick
```

Run the default 30-minute full profile:

```bash
ros2 launch so101_gazebo_demo_cpp so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-full profile:=full
```

Resume an interrupted run or append another equal budget window after `budget_exhausted`:

```bash
ros2 launch so101_gazebo_demo_cpp so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-full profile:=full resume:=true
```

An existing nonempty directory is rejected unless resume is requested and every model, scene,
configuration, executable, and package provenance field matches its checkpoint.

## Artifacts

- `samples.csv` is the canonical double-precision record of joints, TCP pose, collision flags,
  position voxel, and orientation cluster for every geometric sample.
- `all_poses.ply` is the binary little-endian CloudCompare view of every sampled pose.
- `collision_free_poses.ply` contains exactly rows classified bounds-valid with neither self nor
  table/pedestal collision.
- `position_voxels.ply` summarizes sample counts, free/colliding counts, `orientation_count`, and
  `collision_free_orientation_count` per occupied position voxel. In CloudCompare, color this
  cloud by `orientation_count`.
- `collision_pairs.csv` aggregates collision-pair evidence without repeating strings per vertex.
- `manifest.json` records content hashes, fixed scene/preopen assumptions, and the stop reason.
- `summary.json` records counts and per-batch position/orientation discovery rates.
- `checkpoint.json` and `chunks/` are the atomic resume record and committed batch data.

`converged_at_configured_resolution` means five (full) or three (quick) consecutive batches met
both configured new-coverage thresholds after the minimum sample count. `budget_exhausted` is a
successful, resumable sampled result, but it is not convergence. `sample_cap_reached` is also not
convergence.

The output is a deterministic discrete approximation for the current URDF/SRDF, fixed preopen
gripper, and offline table/pedestal scene. It does not prove path reachability, collision-free
motion from Home, Gazebo execution, controller behavior, or real-hardware safety.

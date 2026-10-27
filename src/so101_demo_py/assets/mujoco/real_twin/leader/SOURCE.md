# Source of the leader model files

The files in this directory come from the official SO-101 leader model of the SO-ARM100 project.

- Repository: https://github.com/TheRobotStudio/SO-ARM100
- Commit: `a758567c3978dfeefe282ede0500085a48fe8f78` (resolved from `main` on 2026-10-27)
- Licence: Apache License 2.0, text in `LICENSE` (upstream `LICENSE` at the same commit)
- Downloaded as untrusted data on 2026-10-27 into
  `/data/work/so101-evidence/real-robot/prep-20261026/downloads/so-arm100-a758567c3978dfeefe282ede0500085a48fe8f78/`.
  Nothing from it was executed. The URDF is parsed as XML only; the meshes are loaded as data.

Raw URLs have the prefix `https://raw.githubusercontent.com/TheRobotStudio/SO-ARM100/a758567c3978dfeefe282ede0500085a48fe8f78/`.

| File here | Upstream path | sha256 |
| --- | --- | --- |
| `LICENSE` | `LICENSE` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` |
| `so101_leader_new_calib.urdf` | `Simulation/SO101/so101_leader_new_calib.urdf` | `bc947e2fea65dfc91b0fc40e4cff0c01c6bf426687995937e62e2b0f41122db5` |
| `Handle_SO101.stl` | `Simulation/SO101/assets/Handle_SO101.stl` | `a69b004691392cf0130b32ed9da5cc0c5fee49c2c8abee6ca27bf88e2a11347d` |
| `Trigger_SO101.stl` | `Simulation/SO101/assets/Trigger_SO101.stl` | `7122e0c476e69689eaf18441ecd36f5cf5cdca4d7033c15e5238a9b788e9d71a` |
| `Wrist_Roll_SO101.stl` | `Simulation/SO101/assets/Wrist_Roll_SO101.stl` | `db20e6ac7c08cf8d75692a38db5a217011c97c0ab5d73c248296535df81e39b7` |

The URDF references 14 mesh files, all under `Simulation/SO101/assets/` at the same commit. The other 11 are byte-identical
(same sha256) to files already in this repository under `assets/mujoco/assets/` (symlinks to `assets/common/visual/`), so they
are not copied again. `twin_params.yaml` (`leader.meshes`) lists each mesh with its repository path and sha256, and
`scripts/build_real_twin_scene.py` refuses to generate if any hash differs.

| Upstream mesh | sha256 |
| --- | --- |
| `base_motor_holder_so101_v1.stl` | `8cd2f241037ea377af1191fffe0dd9d9006beea6dcc48543660ed41647072424` |
| `base_so101_v2.stl` | `bb12b7026575e1f70ccc7240051f9d943553bf34e5128537de6cd86fae33924d` |
| `motor_holder_so101_base_v1.stl` | `31242ae6fb59d8b15c66617b88ad8e9bded62d57c35d11c0c43a70d2f4caa95b` |
| `motor_holder_so101_wrist_v1.stl` | `887f92e6013cb64ea3a1ab8675e92da1e0beacfd5e001f972523540545e08011` |
| `rotation_pitch_so101_v1.stl` | `9be900cc2a2bf718102841ef82ef8d2873842427648092c8ed2ca1e2ef4ffa34` |
| `sts3215_03a_no_horn_v1.stl` | `75ef3781b752e4065891aea855e34dc161a38a549549cd0970cedd07eae6f887` |
| `sts3215_03a_v1.stl` | `a37c871fb502483ab96c256baf457d36f2e97afc9205313d9c5ab275ef941cd0` |
| `under_arm_so101_v1.stl` | `d01d1f2de365651dcad9d6669e94ff87ff7652b5bb2d10752a66a456a86dbc71` |
| `upper_arm_so101_v1.stl` | `475056e03a17e71919b82fd88ab9a0b898ab50164f2a7943652a6b2941bb2d4f` |
| `waveshare_mounting_plate_so101_v2.stl` | `e197e24005a07d01bbc06a8c42311664eaeda415bf859f68fa247884d0f1a6e9` |
| `wrist_roll_pitch_so101_v2.stl` | `6c7ec5525b4d8b9e397a30ab4bb0037156a5d5f38a4adf2c7d943d6c56eda5ae` |

## Notes on the model

- The URDF header says the arm links and joints (base to wrist) are unchanged from `so101_new_calib.urdf`; only the gripper
  subtree differs: a fixed wrist-roll part with a handle (`Wrist_Roll_SO101`, `Handle_SO101`) and a `trigger_link` on the
  revolute joint `gripper` (limits 0 to 45 degrees, positive opens).
- The URDF marks the trigger zero, its travel limits and the inertias as provisional estimates, not measurements. The twin
  therefore maps the leader's gripper reading 0..100 linearly onto 0..45 degrees; this is a placeholder, not a calibration.
  The other five joints keep the identity "degrees as radians, clamped" placeholder: the URDF's `new_calib` naming does not
  define a different zero for them (its only calibration remark is a 5-degree offset already inside the elbow limits).
- The URDF `base_link` frame differs from the follower robot file's base frame by a rotation of -90 degrees about z and a
  translation, recorded in `twin_params.yaml` (`leader.urdf_base_in_follower_base`).

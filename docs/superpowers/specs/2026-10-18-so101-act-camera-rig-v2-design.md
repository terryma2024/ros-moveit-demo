# SO-101 ACT camera rig v2: side + wrist on the jaw, head disabled with zero cost — design and plan

Status: CONFIRMED by the human on 2026-10-18 ("确认", twice: poses, then the whole design); queued after O6.

## Human decisions (2026-10-18)

- "把我们的腕部相机也改成和LeRobot一样的方案。头部相机先禁用，上脚架side相机。head search的功能先关掉。但未来，如果把机械臂放到agv上，需要视觉导航和目标定位，还是需要头部相机的。只是现在的头部相机可能还是位置偏低。"
- The answers to the open points, in order:
  1. "用side": the second stream is named `side`.
  2. "ok": keep the neck.
  3. "ok。做到关闭后无额外损耗，比如仿真计算、采样数据、日志log等。"
  4. "ok": 10 Hz.
  5. "head 放到离地 0.8的立杆上。角度按建议。"
  - Then: "头部相机z在踏板之上 0.8m", "那个台子模拟agv", "视野中能看到的机械臂的范围有点小", and finally "确认" for the recommended poses.
- Item 3 overrides item 2. With the head disabled, the neck joint, its actuator and its controller are not loaded at all, and the state becomes 6-dimensional.

## Why

- The current wrist camera sits on the wrist body facing sideways. At task_start the cup is 75° off its axis and the image is mostly the gripper body and black background; the human observed the same. Over an episode the cup is visible 0.42 of the time on average.
- The head camera sits on the robot's base chain behind the arm. The arm fills its view, and the cup is partly hidden.
- The training data starts with 3.8 to 8.6 s of idle per episode, and the offline metric of TRAIN-001 cannot tell whether the policy works. A camera set that sees the grasp clearly is the precondition for a useful policy.
- LeRobot's SO-101 practice is a wrist camera on the moving jaw, looking along the gripping direction, plus a fixed external camera (top, front or side).

## The rig (evidence: REG/diag-delivery-20261016/camera-rig-v2/)

| Camera | Pose | Measured |
| --- | --- | --- |
| `wrist` (moved) | Parent the moving `jaw` body. pos (−0.014, −0.012, 0.050) in the jaw frame; quat wxyz (0.8175, −0.5712, 0.0421, −0.0602); fovy 90 (80 if the real module is narrower). The old `wrist_camera_mount` box and its collision geom are removed. | Fingertips and cup rim in view at pre-grasp and grasp. Cup visible ratio 0.81 over the episode (old: 0.42). The cup is out of frame at task_start, as for any jaw camera. |
| `side` (new) | World body (tripod), `sB_right`: pos (−0.50, −0.32, 0.42), looking at (0, −0.24, 0.30); quat wxyz (0.5969, 0.472, −0.4024, −0.509); fovy 62. | Arm in profile; the arm is in frame at every row. Cup visible mean 0.95, min 0.89. Sampling triangle and place target well inside the image. |
| `task_camera` (unchanged) | World RGB-D camera used by the Teacher's cup perception. | Not touched. Its TF is hard-coded in runtime/camera_tf.py. |
| `head` (disabled) | Kept in code and as a future model variant; not in the collection scene. | See Future head. |

All cameras are 640×480 at 10 Hz (decision 4). The side camera publishes RGB only (no depth).

## Head disabled with zero cost (decision 3)

- **Scene variant.** The ACT collection scene, `act/scene.xml` → a new `act/scene_rig_v2.xml`, includes a robot model variant without `head_mount`, `neck_yaw_joint`, the neck actuator and `head_camera`. The URDF and SRDF variants match.
  - No head rendering, no neck physics, no neck controller.
- **Launch and config.** A new plugin file, `act/mujoco_plugins_rig_v2.yaml`, lists only `wrist`, `side` and `task_camera`; `neck_yaw_joint` is removed from the scalar joint audit names. A new controllers file has no `neck_controller`.
  - The launch takes the variant through the existing scene and plugin arguments.
- **Inventory and readiness.** The exact node and controller inventory, `act_stack_ready` (neck and head RGB checks, `--include-neck`), the recorder topic lists, the supervisor and readback sources, the physics join and the prefix source all become driven by the rig profile. With the head disabled they neither expect nor subscribe to anything of the head or neck.
  - No topic, no bag channel, no log line, no audit stream for them.
- **Head search** is off: no head role, no head-search config, no head-search nodes. Already optional at startup (`act_stack_ready` skips it when no config is named); collection never used it.
- **Kept for the future AGV:** the head-search code, contracts, the C++ neck controller, the teleop head-camera UI and `head_search_scene.xml`. They are untouched, just not composed.

## Camera names and state dimension become data, not code

- **One rig profile document** (`config/act/rig-v2.yaml`) lists:
  - the ordered camera names (`side`, `wrist`), their topics and frame-file keys;
  - whether the head and neck exist;
  - the state layout (six arm joints; neck sin/cos only when the neck exists).
- **Consumers.** About 20 hard-coded `head`/`wrist` points read this profile:
  - synchronizer, episode assembly, continuous capture, synchronized frame capture, recorder schema (`<camera>_png`);
  - contracts observation keys, offline scan, sources, engine and QC camera grid (the "head==wrist" pairing becomes "all configured cameras share the grid");
  - episode QC counts, act_stack_ready, recorder topic lists, delivery diagnostics;
  - training_config `CAMERAS`/`STATE_DIM`, the LeRobot adapter image keys and decode table, the rollout observation adapter.
- **Identity.** The rig profile is part of the frozen inputs and the controlled identity, so a rig change cannot silently mix with an older qualification.
- **Version 1 profile.** The current rig is expressed as a profile too (head+wrist, state 8), so the sealed EXP-620/622 data still export, verify and train exactly as today. A real-data differential readback must stay byte-identical, as in O1/O2.
- **Training.** `training-v2.yaml` sets cameras (side, wrist) and state_dim 6. The PREPROCESSING hash changes with the decode table, as expected; the old hash stays valid for the version 1 profile.

## Future AGV head (specification only, not built now)

- **Mount:** a mast on the pedestal (the simulated AGV) at the right-rear corner (−0.07, 0.07); camera 0.8 m above the pedestal top (world z 1.02).
- **Pan-tilt:** keep `neck_yaw`; add a tilt joint with range 5° to 75° (−10° to 75° if a level or upward view is wanted).
- **Manipulation view:** pitch 67° (look-at on the workspace centre), fovy 60. The arm spans about 70 % of the image height; triangle, place target and all joints in frame at every row.
- **Navigation view:** tilt about 10°.
- **Limit:** from behind the arm, the cup is about 0.46 visible whatever the pitch, because the arm sits between camera and cup. Precise localisation therefore stays with wrist + side; the head does navigation and coarse localisation.
- Renders: REG/diag-delivery-20261016/camera-rig-v2/head-mast/z102-tilt/.

## What does not change

- Data rules and thresholds, the Teacher (task_camera perception), the 10 Hz grid, the 0.004 m scene generation rules.
- The two-phase collection, retry rounds, seal and QC logic, apart from the camera names now coming from the profile.

## Implementation plan (Sonnet writers, one at a time; Opus review)

1. **Rig profile and plumbing.** Add config/act/rig-v1.yaml (today) and rig-v2.yaml, and replace every hard-coded head/wrist/neck point with profile reads (list above).
   - The profile becomes part of the frozen inputs and the identity.
   - Tests: both profiles, per component.
   - Proof: a real-data differential readback over the 101 merged-v2 entries must be byte-identical to today (rig v1).
2. **Model and launch variants.** Write scene_rig_v2.xml, the robot MJCF/URDF/SRDF variants (jaw wrist camera, no head or neck), mujoco_plugins_rig_v2.yaml (wrist, side, task_camera) and controllers without the neck.
   - Wire the launch to the variants.
   - Re-pin the execution snapshot and provenance hashes.
   - Render check: the side and wrist images in sim match the confirmed renders.
3. **Readiness, inventory, recorder and QC for rig v2.** Profile-driven node and controller inventory and readiness; recorder topics; QC camera grid over the configured cameras; zero head/neck artefacts (a test asserts no head or neck topic, node, bag channel or log in a rig-v2 stack composition).
4. **Training and export.** training-v2.yaml (cameras side+wrist, state_dim 6, the O7 hyperparameters and leading-idle trim, **num_workers 16**), adapter keys and decode table from the profile, and the new PREPROCESSING hash.
   - Human, 2026-10-18: "先停止现在的训练。开始做上面的修改。下次跑的时候DataLoader 的 num_workers 从 8 加到 16。直接进行TRAIN-003".
   - TRAIN-002 was stopped at step 2100 of 60000 (loss 0.125, about 30 samples/s, DataLoader wait 15–23 %, ETA about 8 h) and kept as `train-run-20261018T0900Z.stopped-by-human`. There is no further rig-v1 training; the next training is TRAIN-003 on rig v2.
5. **Templates and contracts.** New qualification and formal templates for rig v2 (camera names, image count per row, disk projection), and a new gate contract. A new formal scene list with new seeds is only needed if the human wants new scenes; the existing 70+33 positions can be reused, because data from rig v1 and rig v2 never mix.
6. **Gate (v2 tool) → images → a 16-scene debug run (EXP-623): verify the side and wrist frames and per-camera delivery → qualification (EXP-624) → formal collection of 100 (EXP-625, retry 2) → seal → TRAIN-003 (rig v2) → rollout on the three scene groups.**

## Risks and checks

- **Teacher perception and calibration.** The wrist camera on the jaw moves with the opening angle; nothing in the Teacher uses it, so the Teacher is unaffected. Check that no calibration contract names `wrist_camera_frame` with the old pose (pick-place-phase-camera-matrix.json is head-search-specific and stays with rig v1).
- **Cost of removing the neck.** Readiness, inventory and supervisor changes are needed (no longer configuration only). The rig-v1 profile keeps today's behaviour, protected by the differential readback.
- **The real wrist module's FOV is unknown.** 90 is the sim choice; 80 is the fallback.

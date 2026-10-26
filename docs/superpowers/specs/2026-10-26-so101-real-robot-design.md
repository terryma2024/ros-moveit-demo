# SO-101 real robot: data collection and ACT rollout — design

Date: 2026-10-26. Status: DRAFT for the human's review. Nothing in R1 to R5 runs before the human confirms this plan.

The human said on 2026-10-26: "我已经安装好SO101-ARM，一主一从，一个腕部摄像头，一个side摄像头。配置在/home/matianyi/Projects/so101_test，已经用标准lerobot工具测试过。在本次Indoor模型训练并rollout完成后，就开始真机数据采集和Rollout。你先写方案和做环境准备。" They also said: "侧面摄像头我会调整成和仿真一样的斜侧视".

Evidence root: `/data/work/so101-evidence/real-robot/` (prep: `prep-20261026/`).

## 1. What exists

### Real side
These are in `/home/matianyi/Projects/so101_test` and were checked read-only on 2026-10-26. The torque was never enabled.

- **Software:** LeRobot 0.6.1 `lerobot[feetech,viz]`, Python 3.12, PyTorch 2.11 + cu130, in the uv venv `so101_test/.venv`.
- **Arms:** leader `5CE5113682` and follower `5CE5122459`, each with Feetech STS3215 servos, 1 Mbps, IDs 1 to 6. Their by-id serial paths are in `arms.env`.
- **Calibration:** `/data/models/huggingface/lerobot/calibration/{robots/so_follower/my_follower.json, teleoperators/so_leader/my_leader.json}`.
- **Joint units:** LeRobot reports joints 1 to 5 in degrees, with 0 at the calibration middle pose (raw 2047), and the gripper as 0 to 100.
- **Cameras**, measured with `prep-20261026/frames/capture.json`:

  | Camera | Source | Format | Rate |
  |---|---|---|---|
  | Wrist | icSpring `32e6:9005` | 640x480 YUYV | 22.7 fps measured, used at 20 |
  | Side | icSpring `32e6:9221`, serial `202404160005` | 640x480 MJPG | set to 30, 20.0 fps measured |

  The side camera has a wide-angle lens with visible distortion.
- **Side camera mount:** at the time of capture it looked almost straight down and was rotated about 90 degrees. The human will re-mount it to match the simulated oblique side view.
- **Workspace:** a small wooden board with a cluttered background.

### Sim side
Facts with file citations are in the prep notes. In summary:

- **Joints:**
  - `"1".."6"`, in radians. Zero is an "L" pose: upper arm vertical, forearm and gripper horizontal and pointing forward. The robot faces world -y.
  - This is the pose the LeRobot calibration asks for as its middle pose ("大臂竖直向上，小臂与大臂约 90° 向前伸，手腕伸直"). The nominal offsets are therefore about 0. The real offsets equal the human's placement error at calibration, plus any sign flips.
  - Gripper (joint 6): about -0.17 to 1.75 rad, larger is more open. Grasp target -0.0476, release 0.75.
- **State and action:**
  - The state is the six joint positions at 10 Hz.
  - The action is the JTC's interpolated reference at t + 0.1 s.
- **Cameras:**
  - **side:** world pos (-0.50, -0.32, 0.42), fovy 62°, 640x480, pinhole, no distortion. Relative to the robot it is 0.50 m to the right, 0.32 m forward and 0.30 m above the table. It looks across the workspace toward the robot's left and is pitched about 13° down.
  - **wrist:** mounted on the moving jaw, fovy 90°. The real module's field of view has never been measured.
- **Layout:**
  - Table top at z 0.12. The robot sits on a 0.18 m square pedestal whose top is 0.10 m above the table.
  - Cup: a 12-sided prism, radius about 0.04 m, height 0.088 m, orange.
  - Red ring: inner radius 0.050 m, outer 0.055 m, centred 0.25 m forward and 0.08 m to the right of the base.
  - Cup start region: the triangle with corners task_start (0.02, -0.28), left (-0.08, -0.28) and forward (0.02, -0.36), in world x, y.
- **Policy runtime:**
  - The bundle is a plain LeRobot 0.6.1 `ACTPolicy` state dict, built by `adapters/act/lerobot.py`.
  - State and action normalisation use the bundle's mean and std. Images use ImageNet normalisation at 3x480x640 with no resize.
  - Execution: chunk 50, prefix N, targets at 0.1 s steps.
- **Real-hardware code: none.** `backends/real_stub` is fail-closed, and `so101_teleop` is simulation only.

## 2. Decisions (recommended defaults; the human may change any)

| # | Decision | Recommended | Why |
|---|---|---|---|
| D1 | Hardware I/O stack | **LeRobot native** (`so101_follower`/`so101_leader`, `lerobot-record`) for collection and rollout. No ros2_control Feetech driver for now. | Already tested by the human, standard for SO-101, smallest risk. A ROS driver can come later if MoveIt on the real arm is needed. |
| D2 | Recording rate | Record at **20 Hz**, the rate the cameras deliver. Convert to **10 Hz** for this project's pipeline by taking every second sample. | Keeps teleop smooth, which 10 Hz teleop would not be. 10 Hz matches the sim data and the trained chunk timing (chunk 50 = 5 s). |
| D3 | Action definition on the real arm | action[t] = **leader position at t + 0.1 s**, mapped to sim units. | It is the analogue of "JTC reference at t + 0.1 s" in sim. |
| D4a | Reference and rest pose (human 2026-10-26: "真机的关节零位不用仿真的L型灵位，真机不供电的情况无法保持这个位姿。需要用当前的闭合位姿。") | The **folded rest pose** of the photo is the real reference pose. It rests on the mechanical stops and holds without power, so it is repeatable. Readings on 2026-10-26, read-only (`prep-20261026/poses/folded-rest-20261026.txt`), follower: pan 4.8, lift -104.8, elbow 94.2, wrist_flex 75.2, roll -5.1 (degrees), gripper 13.0. The leader's wrist_flex reads 54.4; the unpowered wrist rests differently. The map's offsets are solved from this pose. Its sim-equivalent q comes from the link angles measured against gravity (phone inclinometer on the upper arm, forearm and wrist). A second pose and a single-joint sweep check the signs. The folded pose is also the start and end of every powered session. Episodes still start at the sim start pose (q = 0, the "L"), reached slowly under power. | The L pose cannot be held unpowered. A pose on the mechanical stops can be reproduced without a jig. |
| D4 | Unit mapping | A versioned joint map in `config/real/so101-follower-joint-map.yaml`: per joint a sign and offset (degrees to radians), and the gripper as a piecewise-linear map from 0..100 to rad, measured at closed, grasp and open. Hash-bound into every real dataset and run. | The sim policy and the co-training need one convention. |
| D5 | Camera handling | Calibrate the intrinsics of both cameras (checkerboard). **Undistort and re-project the side image** to a 62° pinhole before it reaches the policy. Measure the side camera's pose with an ArUco board at a known pose relative to the base, then make a sim rig variant `side-wrist-real` with the measured side pose and the measured wrist field of view. | Makes real images geometrically comparable to sim images, and lets new sim data match the real rig. |
| D6 | Policy for the first real rollout | (a) the indoor TRAIN-009 zero-shot, as a plumbing and baseline check; (b) a **real-only ACT** from teleop demos; (c) **sim + real co-training**. Compare all three on the same real protocol. | (a) is cheap but expected to be weak. (b) is the standard SO-101 recipe. (c) is the goal. |
| D7 | Inference process | Reuse `act_policy_service` (train venv, Unix socket). A new real runner in the LeRobot venv sends observations to it and receives chunks. | The same verified loader and normalisation as the sim rollouts, with no second copy of the model code. |
| D8 | Real scene | Match the sim layout: robot raised about 10 cm above the work surface, a clean table at least 0.5 x 0.6 m, an orange cup of about 8 cm diameter and 9 cm height, and a red ring of 10 to 11 cm diameter at the sim position. Use a printed placement mat with the start triangle and the standard points. | Reproducible starts and the closest match to the sim distribution. |

## 3. Safety rules (apply to every torque-on step)

1. **A human is present** at every torque-on step, within reach of the follower's power switch. Nothing with torque runs unattended or from an unattended background job.
2. **Command filter** in the runner. Every command passes through it:
   - joint soft limits, the intersection of the sim limits and the calibrated range minus 5°;
   - LeRobot `max_relative_target`, starting at 5° per step;
   - a forward-kinematics check that the TCP stays above the table plus 1 cm and inside a workspace box.

   A violation stops the episode and holds the current position. It is never skipped silently.
3. **Speed:** the first runs use servo velocity and acceleration limits, or interpolation at half speed. Full speed only after 10 clean runs.
4. **Start and end of run:**
   - A session starts in the folded rest pose. With the torque on, move slowly from there to the episode start pose (q = 0).
   - The folded pose may lie outside the sim joint limits. For example, the lift reads -104.8° against the sim's -100°. So the filter has a separate **transit mode**: only a scripted, slow path from the rest pose into the limits and back, with a monotone approach toward the allowed range.
   - At the end, go slowly back to the folded pose, then disable the torque. Never drop the torque mid-air. LeRobot's Ctrl+C releases the torque at once, so the runner traps SIGINT and does the slow rest first.
5. **Dry runs first:** every new policy or runner change first runs in the air with no cup, then with the cup.
6. **Records:** every run writes an evidence record: the joint map hash, camera calibration hashes, policy hash, commands, observations and stop reasons.

## 4. Phases

| Phase | Content | Motion | Gate |
|---|---|---|---|
| **R0 prep** (now) | The read-only device and camera checks (done). This design. The evidence root. A decision on venvs (LeRobot venv for I/O; train venv for the policy service, also LeRobot 0.6.1). No repository code yet: one code writer at a time, and to-do 43 is being fixed. | none | human confirms the plan |
| **R1 mapping and calibration** | (1) Joint map: the folded rest pose (D4a) is the reference. Its readings are taken; the link angles are measured against gravity; then a single-joint sweep by hand, with the torque off, gives each sign; then a held-out pose checks the result. The gripper is read closed, open and on the cup. (2) Intrinsics of both cameras (checkerboard, 20+ views). (3) Side camera pose (ArUco board at a known position relative to the base); compare it with the sim pose and adjust the mount until the images match. (4) Wrist camera field of view. (5) Code: `real/joint_map.py`, `real/camera_model.py` with fixture tests, then the gate. | torque off; the human moves the arm | map verified by a held-out pose (error < 2°); reprojection error < 0.5 px |
| **R2 runner** | A LeRobot-venv runner: observation (cams 20 Hz to 10 Hz, joints to rad), the policy-service client, execution of the prefix with 50 Hz linear interpolation between the 10 Hz targets, the safety filter, a SIGINT rest, and evidence. Fixture tests with a fake robot and fake cameras. Gate. Then a dry run of a scripted trajectory (no policy) in the air at half speed. | yes, human present | scripted dry run tracks within 3° and no filter trip |
| **R3 teleop collection** | `lerobot-record` with the leader at 20 Hz. Protocol: the start triangle on the mat, with the 4 standard points plus a grid (about 20 positions), 2 to 3 episodes each. Pilot of 10 episodes, then about 60. A converter turns LeRobotDataset into this project's export format (10 Hz, rad, side image undistorted and re-projected), with hashes and a manifest. QC: frame drops, joint/camera timestamp skew, leader-follower tracking error. | yes, teleop | pilot QC passes |
| **R4 training** | On antzb (human 2026-10-26: training on antzb). (b) Real only. (c) Co-training: indoor sim (EXP-7036 plus the supplementary run) together with real, at a sampling ratio such as 1:1 per batch. Same ACT configuration as TRAIN-007A (chunk 50). | none | — |
| **R5 real rollout** | Policies (a) zero-shot, (b) and (c), on the same protocol: the 4 standard points x 5 trials, then held-out mat positions. Prefix 50 first, then shorter prefixes. Metrics: success (cup inside the ring and upright), grasp success, time, filter trips. | yes, human present | — |

## 5. Open questions for the human

1. Is the real cup the same type and colour as the sim cup, and will there be a red ring? (D8)
2. Can the robot be raised about 10 cm, as in sim? If not, the sim rig has to change instead.
3. Is a background closer to the sim office (a clean wall or board) possible?
4. How many teleop episodes are acceptable for the first round (recommended: a pilot of 10, then 60)?

# Task 4 Mac report

## Status

`REPAIRED_CANDIDATE_FUNCTIONAL_PASS_GUI_EVIDENCE_UNAVAILABLE`

All four requested Mac FULL_RESTART positions completed the repaired installed candidate
`3ea1530530b274af3b3db5b9aa50165ae66b7e31` once with natural `rc=0`, `status=DONE`, and
`transition_count=19`. The required exact-window screenshots remain unavailable: the current upstream
0.1.0 non-bundled GLFW Viewer is visible to CoreGraphics but exposes zero Accessibility windows, so
the unchanged capture helper cannot perform its mandatory `AXRaise`. This report claims Mac 4/4
functional and physical success, but does not claim the unavailable visual clause.

## Repaired candidate four-position results

The repaired candidate changes the MuJoCo TCP micro-lift target from 2 mm to 4 mm while preserving
the physical 1–10 mm acceptance gate. Each row below is a new independent process, ROS domain,
session, evidence directory, MoveIt/controller instance, and MuJoCo world. The validator also proves
nonempty point cloud/PLY, source-stamped `world` `/cup_pose`, nonzero trajectories, fresh monotonic
terminal JointState/FK-TCP evidence, bilateral unsupported lift and transport, detach before open,
stable final table placement, zero final fingertip contacts, world sync, retreat, and ordered clean
shutdown.

| Run / keyframe | Perceived world XYZ (m) | Perception error | Physical micro-lift | Max terminal TCP error | Final XY error | Result |
|---|---:|---:|---:|---:|---:|---|
| EXP-057 `task_start` | `[0.019499,-0.280405,0.165000]` | 0.644 mm | 3.952 mm | 0.701 mm | 2.635 mm | rc0, DONE/19 |
| EXP-058 `cup_test_forward_5cm` | `[0.019624,-0.330460,0.165000]` | 0.594 mm | 4.017 mm | 1.162 mm | 2.489 mm | rc0, DONE/19 |
| EXP-059 `cup_test_left_5cm` | `[-0.030362,-0.280587,0.165000]` | 0.690 mm | 3.976 mm | 0.820 mm | 2.498 mm | rc0, DONE/19 |
| EXP-060 `cup_test_right_5cm` | `[0.069633,-0.280513,0.165000]` | 0.631 mm | 3.947 mm | 1.515 mm | 2.487 mm | rc0, DONE/19 |

Repaired runtime provenance:

- implementation: `3ea1530530b274af3b3db5b9aa50165ae66b7e31`
- mujoco_ros2_control child: `5e9d67ce9fde39d35bf94cc498721abf203a0ddd` (`0.1.0`)
- installed policy SHA256: `7d36a45b9382ba2d8a8d16646e66539ee8f1e499633f7a1b5c266d5ffbfded70`
- installed bundle SHA256: `9c13cd8260ef5df6fd3486cb98dc6c89e06602b5cb8a2b95a1fe300ac94d1171`
- fresh post-run suite: 448 passed in 11.95 s
- fail-closed evidence validator: all checks passed for EXP-057 through EXP-060

Evidence is retained under the registered root in `mac-runs/exp-057` through `mac-runs/exp-060`,
with the aggregate result in `mac-repair-validation-summary.json`. Nothing was deleted or archived.

Publication closure `3edd55a9d922f99bdc380dfaa1a60954c8741a86` was accepted by Gitee on
`codex/rgbd-pick-place-mujoco-0-1-main`; the first `git ls-remote` readback matched exactly. CP-149
records that readback additively and changes no runtime bytes or live evidence.

## Historical pre-repair qualification

### Summary

The frozen production chain was:

`MuJoCo RGB-D -> reliable depth-1 subscribers -> point cloud/cup crop -> world TF -> /cup_pose -> dynamic_cup_pick_place -> MoveIt -> ros2_control -> MuJoCo`

Two production fixes were necessary on Mac:

- `7f767f8`: match the camera publisher's reliable/volatile/depth-1 QoS so aligned RGB-D samples arrive reliably.
- `fff7ba3`: after the first valid PLY/summary/`/cup_pose` publish, release exactly the three high-bandwidth RGB-D subscriptions while keeping the node, TF listener, and `/cup_pose` publisher alive. This removed DDS starvation of MoveIt action results. The causal diagnostic SMOKE-016 completed the full chain and the final four production runs reproduce that result.

Runtime provenance was frozen for all four runs:

- implementation: `fff7ba3b1c7efb4472f51d0842d8bcba87d64621`
- mujoco_ros2_control child: `5e9d67ce9fde39d35bf94cc498721abf203a0ddd` (`0.1.0`)
- installed bundle: `5c84da5a6bed093be023336da815fc2d1c7cb169aefa72cb13d6999346f25a2a`
- simulation-evidence plugin: `f4487cc3e2467e2ffec5b2ca2fa407d8c372b63cfe07cc1e71e777185d1a7ab7`, UUID `74A169FE-F055-3D0D-A333-9F7F7BAEF574`
- installed runner: `8f0cbdce963608c21cc414972208ca439365e8fc90d9fba5574f0ac29353747b`

## Commits

- `74a6523` — require the candidate simulation-evidence plugin, preventing stale ABI loading.
- `7f767f8` — match perception subscriptions to the reliable camera QoS.
- `4f260d2` — RED contract for exact/idempotent post-first-valid input release.
- `fff7ba3` — production input release fix.
- `0c5bd21` — causal full-chain Mac pass for the input-release change.
- `cdc57ba` — frozen installed production build.
- Per-run ledger transitions/closures are recorded from `d33ec7c` through the final Task 4 record commit.

## Four-position results

Perception error is XY distance from the MJCF initial cup position. Final XY error is distance from the center `[-0.08,-0.25]` of the accepted final region; all final poses are inside the policy box `[-0.09,-0.26]..[-0.07,-0.24]`. Tilt limit is `0.0872665 rad`.

| Run / keyframe | Perceived world XYZ (m) | XY error (m) | points full/cup | radius (m) | micro/lift/transport Z (m) | final XYZ (m) | final center error / tilt | final contact | result |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| EXP-023 `task_start` | `[0.019499,-0.280405,0.165000]` | 0.000644 | 98078 / 141 | 0.0393806 | 0.166893 / 0.224923 / 0.228320 | `[-0.077803,-0.247591,0.164831]` | 0.003260 / 0.004653 rad | table true, L/R 0/0 | rc0, DONE/19 |
| EXP-024 `cup_test_forward_5cm` | `[0.019624,-0.330460,0.165000]` | 0.000594 | 98078 / 168 | 0.0394035 | 0.166880 / 0.224816 / 0.228327 | `[-0.077942,-0.247534,0.164825]` | 0.003212 / 0.004506 rad | table true, L/R 0/0 | rc0, DONE/19 |
| EXP-025 `cup_test_left_5cm` | `[-0.030362,-0.280587,0.165000]` | 0.000690 | 98135 / 378 | 0.0393710 | 0.166845 / 0.224868 / 0.228133 | `[-0.077932,-0.247446,0.164928]` | 0.003286 / 0.007082 rad | table true, L/R 0/0 | rc0, DONE/19 |
| EXP-026 `cup_test_right_5cm` | `[0.069633,-0.280513,0.165000]` | 0.000631 | 98078 / 126 | 0.0394509 | 0.166946 / 0.224922 / 0.228360 | `[-0.077911,-0.247547,0.164776]` | 0.003222 / 0.003253 rad | table true, L/R 0/0 | rc0, DONE/19 |

Common gates passed in every functional run:

- Fresh domain/session/evidence/process/Viewer preflight and exact installed prefix/bundle/child/plugin readback.
- Camera topics registered; a fresh 640x480 aligned RGB-D triplet produced a finite point cloud, cup PLY, fitted radius, `world` pose and `/cup_pose` with no TF error or truth-pose bridge.
- `INPUT_RELEASED_AFTER_FIRST_VALID` reported exactly three released input subscriptions once, after evidence and pose publication.
- Full state trace crossed unsupported bilateral grasp, micro-lift verification, attach, lift, transport, descend, `DETACH_MOVEIT`, then `OPEN_GRIPPER`.
- MoveIt trajectories include resolved joint targets, FK pose/error and trajectory point evidence. No `waitForExecution` timeout or execution failure occurred.
- Final table support, accepted XY/Z region, upright tilt, zero fingertip contact, stable velocities, detached Planning Scene and world primitive count 13 all passed.
- Eleven launched processes exited cleanly and each exact domain/session/process/Viewer set was empty after natural exit.

## Evidence and hashes

| Run | log SHA256 | dynamic manifest SHA256 | perception summary SHA256 | PLY SHA256 | CG inventory SHA256 |
|---|---|---|---|---|---|
| EXP-023 | `84bd096a1313a339e8e735456f1637d7420bbf6ca70c3a6674d932d0528bed44` | `fc288004843d8731b05e0b962f392ec162d946a50dd26a3b5bf542e638cbe84b` | `02564ad61ebb87d6906deef3788a23cb1e881ea6f034feb22c6284c055450224` | `be6dc51ee934f0f8fb73a6744ebfa59235600a97c1143056f5d501b18fa3acb5` | `69fb7d0f15a53c4735044d4cf52aa8a5d97e3d8f86b8aa62ff99a620463687d0` |
| EXP-024 | `8a24abf9196e45079c7b67dd20b93645e3166163cf6035afc66351aa815a9d43` | `583b515cb6d61ce3aced523d931f9ee38e3d69ee38040bb1d16b28cd26d0e17e` | `949b2bc37b4412bc7e03fa08a3e203af8bf42601dbc486c33dbaa824b3009c9b` | `2a14f8e3506500bed28b317acc745530f1da3c5dd54506fe0e06ddf1c3daf940` | `315fac726624ad0de5f5b81b2402714c73a719dac008ebd5fd1e7b3955f66798` |
| EXP-025 | `64799c05fd062ba54f6c474292952ca8aeffab3c257f6da22fec6770ed8e5a26` | `0b37d39e81540423c3bdb70cf8f012d71304c0a95515364eb7deec69053f115b` | `c8ada3c35d3de26079e274a597276f8c3efe80b4161b1aa8b9a8d631832d5390` | `063b264db02f7e93271e5c3771322afd96ae764a8a7f5da0767cd03fd6d887a5` | `5b559639f3acd27d082fc247ab1d24157f97b5ccda00dd6f4bd693a6f122c0f4` |
| EXP-026 | `b1efd84620c2568a6005f17aa7acc74056c8643e8357e06cfea55ffda8094237` | `74f9b2b1a7b6454d444284e7bbb2b8b2465696ee80f68a5602b6e6ef5c78f71a` | `2ce334e58bb3ebb02eb3f77015222145f0e2260666c032f0f3e28d13c5b2f775` | `edbe3541ee1d5df9df5456a79eb1831fa47e666b6f4a307b943f3260d64fa47d` | `acd11f98136c2a9ccff42d4138836f5db0852e15cc1a0d6ee50e6d98ec88696e` |

Evidence roots:

- `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-023`
- `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-024`
- `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-025`
- `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/mac-runs/exp-026`

All evidence and diagnosis runs remain under the sole registered root `/private/tmp/so101-debug-rgbd-pick-place-mrc010-main-20260826/`. Nothing was deleted. There are no proposed deletion candidates without explicit user authorization.

## Tests

- TDD RED: exact three-subscription release contract failed before `fff7ba3`.
- Focused GREEN: 1 passed.
- `test_rgbd_cup_pose.py`: 44 passed.
- Full project suite at installed freeze: 445 passed in 12.33 s.
- Fresh post-run full suite: 445 passed in 12.60 s; log SHA256 `17cd7555598a6d031c7370f2345ebb1df0570496a93fce577040bd7a32196434`.
- Fresh installed provenance: 5 passed in 1.99 s; log SHA256 `fbe8847e8062fdfc8e8fa050319ef7d71ee0aed91a6942dc65874da313b44b0e`.

## GUI concern

Historical captures prove negative monitor coordinates are valid: twelve retained manifests successfully captured the same `[308,-1250,1140,773]` bounds. Current CoreGraphics inventories still resolve exactly one owned Viewer in each run, but System Events reports zero AX windows. AppKit activation is accepted without making the process frontmost, task-owned tmux invocation reaches the same AX-mapping failure, and semantic GUI lookup cannot address the non-bundled `ros2_control_node` process. No desktop fallback, unrelated MuJoCo bundle launch, helper weakening, or fabricated screenshot was used.

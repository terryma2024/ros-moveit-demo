# SO-101 ACT: native closed-loop rollout in MuJoCo — design

Status: CONFIRMED by the human on 2026-10-18 ("都确认"). It is part O6 of `docs/superpowers/plans/2026-10-18-so101-act-optimisation-batch.md`.

## Human decisions (2026-10-18)

- **Scenes:** "rollout按你的建议". Three groups, reported separately:
  1. the four standard points;
  2. held-out rollout_validation and rollout_test;
  3. an optional extrapolation group.
- **Calibration gate:** "标定门怎么处理：你的建议". Bind the contact-policy activation receipt instead of the never-produced QUALIFIED calibration report, and record the substitution in the evaluation record.
- **Executor:** "执行器方案：容器外执行，不并发". The executor runs natively on the host, one episode at a time.

## Why

TRAIN-001's offline first-step MAE (0.0143 rad) is worse than repeating the current state (0.0019 rad). The 10 Hz action is almost the current state, so an offline metric cannot show whether the policy picks and places. Only a closed-loop rollout can.

Today nothing runs a policy in the loop:
- `cli/act_session.py` execute mode always refuses. Its ports are never composed, and `act_session` is not an admitted kind.
- `act_inference_worker` is a batch file protocol.
- There are no rollout scenes.

## What is reused

The read-only map, with file and line references, is in the Plan-agent report of 2026-10-18.

- **Stack launch and stop proof:** `runtime/act_instance/program.py` (`instance_stack_launch`, `compose_stack`) and `container_campaign/native_owner.native_instance_environment`. The latter sets the fixed ROS identity, `MUJOCO_GL=egl` and the Fast DDS profile. Also reused: `so101_teleop/unified/act_stack.py` stop and cleanup receipt, `native_stop.marker_survivors`, and the installed graph probe.
- **Reset and initial gate:** through `ActRosRuntimePorts` with a one-scene catalog:
  - `reset_point` → `execute_mujoco_reset(keyframe="task_start", cup_position_world_m=…)`;
  - `initial_gate`, `resume_physics`, `cancel_motion` and `confirm_no_controller_goal`.
  - Not reused: the Teacher-shaped `point_initial_gate` and `run_authorized`.
- **Observation:** `adapters/act/ros_observation.py` with `act/synchronizer.RgbObservationSynchronizer`, which gives head, wrist and an 8-dim state of six arm joints plus neck sin and cos. It uses the frozen limits `rgb_sync.max_age_s` and `max_skew_s` of 0.1.
- **Policy:** `adapters/act/lerobot.build_policy_from_bundle`, `act/policy.ActPolicyRunner` (chunk 10, prefix 1) and `adapters/act/inference_process.ActInferenceProcess` (one request in flight, timeout and stale-reply refusal from `config/act/runtime.yaml`).
- **Command:** `act/execution.ActExecutionAdapter` with two `adapters/act/ros_execution.RosControllerPort` (arm and gripper FollowJointTrajectory). It checks joint limits, refuses `PREFIX_LATE` and has a stop with terminal results.
- **Success:** the pure validator `act/teacher_endpoint.evaluate_teacher_endpoint` with the frozen tolerances. The end target is computed from the frozen motion policy the same way the Teacher computes it.
- **Recording:** `act/offline/pilot.PilotRecording` (raw_recorder bag) for replay and diagnostics.

## Decisions taken in this design (recommended defaults)

| # | Item | Decision |
| --- | --- | --- |
| D1 | Interpreter | One process: train-venv (lerobot 0.6.1, torch 2.11) with ROS Jazzy and the gate install on the path, after an import preflight. Fallback if rclpy and torch conflict: a streaming inference subprocess behind `ActInferenceProcess`. |
| D2 | Loop | Free-running and anchored to sim time; one inference per new head and wrist pair at 10 Hz. A late reply or `PREFIX_LATE` sends nothing (the previous goal holds) and is counted. With no fresh observation for 1.0 s (frozen `state_unavailable_stop_s`) the executor stops with `STOPPED_SAFETY`. |
| D3 | Horizon | `execution_deadline_s` 180 s sim time (frozen). No new early-stop rule. |
| D4 | Neck | Not commanded. It stays at its reset value, and any deviation is logged. Training saw a constant neck. |
| D5 | Admission | Unified admission is bypassed for this native tool. Preconditions are checked and recorded: no container, unified store IDLE with no lease, an empty ROS graph on domain 181, no instance-marker process, no GPU compute process. |
| D6 | Verdicts | `done` = the endpoint PASS with a confirmed stop. Infrastructure faults (stack, gate, recorder, stop unproven) are INVALID and re-run, and reported separately. A policy that never moves before the horizon is its own reason, `NO_MOTION`. |
| D7 | Scenes | See the Scenes section. |
| D8 | Calibration substitution | `act_evaluate` gains `--contact-activation-receipt` as an alternative to `--calibration`. It binds `artifacts.calibration = {substituted_by: "contact_activation_receipt", path, sha256, policy_fingerprint, ruling}` and runs `verify_activation` the way collection admission does. The receipt is the one EXP-618, 620, 621 and 622 used (fingerprint cbd85126…). |

Success is judged with two substitutions, recorded in each episode's evidence:
- the start target is the scene's commanded reset pose (upright), instead of a perceived pose;
- COMPLETED means the horizon was reached, or the policy stopped and settled, with the stop confirmed.

## Scenes

1. **rollout_standard:** the four points of `config/mujoco/rgbd_task_points.yaml`.
   - task_start, forward_5cm and left_5cm lie on the anchor triangle's boundary, 1.2 to 6 mm from training scenes, so they are in distribution.
   - right_5cm (x 0.07) is about 51 mm outside the data, so it is extrapolation.
   - Each point is reported on its own.
2. **rollout_validation and rollout_test:** about 20 each, from new sampler seeds (576010 validation, 576011 test).
   - Same triangle, the 0.060 m place exclusion and the five-pose Teacher reachability filter.
   - 0.004 m apart from each other. The distance to the 151 taken points is relaxed to at least 0.002 m (rollout-only scenes are never trained on), and each scene's actual distance to the nearest training scene is reported.
   - rollout_test is opened once per policy; rollout_validation is used for tuning.
3. **rollout_extrapolation (optional):** reachable points outside the triangle, for example x 0.03 to 0.07, filtered for reachability.

The scene sampler is a pure module with an injected reachability verdict. An evidence-side script runs `task_reachability` against the native stack, as the formal scene generation did, and writes plain decimals.

## Evidence per episode

- **episode.json:** scene id, group, xy, seed, nearest-training distance; bundle and policy sha, snapshot commit, gate install, inputs-manifest sha, runtime.yaml sha; the calibration substitution block; reset receipt, gate result and wall and sim timings.
- **steps.jsonl**, per grid step:
  - observation sim time, per-stream stamps and receive times, the 8-dim state, head and wrist pixel sha256;
  - the full chunk, the applied prefix, inference submit, reply and latency;
  - goal ids, accepted times, late and held flags.
- **world.jsonl:** the cup pose at 10 Hz (diagnostic).
- **endpoint.json:** the stop receipt, the end observation after settle, and the `evaluate_teacher_endpoint` document.
- **stop-proof.json** and **raw/**: the bag and record-stats. QC is NOT_APPLICABLE: there are no Teacher events, so phase 2 does not seal it.
- **Run row:** `<root>/<split>/act-runs.jsonl` with `{search_locked: true (no search phase, noted), done, interventions: 0, elapsed_wall_s, scene_id, evidence}`.

## Implementation tasks (after confirmation; Sonnet writer, Opus review)

1. `act/rollout_scenes.py`: pure sampling and separation, with an injected reachability verdict. Plus the evidence-side generator script.
2. `act/rollout_targets.py`: start and end targets from the frozen execution snapshot. A test pins them to a sealed Teacher manifest's `teacher_targets`.
3. `act/policy.py`: `to_action_prefix()`. Its output satisfies `validate_action_prefix`.
4. `act/rollout_episode.py`: the episode state machine with injected ports: reset → gate → resume → recorder → nodes → loop → stop → settle → endpoint → retire. The executor's nodes are created after the gate, because the gate's exact node inventory refuses extra nodes. Tests with fakes cover:
   - late reply;
   - stale observation abort;
   - stop unconfirmed;
   - no motion;
   - gate failure.
5. `adapters/act/rollout_ros.py`: the observation tick on new image pairs; the command ports, permit (joint limits only) and reference port; the world observer; a thread transport for `ActInferenceProcess`.
6. `cli/act_rollout_native.py`:
   - preconditions, then the owned-root layout and environment;
   - stack launch and composition, `ActRosRuntimePorts` and `PilotRecording`;
   - episodes in sequence, then the stack stop and stop proof.
   - Tests cover the precondition refusals.
7. `cli/act_evaluate.py`: `--contact-activation-receipt`; the splits rollout_standard and rollout_extrapolation; per-group endpoint-error reporting.
8. Evidence scripts on a source snapshot (git archive plus shim), with the stack from the gate install. Before running, the snapshot's reused modules must be sha-equal to the gate install's.

No data rule or threshold changes; every value comes from the frozen inputs manifest or `config/act/runtime.yaml`.

## Risks

- **rclpy and torch in one interpreter (D1).** The import preflight decides; the fallback is the subprocess.
- **A policy that stays still from the reset pose,** because training episodes may begin with an idle stretch. Measure the first-motion row in the exported episodes before the first rollout, and report NO_MOTION separately.
- **The stop and settle definition for a policy (D6),** which replaces the Teacher's normal stop. It is recorded as a substitution.

## Execution modes (added 2026-10-19, CP-3744)

TRAIN-003 stalls at the start pose with the bundle's `execution_prefix` 1 (CP-3743). The rollout can therefore override how a chunk is executed, without retraining. The override is a LOGIC setting: it is recorded in `run.json`, in every `episode.json` (`execution`) and, when it is not the bundle's, in the run identity (`identity.execution_mode`), and invalid values are refused while the inputs load.

- Default (no flag): the bundle's frozen values; nothing changes.
- `--execution-prefix N` (1..chunk_size): infer, send the first N actions as one trajectory (targets at observation + 0.1 s * 1..N), and infer again only from the first observation taken at or after the last target (10 ms tolerance). Observations in between are logged as `PREFIX_IN_PROGRESS` and counted (`prefix_wait_observations`). A late reply, or a prefix that is late at submission, sends nothing (the previous goal holds), applies no wait, and the next observation infers at once. A late prefix is held whole: it is not trimmed, because the action-prefix contract anchors the target grid to the observation.
- `--temporal-ensembling [M]` (ACT paper scheme, default M 0.01): infer at every observation. The action for the target time T = observation + 0.1 s averages the prediction for T of every earlier chunk that still covers it (chunk index `round((T - o) / 0.1) - 1`, within a quarter step), weighted by exp(-M * i) with i = 0 for the oldest contributing chunk. One step is applied per inference. A late chunk is added to the ensemble before the late check, so it still serves later steps; the step rows carry the contributors (`ensemble`).
- The two flags are exclusive.

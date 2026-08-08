# SO-101 物理结果验证实验账本

```yaml
task_id: so101-physical-outcome-validation
goal: 仅以 Gazebo 物理结果判定 SO-101 抓取放置成功，并保持 MoveIt attachment 仅作为 planning shadow
success_contract: 同一提交和已校准策略下五次连续 VALID execute，最终稳定物理结果与全部硬安全不变量均通过
worktree: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation
branch: codex/so101-physical-outcome-validation
base_commit: 05dff7a18e466c01486441dd90c21fcd44d4d8cd
current_commit: eacdff2
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI
confirmed_conclusions:
  - Task 13 branch-tree build、三包测试、dry-run trace 与 uncalibrated plan-only fail-closed gate 已验证（VER-PHYSICAL-001）
  - 用户已批准 Bullet compound-owner support + live-calibrated bounded-negative-depth noise 下限（APR-PHYSICAL-001）
  - compound-owner support 与 bounded-negative-depth policy regression 已按 RED→GREEN 验证（TDD-PHYSICAL-001）
disproven_routes:
  - 0.75 mm seat
  - independent CLOSE seat motion
  - longer close duration as a fix
  - safety-gate relaxation
  - unregistered fixed-port retry fixture
open_hypotheses:
  - 每个 CALIBRATION_REQUIRED 字段的 live calibration 值
  - minimum_support_contact_depth_m 与其他 physical-outcome threshold 的有效 live calibration
latest_checkpoint: CP-PHYSICAL-006
next_experiment: CAL-PHYSICAL-003
```

## VER-PHYSICAL-001：Task 13 自动验证

```yaml
experiment_id: VER-PHYSICAL-001
status: VALID
prior_experiment: NONE
hypothesis: 当前 branch tree 保持 Panda 兼容，并在未校准时于任何 plan-only/execute mutation 前 fail closed
prediction: 三包测试无失败；dry-run 含新状态且无 forward Gazebo attachment；plan-only 报 PHYSICAL_OUTCOME_CALIBRATION_REQUIRED
single_variable: NONE
lifecycle: FULL_RESTART
provenance:
  source_commit: 02c929364f889d73333ec76f7384040cce58d7f0
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/build/so101_gazebo_demo/pick_place_state_machine
  package_prefixes:
    pick_place_common: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/pick_place_common
    panda_gazebo_demo: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/panda_gazebo_demo
    so101_gazebo_demo: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/so101_gazebo_demo
  bun: /home/lenovo/.bun/bin/bun 1.3.14
commands:
  - command: colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
    exit_code: 1
    note: Panda relay 在三包并行负载下内部 timeout 124；SO101 83/83 通过
  - command: ctest --test-dir build/panda_gazebo_demo -R '^test_attachment_state_relay$' --output-on-failure
    exit_code: 0
  - command: PYTHONNOUSERSITE=1 colcon test --packages-select panda_gazebo_demo --event-handlers console_direct+
    exit_code: 0
    result: Panda 35/35；最终聚合 1327 tests、0 errors、0 failures、90 skipped
  - command: ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=dry_run start_simulation:=false
    exit_code: 0
  - command: ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=plan_only plan_only_state:=MOVE_ABOVE_OBJECT start_simulation:=false
    exit_code: 0
    child_exit_code: 2
observed:
  - dry-run trace 含 WAIT_RELEASE_SETTLE 与 VALIDATE_FINAL_PLACEMENT，且不含 ATTACH_GAZEBO/DETACH_GAZEBO
  - plan-only 子进程在 BOOTSTRAP -> ERROR 报 PHYSICAL_OUTCOME_CALIBRATION_REQUIRED，未发生 mutation
  - Panda relay 单独重跑及 Panda 全包均通过；首次并行 timeout 不用于产品行为结论
  - 原 so101-reset-world-five-success-experiment-ledger.md 未修改
invalid_attempts:
  - ROS setup 前启用 set -u，导致 setup 脚本未定义变量错误，应用未启动
  - 未提供 plan_only_state，先触发 PLAN_ONLY_STATE_REQUIRED，未检验 calibration gate
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/dry-run-valid.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/plan-only-state.log
conclusion: 自动化实现边界成立；live execute 仍被未校准策略按设计阻止
decision: KEEP
next_experiment: CAL-PHYSICAL-001
```

## CP-PHYSICAL-001

```yaml
checkpoint_id: CP-PHYSICAL-001
last_valid_experiment: VER-PHYSICAL-001
current_hypothesis: 可从隔离 headless 观测分布中校准全部新阈值，且无需放宽既有安全 ceiling
working_tree_status: docs/experiments/so101-physical-outcome-validation-experiment-ledger.md newly created
owned_processes: NONE
preserved_processes: 其他 so101-gazebo-demo-py worktree 的 gz sim，以及 so101-workspace-sampler 的 clang-tidy
confirmed_conclusions:
  - 当前 overlay 与 source provenance 一致
  - Panda 行为保持，SO101 正常 forward path 无 Gazebo attach/detach
open_risks:
  - 新 policy thresholds 尚未校准，execute 必须继续 fail closed
  - 尚无本提交的 GUI execute 或 final-outcome screenshot
next_command: 建立 CAL-PHYSICAL-001 PLANNED 条目并只读采集隔离 headless baseline evidence
```

## 五次连续最终结果批次（尚未开始）

每次必须记录：run ID、source/policy hash、`ROS_DOMAIN_ID`、`GZ_PARTITION`、overlay、cleanup owner、final code、release epoch id/start/first/last sequence、sample count/duration、final pose、support/gripper contacts、Gazebo/MoveIt detached、world sync、shadow 最大 divergence、collision/penetration maxima、controller health、fresh screenshot 路径与结果。没有五次连续 `VALID` 不得声明验收成功。

## CAL-PHYSICAL-001：隔离 headless observation-only calibration

```yaml
experiment_id: CAL-PHYSICAL-001
status: INVALID
prior_experiment: VER-PHYSICAL-001
hypothesis: 隔离 headless physics evidence 可为全部新阈值提供有限分布与保守 margin，而无需提高任何既有 collision/penetration ceiling
prediction: source/install/session/controller/contact/pose 均新鲜且独立；可测得 target/support/tilt/speed/cadence/settle/shadow distributions
single_variable: observation-only calibration
lifecycle: FULL_RESTART
preconditions:
  - source commit 4119099 且 overlay 为当前 worktree install
  - ROS_DOMAIN_ID 119 无既有 node
  - GZ_PARTITION 唯一且仅启动本实验拥有的进程
  - reset 后 cup/robot/MoveIt scene 初态可独立证明
success_criteria:
  - 每个新阈值都有原始样本、bounded summary、margin 与语义依据
  - controller、Gazebo pose/contact、MoveIt scene evidence 均新鲜有限
  - 既有 forbidden collision 与 penetration ceilings 未改变
failure_criteria:
  - 有效观测显示 workflow 或物理 outcome 失败；保留结果且不计五连成功
invalid_criteria:
  - provenance、初态、controller、contact、session、重复 stack 或证据时间边界错误
provenance:
  source_commit: bd5bf09
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  runtime_executable: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/build/so101_gazebo_demo/pick_place_state_machine
  ros_domain_id: 119
  gz_partition: so101-physical-outcome-707d1460-3904-49bd-b60c-de0e36739bcb
  cleanup_owner: root agent; only PIDs launched under this experiment
commands:
  - command: ros2 launch so101_gazebo_demo so101_gazebo.launch.py headless:=true
    exit_code: RUNNING_THEN_OWNED_CLEANUP
  - command: ros2 control list_controllers
    exit_code: 0
  - command: timeout 8s gz topic -e -t <task_object_contact_bottom> -n 1
    exit_code: 124
  - command: controlled cup set_pose down-probe while bottom subscriber was active
    exit_code: 124
    note: set_pose succeeded, but bottom contact sample remained absent
  - command: controlled lift/drop with simultaneous bottom and wall_near subscribers
    exit_code: 0
    note: bottom timed out; wall_near produced table contact
observed:
  - candidate ROS domain node list empty before launch
  - arm_controller、gripper_controller、joint_state_broadcaster 均为 active
  - bottom contact topic 有 publisher/subscriber，但静置、下压和抬起后自由落体均没有消息
  - 对照落杯消息为 plastic_cup::body::wall_near ↔ table::table_top::collision；contact point 的 world z 约为桌面顶面 0.12 m
  - Gazebo 最终 cup pose 回到约 z=0.165 m，说明物理支撑存在，但当前 scoped collision/sensor identity 不能提供批准 contract 要求的 bottom-to-table 证据
  - 未从本次数据派生或修改任何 production threshold；既有 collision/penetration ceiling 未改
conclusion: contact identity 前置条件失败；CAL-PHYSICAL-001 不具备有效支撑证据，必须停止且不得计入校准或成功批次
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration/bottom-contact-probe.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration/drop-bottom.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration/drop-wall.txt
decision: INVALIDATE_AND_DEBUG_CONTACT_IDENTITY
next_experiment: CAL-PHYSICAL-002 after a focused RED/GREEN regression proves exact bottom-to-table evidence
```

## CP-PHYSICAL-002

```yaml
checkpoint_id: CP-PHYSICAL-002
last_valid_experiment: VER-PHYSICAL-001
current_hypothesis: CAL-PHYSICAL-001
working_tree_status: new ledger PLANNED entry only
owned_processes: NONE
preserved_processes: 其他 worktree 的 gz sim 与 clang-tidy
open_risks:
  - production policy 仍全为 CALIBRATION_REQUIRED
next_command: 以 ROS_DOMAIN_ID=119 和唯一 GZ_PARTITION 启动 owned headless calibration stack
```

## DBG-PHYSICAL-001：Gazebo stable support contact identity/depth

```yaml
experiment_id: DBG-PHYSICAL-001
status: VALID
prior_experiment: CAL-PHYSICAL-001
hypothesis: 当前 Bullet Featherstone compound-link contact routing 无法同时提供独立 bottom identity 与稳定 non-negative depth
single_variable_matrix:
  - production world + Bullet Featherstone
  - production world + DART
  - production world + classic Bullet
  - temporary separate bottom link + Bullet Featherstone
  - temporary compound-owner sensor alias + Bullet Featherstone
lifecycle: FULL_RESTART_PER_VARIANT
provenance:
  source_commit: 5d7d72a
  source_world: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/src/so101_gazebo_demo/worlds/so101_pick_place.sdf
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI
observed:
  - Bullet Featherstone production world 把真实 table support 路由为 plastic_cup::body::wall_near；bottom topic 无消息
  - 静止 Featherstone owner contact 的 1000 messages / 4080 depths 全为负值，范围约 -3.65127e-7 至 -3.57628e-7 m
  - 临时独立 bottom link 恢复 plastic_cup::support_probe::bottom identity，但静止 depth 仍全部为微小负值；drop transient 同时含正负 depth
  - DART production cup 提供 bottom↔table 且正 depth，但完整机器人 spawn 报多项 mesh/VHACD collision couldn't be created，不能保留碰撞安全层
  - classic Bullet 的 cup contact sensors 在 bounded probe 中均无消息
  - compound-owner alias 不改变任何物理属性，但其静止 depth 同样全负，不能满足批准的 negative-depth rejection
  - 所有模型/launch 变体只存在于 /tmp；source tree 未修改
conclusion: 当前平台上，原批准条件“稳定 bottom sensor identity + reject every negative depth + 不改 engine/geometry/physics”不可同时满足
decision: REQUIRE_NARROW_DESIGN_DIRECTION
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration/drop-wall.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/contact-ab-dart/bottom.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/contact-separate-link-bottom-40.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/contact-support-root-drop-500.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/contact-owner-alias-bottom-30.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/contact-featherstone-stable-1000.txt
required_direction: 是否允许把 Bullet compound owner 的真实 table contact 作为 support evidence，并以配置化、live-calibrated 的数值噪声下限处理微小负 depth，同时仍拒绝缺失、non-finite、超出噪声界的负 depth
```

## CP-PHYSICAL-003

```yaml
checkpoint_id: CP-PHYSICAL-003
last_valid_experiment: DBG-PHYSICAL-001
confirmed_conclusions:
  - DART/classic Bullet/独立 link 均不能在现有批准边界内替代 production Featherstone
  - production threshold 仍全部为 CALIBRATION_REQUIRED；未从无效数据派生值
  - 既有 collision/penetration ceiling、engine、质量、摩擦、几何、controller 和 motion target 均未修改
owned_processes: NONE
preserved_processes: 其他 worktree 的 Gazebo 与 clang-tidy 未触碰
open_risk: support evidence contract 在当前 backend 下不可满足
next_command: 获得窄化语义授权后，先写 stable Featherstone support regression RED，再做最小 GREEN
```

## APR-PHYSICAL-001：用户批准 support-evidence 窄化修订

```yaml
approval_id: APR-PHYSICAL-001
status: APPROVED
date: 2026-08-08
prior_experiment: DBG-PHYSICAL-001
approved_semantics:
  - Bullet Featherstone compound owner 上真实 task object ↔ intended table contact 可作为 support evidence
  - 增加配置化且经 live calibration 确定的负 depth 数值噪声下限
  - 缺失、non-finite、比噪声下限更负的 depth 必须拒绝
  - target region/height/upright/speed/no-gripper-contact/Gazebo-detached/MoveIt-detached 全部继续强制
  - 不放宽 collision/penetration safety ceilings
  - 不改变 engine、geometry、mass、friction、controller 或 motion target
  - MoveIt attachment 只作为 planning shadow；SO101 normal forward path 不使用 Gazebo attach/detach
excluded_ledger: docs/experiments/so101-reset-world-five-success-experiment-ledger.md
decision: PROCEED_TDD_THEN_RECALIBRATE
next_experiment: TDD-PHYSICAL-001
```

## CP-PHYSICAL-004

```yaml
checkpoint_id: CP-PHYSICAL-004
last_valid_experiment: DBG-PHYSICAL-001
current_hypothesis: observer 可在不改变物理与安全 ceiling 的条件下严格适配 compound-owner contact 和 bounded-negative-depth noise
working_tree_status:
  - docs/superpowers/plans/2026-08-07-so101-physical-outcome-validation.md 开头有来源未确认的空行，必须保留
  - 本批准记录将以独立 docs commit 提交
owned_processes: NONE
preserved_processes: 其他 worktree 的 Gazebo 与 clang-tidy 未触碰
open_risks:
  - minimum_support_contact_depth_m 尚未经新的有效 live calibration 冻结
  - production policy 仍须 fail closed
next_command: 先写 stable Featherstone compound-owner + bounded-negative-noise observer/policy RED tests
```

## TDD-PHYSICAL-001：compound-owner support + bounded negative noise regression

```yaml
experiment_id: TDD-PHYSICAL-001
status: VALID
prior_experiment: APR-PHYSICAL-001
hypothesis: observer 可从现有 Featherstone compound-owner stream 接受 noise bound 内的真实 table contact，同时严格拒绝缺失、non-finite 与越界负 depth
single_variable: support evidence classification 与 minimum_support_contact_depth_m policy wiring
lifecycle: NO_RUNTIME_STACK_FOR_RED_GREEN
provenance:
  source_commit: f3e49db6078e89ae47f39a76d388554b6f858def
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/tdd-physical-001
red:
  command: compile test_gazebo_world_observer.cpp against pre-change headers
  result: expected compile failure for missing constructor arguments and WorldSnapshot support depth metrics
green:
  - build: pick_place_common + so101_gazebo_demo passed, including clang-tidy/clang-format quality gate
  - observer: 7/7 passed
  - policy: 29/29 passed
  - configuration contract: 18/18 passed
  - launch contract: 35/35 passed
  - compound-owner static world contract: 1/1 passed
  - package suite: 81/83 passed in concurrent run; both unrelated timing failures passed unchanged when isolated
  - fingertip geometry isolated rerun: 17/17 passed in 100.62s after the concurrent suite hit its 60s timeout
  - runtime attach smoke isolated reruns: 1/1 passed twice; no product change made for the concurrent timing failures
observed:
  - raw task-object collision identity plastic_cup::body::wall_near is retained
  - finite depth at or above the configured lower bound is accepted; missing、non-finite、or more-negative depth is rejected
  - accepted/rejected counts and finite raw min/max depth are retained in WorldSnapshot
  - gripper-contact freshness remains independent and a gripper-only callback does not overwrite support evidence
  - production policy remains CALIBRATION_REQUIRED; no test vector was copied into production
  - physics engine、geometry、mass、friction、controller、motion target 与 safety ceilings 均未改变
  - old so101-reset-world-five-success experiment ledger remains unmodified
decision: KEEP
next_experiment: CAL-PHYSICAL-002
```

## CP-PHYSICAL-005

```yaml
checkpoint_id: CP-PHYSICAL-005
last_valid_experiment: TDD-PHYSICAL-001
current_hypothesis: production Featherstone stable owner-contact depth distribution 可为 minimum_support_contact_depth_m 提供独立、保守且不影响 safety ceiling 的 live calibration
owned_processes: NONE
preserved_processes: 其他 worktree 的 Gazebo 与 clang-tidy 未触碰
open_risks:
  - production minimum_support_contact_depth_m 仍为 CALIBRATION_REQUIRED
  - 其他 physical-outcome threshold 仍未完成 live calibration
next_command: 先创建 CAL-PHYSICAL-002 PLANNED 记录并冻结隔离环境、采样分布、margin 与 invalid criteria，再启动 headless calibration stack
```

## CAL-PHYSICAL-002：production Featherstone physical-outcome calibration

```yaml
experiment_id: CAL-PHYSICAL-002
status: INVALID
prior_experiment: TDD-PHYSICAL-001
hypothesis: production Featherstone 的稳定 owner-contact、pose cadence、release settling 与 MoveIt shadow pairing distributions 足以为全部 sentinel 提供非宽松、可复核的冻结值
prediction:
  - stable plastic_cup::body::wall_near ↔ table::link::collision depth distribution 有界且 finite
  - conservative minimum_support_contact_depth_m margin 仅包络数值噪声，不接近或改变任何 collision/penetration ceiling
  - 其余 threshold 可由相同 production source/overlay 的观测分布或语义完全相同的既有已证明 gate 得出
single_variable: observation-only calibration；不改变 engine、geometry、mass、friction、controller、motion target 或 safety ceiling
lifecycle: FULL_RESTART
preconditions:
  - source commit 48709c3cb944f9ab77bc40f2d0ff2f8b0400e314
  - install overlay /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  - executable /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/build/so101_gazebo_demo/pick_place_state_machine
  - ROS_DOMAIN_ID 39 initially empty
  - GZ_PARTITION so101-physical-outcome-4fc1e1f5-a06b-4e21-9430-467d4470f802 unique
  - production policy remains CALIBRATION_REQUIRED；calibration run cannot count as success
success_criteria:
  - provenance、controller、pose、contact、scene evidence fresh and finite
  - each new threshold has sample source、distribution summary、conservative margin and semantic justification
  - negative-depth bound remains orders of magnitude below immutable grasp max_penetration_m 0.0008 and final validation penetration ceiling 0.0013
  - no existing hard safety number is increased
failure_criteria:
  - production evidence shows a threshold cannot be calibrated without semantic relaxation
  - compound-owner/table identity is absent or depth distribution is unbounded/non-finite
invalid_criteria:
  - duplicate node/partition、wrong overlay/binary、stale session、controller unhealthy、contact source mismatch、incomplete cleanup or contaminated screenshot timing
commands:
  - headless production stack with the frozen ROS_DOMAIN_ID/GZ_PARTITION and owned PID log
  - bounded raw Gazebo pose/contact samples under the same lifecycle
  - plan-only/shadow pairing probes after support-only calibration permits controlled runtime gating
evidence_paths:
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-002
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-domain-probe.txt
cleanup_ownership: only PIDs created by CAL-PHYSICAL-002; preserved so101-gazebo-demo-py stacks and workspace-sampler clang-tidy are out of scope
started_at: 2026-08-08T13:26:24+08:00
ended_at: 2026-08-08T13:28:25+08:00
observed:
  - exact production pair is plastic_cup::body::wall_near ↔ table::table_top::collision
  - configured/parser-required intended identity remains table::link::collision, so production support would be classified non-intended
  - raw bounded capture contained 1001 contact messages and 4004 depths; values are retained only as invalid diagnostic evidence and cannot calibrate a threshold
  - all controllers were active and Bullet Featherstone provenance was confirmed
invalid_reason: frozen contact identity precondition mismatched the exact production collision identity
cleanup:
  - owned launch PID 3839349 and children stopped with launch-session SIGINT
  - preserved so101-gazebo-demo-py stacks and workspace-sampler clang-tidy were not touched
decision: DO_NOT_DERIVE_THRESHOLDS
next_experiment: TDD-PHYSICAL-002
```

## CP-PHYSICAL-006

```yaml
checkpoint_id: CP-PHYSICAL-006
last_valid_experiment: TDD-PHYSICAL-001
invalid_experiment: CAL-PHYSICAL-002
first_bad_boundary: intended_support_collision identity contract
current_hypothesis: parser/config/test contract must use the exact production table::table_top::collision identity before calibration can be valid
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-002/wall-near-1000.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-002/depth-summary.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-002/stack.log
owned_processes: NONE
next_command: RED exact production identity in policy/observer/world contract, then minimal GREEN without changing physics or safety ceilings
```

## TDD-PHYSICAL-002：exact intended table collision identity

```yaml
experiment_id: TDD-PHYSICAL-002
status: VALID
prior_experiment: CAL-PHYSICAL-002
hypothesis: 用 production 实际 table::table_top::collision 替换过时的 table::link::collision 即可让 intended support identity 与 runtime 一致
red:
  command: pytest test_configuration_contract.py::test_physical_outcome_policy_requires_explicit_calibration
  result: expected table::table_top::collision but production YAML contained table::link::collision
green:
  - pick_place_common + so101_gazebo_demo build and full C++ quality gate passed
  - PolicyConfig 29/29 passed
  - GazeboWorldObserver 7/7 passed
  - exact configuration/world/launch contracts 37/37 passed
observed:
  - policy parser、production YAML、observer fixture and legacy matrix diagnostic now agree on table::table_top::collision
  - no physics、motion、controller、geometry、mass、friction、threshold or safety ceiling changed
decision: KEEP
next_experiment: CAL-PHYSICAL-003
```

## CAL-PHYSICAL-003：corrected production identity calibration

```yaml
experiment_id: CAL-PHYSICAL-003
status: VALID
prior_experiment: TDD-PHYSICAL-002
hypothesis: corrected exact identity enables valid production observation-only calibration of every physical-outcome sentinel
single_variable: observation-only calibration on corrected identity contract
lifecycle: FULL_RESTART
preconditions:
  - source commit eacdff21e046d110ad3c60d8b41cd9353fef9744
  - overlay /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  - ROS_DOMAIN_ID 162 initially empty
  - GZ_PARTITION so101-physical-outcome-e8207b3d-8fd4-4cc6-ae2b-9671cf27b40a unique
  - all owned PIDs recorded and production Bullet Featherstone confirmed
success_criteria:
  - exact owner/table identity and finite depth samples are stable across bounded capture
  - every sentinel gets source distribution or semantically identical already-justified gate plus conservative non-permissive margin
  - all values remain separate from immutable collision/penetration safety ceilings
failure_criteria:
  - evidence cannot support a finite non-permissive value without semantic relaxation
invalid_criteria:
  - wrong identity/provenance、stale evidence、duplicate domain/partition、controller failure or cleanup contamination
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003
next_transition: commit PLANNED, recheck domain/provenance, then RUNNING
started_at: 2026-08-08T13:39:00+08:00
ended_at: 2026-08-08T13:43:50+08:00
observed:
  support_identity:
    pair: plastic_cup::body::wall_near <-> table::table_top::collision
    contact_pairs: 3017
    depth_samples: 12068
    depth_min_m: -1.49011984973e-08
    depth_max_m: -1.87528118034e-11
    depth_mean_m: -7.81770738521e-09
    depth_stddev_m: 1.6854477327e-09
  target_pose:
    commanded_xyz_m: [-0.08, -0.25, 0.165]
    samples: 1000
    x_range_m: [-0.0800199732184, -0.0799964815378]
    y_range_m: [-0.250000029802, -0.249995708466]
    z_range_m: [0.164993032813, 0.165000006557]
    observation_span_s: 16.993
  intended_support_at_target:
    contact_messages: 1040
    depth_samples: 4160
    depth_min_m: -3.72691602024e-08
    depth_max_m: 7.45178638795e-08
    depth_mean_m: 1.4075708649e-08
    depth_stddev_m: 3.68146151999e-08
  derived_speed:
    usable_adjacent_pairs: 977
    raw_nominal_period_s: 0.017
    linear_max_m_s: 0.000342196114006
    linear_mean_m_s: 1.87302040927e-06
    angular_max_rad_s: 0.0134827757314
    angular_mean_rad_s: 2.00330759412e-05
calibrated_policy:
  minimum_support_contact_depth_m:
    value: -1.0e-07
    basis: 包络 owner-contact 与 target-contact 的最负有效样本，分别留 6.7x 与 2.7x 数值裕量
    safety_separation: 该绝对值仅为 0.0008 m grasp ceiling 的 1/8000、0.0013 m final penetration ceiling 的 1/13000；不改变二者
  final_target_region:
    value: {kind: axis_aligned_box, min_xy_m: [-0.085, -0.255], max_xy_m: [-0.075, -0.245]}
    basis: 精确 place target 各轴 +/- 既有且同语义的 place_support_xy_tolerance 0.005 m；远宽于本次稳定 span
  support_height_range_m:
    value: [0.155, 0.175]
    basis: 精确 place target z=0.165 m +/- 既有且同语义的 place_support_height_tolerance 0.010 m
  max_upright_tilt_rad:
    value: 0.08726646259971647
    basis: 复用既有 supportedAtPlace 的同语义 place_support_tilt_tolerance_rad，不放宽
  max_linear_speed_m_s:
    value: 0.001
    basis: 本次稳定窗口最大值 0.000342196114006 m/s 的 2.9x conservative margin，仍要求近静止
  max_angular_speed_rad_s:
    value: 0.05
    basis: 本次稳定窗口最大值 0.0134827757314 rad/s 的 3.7x conservative margin，仍要求近静止
  consecutive_samples:
    value: 5
    basis: 与 0.05 s executor cadence 配合，至少覆盖 0.20 s；不能由单样本成功
  minimum_stable_duration_s:
    value: 0.20
    basis: 五个 counted samples 的首尾跨度；本次稳定证据连续 16.993 s
  sample_interval_s:
    value: 0.05
    basis: 慢于约 0.017 s 原始 Gazebo pose 周期，保证每次采样可获得新的 sequence
  settle_timeout_s:
    value: 2.0
    basis: 复用既有 post_attach_hold_settle_seconds 的已验证物理 settling 时间预算；大于 0.20 s minimum duration
  max_observation_age_s:
    value: 0.10
    basis: 两倍 executor sample interval，且约为正常 0.017 s pose 周期的 5.9x；超时/停更仍 fail closed
  max_telemetry_samples:
    value: 40
    basis: 完整容纳 2.0 s / 0.05 s 的 bounded settle window，不截断 timeout 内分布证据
  catastrophic_loss:
    workspace_bounds_m:
      value: [-0.21, -0.46, 0.12, 0.21, 0.06, 0.30]
      basis: production table top footprint x=[-0.25,0.25]、y=[-0.50,0.10] 各内缩 cup outer radius 0.04 m；z 下界为 table top 0.12 m，上界覆盖 release/place 而拒绝异常飞失
    max_relative_position_drift_m:
      value: 0.005
      basis: 复用既有 hard carry task_object_position_drift_tolerance，不放宽
    max_relative_orientation_drift_rad:
      value: 0.070
      basis: 复用既有 hard carry task_object_orientation_drift_tolerance_rad，不放宽
  planning_shadow:
    max_position_divergence_m:
      value: 0.005
      basis: collision shadow 规划有效性不得比既有 hard carry position drift gate 更宽
    max_orientation_divergence_rad:
      value: 0.070
      basis: collision shadow 规划有效性不得比既有 hard carry orientation drift gate 更宽
    max_pair_age_s:
      value: 0.10
      basis: 与独立 final evidence freshness gate 相同，约为正常 pose cadence 的 5.9x，停更仍拒绝
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/wall-near-1.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/wall-near-2.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/wall-near-3.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/place-pose-1000.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/place-contact-1000.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/place-pose-summary.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/calibration-003/place-derived-speeds-summary.txt
invariants:
  - production Bullet Featherstone、geometry、mass、friction、controller、motion target 未修改
  - grasp max_penetration_m=0.0013 与所有既有 collision/penetration ceiling 未修改
  - calibration run 不计入 five-consecutive acceptance
cleanup:
  - 仅向 owned launch session 32350 / PID 3861046 发送 SIGINT
  - owned PIDs 3861046、3861089、3861090、3861120 均已退出
  - 其他 worktree 的 Gazebo 与 clang-tidy 未触碰
decision: FREEZE_VALUES_FOR_CONFIG_TDD
next_experiment: TDD-PHYSICAL-003
```

## TDD-PHYSICAL-003：freeze calibrated production policy

```yaml
experiment_id: TDD-PHYSICAL-003
status: VALID
prior_experiment: CAL-PHYSICAL-003
hypothesis: production policy 可精确冻结 CAL-PHYSICAL-003 的全部值并通过 strict parser/config contract
single_variable: 将全部 physical_outcome sentinel 替换为已记录的 calibrated value
red:
  command: PYTHONNOUSERSITE=1 python3 -m pytest -q src/so101_gazebo_demo/test/test_configuration_contract.py::test_physical_outcome_policy_matches_cal_physical_003
  result: 1 failed；production YAML 仍返回 CALIBRATION_REQUIRED，符合预期
green:
  build: pick_place_common + so101_gazebo_demo passed
  focused_ctest:
    test_policy_config: 29/29 passed
    test_configuration_contract: 18/18 passed
  direct_exact_config_test: 1/1 passed
  parser_numeric_fixture_smoke: 1/1 passed
systematic_debugging:
  symptom: focused ctest 全绿后 colcon test-result --verbose 仍非零
  root_cause: 汇总包含 13:17/13:18 的旧 package-suite XML；本次两个 fresh XML 时间为 13:47 且均通过
  action: 未修改 production、测试 timeout 或 safety gate；后续 fresh full-suite verification 重新生成全量结果
invariants:
  - grasp max_penetration_m 0.0013 与所有 collision/penetration ceiling 未修改
  - physics、geometry、mass、friction、controller、motion target 未修改
  - old so101-reset-world-five-success ledger remains unmodified
decision: KEEP
next_experiment: VERIFY-PHYSICAL-002
```

## VERIFY-PHYSICAL-002：calibrated branch-tree verification

```yaml
experiment_id: VERIFY-PHYSICAL-002
status: VALID
source_commit: 669cd236cf27b9ec592779c05581ac4b8cf3353a
overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install/so101_gazebo_demo
build:
  command: colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
  result: 3 packages passed；C++ tidy/format quality gates passed
test:
  command: PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
  initial_result: runtime resource contention caused one Panda relay timing failure and one SO101 world smoke timing failure
  systematic_debugging:
    - Panda test_attachment_state_relay unchanged isolated rerun passed 1/1 in 6.20 s
    - SO101 test_runtime_joint_and_detachable_joint_observation_smoke first isolated rerun advanced past the original motion gate but hit its legacy attach-state wait
    - the unchanged exact pytest then passed 1/1 in 72.52 s
    - unchanged CTest test_so101_pick_place_world passed 14/14 in 79.40 s
    - no timeout、motion、attachment、safety or production change was made
  fresh_final_summary: 1215 tests, 0 errors, 0 failures, 90 skipped
invariants:
  - forward workflow does not use Gazebo attach/detach
  - Panda behavior and existing collision/penetration ceilings remain unchanged
  - old so101-reset-world-five-success ledger has zero diff
decision: QUALIFIED_FOR_DRY_RUN_PLAN_ONLY
next_experiment: DRY-PHYSICAL-001
```

## DRY-PHYSICAL-001：calibrated workflow trace

```yaml
experiment_id: DRY-PHYSICAL-001
status: VALID
source_commit: 9e6e5ae7b48e9f7ae93412774b28d08c1325276f
run_mode: dry_run
start_simulation: false
ROS_DOMAIN_ID: 163
GZ_PARTITION: so101-physical-outcome-dry-20260808
result:
  exit: 0
  status: DONE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE
assertions:
  - no ATTACH_GAZEBO or DETACH_GAZEBO in normal forward trace
  - DETACH_MOVEIT precedes OPEN_GRIPPER
  - release settle and final validation precede synchronization and retreat
evidence: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/dry-run.log
decision: KEEP
next_experiment: PLAN-PHYSICAL-001
```

## PLAN-PHYSICAL-001：isolated calibrated plan-only qualification

```yaml
experiment_id: PLAN-PHYSICAL-001
status: INVALID
source_commit: 9e6e5ae7b48e9f7ae93412774b28d08c1325276f
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: plan_only
start_simulation: true
headless: true
ROS_DOMAIN_ID: 164
GZ_PARTITION: so101-physical-outcome-plan-20260808
success_criteria:
  - isolated stack provenance and controllers healthy
  - plan-only completes without physical execution or final-success claim
  - planning shadow gate is available and no forward Gazebo attachment is invoked
invalid_criteria:
  - duplicate domain/partition、wrong overlay、stale stack or uncontrolled cleanup
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/plan-only-001
cleanup_ownership: only process group created by this experiment
started_at: 2026-08-08T14:07:33+08:00
ended_at: 2026-08-08T14:08:14+08:00
observed:
  status: ERROR
  trace: BOOTSTRAP -> ERROR
  failure: PLAN_ONLY_STATE_REQUIRED
invalid_reason: operator command omitted required plan_only_state；state machine rejected before planning or physical execution
cleanup:
  - Ctrl-C sent only to owned launch pipeline session 21671
  - owned PIDs 3909665、3909688、3909689、3909693、3909743 no longer exist
decision: DO_NOT_COUNT
next_experiment: PLAN-PHYSICAL-002
```

## PLAN-PHYSICAL-002：bounded MOVE_ABOVE_OBJECT plan-only qualification

```yaml
experiment_id: PLAN-PHYSICAL-002
status: VALID
source_commit: 47f4a7a
run_mode: plan_only
plan_only_state: MOVE_ABOVE_OBJECT
start_simulation: true
headless: true
ROS_DOMAIN_ID: 165
GZ_PARTITION: so101-physical-outcome-plan-002-20260808
success_criteria:
  - exact isolated stack reaches healthy controllers and MoveIt scene
  - MOVE_ABOVE_OBJECT planning succeeds without trajectory execution
  - no physical success claim and no forward Gazebo attachment
invalid_criteria:
  - provenance、domain、partition、overlay or cleanup contamination
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/plan-only-002
cleanup_ownership: only process group created by PLAN-PHYSICAL-002
started_at: 2026-08-08T14:09:23+08:00
ended_at: 2026-08-08T14:10:10+08:00
observed:
  physics: gz::physics::bullet_featherstone::Plugin
  controllers: joint_state_broadcaster、arm_controller、gripper_controller active
  moveit: repeated OMPL plans computed successfully
  status: PLAN_ONLY_COMPLETE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT
  physical_execution: NONE
  forward_gazebo_attachment: NONE
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/plan-only-002/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/plan-only-002/preflight-nodes.txt
cleanup: Ctrl-C sent only to owned launch session 20128 after PLAN_ONLY_COMPLETE；owned PIDs exited
decision: QUALIFIED_FOR_HEADLESS_EXECUTE
next_experiment: HEADLESS-PHYSICAL-001
```

## HEADLESS-PHYSICAL-001：final-outcome execute qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-001
status: INVALID
source_commit: bd54288
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
start_simulation: true
headless: true
ROS_DOMAIN_ID: 166
GZ_PARTITION: so101-physical-outcome-headless-001-20260808
lifecycle: FULL_RESTART
success_criteria:
  - final release-epoch evaluator reports stable physical outcome and all hard gates pass
  - controller、Gazebo pose/contact、MoveIt scene/shadow and checkpoint evidence are independent and fresh
  - Gazebo remains detached throughout forward path；MoveIt detaches before OPEN_GRIPPER
  - no forbidden collision or existing penetration ceiling violation
failure_semantics: freeze all evidence before any separate reset；never auto-open a held unsupported cup
invalid_criteria: duplicate runtime、wrong overlay/provenance、stale session or cleanup contamination
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001
cleanup_ownership: only process group created by HEADLESS-PHYSICAL-001
started_at: 2026-08-08T14:11:22+08:00
ended_at: 2026-08-08T14:13:48+08:00
invalid_reason: planned source_commit bd54288 did not equal runtime branch HEAD d544ed4；strict provenance mismatch
diagnostic_only:
  original_failure: PHYSICAL_GRASP_BILATERAL_STABILITY_TIMEOUT
  terminal_failure: TASK_OBJECT_SUPPORT_POSE_MISMATCH
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> RECOVER_OPEN_GRIPPER -> RECOVER_DETACH_GAZEBO -> ERROR
  frozen_gazebo_pose_xyz_m: [0.0100756352767, -0.279838770628, 0.168406680226]
  intended_support_contact: true
  gazebo_attached: false
  moveit_attached: false
  controllers: all active
  recovery_checkpoint_issue: CHECKPOINT_INVALID_DATA recovery context does not match phase
  counting: NONE；不得派生成功/失败率或改阈值
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/failure-gazebo-attachment.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-001/failure-controllers.txt
cleanup: evidence frozen before Ctrl-C；only owned launch session 29797 stopped；no reset performed
decision: DO_NOT_COUNT_RESTART_WITH_FROZEN_HEAD
next_experiment: HEADLESS-PHYSICAL-002
```

## HEADLESS-PHYSICAL-002：provenance-correct execute qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-002
status: VALID_FAILURE
implementation_commit: 669cd236cf27b9ec592779c05581ac4b8cf3353a
runtime_source_head: 5e52539cb639970e233fe42918ff7205e9c50768
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 167
GZ_PARTITION: so101-physical-outcome-headless-002-20260808
lifecycle: FULL_RESTART
success_criteria: stable final physical outcome plus every hard invariant and independent evidence layer
failure_criteria: any valid workflow/hard-gate/final-outcome failure after evidence freeze
invalid_criteria: any source/overlay/domain/partition/session/evidence/cleanup mismatch
failure_semantics: preserve evidence before separate cleanup；no reset and no off-support automatic open
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002
cleanup_ownership: only process group created by HEADLESS-PHYSICAL-002
started_at: 2026-08-08T14:15:34+08:00
ended_at: 2026-08-08T14:18:15+08:00
observed:
  failure: Q6_NATIVE_PAD_INTERFERENCE_EXCEEDED
  failed_state: ATTACH_MOVEIT
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> RECOVER_OPEN_GRIPPER -> RECOVER_DETACH_GAZEBO -> RECOVER_DETACH_MOVEIT -> RECOVER_SYNC_WORLD_OBJECT -> RECOVER_RETREAT -> ERROR
  hard_gate: native-pad wall-interference ceiling remained strict；no value changed
  final_outcome_reached: false
  acceptance_counting: valid qualification failure；not part of five-run batch
recovery_audit:
  - source requires fresh intended support and detached MoveIt shadow before controlled opening
  - frozen post-recovery evidence cannot establish that opening occurred off-support；no speculative patch made
  - CHECKPOINT_INVALID_DATA recovery-context persistence annotation remains an open defect/risk for later TDD
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/failure-gazebo-attachment.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-002/failure-moveit-scene.txt
cleanup: all evidence frozen before Ctrl-C；only owned launch session 13296 stopped；no reset performed
decision: HARD_GATE_WORKED_RETRY_FRESH_LIFECYCLE
next_experiment: HEADLESS-PHYSICAL-003
```

## HEADLESS-PHYSICAL-003：fresh execute qualification retry

```yaml
experiment_id: HEADLESS-PHYSICAL-003
status: VALID_FAILURE
implementation_commit: 669cd236cf27b9ec592779c05581ac4b8cf3353a
runtime_source_head: 5c8bc7e7c1aa30eb61695aa05dba6f8c7ae587c4
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 168
GZ_PARTITION: so101-physical-outcome-headless-003-20260808
lifecycle: FULL_RESTART
success_criteria: stable final physical outcome plus all independent hard-gate evidence
failure_criteria: any valid workflow/hard-gate/final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003
cleanup_ownership: only HEADLESS-PHYSICAL-003 process group
started_at: 2026-08-08T14:21:22+08:00
ended_at: 2026-08-08T14:25:24+08:00
observed:
  failure: Q6_NATIVE_PAD_INTERFERENCE_EXCEEDED
  reported_failure_after_recovery: GRIPPER_ENVIRONMENT_EVIDENCE_INCOMPLETE
  failed_state: ATTACH_MOVEIT
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> RECOVER_OPEN_GRIPPER -> ERROR
  actual_q6: 0.75000244379
  expected_q6: 0.75
  actual_q6_velocity: 0.0000113565474749
  final_outcome_reached: false
  acceptance_counting: valid qualification failure；not part of five-run batch
hard_gate_audit:
  - native-pad wall-interference ceiling rejected the transition；no ceiling or motion value changed
  - Gazebo pose/contact evidence and MoveIt Planning Scene were frozen before cleanup
  - MoveIt scene reported attached_collision_objects=[]；Gazebo attachment relay had no publisher at freeze time
recovery_audit:
  - workflow reported original_recovery_disposition_hold_for_operator=1
  - post-recovery GRIPPER_ENVIRONMENT_EVIDENCE_INCOMPLETE cannot prove an off-support open；no speculative recovery patch made
  - recovery checkpoint persistence still reports CHECKPOINT_INVALID_DATA and remains a separate open risk
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/failure-gazebo-attachment.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-003/failure-evidence.sha256
cleanup: all evidence frozen before Ctrl-C；only owned launch and ROS_DOMAIN_ID 168 daemon stopped；no reset performed
decision: REPEATED_HARD_GATE_FAILURE_INVOKE_SYSTEMATIC_DEBUGGING
next_experiment: none until a RED test proves the root cause and a focused GREEN preserves every existing safety ceiling
```

## HEADLESS-PHYSICAL-004：carry-q6 telemetry regression qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-004
status: VALID_FAILURE
implementation_commit: 65b40df
runtime_source_head: 24204c39be278750a0d3758169925ee10e55d9d9
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 169
GZ_PARTITION: so101-physical-outcome-headless-004-20260808
lifecycle: FULL_RESTART
regression_scope: ATTACH_MOVEIT treats bounded regrasp q6 as telemetry while preserving fresh/finite、safe-floor、stationarity、forbidden-collision and solver penetration hard gates
success_criteria: stable final physical outcome plus every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004
cleanup_ownership: only HEADLESS-PHYSICAL-004 launch process group and ROS_DOMAIN_ID 169 daemon
started_at: 2026-08-08T14:54:04+08:00
ended_at: 2026-08-08T14:56:04+08:00
observed:
  failure: Q6_NATIVE_PAD_INTERFERENCE_EXCEEDED
  failed_state: LIFT
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> RECOVER_LIFT_TO_SAFE_HEIGHT -> ERROR
  q6_at_attach_checkpoint: -0.053083520382642746
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  acceptance_counting: valid qualification failure；not part of five-run batch
regression_result:
  - ATTACH_MOVEIT completed, proving the bounded-regrasp-q6 attachment regression GREEN live
  - the same nominal-q6 validator remained in the LIFT motion contract and rejected before carrying execution
  - no threshold、controller、motion target or penetration ceiling changed
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-004/failure-evidence.sha256
cleanup: all evidence frozen before Ctrl-C；only owned launch process group stopped；no reset performed
decision: APPLY_APPROVED_CARRY_TELEMETRY_SEMANTICS_TO_MOTION_CONTRACT_WITH_TDD
next_experiment: none until the LIFT motion-contract RED/GREEN is committed and focused verification passes
```

## HEADLESS-PHYSICAL-005：full carry telemetry qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-005
status: INVALID
implementation_commit: 49f7cc3
runtime_source_head: freeze after this PLANNED record commit
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 170
GZ_PARTITION: so101-physical-outcome-headless-005-20260808
lifecycle: FULL_RESTART
success_criteria: stable final physical outcome plus every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-005
cleanup_ownership: only HEADLESS-PHYSICAL-005 launch process group and ROS_DOMAIN_ID 170 daemon
observed: preflight found generated untracked symlink_install_manifest.txt；startup then failed to resolve libso101_attachment_collision_system.so because direct cmake install had overwritten the colcon-generated LD_LIBRARY_PATH hook
workflow_started: false
cleanup: immediate Ctrl-C；only owned launch process group stopped；no reset performed
decision: INVALID_PROVENANCE_AND_OVERLAY_HOOK
remediation: removed only the generated manifest with an explicit patch；restored the supported overlay using colcon build --symlink-install；verified LD_LIBRARY_PATH contains the package lib directory
```

## HEADLESS-PHYSICAL-006：clean-overlay full carry qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-006
status: INVALID
implementation_commit: 49f7cc3
runtime_source_head: freeze after this PLANNED record commit
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 171
GZ_PARTITION: so101-physical-outcome-headless-006-20260808
lifecycle: FULL_RESTART
success_criteria: stable final physical outcome plus every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-006
cleanup_ownership: only HEADLESS-PHYSICAL-006 launch process group and ROS_DOMAIN_ID 171 daemon
observed: preflight-nodes already contained /controller_manager、/arm_controller、/gripper_controller、/gz_ros_control and /joint_state_broadcaster；controller spawners then collided and PREPARE_OPEN_GRIPPER timed out
workflow_started: false
failure_after_invalid_preflight: GRIPPER_RESULT_TIMEOUT
cleanup: immediate Ctrl-C；owned launch PIDs verified absent；pre-existing ROS_DOMAIN_ID 171 processes and daemon were not touched；no reset performed
decision: INVALID_DOMAIN_COLLISION
next_experiment: choose a domain only after a clean preflight proves no nodes；do not count this run
```

## HEADLESS-PHYSICAL-007：clean-domain full physical qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-007
status: VALID_FAILURE
implementation_commit: 49f7cc3
runtime_source_head: freeze after this PLANNED record commit
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 211
GZ_PARTITION: so101-physical-outcome-headless-007-20260808
lifecycle: FULL_RESTART
domain_preflight: ros2 node list --no-daemon --spin-time 2 returned no nodes；domains 171-174 were rejected as occupied
overlay_preflight: LD_LIBRARY_PATH contains install/so101_gazebo_demo/lib；no generated manifest remains
success_criteria: complete DONE trace、stable final physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-007
cleanup_ownership: only HEADLESS-PHYSICAL-007 launch process group and any daemon created for ROS_DOMAIN_ID 211
started_at: 2026-08-08T15:18:42+08:00
ended_at: 2026-08-08T15:20:00+08:00
observed:
  failure: CARRYING_ENVIRONMENT_OBSERVATION_INVALID
  failed_state: LIFT
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> RECOVER_LIFT_TO_SAFE_HEIGHT -> ERROR
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  acceptance_counting: valid qualification failure；not part of five-run batch
root_cause_checkpoint: ProfiledJointMotionAdapter::validScene still requires Gazebo attached and calibrated legacy relative pose for carrying, contradicting the approved physics-only carry and latest-pose planning shadow
evidence_root_frozen: true
cleanup: pose、contact、controllers、MoveIt scene and checkpoint frozen before Ctrl-C；owned launch and ROS_DOMAIN_ID 211 daemon stopped；no reset
decision: TDD_NORMAL_CARRY_SCENE_REQUIRES_GAZEBO_DETACHED_AND_LIVE_SHADOW
```

## HEADLESS-PHYSICAL-008：detached physical carry qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-008
status: VALID_FAILURE
implementation_commit: 50fde52
runtime_source_head: dc22bb34cbacfbeb1ee2586cdab38c1f35b97e18
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 212
GZ_PARTITION: so101-physical-outcome-headless-008-20260808
lifecycle: FULL_RESTART
domain_preflight: ros2 node list --no-daemon --spin-time 2 returned no nodes
partition_preflight: gz topic -l returned no topics
overlay_preflight: LD_LIBRARY_PATH contains install/so101_gazebo_demo/lib；no generated manifest exists
success_criteria: complete DONE trace、stable final physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008
cleanup_ownership: only HEADLESS-PHYSICAL-008 launch process group and any daemon created for ROS_DOMAIN_ID 212
acceptance_counting: qualification only；not part of the five-consecutive-run batch
started_at: 2026-08-08T15:36:17+08:00
ended_at: 2026-08-08T15:37:57+08:00
observed:
  failure: TASK_OBJECT_SUPPORT_POSE_MISMATCH
  failed_state: DETACH_MOVEIT
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> DETACH_MOVEIT -> ERROR
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  gripper_open_at_checkpoint: false
  task_object_pose_xyz: [-0.07489179074764252, -0.25029996037483215, 0.17534954845905304]
  release_xy_error_m: 0.005117008695745988
  release_height_error_m: 0.010349548459053032
  carry_tilt_rad: 0.26072934935969655
root_cause: DETACH_MOVEIT and OPEN_GRIPPER contracts retained the legacy post-physical-detach support/upright/attachment semantics；they rejected bounded pre-release carry evidence before the release epoch
safety_disposition: stopped before OPEN_GRIPPER with the cup physically held；no recovery motion and no reset
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-008/failure-evidence.sha256
evidence_limitation: state-machine exit removed pose/contact bridge topics before bounded captures completed；empty captures are retained and the last fresh Gazebo pose remains frozen in the checkpoint
cleanup: all available evidence frozen before Ctrl-C；only owned launch and ROS_DOMAIN_ID 212 daemon stopped；no reset
decision: TDD_ALIGN_PLANNING_SHADOW_DETACH_AND_PHYSICAL_OPEN_WITH_RELEASE_EPOCH
fix_commit: d4766f6
```

## HEADLESS-PHYSICAL-009：release-epoch qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-009
status: VALID_FAILURE
implementation_commit: d4766f6
runtime_source_head: 24a4c8f05baac9881384991a79a4499c66e27528
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 213
GZ_PARTITION: so101-physical-outcome-headless-009-20260808
lifecycle: FULL_RESTART
domain_preflight: ros2 node list --no-daemon --spin-time 2 returned no nodes
partition_preflight: gz topic -l returned no topics
overlay_preflight: LD_LIBRARY_PATH contains install/so101_gazebo_demo/lib；no generated manifest exists
success_criteria: complete DONE trace、stable final physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009
cleanup_ownership: only HEADLESS-PHYSICAL-009 launch process group and any daemon created for ROS_DOMAIN_ID 213
acceptance_counting: qualification only；not part of the five-consecutive-run batch
observed:
  failure: CARRYING_ENVIRONMENT_OBSERVATION_INVALID
  recovery_failure: UNSAFE_RECOVERY_OBSERVATION
  failed_state: MOVE_ABOVE_PLACE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> ERROR
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  gripper_open_at_checkpoint: false
  retracted_unusable_tcp_frame_reconstruction: true
hard_limits_unchanged:
  planning_shadow_position_m: 0.005
  planning_shadow_orientation_rad: 0.070
root_cause: undetermined within the adapter's combined CARRYING_ENVIRONMENT_OBSERVATION_INVALID code；checkpoint tcp_pose_world cannot be compared directly with the gripper-link-relative Planning Scene attachment
safety_disposition: recovery rejected automatic motion/opening away from known support；no reset
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-009/failure-evidence.sha256
evidence_limitation: pose/contact bridge topics disappeared after state-machine exit；last fresh pose is frozen in checkpoint and shadow pose in Planning Scene response
cleanup: all available evidence frozen before Ctrl-C；only owned launch and ROS_DOMAIN_ID 213 daemon stopped；no reset
decision: VALID_COMBINED_CARRY_SCENE_FAILURE_REQUIRES_DIAGNOSTIC_DISAMBIGUATION
```

## HEADLESS-PHYSICAL-010：unchanged-policy release qualification retry

```yaml
experiment_id: HEADLESS-PHYSICAL-010
status: VALID_FAILURE
implementation_commit: d4766f6
runtime_source_head: 8be1ef4d5fc28912c9222c653742ed654783ff48
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 215
GZ_PARTITION: so101-physical-outcome-headless-010-20260808
lifecycle: FULL_RESTART
domain_preflight: ros2 node list --no-daemon --spin-time 2 returned no nodes
partition_preflight: gz topic -l returned no topics
overlay_preflight: same supported colcon overlay built from d4766f6；no generated manifest exists
success_criteria: complete DONE trace、stable final physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-010
cleanup_ownership: only HEADLESS-PHYSICAL-010 launch process group and any daemon created for ROS_DOMAIN_ID 215
acceptance_counting: qualification only；not part of the five-consecutive-run batch
observed:
  failure: CARRYING_ENVIRONMENT_OBSERVATION_INVALID
  recovery_failure: UNSAFE_RECOVERY_OBSERVATION
  failed_state: DESCEND_TO_PLACE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> ERROR
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  gripper_open_at_checkpoint: false
  retracted_unusable_tcp_frame_reconstruction: true
root_cause: undetermined within the adapter's combined CARRYING_ENVIRONMENT_OBSERVATION_INVALID code；the attempted tcp-vs-gripper-frame reconstruction is invalid
safety_disposition: no physical opening、recovery motion or reset
evidence_root_frozen: true
cleanup: owned launch and ROS_DOMAIN_ID 215 daemon stopped after evidence freeze；no reset
decision: VALID_COMBINED_CARRY_SCENE_FAILURE_REQUIRES_DIAGNOSTIC_DISAMBIGUATION
```

## HEADLESS-PHYSICAL-011：second unchanged-policy release qualification retry

```yaml
experiment_id: HEADLESS-PHYSICAL-011
status: VALID_FAILURE
implementation_commit: d4766f6
runtime_source_head: ba229c79e00010f1038d014e867fb796980411ef
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 216
GZ_PARTITION: so101-physical-outcome-headless-011-20260808
lifecycle: FULL_RESTART
success_criteria: complete DONE trace、stable final physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-011
cleanup_ownership: only HEADLESS-PHYSICAL-011 launch process group and any daemon created for ROS_DOMAIN_ID 216
acceptance_counting: qualification only；not part of the five-consecutive-run batch
observed:
  failure: CARRYING_ENVIRONMENT_OBSERVATION_INVALID
  recovery_failure: UNSAFE_RECOVERY_OBSERVATION
  failed_state: DESCEND_TO_PLACE
  process_exit_after_failure_report: -11
  last_completed_state: MOVE_ABOVE_PLACE
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  gripper_open_at_checkpoint: false
root_cause: undetermined within the adapter's combined carry-scene predicate；requires code-level diagnostic disambiguation before another live retry
safety_disposition: no physical opening、recovery motion or reset
evidence_root_frozen: true
cleanup: owned launch and ROS_DOMAIN_ID 216 daemon stopped after evidence freeze；no reset
decision: TDD_DISAMBIGUATE_CARRY_SCENE_FAILURE_WITHOUT_CHANGING_GATES
```

## HEADLESS-PHYSICAL-012：disambiguated carry-scene qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-012
status: VALID_FAILURE
implementation_commit: b7d43a64078a94b2a6b968c1eb1f7f395b7265f6
runtime_source_head: 8e8ff9e90a1f3ab8f02b476646adfb25d26ef95b
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 217
GZ_PARTITION: so101-physical-outcome-headless-012-20260808
lifecycle: FULL_RESTART
domain_preflight: ros2 node list --no-daemon --spin-time 2 returned no nodes
partition_preflight: gz topic -l returned no topics
overlay_preflight: supported colcon symlink-install overlay rebuilt from b7d43a6
success_criteria: complete DONE trace、stable release-epoch physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
diagnostic_contract:
  - carrying stationarity failure reports CARRYING_TASK_OBJECT_NOT_STATIONARY
  - planning-shadow mismatch reports PLANNING_SHADOW_DIVERGENCE with bounded position/axial-tilt metrics
  - existing planning-shadow、collision and penetration thresholds remain unchanged
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012
cleanup_ownership: only HEADLESS-PHYSICAL-012 launch process group and any daemon created for ROS_DOMAIN_ID 217
acceptance_counting: qualification only；not part of the five-consecutive-run batch
safety_disposition: freeze evidence before cleanup；no reset；never open a physically held unsupported cup
started_at: 2026-08-08T16:43:12+08:00
ended_at: 2026-08-08T16:45:10+08:00
observed:
  original_failure: GRIPPER_CONTACT_PENETRATION_EXCEEDED
  reported_failure_after_recovery: TASK_OBJECT_POSITION_DRIFT
  failed_state: ATTACH_MOVEIT
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> RECOVER_OPEN_GRIPPER -> ERROR
  final_outcome_reached: false
  diagnostic_branch_reached: false
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: false
  controllers_at_freeze: all active
hard_gate_audit:
  - existing carry solver penetration ceiling rejected the physical sample；no ceiling or policy value changed
  - failure occurred before any carrying plan, so neither CARRYING_TASK_OBJECT_NOT_STATIONARY nor PLANNING_SHADOW_DIVERGENCE was expected
recovery_audit:
  - runtime reported original_recovery_disposition_hold_for_operator=1
  - recovery checkpoint persistence still failed with CHECKPOINT_INVALID_DATA and remains a separate defect
  - no reset was run；all available evidence was frozen before owned-stack cleanup
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-012/failure-evidence.sha256
cleanup: only owned launch process group stopped after evidence freeze；ROS_DOMAIN_ID 217 returned empty；no reset
decision: HARD_GATE_WORKED_RETRY_UNCHANGED_POLICY_FRESH_LIFECYCLE
```

## HEADLESS-PHYSICAL-013：fresh-lifecycle carry qualification retry

```yaml
experiment_id: HEADLESS-PHYSICAL-013
status: VALID_FAILURE
implementation_commit: b7d43a64078a94b2a6b968c1eb1f7f395b7265f6
runtime_source_head: 7e8ec0445cc27753a296329e6a254dc574bd16ef
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 218
GZ_PARTITION: so101-physical-outcome-headless-013-20260808
lifecycle: FULL_RESTART
domain_preflight: no nodes
partition_preflight: no topics
single_variable: fresh physics lifecycle；code、policy、physics、motion and safety ceilings unchanged from HEADLESS-PHYSICAL-012
success_criteria: complete DONE trace、stable release-epoch physical outcome and every independent hard invariant
failure_criteria: any valid workflow、hard-gate or final-outcome failure after evidence freeze
invalid_criteria: provenance、overlay、runtime identity、evidence or cleanup mismatch
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013
cleanup_ownership: only HEADLESS-PHYSICAL-013 launch process group and any daemon created for ROS_DOMAIN_ID 218
acceptance_counting: qualification only；not part of five-consecutive acceptance
safety_disposition: freeze evidence before cleanup；no reset；never open a held unsupported cup
started_at: 2026-08-08T16:46:29+08:00
ended_at: 2026-08-08T16:48:30+08:00
observed:
  original_failure: GRIPPER_CONTACT_PENETRATION_EXCEEDED
  reported_failure_after_recovery: RECOVERY_GRIPPER_NOT_STATIONARY
  failed_state: DESCEND_TO_PLACE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> ERROR
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  gripper_open_at_checkpoint: false
  task_object_stationary_at_checkpoint: false
diagnostic_result:
  - LIFT、MOVE_ABOVE_PLACE and DESCEND_TO_PLACE planning all passed the unchanged stationarity and planning-shadow gates
  - no CARRYING_TASK_OBJECT_NOT_STATIONARY or PLANNING_SHADOW_DIVERGENCE occurred
  - failure arose from the existing post-motion solver penetration ceiling；no ceiling was changed
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-013/failure-evidence.sha256
cleanup: evidence frozen before stopping only the owned launch process group；ROS_DOMAIN_ID 218 returned empty；no reset
decision: CARRY_SCENE_DIAGNOSTIC_QUALIFIED_KEEP_PENETRATION_CEILING
```

## HEADLESS-PHYSICAL-014：release-epoch qualification after carry-scene proof

```yaml
experiment_id: HEADLESS-PHYSICAL-014
status: VALID_FAILURE
implementation_commit: b7d43a64078a94b2a6b968c1eb1f7f395b7265f6
runtime_source_head: a36aa72209c2bd814632170ac5cb5c13a4574397
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 219
GZ_PARTITION: so101-physical-outcome-headless-014-20260808
lifecycle: FULL_RESTART
domain_preflight: no nodes
partition_preflight: no topics
single_variable: fresh physics lifecycle；all code、policy、motion、physics and safety ceilings unchanged
success_criteria: complete DONE trace、stable post-release physical outcome and all hard gates
failure_criteria: any valid hard-gate or final-outcome failure after evidence freeze
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014
cleanup_ownership: only HEADLESS-PHYSICAL-014 launch process group and ROS_DOMAIN_ID 219 daemon if created
acceptance_counting: qualification only
safety_disposition: freeze evidence before cleanup；no reset；never open a held unsupported cup
started_at: 2026-08-08T16:50:01+08:00
ended_at: 2026-08-08T16:52:10+08:00
observed:
  original_failure: PLANNING_SHADOW_DIVERGENCE
  reported_failure_after_recovery: UNSAFE_RECOVERY_OBSERVATION
  failed_state: DESCEND_TO_PLACE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> ERROR
  planning_shadow_position_divergence_m: 0.00212028861
  planning_shadow_axial_tilt_divergence_rad: 0.0898560240801
  position_limit_m: 0.005
  orientation_limit_rad: 0.070
  gazebo_attached_at_checkpoint: false
  moveit_attached_at_checkpoint: true
  gripper_open_at_checkpoint: false
safety_audit:
  - position divergence remained within its frozen limit；orientation divergence exceeded its frozen limit and was correctly rejected before planning
  - no threshold、physics、motion、geometry、controller or penetration ceiling changed
  - recovery refused automatic motion/opening while the cup was held away from known support
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-014/failure-evidence.sha256
cleanup: evidence frozen before stopping only the owned launch process group；no reset
decision: PLANNING_VALIDITY_GATE_WORKED_DO_NOT_RELAX
```

## HEADLESS-PHYSICAL-015：unchanged-policy physical qualification retry

```yaml
experiment_id: HEADLESS-PHYSICAL-015
status: VALID_FAILURE
implementation_commit: b7d43a64078a94b2a6b968c1eb1f7f395b7265f6
runtime_source_head: fb20e97
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 220
GZ_PARTITION: so101-physical-outcome-headless-015-20260808
lifecycle: FULL_RESTART
domain_preflight: no nodes
partition_preflight: no topics
single_variable: fresh physics lifecycle；all code、policy、motion、physics and hard ceilings unchanged
success_criteria: complete DONE trace、stable final physical outcome and every hard invariant
failure_criteria: any valid hard-gate or final-outcome failure after evidence freeze
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015
cleanup_ownership: only HEADLESS-PHYSICAL-015 launch process group and ROS_DOMAIN_ID 220 daemon if created
acceptance_counting: qualification only
safety_disposition: freeze evidence before cleanup；no reset；never open a held unsupported cup
started_at: 2026-08-08T16:53:15+08:00
ended_at: 2026-08-08T16:55:20+08:00
observed:
  original_failure: GRIPPER_CONTACT_PENETRATION_EXCEEDED
  reported_failure_after_recovery: RECOVERY_GRIPPER_NOT_STATIONARY
  failed_state: MOVE_ABOVE_PLACE
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> ERROR
  solver_reported_max_depth_m: 0.00134449661709
  stable_solver_depth_limit_m: 0.0013
  task_object_follow_position_error_m: 0.00710024893681
  task_object_follow_orientation_error_rad: 0.157934951101
  task_object_follow_tilt_error_rad: 0.142165983442
  actual_q6_velocity_rad_s: -0.0236519817263
systematic_debugging:
  - repeated fresh-lifecycle qualification failures now establish a physical carry-stability problem rather than a generic diagnostic or provenance problem
  - the depth exceedance co-occurs with large object-follow drift；it is not treated as bounded numerical noise
  - no further unchanged-policy retry may be counted as progress before a RED regression isolates the evidence/contract root cause
  - existing penetration、shadow、collision and catastrophic-loss ceilings remain unchanged
evidence:
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/source-head.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/launch.log
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/frozen-checkpoint.json
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/failure-controllers.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/failure-pose.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/failure-wall-near-contact.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/failure-moveit-scene.txt
  - /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-015/failure-evidence.sha256
cleanup: evidence frozen before stopping only the owned launch process group；no reset
decision: STOP_RETRY_STACKING_AND_DEBUG_PHYSICAL_CARRY_STABILITY
```

## HEADLESS-PHYSICAL-016：fresh-lifecycle final-outcome qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-016
status: VALID_FAILURE
implementation_commit: b7d43a64078a94b2a6b968c1eb1f7f395b7265f6
runtime_source_head: 0d3af18c4da970de596595d849b185bdaac11d17
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 221
GZ_PARTITION: so101-physical-outcome-headless-016-20260808
lifecycle: FULL_RESTART
domain_preflight: no nodes
partition_preflight: no topics
single_variable: fresh physics lifecycle；code、policy、motion、controller、physics and every hard ceiling unchanged
success_criteria: complete DONE trace、stable final release-epoch physical outcome and every hard invariant
failure_criteria: any valid hard-gate or final-outcome failure after evidence freeze
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-016
cleanup_ownership: only HEADLESS-PHYSICAL-016 launch process group and ROS_DOMAIN_ID 221 daemon if created
acceptance_counting: qualification only；a successful run proves the active one-task objective but does not start the frozen five-run campaign until recorded
safety_disposition: freeze evidence before cleanup；no reset；never open a held unsupported cup
started_at: 2026-08-08T16:57:41+08:00
ended_at: 2026-08-08T16:59:40+08:00
observed:
  original_failure: PLANNING_SHADOW_DIVERGENCE
  reported_failure_after_recovery: UNSAFE_RECOVERY_OBSERVATION
  failed_state: DESCEND_TO_PLACE
  planning_shadow_position_divergence_m: 0.00247496629272
  planning_shadow_axial_tilt_divergence_rad: 0.106524517287
  position_limit_m: 0.005
  orientation_limit_rad: 0.070
  trace: IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND -> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> ERROR
comparison:
  - HEADLESS-PHYSICAL-013 passed the same shadow gates through DESCEND_TO_PLACE under identical policy
  - 014 and 016 independently show out-of-bound relative axial tilt before DESCEND；the gate is repeatable and not a generic-scene artifact
  - no approved hard limit or physical parameter changed
evidence_root_frozen: true
cleanup: only owned launch process group stopped after evidence freeze；no reset
decision: RETAIN_HARD_GATE_COMPARE_CARRY_EVIDENCE_BEFORE_NEXT_RUN
```

## HEADLESS-PHYSICAL-017：unchanged-boundary physical qualification

```yaml
experiment_id: HEADLESS-PHYSICAL-017
status: VALID_FAILURE
implementation_commit: b7d43a64078a94b2a6b968c1eb1f7f395b7265f6
runtime_source_head: e928a5a
policy_bundle_sha256: af24ad5bd5daa1bad10c3d7e1164f1b836a020412f9ffb8b80d86a601dd0a47d
run_mode: execute
ROS_DOMAIN_ID: 222
GZ_PARTITION: so101-physical-outcome-headless-017-20260808
lifecycle: FULL_RESTART
domain_preflight: no nodes
partition_preflight: no topics
single_variable: fresh physics lifecycle only；all implementation、policy、motion、controller and safety values frozen
success_criteria: complete DONE trace and stable final physical outcome with every hard invariant
failure_criteria: any valid hard-gate or final evaluator failure after evidence freeze
evidence_root: /tmp/so101-debug-physical-outcome-xZlFSI/qualification/headless-017
cleanup_ownership: only HEADLESS-PHYSICAL-017 launch group and ROS_DOMAIN_ID 222 daemon if created
acceptance_counting: qualification only
safety_disposition: preserve evidence first；no reset；never open a held unsupported cup
started_at: 2026-08-08T17:01:19+08:00
ended_at: 2026-08-08T17:03:10+08:00
observed:
  original_failure: GRIPPER_CONTACT_PENETRATION_EXCEEDED
  reported_failure_after_recovery: UNSAFE_RECOVERY_OBSERVATION
  failed_state: MOVE_ABOVE_PLACE
  solver_reported_max_depth_m: 0.00143691746052
  stable_solver_depth_limit_m: 0.0013
  task_object_follow_position_error_m: 0.00528967213822
  task_object_follow_orientation_error_rad: 0.230848103034
  task_object_follow_tilt_error_rad: 0.229376293963
  actual_q6_velocity_rad_s: -0.00766886305064
root_cause_audit:
  - observer gripper depth path only accepts actual task-object ↔ fixed/moving finger collisions and does not mix support-table contacts
  - depth exceedance co-occurs with out-of-bound physical relative drift；not numerical support-depth noise
  - all prohibited physics、motion、controller、geometry and hard-limit changes remain absent
evidence_root_frozen: true
cleanup: only owned launch process group stopped after evidence freeze；no reset
decision: APPROVED_BOUNDARY_EXHAUSTED_BY_REPEATABLE_PHYSICAL_CARRY_LIMIT_FAILURE
```

## AUTH-TARGET-001：target-only calibration authorization and matrix

```yaml
authorization_id: AUTH-TARGET-001
approved_at: 2026-08-08 Asia/Shanghai
baseline_commit: 2eda34cebc26f359b6687e1f03808fe700c49d01
allowed: TCP grasp pose; q6 close; micro-lift pose/vector; carry/place/retreat targets; trajectory timing/scaling; minimal TDD plumbing
frozen: controller; physics; geometry; mass; friction; attach/shadow semantics; final tolerances; every penetration/shadow/collision/recovery ceiling
baseline:
  grasp_tcp_xyz_m: [0.020676684, -0.262821021, 0.200630611]
  cup_spawn_xyz_m: [0.020, -0.280, 0.165]
  grasp_tcp_relative_translation_m: [0.000676684, 0.017178979, 0.035630611]
  q6_preopen_close_safe_lower_release_rad: [0.465038000, -0.047608632840292, -0.059600220867817, 0.750]
  micro_lift_world_z_m: 0.002
  velocity_acceleration_scaling: {above: [0.03, 0.03], descend_lift: [0.10, 0.10], carry: [0.02, 0.02], place_retreat: [0.03, 0.03]}
geometry:
  cup_height_radius_wall_bottom_m: [0.090, 0.040, 0.002, 0.002]
  below_rim_nominal_min_max_m: [0.025, 0.008, 0.035]
  bottom_clearance_pad_thickness_pad_gap_m: [0.020, 0.005, 0.00196]
matrix:
  A: TCP translation x,y,z; each baseline +/- 0.001 m and geometry intersection
  B: orientation roll,pitch,yaw; each within existing axis_tolerance_rad
  C: safe_lower_q6 <= q6 <= baseline close q6
  D: 0 < micro-lift norm <= 0.002 m
  E: one waypoint/pose scalar within existing endpoint/axis/workspace/joint/collision contracts
  F: one finite-positive timing/scaling scalar; conservative non-acceleration range first
selection: unchanged hard gates all pass; greatest worst normalized safety margin
qualification: selected candidate requires >=3 independent FULL_RESTART runs
publication_gate: five consecutive frozen-commit final-outcome VALID_SUCCESS
old_ledger: MUST_REMAIN_ZERO_DIFF
```

## TARGET-A-X-001：first single-variable TCP-x candidate

```yaml
experiment_id: TARGET-A-X-001
status: PLANNED
prior_experiment: HEADLESS-PHYSICAL-017
hypothesis: 将 grasp TCP x 对齐 cup-center x 可降低偏心载荷，同时保持 y/z/orientation 与全部 hard ceilings
prediction: FK 只改变 x -0.000676684 m；plan-only 仍满足 IK/path/collision；短路径消除首个 hard-gate failure，否则一次 valid failure 淘汰
single_variable: DESCEND grasp TCP x 0.020676684 -> 0.020000000 m
lifecycle: FULL_RESTART
preconditions: [exact RED/GREEN contract, clean build/source/prefix, full plan_only before execute]
success_criteria: [all unchanged hard gates pass, fresh controller/Gazebo/MoveIt/contact short-path evidence]
failure_criteria: [any valid existing hard-gate failure eliminates candidate and ends sequence]
invalid_criteria: [provenance, initial-state, domain/partition, controller, hash or evidence contamination]
provenance:
  source_commit: PENDING_GREEN_COMMIT
  config_hash: PENDING_GREEN_COMMIT
  install_overlay: /data/work/ws_moveit/.worktrees/so101-physical-outcome-validation/install
  runtime_executable: PENDING_BUILD
  ros_domain_id: PENDING_UNIQUE
  gz_partition: PENDING_UNIQUE
  evidence_root: /tmp/so101-debug-physical-outcome-target-a-x-001/
decision: PENDING
next_experiment: NONE_UNTIL_RESULT
```

## CP-PHYSICAL-005

```yaml
checkpoint_id: CP-PHYSICAL-005
last_valid_experiment: HEADLESS-PHYSICAL-017
current_hypothesis: TARGET-A-X-001
working_tree_status: plan leading blank-line diff preserved separately; authorization docs pending commit
owned_processes: NONE
preserved_processes: other worktrees' Gazebo servers and so101-workspace-sampler clang-tidy
confirmed_conclusions:
  - repeated valid failures isolate physical grasp/carry stability inside the target-only authorization
  - support calibration and every hard ceiling remain frozen
disproven_routes: [unchanged-target stochastic retry, support routing contamination as finger-depth cause]
open_risks: [x-only IK must preserve y/z/orientation and every existing path contract]
next_command: add and run SO101FixedMotionTargets.GraspTcpXCandidateMovesTowardCupCenterOnly RED
```

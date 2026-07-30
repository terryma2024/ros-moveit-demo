# SO-101 轻塑料杯跨杯壁抓取与配置化策略 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将抓取对象由 Coke 圆柱替换为 20 g 开口轻塑料杯，让 SO-101 从靠近机器人一侧的杯壁上方下降、两指跨在单侧杯壁内外后夹紧、抬起、搬运并放下；动作策略和验证策略从 YAML 读取，修改参数后重启任务进程即可生效，无需重新编译 C++。

**Architecture:** 使用一个对象配置文件描述杯子与场景，使用相互独立的 motion-policy 和 validation-policy YAML 描述关节路点/夹爪命令及验证门。C++ 只保留类型、schema 校验、状态机执行和证据采集；启动时一次性加载配置并计算内容摘要，checkpoint 绑定三个配置摘要。杯子采用保留开口内腔的复合 primitive collision，不使用会封死杯口的单一 convex hull；SO-101 两根手指继续使用已经离线生成并缓存的凸分解碰撞体。

**Tech Stack:** ROS 2 Jazzy、Gazebo Harmonic、gz-physics-bullet-featherstone-plugin、MoveIt 2、gz_ros2_control、C++17、yaml-cpp、ament/colcon、GoogleTest、pytest、tmux、Codex CUA。

## Global Constraints

- 先在 ai-station 同步最新 `origin/main`；不得 reset、checkout、stash、clean 或覆盖 `/data/work/ws_moveit` 现有脏改动。若脏工作树不能安全快进，使用基于最新 `origin/main` 的独立 worktree，并在实施前逐项审查要带入的新实验改动。
- 仅做仿真；不得连接或驱动真实机械臂。
- 物理引擎保持 `gz-physics-bullet-featherstone-plugin`。
- 保留 SO-101 visual STL；固定指与 moving jaw 使用已经离线缓存的凸碰撞体，不在 Gazebo 启动时运行 VHACD。
- 杯子必须保留真实开口内腔；禁止用一个封闭 cylinder 或单一 convex hull 作为整杯 collision。
- YAML 缺失、schema/version 不匹配、数值非有限、数组长度错误、状态缺失、未知字段或对象 ID 不一致时必须 fail closed，不得静默回退到 C++ 默认动作。
- 本期不做运行中热重载。验收目标是“修改 YAML，重新启动任务进程，不重新 build，行为发生变化”。
- 每一项实现都要先 RED 再 GREEN；不得用放宽门限掩盖错误姿态、错误接触面或穿透。
- GUI 必须由 `so101-moveit` tmux 持有并先 `source ~/gui-env.zsh`；最终视觉验收必须通过 `codex-cua` 或新鲜截图实际查看。
- 不得把 `DONE`、MoveIt `SUCCESS`、controller action 成功或一张截图单独当作完整抓取成功。

---

## 接管基线与已知现场

实施前把本节与 live checkout 对照；以下是 2026-07-28 交接事实，不是最新代码的替代证明。

- 旧工作区：`/data/work/ws_moveit`，交接时 `main` at `54c2732231f581ac2b9575ba5beedec90884720c`，有大量未提交 Coke/VHACD/attachment 实验改动。
- 代码同步已由 ai-station Codex 完成：`git fetch origin` 成功；`origin/main` 为 `7185a3152cd56ed1dfca86e10c6996c2d65b4fd8`；当前分支相对远端领先 2、落后 0；`git pull --ff-only` 返回 `Already up to date`。旧/新 HEAD 均为 `54c2732231f581ac2b9575ba5beedec90884720c`，同步前后 status、worktree diff、index diff 的 SHA-256 指纹一致，未提交改动完整保留。因此 Task 1 实施时只需把这份已验证结论写入新证据目录并重新确认一次，不应重复创建 worktree。
- 已运行 GUI：`so101-moveit` tmux；Gazebo、MoveIt、RViz 正在运行。不得在未检查进程和 ROS graph 时启动第二套 stack。
- 证据目录：`/tmp/so101-debug-cup-handoff-20260728/`。后续每轮另建带时间戳的子目录。
- 已验证可保留：Bullet Featherstone；固定指与 moving jaw 的离线 convex collision；visual STL；无运行期 VHACD；RTF 约 1.0。
- Coke 最终未通过：双侧接触虽存在，但 moving jaw 同时碰到顶缘，attach gate 在 `ATTACH_GAZEBO` fail closed。不要继续围绕 Coke 调 q6 或降低顶缘门。
- `position_proportional_gain` 已恢复 1.0；不要重做 gain=10 或 gain=2 的振荡实验。
- `src/gazebo/attachment_collision_system.cpp` 是尚未完成整链验收的实验插件。它在 attach 时删除物体 collision、detach 时恢复，曾缓解刚性 DetachableJoint 与主动接触的约束冲突。新方案只能在泛化命名、事件顺序和放置恢复 collision 的测试通过后保留。
- 旧 reset 在失败 attach 后可能只复位 pose、不清物体速度。live 验收每次使用干净 Gazebo 重启，除非本轮先修复并验证 reset 速度清零。
- 当前 `Coke`、`coke_model`、`attachCoke` 等命名散布在 runtime、observer、MoveIt scene 和 topics。新功能不得继续把塑料杯伪装成 Coke；应迁移为 task object/object。

## 已冻结的首版杯子与抓取定义

这些值是为了降低仿真难度的首版基线，可在 YAML 中调整，不应硬编码进 C++：

```yaml
schema_version: 1
object_id: plastic_cup
model:
  mass_kg: 0.020
  height_m: 0.090
  outer_radius_m: 0.040
  wall_thickness_m: 0.002
  bottom_thickness_m: 0.002
  side_count: 12
  collision_kind: compound_primitives
scene:
  spawn_pose_xyz_xyzw: [0.020, -0.280, 0.165, 0.0, 0.0, 0.0, 1.0]
  place_pose_xyz_xyzw: [-0.080, -0.250, 0.165, 0.0, 0.0, 0.0, 1.0]
grasp_frame:
  near_wall_outward_world: [0.0, 1.0, 0.0]
  fixed_finger_side: outside
  moving_jaw_side: inside
  insertion_depth_below_rim_m: 0.025
  rim_clearance_m: 0.008
  bottom_clearance_m: 0.020
```

`near_wall_outward_world` 指杯心指向机器人基座的大致方向。首版固定指在杯外作为靠背，moving jaw 进入杯内后向固定指闭合。若 GUI/TF 证明实际机构闭合方向相反，只改 YAML 中抓取侧、腕部姿态与 joint waypoints，不改碰撞门语义。

杯子 collision 采用 12 个薄 box 围成开口十二边形杯壁，外加一个底部 cylinder；靠机器人一面单独命名 `wall_near`，其余为 `wall_01`…`wall_11`，底部为 `bottom`。这比加载多个 STL convex hull 更快，也能让手指进入杯内。visual 可使用一个轻量开口杯 mesh 或同样的 primitive 组合，外观不参与物理判断。

---

### Task 1: 安全同步、选择实施基线并冻结现有实验

**Files:**
- Create: `/tmp/so101-debug-cup-<timestamp>/baseline.txt`
- Create: `/tmp/so101-debug-cup-<timestamp>/incoming.diffstat`
- Modify: none

**Interfaces:**
- Consumes: `origin/main`、当前 dirty worktree、运行中的 tmux/ROS stack。
- Produces: 一个明确的实施目录 `WORKTREE`、旧/新 HEAD、被保留或暂不带入的实验文件清单。

- [ ] **Step 1: 记录旧工作树和运行现场**

```bash
cd /data/work/ws_moveit
debug_dir=/tmp/so101-debug-cup-$(date +%Y%m%d-%H%M%S)
mkdir -p "$debug_dir"
{
  pwd
  git branch --show-current
  git rev-parse HEAD
  git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}'
  git status --short
  git submodule status
  tmux list-sessions
  pgrep -af 'gz sim|move_group|rviz2|pick_place_state_machine'
} | tee "$debug_dir/baseline.txt"
```

- [ ] **Step 2: 获取远端并选择不丢改动的基线**

```bash
git fetch origin
git rev-list --left-right --count HEAD...origin/main
git diff --stat HEAD..origin/main | tee "$debug_dir/incoming.diffstat"
```

如果工作树干净且仅 behind，执行 `git pull --ff-only`。如果工作树脏或 incoming 与脏文件重叠，创建 `/data/work/ws_moveit-light-cup`：

```bash
git worktree add -b codex/light-cup-config-policy /data/work/ws_moveit-light-cup origin/main
```

不得删除旧工作树。后续所有命令中的 `WORKTREE` 明确设为所选目录。

- [ ] **Step 3: 审查哪些旧实验可以移植**

只允许逐文件审查后移植：固定指/moving-jaw 离线 collision 及生成器、Bullet world 配置、已通过的 contact observer 证据字段。暂不移植 Coke 固定关节路点、Coke 半径/高度、Coke 专用 contact band、q6 边界试验和未经完整验收的 attachment collision plugin。

- [ ] **Step 4: 保存基线结论**

在 `baseline.txt` 末尾记录 `WORKTREE`、old/new HEAD、dirty changes preserved=yes，以及每项移植决定。此任务不提交代码。

---

### Task 2: 定义并解析三个 YAML 配置契约

**Files:**
- Create: `src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml`
- Create: `src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml`
- Create: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
- Create: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp`
- Create: `src/so101_gazebo_demo/src/pick_place/policy_config.cpp`
- Create: `src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/package.xml`

**Interfaces:**
- Produces: `TaskObjectConfig`, `MotionPolicyConfig`, `ValidationPolicyConfig`, `LoadedPolicyBundle loadPolicyBundle(const PolicyPaths&)`。
- `LoadedPolicyBundle` 包含三份 typed config、每份 canonical absolute path、SHA-256 内容摘要及组合摘要。

- [ ] **Step 1: 写 loader 的失败测试**

覆盖：有效 fixture；缺文件；未知顶层字段；`schema_version != 1`；NaN/Inf；pose 非 7 项；joint waypoint 非 5 项；缺状态；motion/object ID 不一致；validation/motion `policy_id` 不一致。错误码固定为 `POLICY_FILE_MISSING`、`POLICY_SCHEMA_UNSUPPORTED`、`POLICY_UNKNOWN_FIELD`、`POLICY_INVALID_VALUE`、`POLICY_STATE_MISSING`、`POLICY_ID_MISMATCH`。

```cpp
TEST(PolicyConfig, RejectsObjectIdMismatch)
{
  const auto result = loadPolicyBundle(fixturePaths("mismatched_object"));
  ASSERT_FALSE(result.bundle.has_value());
  ASSERT_TRUE(result.failure.has_value());
  EXPECT_EQ(result.failure->code, "POLICY_ID_MISMATCH");
}
```

- [ ] **Step 2: 运行 RED**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
ctest --test-dir build/so101_gazebo_demo -R test_policy_config --output-on-failure
```

预期：因 `policy_config.hpp`/target 尚不存在而失败。

- [ ] **Step 3: 实现类型与严格解析器**

类型至少包含：

```cpp
struct PolicyPaths { std::string object; std::string motion; std::string validation; };
struct StateMotionConfig {
  State state;
  std::vector<double> logical_start;
  std::vector<std::vector<double>> waypoints;
  bool require_waypoint_ladder;
  double gripper_q6;
};
struct MotionPolicyConfig {
  int schema_version;
  std::string policy_id;
  std::string object_id;
  std::vector<std::string> arm_joints;
  std::map<State, StateMotionConfig> states;
};
struct StateValidationConfig {
  State state;
  MotionValidationConfig motion;
};
struct LoadedPolicyBundle {
  TaskObjectConfig object;
  MotionPolicyConfig motion;
  ValidationPolicyConfig validation;
  std::array<std::string, 3> sha256;
  std::string bundle_sha256;
};
```

使用 `yaml-cpp`，显式枚举允许字段。不得用 `node.as<T>(default)` 吞掉缺字段。摘要对原始文件 bytes 计算，使一次参数改动必然改变 checkpoint identity。

- [ ] **Step 4: 填入完整首版 YAML**

motion YAML 为每个运动状态显式提供 `logical_start`、`waypoints`、`require_waypoint_ladder`、`gripper_q6`；包括正常链和 recovery 状态。validation YAML 为每个状态显式提供 endpoint、轴向、path direction、position/axis/lateral/joint/duration/monotonic tolerances、allowed touch、temporal contact。数值先从最新可运行基线复制作为“可加载 fixture”，Task 6 再通过 GUI 标定杯子路点；不得留下占位符。

- [ ] **Step 5: 运行 GREEN 并提交**

```bash
ctest --test-dir build/so101_gazebo_demo -R test_policy_config --output-on-failure
git add src/so101_gazebo_demo/config src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/policy_config.hpp src/so101_gazebo_demo/src/pick_place/policy_config.cpp src/so101_gazebo_demo/test/pick_place/test_policy_config.cpp src/so101_gazebo_demo/CMakeLists.txt src/so101_gazebo_demo/package.xml
git commit -m "feat: load SO-101 task policies from YAML"
```

---

### Task 3: 用配置驱动 motion policy、validation policy 与 checkpoint provenance

**Files:**
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_fixed_motion_targets.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_fixed_motion_targets.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_task3_runtime.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_task3_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/runner.cpp`
- Modify: `src/so101_gazebo_demo/src/nodes/pick_place_state_machine.cpp`
- Modify: `src/so101_gazebo_demo/launch/so101_pick_place.launch.py`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_fixed_motion_targets.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_checkpoint.cpp`
- Modify: `src/so101_gazebo_demo/test/test_so101_launch_contract.py`

**Interfaces:**
- Consumes: `LoadedPolicyBundle`。
- Produces: `SO101ConfiguredMotionTargetPolicy(MotionPolicyConfig, ValidationPolicyConfig)`；CLI `--object-config`、`--motion-policy`、`--validation-policy`；checkpoint 字段 `policy_bundle_sha256`。

- [ ] **Step 1: 写 RED 测试，证明 C++ 表不再是事实源**

测试从两份只差 `MOVE_ABOVE_OBJECT.gripper_q6` 或 endpoint tolerance 的临时 YAML 加载两次，断言同一 binary 得到不同 target/validator；恢复 checkpoint 时摘要不同必须返回 `CHECKPOINT_POLICY_MISMATCH`。

- [ ] **Step 2: 实现配置驱动 policy**

删除 `so101_fixed_motion_targets.cpp` 中的 `kAbovePick`、`kPick*`、`kAbovePlace`、`kPlace*` 和 `config(...)` 常量表。保留 `IJointMotionTargetPolicy` 接口，把 `spec(State)` 变为对 typed map 的只读查询。类名可迁移为 `SO101ConfiguredMotionTargetPolicy`；若保留旧类名作为兼容 alias，不能再构造 canonical hardcoded policy。

- [ ] **Step 3: 接入 CLI 与 launch**

launch 默认路径必须来自 installed package share：

```python
DeclareLaunchArgument("object_config", default_value=os.path.join(package_share, "config", "task_objects", "light_plastic_cup.yaml"))
DeclareLaunchArgument("motion_policy", default_value=os.path.join(package_share, "config", "motion_policies", "light_cup_wall_pick.yaml"))
DeclareLaunchArgument("validation_policy", default_value=os.path.join(package_share, "config", "validation_policies", "light_cup_wall_pick.yaml"))
```

节点启动时打印三条 canonical path、各自摘要和 bundle 摘要；不得打印整个 YAML。配置错误在创建 ROS/Gazebo side effect 前退出非零。

- [ ] **Step 4: 安装 config 并运行测试**

```bash
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
pytest -q src/so101_gazebo_demo/test/test_so101_launch_contract.py
ctest --test-dir build/so101_gazebo_demo -R 'test_policy_config|test_so101_fixed_motion_targets|test_checkpoint' --output-on-failure
```

- [ ] **Step 5: 证明修改 YAML 无需重新编译**

```bash
binary=install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
before=$(stat -c %Y "$binary")
cp install/so101_gazebo_demo/share/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml /tmp/light-cup-motion.yaml
# 仅修改 /tmp YAML 中一个可观察的 dry-run q6 值，然后分别启动两次 dry_run。
after=$(stat -c %Y "$binary")
test "$before" = "$after"
```

两次日志必须显示不同配置摘要及不同 target，binary mtime 相同。

- [ ] **Step 6: 提交**

```bash
git add src/so101_gazebo_demo
git commit -m "refactor: drive SO-101 motion and validation from config"
```

提交前用 `git diff --cached --name-only` 排除 assets、日志、IDE 文件和旧工作树无关改动。

---

### Task 4: 将 Coke 领域对象泛化为 task object，并加入开口杯模型

**Files:**
- Modify: `src/so101_gazebo_demo/worlds/so101_pick_place.sdf`
- Modify: `src/so101_gazebo_demo/launch/so101_gazebo.launch.py`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/so101_profile.hpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/world_observer.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/moveit_scene_adapter.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/moveit_scene_adapter.cpp`
- Modify: attachment/reset/relay files found by `rg -l 'Coke|coke_' src/so101_gazebo_demo/{include,src,launch,test}`
- Modify: `src/so101_gazebo_demo/test/test_so101_pick_place_world.py`
- Modify: affected C++ contract tests

**Interfaces:**
- `TaskObjectConfig.object_id == "plastic_cup"` 是 Gazebo、MoveIt 和 state machine 的共同 ID。
- Topic 使用 `/so101/attach_object`、`/so101/detach_object`、`/so101/object_attached_event`、`/so101/object_attached`、`/task_object/contacts`。

- [ ] **Step 1: 写杯子几何 RED tests**

pytest 解析 SDF 并断言：model=`plastic_cup`；mass=0.020；12 个 wall collision + bottom；不存在覆盖整个杯体的 solid cylinder/convex hull；杯内半径至少 0.038 m；contact sensor 指向所有杯体 collision；旧 `model name="coke"` 不存在。

- [ ] **Step 2: 写通用对象 API RED tests**

测试名称和 failure message 不再写 Coke；MoveIt object 使用 `plastic_cup`；attach/detach topics 全部来自 object config；world snapshot 提供 `task_object_*` 字段。一次性迁移测试与 production call sites，避免 Coke/TaskObject 双份事实源长期共存。

- [ ] **Step 3: 实现杯子 SDF**

12 个 wall box 围绕 z 轴，box 长度取相邻多边形顶点的 chord 并仅留很小 overlap；`wall_near` 的外法线对齐世界 +Y。底部 collision 的半径不得堵塞内腔以上空间。惯量必须根据 20 g 总质量给出有限、正值且满足三角不等式。

- [ ] **Step 4: 泛化观察、scene、attach 与 reset**

用 `task_object` 命名替换 `coke` 命名；MoveIt collision 不能用实心 cylinder 代表开口杯。MoveIt 使用同样的 12 wall boxes + bottom cylinder，使 moving jaw 在杯内时不会被虚假的实心体阻挡。

- [ ] **Step 5: 处理 attachment collision gate**

将实验插件改为对象 ID/command topic 配置驱动，并新增状态 readback。attach 前必须有双指杯壁接触；attach 成功后才禁用杯 collision。放置时 TCP 停在杯底高于桌面 2–3 mm，先移除 DetachableJoint，再恢复 collision，让重力完成最后 settling；不得在杯底已经深穿桌面时恢复 collision。

- [ ] **Step 6: GREEN、构建与提交**

```bash
pytest -q src/so101_gazebo_demo/test/test_so101_pick_place_world.py src/so101_gazebo_demo/test/test_configuration_contract.py
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
ctest --test-dir build/so101_gazebo_demo -R 'attachment|moveit_scene|world_reset' --output-on-failure
git add src/so101_gazebo_demo
git commit -m "feat: replace Coke with open light plastic cup"
```

---

### Task 5: 实现跨单侧杯壁的动作与接触验证

**Files:**
- Modify: `src/so101_gazebo_demo/config/motion_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/config/validation_policies/light_cup_wall_pick.yaml`
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_attachment_contracts.cpp`
- Modify: `src/so101_gazebo_demo/test/pick_place/test_so101_fixed_motion_targets.cpp`

**Interfaces:**
- Observer 输出每根手指所接触的 cup collision、contact point、normal、depth 和相对杯坐标。
- Attach contract 要求 fixed finger 接触 `wall_near` 外表面、moving jaw 接触同一 `wall_near` 内表面；禁止 rim、bottom、opposite wall contact。

- [ ] **Step 1: 写接触语义 RED tests**

最少覆盖六例：正确同壁内外双侧接触通过；只有固定指失败；只有 moving jaw 失败；moving jaw 碰 rim 失败；任一手指碰 bottom 失败；两指分别碰 near/opposite wall 失败；depth 超阈值失败。

- [ ] **Step 2: 在 validation YAML 固化首版门**

```yaml
grasp_contact:
  require_fixed_finger: true
  require_moving_jaw: true
  required_wall_collision: wall_near
  fixed_surface: outside
  moving_surface: inside
  max_penetration_m: 0.0008
  min_below_rim_m: 0.008
  max_below_rim_m: 0.035
  min_bottom_clearance_m: 0.020
  forbidden_collisions: [rim, bottom, wall_opposite]
runtime:
  min_real_time_factor: 0.85
  q6_velocity_tolerance_rad_s: 0.01
```

- [ ] **Step 3: 配置动作序列**

保持状态机主链，但改变含义：`MOVE_ABOVE_OBJECT` 到 `wall_near` 上方；`DESCEND` 垂直下插 25 mm，使 fixed finger 在外、moving jaw 在杯内；`CLOSE_GRIPPER` 夹单层 2 mm 杯壁；`LIFT` 先纯竖直抬升至少 50 mm；`MOVE_ABOVE_PLACE` 横移；`DESCEND_TO_PLACE` 停在杯底离桌面 2–3 mm；detach/恢复 collision；`RETREAT` 开爪后竖直离开。

第一次 joint waypoints 可通过 plan-only/交互标定写入 YAML，但每次只改变一个 waypoint。不要在 C++ 增加补偿常量。

- [ ] **Step 4: GREEN 并提交**

```bash
ctest --test-dir build/so101_gazebo_demo -R 'test_so101_attachment_contracts|test_so101_fixed_motion_targets' --output-on-failure
git add src/so101_gazebo_demo/config src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp src/so101_gazebo_demo/src/pick_place/so101_attachment_contracts.cpp src/so101_gazebo_demo/test/pick_place
git commit -m "feat: pinch the near wall of the plastic cup"
```

---

### Task 6: 分级标定并验证完整状态机

**Files:**
- Modify: only the two policy YAML files unless a test proves a code defect
- Create: `/tmp/so101-debug-cup-<timestamp>/commands.log`
- Create: `/tmp/so101-debug-cup-<timestamp>/acceptance.md`

**Interfaces:**
- Produces: 每个状态的 plan/execute/controller/Gazebo/MoveIt/visual 证据，以及最终 `DONE` 或明确首个失败边界。

- [ ] **Step 1: 干净构建与 provenance**

```bash
cd "$WORKTREE"
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
ros2 pkg prefix so101_gazebo_demo
stat install/so101_gazebo_demo/lib/so101_gazebo_demo/pick_place_state_machine
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] **Step 2: 干净重启 GUI stack**

先列出并只停止本轮/旧 SO101 stack 的已确认 PID，不使用宽泛 `pkill -f ros`。在 `so101-moveit` tmux 内：

```bash
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source "$WORKTREE/install/setup.zsh"
export ROS_DOMAIN_ID=96 ROS2CLI_DISABLE_DAEMON=1
export GZ_PARTITION=so101_light_cup_$(date +%H%M%S)
```

启动 Gazebo GUI 和 MoveIt/RViz 后运行分屏工具并保存 baseline screenshot。

- [ ] **Step 3: 按 checkpoint 逐级执行**

顺序只推进到：`MOVE_ABOVE_OBJECT`、`DESCEND`、`CLOSE_GRIPPER`、`ATTACH_GAZEBO`、`ATTACH_MOVEIT`、`LIFT`、`MOVE_ABOVE_PLACE`、`DESCEND_TO_PLACE`、detach/sync、`RETREAT`。每一级记录：目标与实际 joints、TCP 前后、q6/velocity、contact collision/point/normal/depth、cup pose、attachment state、Planning Scene membership、RTF。

- [ ] **Step 4: CLOSE_GRIPPER 专项门**

只有同时满足以下条件才能 attach：

- fixed finger 与 moving jaw 都接触 `wall_near`；
- 两者 contact point 都在 rim 下 8–35 mm 且离 bottom 至少 20 mm；
- fixed contact normal 指向杯外、moving contact normal 指向杯内（允许 validation YAML 的角度容差）；
- 无 rim/bottom/opposite-wall contact；
- penetration ≤ 0.8 mm；
- q6 停稳且 position controller 没有继续强行推进；
- RTF ≥ 0.85。

- [ ] **Step 5: attach/lift/place/detach 专项门**

Attach 后杯 pose 必须随 TCP，MoveIt world object 必须转为 attached object。Lift 中杯底离桌面增加至少 45 mm，杯姿态漂移在 YAML 容差内。Place 时先解除刚性 joint，再恢复 collision，杯子稳定落桌；最终 Gazebo 与 MoveIt 都 detached/world，杯 pose 位于 place tolerance 内，机器人 retreat 后无接触。

- [ ] **Step 6: 新鲜视觉验收**

使用 `codex-cua` 按 `snapshot -> action -> fresh snapshot` 查看：杯子确实开口；一指在杯内、一指在杯外；夹爪没有穿 rim/bottom；抬起时杯子离桌；放下后杯子独立站在目标位置。运行 `capture-ai-station.sh` 并实际打开最终 desktop/RViz/Gazebo 图片。

- [ ] **Step 7: 记录结果，不伪造完成**

`acceptance.md` 使用：

```text
Root cause: CONFIRMED | NOT CONFIRMED
First bad boundary:
Policy paths and SHA-256:
Build/test exit codes:
Gazebo proof:
MoveIt proof:
Controller/joint/TF proof:
Contact/depth/RTF proof:
Visual proof and screenshot path:
Preserved user changes:
Remaining risks / next exact command:
```

只有所有层通过才写完整抓取成功；否则停在首个失败边界，下一轮只改一个 YAML 变量或一个已被测试证明的代码根因。

---

### Task 7: 启动性能与最终回归

**Files:**
- Modify: `src/so101_gazebo_demo/scripts/prepare_simulation_model.py` only if the current latest branch still needs it
- Modify: `src/so101_gazebo_demo/scripts/benchmark_gazebo_startup.py`
- Modify: corresponding tests
- Modify: `src/so101_gazebo_demo/README.md`

**Interfaces:**
- Produces: 三次 cold-start 数据、配置使用说明、最终回归报告。

- [ ] **Step 1: 写启动门 RED test**

静态测试断言 Gazebo 启动不调用 VHACD，杯子仅使用 primitive collision，fixed/moving finger 使用已安装缓存文件，缺缓存时 prepare 阶段 fail closed。

- [ ] **Step 2: 三次 cold-start benchmark**

每次干净关闭本轮 Gazebo server 后启动，记录从进程开始到 world/control/contact topics ready 的时间与 RTF。报告 median 和三次原始值；与历史 55.722 s 及 16-piece 17.168 s 只能作为旧参考，不能伪装为本轮实测。检查日志中无 mesh/resource construction error，并确认实际加载的 finger convex piece 数。

- [ ] **Step 3: 更新 README**

说明三个配置路径、字段职责、如何复制到 `/tmp` 做 A/B、修改 YAML 后只重启进程、不需要 build，以及为何杯子不能用单一 convex hull。补一条最小练习：让用户把 lift height 增加 10 mm，预测并观察 TCP/cup z 变化。

- [ ] **Step 4: 全包回归与最终提交**

```bash
PYTHONNOUSERSITE=1 colcon test --packages-select so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
git diff --check
git status --short
git add src/so101_gazebo_demo/README.md src/so101_gazebo_demo/scripts src/so101_gazebo_demo/test
git commit -m "test: verify light-cup startup and runtime policy workflow"
```

不得提交 `assets/captures`、`build`、`install`、`log`、`.idea` 或用户旧工作树的无关文件。

## 最终完成判据

- 最新代码同步方式、old/new HEAD 和 dirty preservation 有书面记录。
- 三份 YAML 均从 installed package 或显式 CLI 路径加载，错误配置 fail closed。
- 修改 motion 或 validation YAML 后不重新 build 即改变行为，binary mtime 不变且配置摘要改变。
- Gazebo 中是开口的 20 g 杯子；MoveIt collision 同样保留内腔。
- 两指跨在 `wall_near` 内外，接触高度/法线/collision/depth 通过配置门；无 rim/bottom/opposite-wall 接触。
- q6 停稳，没有 position controller 持续强行穿透；RTF 达标。
- Gazebo attach/detach、MoveIt attach/detach、controller/joints/TF、cup pose 和 Planning Scene 全部一致。
- 完整状态机到 `DONE`，杯子在预定位置稳定落桌，机器人退开。
- 本轮新 GUI 截图已被实际查看；截图中的一指内一指外、抬起和放置结果可辨认。
- package tests 无新增失败，未覆盖或夹带用户既有改动。

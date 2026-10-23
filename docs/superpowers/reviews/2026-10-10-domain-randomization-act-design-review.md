# 审查：SO-101 MuJoCo 环境随机化与 ACT 示教采集设计草案

审查对象：`docs/superpowers/specs/2026-10-09-so101-mujoco-domain-randomization-act-design.md`（下称“本文”，行号以当前文件为准）
审查日期：2026-10-10。方式：只读静态审查，对照本地 `scene.xml`、`so101.xml`、`config/mujoco/*`、`third_party/mujoco_ros2_control` 源码和 09-10 / 10-01 / 10-03 / 10-05 / 10-06 等相关 specs。没有修改仓库内容，也没有运行仿真。MuJoCo 默认类继承行为用 MuJoCo 3.15.0 的最小复现模型验证过。

## 结论

方向正确，可以作为下一轮修订的基础，但目前**不建议直接冻结进入实施计划**。路线选择、Teacher/Recorder 权限边界、action 标签与 plant 扰动分离、按接触对处理摩擦、split 防泄漏、`QUOTA_UNSATISFIED` 不补齐这些原则都写得扎实，和 10-05 分离修订、09-10 ACT 合同一致。

需要先补的是三类问题：

1. **事实前提有漏项**：杯子自由关节实际继承了机械臂默认的 `armature=0.028` 和 `frictionloss=0.052`，杯子的有效惯性和落体/滑移响应被它主导。本文的“杯质量 ±10%”和“先审计阻尼”都建立在不完整的事实上。
2. **与现有身份/资格链冲突未处理**：已批准的接触策略和 batch 资源身份都按 `scene.xml`/`so101.xml` 的 sha256 指纹锁定，每 episode 改模型会触发 `POLICY_FINGERPRINT_MISMATCH`，或者绕过指纹后让旧校准静默套到新物理上。本文没有讨论。
3. **几个“视觉”参数其实会改几何或门禁**：相机安装外参会带动带碰撞体的支架/外壳；光照与背景会影响已冻结的 Head Search 检测器和 Teacher 感知。这些影响本文没有展开到资格层面。

另外，阶段 E 的四组等量对照和 1,000 条预算之间存在数量矛盾，需要说清楚。

## 问题（按重要性排序）

### P0：必须在冻结前解决

**P0-1 杯子自由关节继承了机械臂的 armature 和 frictionloss（本文 §2 第 25 行、§3 第 41 行、§4 第 61 行）**

- 事实：`so101.xml:52` 的顶层 `<default><joint damping="0.60" frictionloss="0.052" armature="0.028"/>` 会经 `<include>` 作用到 `scene.xml` 里的 `cup_free_joint`。该关节只显式覆盖了 `damping="1.0"`，所以 6 个自由度都带 `armature=0.028`、`frictionloss=0.052`。我用 MuJoCo 3.15.0 编译同结构的最小模型，读回结果就是这些值。`v5_multi_object_scene.xml` 里的杯 B 和瓶子同样受影响。
- 影响（按动力学推算，没有在完整场景里实测）：平移方向有效质量约为 0.020 + 0.028 = 0.048 kg，自由落体加速度约降到 4 m/s²；再叠加 1.0 N·s/m 的平移阻尼，终端速度约 0.2 m/s。转动方向 armature 比杯子主惯量（约 3e-5 kg·m²）大将近三个数量级。因此“杯质量 0.9–1.1×”几乎不改变杯子的实际响应，§3 只审计 damping 也会漏掉主因。
- 建议：在 §2 事实表里补上这条。§3.3 改成审计“自由关节的 damping、armature、frictionloss 三者是否只是数值稳定补偿”。nominal 修正属于物理基线变更，应该先单独立项（它会改变现有 Teacher 成功率和接触校准，见 P0-2），再谈质量随机化。

**P0-2 每 episode 改模型和现有的指纹/资格链冲突（本文 §5 第 81 行、§6 第 110 行、§7 第 124 行）**

- 事实：`config/mujoco/contact_calibration.yaml` 的 `fingerprint` 锁定了 `model_sha256`/`scene_sha256`。`application/pick_place.py:343` 读的是安装目录里 `assets/mujoco/scene.xml` 的 sha256，不匹配时 `core/contact_policy.py:720` 拒绝，`_preflight_task_policy` 返回 `POLICY_FINGERPRINT_MISMATCH`。`parallel_batch/resources.py:802/816` 也把 `scene_manifest` hash 当作 batch 的 source identity。
- 影响：SceneRealizer 不管走哪条路都会出问题。加载新生成的 XML，就会被指纹拒绝；继续读安装目录的 nominal 文件，指纹虽然通过，但接触校准里的分位数阈值（bilateral_touch、micro_lift_slip 等）会静默套到摩擦、质量、阻尼都已改变的物理上。虽然 10-05 修订已经把过程质量从成功判据里移出，接触策略仍是 Teacher 预检必需的已批准工件。
- 建议：新增一节“身份与资格”，至少写清四件事：nominal 指纹和 per-episode realized 指纹各自的含义；接触策略批准覆盖的是 nominal 还是整个 profile 包络，以及动力学 profile 是否需要重新校准或另批；batch 级 `scene_manifest` 怎样表示“同一 profile 的多个变体”；AppliedSceneManifest 怎样与 coordinator journal/campaign-index 关联。

**P0-3 head/wrist 相机安装外参被归为“视觉”，但支架和外壳带碰撞体（本文 §4 第 54–55 行、§8 阶段 B）**

- 事实：09-10 设计第 103 行要求 head 支架和相机外壳加入碰撞几何，规划、reset 和 MuJoCo 接触都要识别；第 276 行的 rollout 监督也按 head 支架和相机外壳做路径检查。
- 影响：head 平移 ±10 mm 或 wrist ±3 mm 如果移动的是整个安装体，就属于几何变化，必须同步 MJCF、URDF、Planning Scene 和监督几何（本文 §6 第 114 行自己也说“任何几何变化都需同步规划碰撞体”）；如果只移动光学 frame，碰撞体就会和画面里看到的外壳位置不一致。
- 建议：明确选一种做法。我的推荐是首版只扰动光学 frame 相对外壳的小位姿，外壳碰撞体保持不动；把整体安装位置变化放进几何类，和杯尺寸、杂物一起后置。

### P1：冻结前应补充

**P1-1 Head Search 门禁没有纳入随机化影响（§6 第 116 行只提到 Teacher 感知）**
10-03/10-06 修订冻结了 17 项搜索参数、单模型和三帧锁定；09-10 第 140 行要求检测器“在 head 视角单独验证”。光照、背景、杯色变化会直接改变 head 检测，造成 `TARGET_NOT_FOUND`/`TARGET_AMBIGUOUS`，使采集分布偏向检测器擅长的外观。建议在 §6 把 Head Search 失败单独分桶，并在阶段 B 增加“随机化包络下的 head 检测器资格”放行项，或者首版先在非 Head 流程（固定目标输入）上做随机化。

**P1-2 本文依据的基线不是 ACT 场景（§2 第 25 行、第 31 行）**
本地 `scene.xml` 只有 `task_camera` 和 `key_light`，没有 head/wrist 相机、head_mast 和 neck；本地 src 里也找不到这些定义。本文把 `scene.xml` 当 nominal 来分析，但随机化真正要作用的是 09-10 所说的“显式 ACT 场景入口”。建议把“在执行机读取 ACT 场景 MJCF 并重做 §2 事实表”列为实施计划的第一步，而不只是写一句“须核对”。

**P1-3 光照模型不完整（§4 第 52 行）**
场景里还有 MuJoCo 默认 headlight（`scene.xml` 没有关闭），v5 场景另有 `fill_light`。只扰动 `key_light` 强度和方位时，固定的 headlight 会稀释扰动效果。建议 profile 显式列出所有光源（含 headlight），说明扰动的是 diffuse、ambient 还是 specular，并注明 MuJoCo 的光源属性是 RGB 系数，不是物理照度。

**P1-4 接触对覆盖不完整（§4 第 59 行、§5 第 71 行）**
本文写的是“杯–指垫”。实际上夹爪与杯子之间有两组碰撞体：`*_fingertip_pad_collision_*`（friction 3.0，`solref="-1000000 -100"` 直接刚度/阻尼）和 `*_contact_convex_*`（继承默认 friction 1.0）。按 max 规则，与杯子（1.2）组合后分别是 3.0 和 1.2。另外 `noslip_iterations=10` 和指垫的 solref/solimp 对夹持滑移的影响可能和摩擦同量级。建议按 geom 组列出接触对，并说明首版是否固定软接触参数和 noslip。

**P1-5 延迟/偏置注入与 JTC 闭环的交互（§5 第 73–77 行）**
`arm_controller`/`gripper_controller` 都是 `open_loop_control: false` 的 JTC，`controller_manager` 运行在 500 Hz。插件在 `mujoco_system_interface.cpp:1162` 之后改写 `ctrl`，JTC 看到的状态反馈就会滞后或偏移，可能触发路径/目标容差 abort，Teacher 失败会被错误地记到“随机化难度”上。reset 路径 `set_initial_pose()`（第 2207 行起）会把 `ctrl` 直接写成当前状态，延迟队列必须在这一步之前或同步清空。建议在 §5 写明延迟的粒度（2 ms 控制周期）、JTC 容差配置核对，以及“扰动导致的控制 abort”单独分桶。

**P1-6 阶段 E 的数据量与预算不一致（§7 第 128 行 vs §8 第 142–144 行）**
D 阶段是 1,000 条按 20/30/20/30 混合的数据；E 阶段却要 nominal、visual、dynamics、combined 四组等量对照，还要做 250/500/1,000 的学习曲线。这至少需要 4 组各 1,000 条，即约 4,000 条，按 §7 的估算约 4.4 TB 未压缩。建议说明 E 是从混合池里按桶抽子集（这时各组上限只有 200–300 条），还是另行按组采集，并据此改预算和磁盘估算。

**P1-7 rollout 场景数改变了 09-10 合同（§8 第 148 行）**
09-10 规定 Rollout Validation/Test 各至少 10 个场景；本文要求“每个条件桶至少 50 个”，4 个桶就是 200 个以上，单个 ACT 运行上限 120 s。这是合同修订，应在文首写成显式优先级条款（像 10-05 修订那样列出被替代的文档和范围），否则两份文档会并存矛盾。

### P2：建议改进

- **P2-1 内参实现路径**（§4 第 56 行、§5 第 79 行）：MuJoCo 3.x 的 camera 原生支持 `sensorsize`/`focal`/`principal`（及 pixel 变体），设置后渲染不再使用 `fovy`。CameraPlugin 只读 `cam_fovy`（`camera_plugin.cpp:299`），所以改内参首先要让 CameraInfo 从 `cam_intrinsic`/`cam_sensorsize` 推导。畸变 MuJoCo 不支持，需要后处理重映射。建议把这条具体路径写进 §5。
- **P2-2 延迟范围的依据**（§4 第 63 行）：0–20 ms 是在 500 Hz 控制、10 Hz action 网格下的额外延迟，相对 100 ms 的标签间隔较小。建议注明实机 STS3215 总线读写周期的预期量级，并在 A 阶段测出来之后再定上限。
- **P2-3 episode 时长假设**（§7 第 132 行）：60 s 只是估算用的假设，建议标明来源或改用首条真实 episode 的时长。
- **P2-4 基线 hash 无法本地复核**（§2 第 21 行）：本地这个目录的 `.git` 指向上层 modules 目录，当前无法回读 `7a62d8e`。实施计划应在执行机重新取 HEAD/submodule/dirty 状态，和 10-03、10-06 的做法一致。
- **P2-5 命名**：§9 提到的 `RandomizationProfile` 等组件名“待冻结”，但 §7 已经开始使用 `scenario_id`/`scene_family_id` 字段名。建议在 §6 给出 manifest 最小 schema（字段、类型、单位），方便后续测试直接引用。

## 建议的下一步

1. 先单独立一个“杯子自由关节 nominal 修正”的小设计或修订：确认 armature/frictionloss/damping 的意图，评估对现有 Teacher 成功率和接触校准的影响。它是所有动力学随机化的前提。
2. 在本文补一节“身份、指纹与资格”（P0-2），并把相机安装外参的处理方式（P0-3）、Head Search 资格（P1-1）写清楚。
3. 拿到执行机上的 ACT 场景 MJCF 后，重做 §2 事实表，包括光源、相机和接触对清单。
4. 把阶段 E 的数据设计和 rollout 数量改成与预算一致，并用显式优先级条款修订 09-10 合同。
5. 首版范围建议进一步收窄：先做视觉（光照、纹理、光学 frame 小扰动、FOV）+ 非 Head 流程，动力学放到 nominal 修正和校准之后。这样能最早验证 SceneRealizer、manifest 和 split 这条链路，同时不触碰已批准的接触策略。

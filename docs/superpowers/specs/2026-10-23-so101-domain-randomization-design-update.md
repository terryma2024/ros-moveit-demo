# SO-101 MuJoCo 环境随机化：设计审查与更新方案

日期：2026-10-23。状态：设计更新，供人工审阅。人工要求“先不动手做，记到优化 todo 里即可”，所以本文不授权任何实施、采集或训练。

## 输入

- 原草案：`docs/superpowers/specs/2026-10-09-so101-mujoco-domain-randomization-act-design.md`。
- 原审查：`docs/superpowers/reviews/2026-10-10-domain-randomization-act-design-review.md`。

两份都在提交 `49119c153` 中。该提交不在 `codex/so101-act-data-0917a` 的祖先链上，阅读请用 `git show 49119c153:<path>`。

本文先逐条对照 2026-10-23 的仓库与实验状态，判断原草案和原审查哪些已过时、哪些仍成立，再给出更新后的分期方案。

## 人工决定（2026-10-23）

- **D1**：选 c，按物理相关子树计算指纹。视觉字段不进入指纹，所以视觉随机化沿用 nominal 的接触校准；动力学随机化需要重新校准或另批。要先把拆分做对，并用测试证明：只改视觉字段时，物理指纹不变；任一物理字段改变时，指纹随之改变。
- **D2**：选 a，随机化 episode 中 Teacher 用特权真值杯位（`teacher_source: privileged_pose`）。**另加一项**：YOLO（Teacher 的 `task_camera` 感知）也要做微调，以适应随机化后的场景外观。微调数据来自随机化场景的渲染，标注用仿真真值；资格评估按随机化分桶报告。
- **D3**：首版只做 R0。拿到 R0 数据后，再定 R2、R3 的具体参数和预算。

## R0 实施方案（2026-10-23，人工设定目标“完成35-R0”）

- **评估用场景变体**：新增一个纯函数模块。输入是 nominal 的 `scene_side_wrist.xml` 和一个变体描述（JSON），输出三样东西：变体 MJCF、实际生效值清单、realized 哈希。只允许白名单内的视觉字段：
  - `key_light` 的 diffuse 和方向；
  - headlight 的 ambient、diffuse；
  - 杯子材质的 rgba；
  - 桌面材质的 rgba，或 builtin 纹理；
  - `side_camera` 的 pos、quat 增量，以及 fovy。

  wrist 相机定义在机器人 MJCF 里，首版不改。其他字段一律拒绝。
- **物理子树指纹（D1 的落地）**：去掉渲染字段后，对物理相关部分做规范化哈希。白名单里的视觉编辑必须让该指纹保持不变，任一物理字段的修改必须让它改变；这两点都要有测试证明。rollout 仍然按现在的方式，用 nominal 安装文件校验接触激活回执，再额外核对“变体的物理指纹 == nominal 的物理指纹”，不相等就拒绝。现有回执的键不变。
- **rollout 接入**：`act_rollout_parallel` 和 `act_rollout_native` 增加 `--scene-variant <json>` 参数。变体 MJCF 写到运行自己的 owned 目录，栈启动时从这里加载。变体是逻辑参数，所以变体描述和 realized 哈希都写进 `run.json` 和每个 `episode.json`，并进入运行身份。
- **分桶**（TRAIN-007A，prefix 50，N=8，rollout_validation 28 个点 × 1 次）：
  - nominal 复测 1 桶；
  - 光照：强度 0.5×、0.75×、1.25×、1.5×，方向 ±20°，关闭 headlight，共 7 桶；
  - side 相机：平移 ±5 mm（x、y、z 各一桶）、旋转 ±1°（两桶）、fovy ±3%（两桶），共 7 桶；
  - 杯色：3 档；
  - 桌面：2 档。

  每桶报告成功率和 Wilson 95% 区间，并与 nominal 的 27/28 对比。
- **杯–桌摩擦桶暂缓**：按 D1，动力学变化需要重新校准接触策略，R0 首版只做视觉。这一项记入待办。
- **磁盘**：每桶的 bag 在提取完指标后删除（已预授权，并记日志），只保留 json 和 jsonl。

## 1. 自原草案以来改变的事实

| 变化 | 依据 | 对随机化设计的影响 |
|---|---|---|
| 采集与训练改用 **side + wrist** 相机，不再用 head 相机。side 相机固定在世界坐标系：`act/scene_side_wrist.xml`，`side_camera`，fovy 62。wrist 相机在 `act/so101_side_wrist.xml:143`，fovy 90。 | rig `side-wrist`，TRAIN-005/006/007 | 原审查 P0-3（head 支架外参牵动碰撞体）和 P1-1（Head Search 门禁）**不再是首版前提**。side 相机外参扰动只需同步光学 frame。若 side 相机有支架几何，需另行核对。 |
| ACT 场景中的杯子自由关节已显式覆盖为 `damping 0.01`、`frictionloss 0`、`armature 0`（`act/scene_side_wrist.xml:38`、`act/scene.xml:33`）。 | 源码 | 原审查 P0-1（杯子继承机械臂 armature/frictionloss）**在 ACT 场景已解决**。`assets/mujoco/scene.xml` 和 `head_search_scene.xml` 仍是旧值，它们不是 ACT 采集入口。 |
| Teacher 用 `task_camera` 加感知来定位杯子，然后规划执行。 | 采集链路 | 光照、材质、背景随机化**会同时改变 Teacher 的感知输入**，这是视觉随机化最大的耦合点，见 §3 D2。 |
| TRAIN-007A 在 prefix 50 下 4 个标准点都是 5/5（CP-3776）。TRAIN-006 的失败主因是策略不按杯子远近决定伸臂深度。当时每个位置只有 1 条确定性示教，没有恢复样本。 | ledger CP-3774..3776 | 泛化的短板不只在外观。**示教轨迹多样性**（同位置多条、起始姿态变化、带扰动的恢复示教）原草案没有覆盖，应作为独立随机化轴，见 R3。 |
| rollout 中出现过杯子被挤飞、仿真发散（CP-3774 ens-t1、TRAIN-007A p10-t1）。 | ledger | 动力学随机化会扩大接触参数范围，**必须先有仿真发散检测**，发散要判 `SIM_INSTABILITY` / INVALID，不能算策略失败。antzb goal10 第 2 项正在查根因。 |
| 并行 rollout（容器分片，每台主机一个策略服务）已打通：N=1 与原生等价，N=2/4/6 的全部 rollout 成功，选定 N 的时序门结论待出。 | `2026-10-22-so101-act-parallel-rollout-design.md`，T4 | 原草案要求“每个条件桶至少 50 个场景”的评估，现在可以承受：单 episode 约 200 s，N=6 时 50 个场景约 30 min。 |
| 采集吞吐约 141 场景/小时（staged 加 mount 模式）。每条约 0.6 GB 原始 bag，导出后约 50 MB。 | 采集实测 | 原草案按 60 s × 1.1 GB 估算偏大。1000 条约 7 小时采集、约 600 GB 原始证据，需要按批次封存并清理 bag。 |
| 场景身份、frozen inputs、密封根、`BUILD-COMMIT` 和 mount 树已经成体系。逻辑参数受 sha 绑定，运行参数不受约束（memory：runtime vs logic params）。 | 现行规则 | 随机化 profile 和每个 episode 的实际参数都是**逻辑参数**：要冻结、要做哈希、要写进 frozen inputs。 |

## 2. 原审查各条的现状

| 条目 | 现状 |
|---|---|
| P0-1 杯子 armature/frictionloss | ACT 场景已解决。剩余工作：确认 `damping 0.01` 的来由，并用落体/滑移测试留证。 |
| P0-2 指纹与资格链冲突 | **仍然成立。** 接触策略 `contact_calibration.yaml` 按 `scene_sha256` 锁定，每个 episode 换一个模型就会出现 `POLICY_FINGERPRINT_MISMATCH`。见 D1。 |
| P0-3 head 外参牵动碰撞体 | 改为 side 相机，问题弱化，但要核对 side 相机有没有碰撞几何。 |
| P1-1 Head Search 门禁 | 不在 side-wrist 首版范围。换成 Teacher 感知门禁问题，见 D2。 |
| P1-2 基线不是 ACT 场景 | 本文已改用 `act/scene_side_wrist.xml` 作为 nominal。 |
| P1-3 光照不完整 | 仍然成立。`scene_side_wrist.xml` 只有 `key_light`，加上 MuJoCo 默认 headlight。profile 必须显式列出所有光源，并说明扰动的是哪个分量。 |
| P1-4 接触对覆盖 | 仍然成立。夹爪指垫有两组碰撞体，组合摩擦取 max 规则；`noslip_iterations` 也有影响。 |
| P1-5 延迟/偏置与 JTC 闭环 | 仍然成立。另外，T0b 证明 goal 接受的时序很敏感，动力学延迟注入必须放在 plant 侧，不能动控制接口的时序。 |
| P1-6 阶段 E 预算矛盾 | 按 §4 R5 重算。 |
| P1-7 rollout 场景数改变合同 | 并行 rollout 让它变得可行。仍需显式的合同修订条款。 |
| P2-1 内参实现路径 | 仍然成立。CameraPlugin 只读 `fovy`，独立的 fx/fy、主点、畸变要先做插件和投影测试。 |

## 3. 需要人工决定的事项

- **D1 资格覆盖范围**（P0-2）。推荐：接触策略的批准对象改成“nominal 加一个 profile 包络”，并在每个 episode 记录 realized 模型哈希。
  - 视觉类随机化不改动力学，可沿用 nominal 的接触校准：只在指纹里排除纯渲染字段（光照、材质、纹理、相机）。这需要指纹按“物理相关子树”计算。
  - 动力学类随机化需要重新校准，或者另批一个 profile。
- **D2 视觉随机化下的 Teacher 感知。**
  - 方案 a（推荐）：随机化 episode 中，Teacher 用**特权真值杯位**规划，来源记为 `teacher_source: privileged_pose`。ACT 只看随机化后的 side/wrist 图像。这样 Teacher 的成功率不受外观影响，采集分布也不会偏向检测器擅长的外观。
  - 方案 b：Teacher 仍用 `task_camera` 感知。这会同时检验感知的鲁棒性，但 Teacher 失败会和随机化难度混在一起。
  - 方案 a 改变了“相机 Teacher”的原则，需要人工批准，并在数据中显式标记来源。
- **D3 首版范围。** 推荐顺序：先做仅评估的敏感性探测（R0），再做视觉（R2）和示教多样性（R3），动力学（R4）放在实机标定之后。不推荐一开始就做组合随机化。

## 4. 更新后的分期方案

| 阶段 | 内容 | 放行证据 |
|---|---|---|
| **R0 评估基线与敏感性探测（不采集、不训练）** | ① 用 TRAIN-007A 在 prefix 50 下跑 held-out 的 rollout_validation/test（todo #5）。② **只在评估时扰动**：同一模型，单因素地改变光照强度/方位、side 相机光学 frame（±5 mm / ±1°）、fovy ±3%、杯色（3 档）、桌面纹理（2 档）、杯–桌摩擦 0.8/1.2×。每个桶 20–50 个场景，用并行 rollout 跑。 | 每个因素的成功率曲线及二项置信区间，得到“模型对哪个因素最脆弱”的排序，用来决定 R2–R4 的轴和范围，避免盲目扩大范围。 |
| **R1 SceneRealizer 基础设施** | profile → 每个 episode 的 MJCF 变体，走 XML 编译路径，FULL_RESTART，在分片里一个 episode 一次。还包括 AppliedSceneManifest（请求值、生效值、realized 模型哈希、种子）、按物理子树计算的指纹（D1）、frozen inputs 绑定 profile 哈希、`SIM_INSTABILITY` 检测（杯速度或穿透超过阈值时判 INVALID）。 | fixture 测试；同种子重建得到相同 realized 哈希；视觉变体的物理子树哈希不变；新图像读回能证明变化真的生效；单因素读回；nominal 能恢复。 |
| **R2 视觉随机化采集** | 光照（所有光源，包括 headlight 的强度、方位和色偏档位）、桌面纹理库（按身份划分 split）、杯色和反光档位（排除透明和镜面）、side 光学 frame 小扰动、fovy ±3%、wrist 光学 frame ±2 mm / ±1°、曝光/白平衡后处理（训练侧增强另记）。范围由 R0 的敏感性排序确定。 | 约 100 条候选的链路预试；每个桶有成功率和失败分桶；split 不泄漏。 |
| **R3 示教多样性**（新增） | ① 同一杯位采 k=2–3 条示教，起始关节姿态在安全范围内随机。② **噪声注入加恢复示教**（DART 思路）：Teacher 执行时在关节目标上叠加有界低频噪声，**动作标签记录 Teacher 的纠正目标而不是加噪后的指令**，让 ACT 学到偏离后如何回来。③ 杯位继续在可达域内分层采样（复用 boundary sampling 和 reach 栈）。 | 和 TRAIN-007A 等量的数据对照：标准点、held-out、R0 扰动集上的成功率；最大开环长度缩短后（prefix 10/25）成功率的变化，用来量化闭环纠错能力。 |
| **R4 动力学随机化**（实机标定之后） | 接触对摩擦（按 geom 组和 max 规则）、杯质量与惯量联动、关节阻尼和干摩擦、执行器 kp/kv 联动、plant 侧延迟与偏置队列（reset 时清空）。必须先完成 R1 的 `SIM_INSTABILITY` 检测和接触策略的重新校准（D1）。 | 单因素边界试验；扰动引起的控制 abort 单独分桶；停止和 reset 不残留旧命令。 |
| **R5 训练对照** | 从混合池按桶抽等量子集，对比 nominal / +R2 / +R3 / +R2+R3（R4 之后再加入）。学习曲线 250/500/1000。在实测吞吐下，1000 条约 7 小时采集、约 600 GB 原始 bag，必须按批封存后清理 bag，导出数据约 50 GB。 | 统一的 held-out 和扰动评估集，二项置信区间，按桶报告，防止总分掩盖某个桶退化。 |

## 5. 保留不变的原则（来自原草案和原审查）

- **动作标签** = Teacher 或策略在控制接口发出的、已被接受的 reference，不是加了扰动的 plant 输入。
- **随机化参数只写审计侧**，不进入 ACT observation。
- **split 按场景族、资产身份和相机 profile 分组**，同一轨迹的变体留在同一个 split。
- **配额不足报告 `QUOTA_UNSATISFIED`**，不复制数据、不放宽阈值、不缩小范围来凑数。
- **Recorder/QC 不能反向控制 Teacher**（10-05 分离修订）。
- **不提前用“是否抓放成功”去筛掉难样本。**

## 6. 与现有工作的依赖

- **todo #5**：held-out 场景评估，即 R0 的①。
- **并行 rollout T4/T5**：R0 和 R5 的评估都依赖它。
- **mount 树迁移设计**（2026-10-23，另文）：SceneRealizer 要在 mount 模式的分片中运行。
- **antzb goal10 第 2 项**：杯子炸飞的根因，是 R1 中 `SIM_INSTABILITY` 检测的输入。

## 7. 下一步（需要人工确认后才执行）

1. 人工决定 D1、D2、D3。
2. R0 只需要已有能力（并行 rollout 加评估时扰动），可以最先做。它需要一个“评估时场景变体”的最小实现，可以是 R1 的子集：只做视觉扰动和杯–桌摩擦，并且只用于评估。
3. 拿到 R0 的敏感性排序后，冻结 R2/R3 的首版参数和预算，再写实施计划。

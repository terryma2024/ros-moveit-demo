# SO-101 MuJoCo ROS 2 迁移实验总结

本文按实验编号汇总 `so101-mujoco-ros2-migration-experiment-ledger.md` 中的全部唯一实验引用，每个实验只保留“尝试”和“一句话结论”，详细证据链、哈希、命令及 checkpoint 仍以原 ledger 为准。

## 统计与口径

- 原 ledger 共出现 166 个唯一实验编号，范围为 `EXP-001`～`EXP-168`。
- `EXP-029`、`EXP-112` 在 ledger 中完全缺号，因此不创建虚构记录。
- `EXP-065`、`EXP-067` 被预留但未执行；`EXP-110` 只有 `RUNNING` 登记而没有终态；`EXP-111` 仅被后文引用而没有独立记录。
- `EXP-153`～`EXP-167` 的结果记录在 Task 15 批次终态中，本文拆回各实验编号展示。
- `VALID` 表示实验取证有效，不等于结果成功；`INVALID` 表示该次运行不能用于产品行为结论。

## EXP-001～EXP-047：依赖、模型、观测、ResetWorld 与基础执行

| 实验 | 尝试 | 一句话结论 |
|---|---|---|
| EXP-001 | 核验 apt `mujoco_ros2_control` 0.0.3 的包、前缀、哈希和服务接口。 | `VALID`：安装依赖与固定契约完全匹配。 |
| EXP-002 | 运行未校准独立场景十秒，检查状态有限性和杯子静止性。 | `INVALID`：状态有限但杯子位移和速度超门限，而且运行前未登记。 |
| EXP-003 | 记录完整自由关节状态，判断杯速异常是否只是竖直接触残差。 | `INVALID`：残差主要是水平漂移，原假设被否定。 |
| EXP-004 | 仅给杯子自由关节增加 `0.01` 被动阻尼。 | `INVALID`：位移和末速度仍高于静止门限。 |
| EXP-005 | 将杯子自由关节阻尼提高到 `0.1`。 | `INVALID`：位移通过，但瞬时末速度仍超限。 |
| EXP-006 | 用最后两秒的位姿包络和有限差分速度区分求解器 qvel 残差。 | `INVALID`：净速度很小，但位姿包络仍超过门限。 |
| EXP-007 | 将杯子自由关节阻尼提高到 `1.0`。 | `VALID`：十秒有限性、位移、包络和净速度全部通过。 |
| EXP-008 | 在隔离 ROS domain 启动 MuJoCo、控制器和原子证据插件。 | `VALID`：三个控制器、关节状态、时钟和原子场景证据均正常。 |
| EXP-009 | 用 `MujocoWorldObserver` 接收真实插件消息并验证 session/freshness。 | `INVALID`：十秒内没有接受到快照，尚不能区分 discovery、QoS 或转换问题。 |
| EXP-010 | 增加回调拒绝计数和原因，诊断 EXP-009。 | `INVALID`：问题未复现且观察器直接通过，未证明系统性拒绝。 |
| EXP-011 | 在五个全新 domain 中复验观察器发现边界。 | `INVALID`：shell `nounset` 破坏 ROS 环境，测试尚未进入观察器逻辑。 |
| EXP-012 | 修正 ROS 环境和无 daemon 清理后再做五次新栈复验。 | `VALID`：五次观察器测试全部通过且每个 domain 清理干净。 |
| EXP-013 | 连续执行两次事务式 `task_start` reset。 | `INVALID`：暂停成功，但严格停用控制器在 reset 前超时。 |
| EXP-014 | 在暂停状态推进一个 `StepSimulation`，尝试完成严格控制器切换。 | `INVALID`：严格停用仍超时，未产生 reset receipt。 |
| EXP-015 | 不等待不可靠的 switch future，改轮询 `list_controllers`。 | `INVALID`：观察器十秒未就绪，修正后的切换路径未真正执行。 |
| EXP-016 | 分开统计 publisher、原始 callback 和转换拒绝数量。 | `INVALID` 诊断：publisher 存在但 callback 为零，排除了转换拒绝作为首个边界。 |
| EXP-017 | 检查高频 joint callback 是否饿死原子证据 callback。 | `INVALID`：证据与 readiness 实际通过，失败转移到待完成的 controller switch。 |
| EXP-018 | 将观察器、关节状态和服务客户端拆到三个 rclpy node。 | `INVALID`：readiness 通过，但 controller manager 自身严格切换仍超时。 |
| EXP-019 | A/B 比较运行中停用控制器与暂停后停用控制器。 | `VALID`：运行中成功、暂停后超时，证明 pause-first 架构不成立。 |
| EXP-020 | 改为运行中停用、暂停、reset、恢复并激活、再暂停。 | `INVALID`：控制器顺序可行，但原子证据不完整。 |
| EXP-021 | 在每次收敛快照前增加一次 progress。 | `INVALID`：仍缺完整物理证据，只能继续诊断证据交付顺序。 |
| EXP-022 | 只对 `EvidenceStale` 做有界重试。 | `INVALID`：重试/执行器修补无法满足原子 reset 契约，该路线被放弃。 |
| EXP-023 | 使用固定 0.0.3 commit 加 reset hook patch。 | `INVALID`：进入关节收敛硬门失败，不能据此调整容差或顺序。 |
| EXP-024 | 在事务每个服务边界连续记录 callback 和关节位置。 | `VALID` 诊断：关节偏差首次出现在 `StepSimulation(20)`，不是 reset 或陈旧缓存。 |
| EXP-025 | 将暂停步数从 20 恢复为包默认的 5。 | `INVALID`：仍有一个关节超限且最终出现 `EvidenceStale`。 |
| EXP-026 | 离线把 MJCF 位置执行器 `kp` 从 1 提高到 50。 | `INVALID`：`kp=1` 不能解释五步 home 漂移，放弃刚度补丁路线。 |
| EXP-027 | 使用权威 pause hook、reset 发布优先级和单步事务。 | `INVALID`：Python 后置条件拒绝了 schema 合法的 reset step zero。 |
| EXP-028 | 绕开客户端后置循环，直接序列化 `StepSimulation(1)` 后的消息。 | `INVALID`：单步仍不能提供要求的 reset 后暂停原子观察。 |
| EXP-030 | reset 前订阅并序列化全部原子消息和 joint callback。 | `INVALID`：暂停态原子对象证据与独立关节/控制器前提不同时成立。 |
| EXP-031 | 使用专门的 post-pause snapshot hook 执行双 reset。 | `VALID` 失败：step-zero epoch 正确，但独立关节收敛门失败。 |
| EXP-032 | 追踪 reset 边界 callback，判断关节样本是否来自 reset 之前。 | `VALID` 诊断：重新暂停前没有收到 reset 后关节反馈，定位到 freshness 边界。 |
| EXP-033 | 在有界恢复阶段等待一个 reset 后 joint callback 再暂停。 | `VALID`：两次 reset、step zero、关节收敛和非法 keyframe 契约全部通过。 |
| EXP-034 | 只允许完整且有限的六关节消息推进 freshness 计数。 | `VALID`：关闭陈旧/不完整向量漏洞后完整 reset 契约再次通过。 |
| EXP-035 | 首次用独立 headless launch 组合 MuJoCo、MoveIt、Planning Scene 和 dry-run。 | `INVALID`：provenance、fail-fast、summary 和管道退出码取证均有缺陷。 |
| EXP-036 | 修复四项测量缺陷后重跑 dry-run。 | `VALID` 失败：MoveIt 因 joint 1 缺少加速度限制而无法时间参数化。 |
| EXP-037 | 注入固定的六关节 dynamics limits。 | `VALID` 失败：启动 readiness 只采样一次，未等待 gripper controller 激活。 |
| EXP-038 | 在原 deadline 内轮询所有必需 controller 为 active。 | `VALID`：完整 headless dry-run 规划成功且没有发送执行目标。 |
| EXP-039 | 在同一配置下执行非抓取 `task12_safe` 轨迹。 | `VALID` 失败：规划期间 joint 2 漂移超过 `0.01 rad` 起点容差。 |
| EXP-040 | 对齐记录 plan request、plan response 和 execute 前的关节状态。 | `VALID` 诊断：轨迹起点在请求时正确，但规划期间物理继续漂移而变陈旧。 |
| EXP-041 | 记录完整 controller reference、feedback、error 和 output。 | `VALID` 诊断：参考和输出保持不变而反馈漂移，问题不在目标命令变化。 |
| EXP-042 | 在规划前权威暂停，规划完成后立即恢复并执行。 | `INVALID`：环境/取证污染发生在产品行为前，本次不计入结论。 |
| EXP-043 | 修正 shell 和 graph 取证后复验 freeze-plan-resume。 | `INVALID`：控制器报告成功，但外部六关节记录器未落盘，不能判定最终收敛。 |
| EXP-044 | 修正记录器 flush 顺序后再次复验同一策略。 | `VALID` 失败：恢复后约 1.13 ms 即超起点容差，freeze-plan-resume 不具确定性。 |
| EXP-045 | 不规划不执行，只等待固定 controller reference 下的稳定窗口。 | `VALID` 失败：30 秒内没有满足 0.20 秒稳定窗口，禁止实现有界重规划。 |
| EXP-046 | 仅替换为校准 SO-101 的 damping、frictionloss、armature 和 actuator 参数。 | `VALID`：同一稳定窗口判据通过，确认漂移来自未校准动力学。 |
| EXP-047 | 在校准动力学下重新执行 `task12_safe`。 | `VALID`：MoveIt、控制器、六关节收敛和 MuJoCo 运动证据全部通过。 |

## EXP-048～EXP-086：接触采样、视觉几何、规划路径与首次物理微抬升

| 实验 | 尝试 | 一句话结论 |
|---|---|---|
| EXP-048 | 用控制器动作采集无接触、单侧、双侧、过压、滑移和稳定保持七类样本。 | `INVALID`：topic readiness 调用不受支持，未获得可用接触矩阵。 |
| EXP-049 | 将不支持的 topic readiness 命令替换为受支持形式。 | `INVALID`：外部 CLI readiness 仍使测量契约不可靠。 |
| EXP-050 | 改为 collector 内部等待 action server 和原子 callback。 | `INVALID`：测量链仍未满足预注册条件，按停止门暂停。 |
| EXP-051 | 将证据订阅 QoS 改成 sensor-data Best Effort。 | `INVALID`：单独改 QoS 仍未形成有效七类样本矩阵。 |
| EXP-052 | 组合已经批准的 readiness 与 QoS 修正。 | `INVALID`：wrapper 组合文本仍不可靠，未执行有效物理比较。 |
| EXP-053 | 用干净直接 wrapper 重新采集七类样本。 | `VALID` 失败：目标动作没有产生完整七类接触分布，不能据此定阈值。 |
| EXP-054 | 用 MuJoCo FK 求得的确定性夹取终点替换错误坐标目标。 | `VALID` 失败：路径横扫杯子且没有形成稳定双侧接触。 |
| EXP-055 | 先预开夹爪、移到杯子上方，再下降到相同终点。 | `VALID` 失败：杯子位移/力安全边界被触发，仍无稳定保持。 |
| EXP-056 | 在 GUI 中原样回放 EXP-055 路径。 | `INVALID`：画面没有完整机械臂，无法做策略视觉判断。 |
| EXP-057 | 按 Gazebo 参考重建机器人、基座、杯子和桌面的 MJCF visual/collision。 | `VALID` 静态阶段：资源与结构就位，但运行时机器人仍显示为球体。 |
| EXP-058 | 给 robot visual/collision 默认 geom 显式增加 `type="mesh"`。 | `VALID`：ai-station mesh 正确显示并用于配对碰撞几何，球体问题消失。 |
| EXP-059 | 对生产 collision 做启用/禁用 A/B，定位 home 小幅抖动。 | `VALID`：发现并修复 base/shoulder 自碰撞，校准 home 可稳定保持。 |
| EXP-060 | 从稳定 home 规划执行到 Gazebo DESCEND 对应的 TCP 位姿。 | `VALID`：MoveIt 和 ros2_control 成功到达安全 TCP 目标。 |
| EXP-061 | 直接执行 full-pose pre-grasp 与轴向下降。 | `VALID` 失败：姿态约束路径无法可靠规划到目标。 |
| EXP-062 | 在显式 MoveIt start RobotState 中补入预开的 q6。 | `VALID` 失败：完整 q1～q6 起点仍未解决 full-pose 规划。 |
| EXP-063 | pre-grasp 只用姿态 goal，下降阶段再加姿态 path constraint。 | `VALID` 失败：约束分阶段仍不能形成可用路径。 |
| EXP-064 | 在 0～40 mm 的有限竖直偏移网格上搜索 full-pose 候选。 | `VALID` 诊断：结果具有随机性且没有可稳定采用的生产候选。 |
| EXP-065 | 预留给满足 EXP-064 条件后的 plan-only 验证。 | `NOT RUN`：EXP-064 的前置门未满足，因此没有登记或执行本实验。 |
| EXP-066 | A/B 比较三轴姿态约束与相同位置的 position-only goal。 | `VALID` 诊断：位置目标可行而姿态约束不稳定，问题集中在 5-DoF IK 契约。 |
| EXP-067 | 预留给唯一生产 request 修复后的验证。 | `NOT RUN`：没有推导出唯一可证明的修复，因此本实验未执行。 |
| EXP-068 | 在新栈重复 full-pose 与 position-only 的只读对比。 | `VALID` 诊断：进一步确认 5-DoF KDL 与独立三轴姿态约束随机不兼容。 |
| EXP-069 | 在 RViz 显示 direct-TCP full-pose 规划候选。 | `VALID` 视觉诊断：路径可偶发显示，但该路线被明确拒绝用于生产。 |
| EXP-070 | 改用 Gazebo 派生的分段 joint waypoint ladder 做 plan-only。 | `VALID`：分段 waypoint 路线可以规划，替代 direct-TCP 路线。 |
| EXP-071 | 用正式 `staged_approach` 规划 PREOPEN、10 段上方移动和 5 段下降。 | `VALID`：正式分段规划到达 Close-ready，尚未执行物理动作。 |
| EXP-072 | 在未暂停物理下预开夹爪并执行全部 15 段 approach。 | `VALID`：机械臂物理到达 Close-ready，杯子未被提前触碰。 |
| EXP-073 | 执行 nominal close 后直接进入首个 LIFT waypoint。 | `VALID` 失败：缺少 seating preload，夹爪没有建立可承载抓取。 |
| EXP-074 | 直接用旧 ResetWorld 路线恢复场景。 | `INVALID`：客户端出现不安全的 reset 成功假阳性，暂停后续抓取。 |
| EXP-075 | 修复 fail-closed 事务并连续验证同栈 ResetWorld。 | `VALID`：正式 reset transaction 可重复恢复物理与视觉初态。 |
| EXP-076 | ResetWorld 后重建 Planning Scene 并重新执行 staged approach。 | `VALID`：标准 fork 栈重新回到 Close-ready。 |
| EXP-077 | nominal close 后增加 `0.006 rad` seating preload。 | `VALID`：形成稳定双侧杯壁夹持，不需要 arm motion 或仿真约束。 |
| EXP-078 | 保持该预载执行 2 mm 微抬升。 | `VALID` 失败：夹爪沿杯壁滑移，杯子没有可靠抬起。 |
| EXP-079 | 再增加一次 `0.006 rad` q6 预载。 | `VALID`：双侧法向力提高且仍在安全边界内。 |
| EXP-080 | 在更强预载下再执行 2 mm 抬升。 | `VALID` 失败：杯子仍保持桌面支撑。 |
| EXP-081 | 将本次 arm 增量改为 3 mm。 | `VALID`：首次无隐藏约束地把杯子实际抬高约 2.097 mm。 |
| EXP-082 | 从已抬起状态执行首个正式 LIFT waypoint。 | `VALID` 前置失败：长时间等待期间杯子已缓慢滑落。 |
| EXP-083 | 将 Gazebo 杯子/TPU 摩擦语义映射到 MuJoCo 并从 reset 重放。 | `VALID` 行为未完成：ResetWorld 可见恢复，但原子 reset 证据发布失败。 |
| EXP-084 | 在 fork reset callback 后主动发布暂停态 step-zero snapshot。 | `INVALID`：实现和视觉通过，但调试过程污染了冻结的 epoch 基线。 |
| EXP-085 | 在全新栈验证精确 `0→1→2` reset receipt。 | `INVALID`：事务本身通过，但测试错误地要求 service return 时 joint sample 已刷新。 |
| EXP-086 | 修正测试时序语义后再次从干净新栈验证。 | `VALID`：双 ResetWorld、关节/控制器收敛、非法 keyframe 和视觉恢复全部通过。 |

## EXP-087～EXP-135：物理抓取、Noslip、运输、放置与首次完整成功

| 实验 | 尝试 | 一句话结论 |
|---|---|---|
| EXP-087 | 在摩擦 parity 模型下重放第一次预载和 2 mm 抬升。 | `VALID` 失败：预载成功，但第一次 2 mm 抬升没有带起杯子。 |
| EXP-088 | 增加最后允许的 `0.006 rad` 预载后再抬升 2 mm。 | `VALID` 失败：额外预载成功，但杯子仍基本没有抬起。 |
| EXP-089 | 保持预载，仅执行最后 3 mm arm 增量。 | `VALID` 失败：arm 到位，但杯子仍有桌面支撑，纯摩擦路线被终止。 |
| EXP-090 | 给 13 个 TPU pad collision 增加直接格式接触刚度/阻尼。 | `INVALID`：调用遗漏 `--execute`，CLI 在动作前安全拒绝。 |
| EXP-091 | 补上执行确认后重新搜索接触。 | `VALID`：到达 Close-ready 并产生安全右侧接触，但尚未形成双侧接触。 |
| EXP-092 | 允许短暂单侧 seating，再继续有界 q6 搜索。 | `VALID`：形成持续两秒且每侧至少约 0.167 N 的双侧接触。 |
| EXP-093 | 在双侧接触下执行第一段 2 mm arm 抬升。 | `VALID` 失败：arm 执行成功，但杯子仍在桌面并出现瞬态接触丢失。 |
| EXP-094 | 用 20 µrad 步长逐步提高每侧夹紧力到 0.5 N。 | `INVALID`：目标错误地从受约束实际 q6 重算，形成不收敛微爬行。 |
| EXP-095 | 改为从上一条 command reference 累加 20 µrad。 | `INVALID`：达到力目标，但 hold 又切回实际 q6 并卸载预紧力。 |
| EXP-096 | hold 始终保持最终累计 command reference。 | `VALID`：每侧约 0.51 N 的动态预载持续两秒。 |
| EXP-097 | 在 0.5 N 预载下执行下一段 2 mm 抬升。 | `VALID` 失败：双侧接触保持，但杯子切向滑动且没有离桌。 |
| EXP-098 | 将双侧法向力提高到每侧约 1 N 并保持。 | `VALID`：1 N 双侧预载在安全边界内稳定。 |
| EXP-099 | 用新鲜 collision-aware world-Z 目标抬升 2 mm。 | `VALID` 失败：1 N 预载仍发生滑移，因此停止继续加力。 |
| EXP-100 | 仅把 MuJoCo `noslip_iterations` 从 0 改为 10 并启动新栈。 | `VALID`：模型、ResetWorld 和 staged approach 均正常到达 Close-ready。 |
| EXP-101 | 在 Noslip 模型中重新建立约 0.5 N 双侧预载。 | `VALID`：预载稳定保持，允许进入物理抬升。 |
| EXP-102 | 在 Noslip 下执行已验证的第一段 2 mm arm target。 | `VALID`：首次稳定完成 Noslip 物理微抬升。 |
| EXP-103 | 不发送动作，观察已抬起杯子十秒。 | `VALID`：杯子离桌、双侧接触并在十秒内保持稳定。 |
| EXP-104 | 只执行正式 LIFT waypoint 1。 | `VALID`：杯子继续上升并保持双侧接触。 |
| EXP-105 | 顺序执行剩余四个 LIFT waypoint。 | `VALID`：杯子被提升到安全高度且侧向偏移受控。 |
| EXP-106 | 执行五个 MOVE_ABOVE_PLACE 运输 waypoint。 | `VALID` 失败：MoveIt 执行监视器被瞬时单帧接触丢失触发。 |
| EXP-107 | 不动作观察运输终点两秒。 | `VALID`：终点实际稳定，证明 EXP-106 属于监视器瞬态误报。 |
| EXP-108 | 给双侧接触丢失增加 50 ms grace 并执行三段下降。 | `VALID` 失败：下降物理完成，但脚本错误地要求开爪前已经桌面支撑。 |
| EXP-109 | 按 Gazebo 语义开爪、撤退、detach/sync 并评估落点。 | `VALID` 失败：杯子已落桌，但 0.0186 N 固定指擦碰被零接触门误拒绝。 |
| EXP-110 | 允许撤退过程存在低于 1 N 的固定指残余接触并继续三段 RETREAT。 | `RUNNING/INCOMPLETE`：ledger 只有开始登记，没有独立终态，不能补写结果。 |
| EXP-111 | 后续 checkpoint 将其与 EXP-102～110 一起称为分段结果。 | `UNRECORDED`：ledger 没有独立登记、假设或终态，不能重建该实验。 |
| EXP-113 | 从分段状态调用生产 ResetWorld 客户端。 | `VALID` 失败：十秒内约 930 次 pause snapshot 重试造成服务与 DDS 证据拥塞。 |
| EXP-114 | 将 snapshot retry 限制为每 50 ms 一次并先排空订阅。 | `VALID`：ResetWorld 的 epoch、step zero、关节、杯子、场景和视觉全部通过。 |
| EXP-115 | 把已验证的抓取、抬升、运输、下降、对齐和释放合成一次完整流程。 | `VALID` 失败：remaining-lift gate 仍硬编码旧 reset epoch。 |
| EXP-116 | 从中断的持杯状态执行 ResetWorld 和正式 scene restore。 | `VALID` 失败：物理 reset 成功，但 MoveIt 中陈旧 attached cup 仍存在。 |
| EXP-117 | scene restore 先显式 REMOVE attached cup 再添加 world geometry。 | `VALID` 前置失败：新订阅者无法从已暂停的 sensor QoS 获得当前快照。 |
| EXP-118 | 客户端遇到 stale 时主动发一次幂等 pause snapshot 请求。 | `VALID` 前置失败：测试 wrapper 仍有多余的 reset 前 joint wait。 |
| EXP-119 | 删除 wrapper 的冗余前置 joint wait，直接调用生产客户端。 | `VALID`：新客户端可加入已暂停世界并完整恢复物理和 Planning Scene。 |
| EXP-120 | 修正当前 epoch 常量后重跑完整闭环。 | `VALID` 失败：运输接触监视器再次被单样本丢失触发。 |
| EXP-121 | 从运输失败状态执行 ResetWorld。 | `VALID` 失败：pause 请求后错误接受了队列中的 running frame。 |
| EXP-122 | pause snapshot 请求后只接受 `paused=true` 的新证据。 | `VALID`：有序快照 ResetWorld 和视觉验收通过。 |
| EXP-123 | 在运输阶段加入 50 ms `SustainedConditionGuard`。 | `VALID` 失败：接触误报消失，但运输瞬态力超过 11.60 N 原门限。 |
| EXP-124 | 从运输力失败状态执行未放宽门限的 ResetWorld。 | `VALID`：完整恢复到新 epoch 的 task_start。 |
| EXP-125 | 将运输速度和加速度 scaling 从 0.10 降到 0.05。 | `VALID` 前置失败：运输通过，但下降 stable gate 仍残留旧 epoch 字面量。 |
| EXP-126 | 将下降 gate 改为读取当前 reset epoch。 | `VALID` 前置失败：对齐后仍用陈旧 arm vector 做 handoff 断言。 |
| EXP-127 | 删除过时的预对齐 arm-vector 断言并继续释放撤退。 | `VALID` 失败：释放和撤退完成，但杯子最终位于红圈外。 |
| EXP-128 | 对释放失败后的场景执行完整 ResetWorld。 | `VALID`：物理、控制器、Planning Scene 与 GUI 均恢复。 |
| EXP-129 | 根据测得落地偏移把预释放 Y 补偿从 0.0025 m 改为 0.015 m。 | `VALID` 失败：固定 joint retreat 扫到已释放杯子并把它推出目标区。 |
| EXP-130 | 撤退碰撞失败后再次 ResetWorld。 | `VALID`：恢复到 epoch 8 task_start，允许测试 outcome-first retreat。 |
| EXP-131 | 改为开爪后先径向远离 10 mm，再向上 60 mm。 | `VALID` 前置失败：约 0.003 N 固定指残余接触被零接触门拒绝。 |
| EXP-132 | 允许有界低力残余接触进入径向分离。 | `VALID` 前置失败：MoveIt 因起点的杯子/固定指碰撞拒绝规划。 |
| EXP-133 | 仅在径向分离期间临时允许杯子与固定指的 ACM collision pair。 | `VALID` 诊断：径向/垂直撤退和最终落圈成功，但因从释放后续跑而不算完整闭环。 |
| EXP-134 | 从 EXP-133 终态执行 ResetWorld 与完整 scene restore。 | `VALID`：电子和视觉初态恢复通过，冻结 epoch 9。 |
| EXP-135 | 将可逆 ACM 径向撤退集成进一次不间断完整生命周期。 | `VALID`：首次完整物理 pick-and-place、落圈、scene sync 和视觉证明成功。 |

## EXP-136～EXP-168：生产入口、Clean Shutdown、Teleop 与连续资格测试

| 实验 | 尝试 | 一句话结论 |
|---|---|---|
| EXP-136 | 在生产 runner 验证前执行一次 ResetWorld 和视觉初态检查。 | `VALID`：task_start 物理与视觉状态通过。 |
| EXP-137 | 从继承 zsh 环境直接 source overlay 后运行生产 runner。 | `INVALID`：陈旧 `COLCON_CURRENT_PREFIX` 使 ROS setup 指向错误路径。 |
| EXP-138 | 在隔离 Bash 中把 ament console script 当普通 PATH 命令调用。 | `INVALID`：脚本安装在包的 `lib` 目录，不能裸命令执行。 |
| EXP-139 | 改用正式 `ros2 run so101_mujoco_demo_py ...` 入口。 | `VALID`：安装后的生产 runner 完成物理 pick-and-place 并通过视觉证明。 |
| EXP-140 | 停物理后让 render context 线程销毁 Viewer，并用 tee 捕获退出日志。 | `INVALID`：Ctrl-C 同时终止 tee，无法证明完整 shutdown 和 child exit。 |
| EXP-141 | 重新跑 clean-shutdown patch 验证。 | `INVALID`：overlay 顺序错误，运行的 patch provenance 不可判定。 |
| EXP-142 | 修正 overlay 后验证 fork 侧 context-owner teardown。 | `VALID`：MuJoCo GUI 可以无崩溃地干净退出。 |
| EXP-143 | 在正式 MoveIt 组合中验证 ordered shutdown executable。 | `VALID` 失败：MoveIt 析构阶段仍崩溃，需要线程级回溯。 |
| EXP-144 | 给 move_group 配置 GDB launch prefix。 | `INVALID`：prefix 被拼成一个可执行文件名，GDB 没有启动。 |
| EXP-145 | 修正 prefix 后用 GDB 捕获 shutdown。 | `VALID` 但诊断不充分：GDB 在 SIGINT 停住，未捕获后续 SIGSEGV。 |
| EXP-146 | 让 GDB 透传 SIGINT 后捕获真正 SIGSEGV。 | `VALID` 诊断：崩溃位于 MoveIt/PlanningSceneMonitor 析构链，提出有序停 worker。 |
| EXP-147 | 先停止公开 PlanningSceneMonitor worker，再析构 MoveIt。 | `VALID` 失败：TEM 私有 executor 仍存活，崩溃没有消失。 |
| EXP-148 | 停公开 worker 后先使 ROS context 失效，再析构对象。 | `VALID` 失败：第三方析构缺陷仍可触发，改用进程边界规避。 |
| EXP-149 | 在专用 move_group 完成公开清理后以 code 0 有界退出，避开缺陷析构。 | `VALID`：接受为 Jazzy apt MoveIt/rclcpp 析构缺陷的项目级兼容边界。 |
| EXP-150 | rebase 最新 main 并接入 Teleop 后执行首次 FULL_RESTART 闭环。 | `VALID` 物理诊断：动作成功，但 launch 日志捕获不完整，不能计入资格。 |
| EXP-151 | 用不可变源码和直接 launch 日志重跑 Teleop FULL_RESTART。 | `VALID`：post-rebase Teleop 物理闭环和 clean shutdown 通过。 |
| EXP-152 | Ruff 格式化改变源码哈希后在最终指纹上重跑。 | `VALID`：最终 Ruff-clean 源码下 Teleop 闭环通过，Task 15 得以开始。 |
| EXP-153 | 在 headless FULL_RESTART Batch A 中启动第 1 次资格运行。 | `INVALID`：Viewer camera preset 返回 503，且 runner 错误分类基础设施失败，本批次全部不计。 |
| EXP-154 | 在同一 Batch A runner 中启动第 2 次全新栈运行。 | `INVALID`：与 EXP-153 相同的 headless camera/readiness 污染，不能计数。 |
| EXP-155 | 在同一 Batch A runner 中启动第 3 次全新栈运行。 | `INVALID`：runner 未在首个无效运行后终止，本次也不进入分母。 |
| EXP-156 | 在同一 Batch A runner 中启动第 4 次全新栈运行。 | `INVALID`：launch 还包含 ros2_control child `-2` 退出，不能视为 clean shutdown。 |
| EXP-157 | 在同一 Batch A runner 中启动第 5 次全新栈运行。 | `INVALID`：整个 Batch A 被环境与分类器缺陷污染，五次均作废。 |
| EXP-158 | 修复 runner 后在 domain 175 做第 1 次非 headless FULL_RESTART。 | `VALID`：完整九阶段闭环、落圈、scene sync 和 clean shutdown 成功。 |
| EXP-159 | 在 domain 176 做第 2 次独立 FULL_RESTART。 | `VALID`：相同冻结指纹下第 2 次完整成功。 |
| EXP-160 | 在 domain 177 做第 3 次独立 FULL_RESTART。 | `VALID`：相同冻结指纹下第 3 次完整成功。 |
| EXP-161 | 在 domain 178 做第 4 次独立 FULL_RESTART。 | `VALID`：相同冻结指纹下第 4 次完整成功。 |
| EXP-162 | 在 domain 179 做第 5 次独立 FULL_RESTART。 | `VALID`：相同冻结指纹下第 5 次完整成功，首次取得 FULL_RESTART 五连胜。 |
| EXP-163 | 在共享 domain 180 上先 ResetWorld 到 epoch 1 后执行闭环。 | `VALID`：第一次 RESET_WORLD 生命周期完整成功。 |
| EXP-164 | 不重启栈，ResetWorld 到 epoch 2 后再次执行。 | `VALID`：第二次共享栈闭环成功。 |
| EXP-165 | 不重启栈，ResetWorld 到 epoch 3 后再次执行。 | `VALID`：第三次共享栈闭环成功。 |
| EXP-166 | 不重启栈，ResetWorld 到 epoch 4 后再次执行。 | `VALID`：第四次共享栈闭环成功。 |
| EXP-167 | 不重启栈，ResetWorld 到 epoch 5 后再次执行。 | `VALID`：第五次共享栈闭环成功，RESET_WORLD 也取得独立五连胜。 |
| EXP-168 | 在最终冻结实现上做一次不计数的 CUA FULL_RESTART 视觉复核。 | `VALID`：新截图与物理、Planning Scene 和类型化结果证据一致。 |

## 总体演进结论

整个迁移从“依赖和独立 MJCF 可运行”推进到“ResetWorld 可验证、动力学稳定、真实接触抓取、分段 MoveIt 执行、物理放置、Teleop 接入和两类五连胜资格验证”。关键转折依次是：权威暂停快照替代暂停步进、采用校准 SO-101 动力学、拒绝随机 direct-TCP full-pose 路线、改用 Gazebo 派生 waypoint、引入有界 Noslip 接触求解、修正 outcome-first 撤退、把 ResetWorld 扩展为物理与 Planning Scene 的跨系统事务，以及用独立 FULL_RESTART 与共享 RESET_WORLD 批次分别验证稳定性。

# SO-101 开爪前倾斜：根因与落放策略矩阵

- 记录日期：2026-08-11
- 当前 main：`f31ee7af0179c7107661afbc10ba55ab48ce3cd6`
- 分析对象：`PHY5-G12-CONTROLLED-RELEASE-RETREAT-RUNTIME-001` 及 R0、G1、G3、G8、G11 历史实验
- 生命周期约束：后续物理实验只使用 `RESET_WORLD`，不使用 `FULL_RESTART`
- 资格状态：五次连续成功尚未开始
- 证据分类：本文明确区分 `OBSERVED`、`INFERRED`、`HYPOTHESIS`

## 结论

当前“开爪前倾斜”不是一个单点故障，而是两段累积：

1. 横向搬运时产生第一次明显倾斜。
2. 对位与落座时又被显著放大。

开爪和 +35 mm 撤离不是倾斜起点。G12 已经证明受控撤离能完整清除夹爪接触；下一阶段应冻结该撤离路径，优先修正开爪前的搬运、对位和落座。

C10 不作为杯子倾斜的直接物理根因：杯子真实位姿来自 Gazebo，MoveIt Planning Scene 只保存从 Gazebo 同步得到的碰撞 shadow。C10 更准确的定位是控制与建模缺口，它会让规划在一次运动内部看不到并修正夹内滑转。

当前最可能的物理链路是：

```text
接触载荷不对称
→ 横向搬运产生夹内转动
→ 三轴斜向对位进一步改变两侧载荷
→ 倾斜杯最低侧先碰桌
→ 夹紧状态下继续下降，绕桌面/固定指支点转动
→ 开爪前已倾斜约 18°
→ 撤离成功清除接触，但把杯子推出目标区
```

## G12 阶段定位

下表来自 G12 的 50 Hz Gazebo 物理记录。代码中的 shadow gate 在对应动作执行前采样，因此阶段名已经换算为动作结束边界。指垫深度来自与该姿态最接近的 50 Hz 样本。

| 阶段 | 杯子倾角 | 相邻阶段变化 | moving/fixed 指垫侵入深度 | 桌面接触 | 判断 |
|---|---:|---:|---:|---|---|
| 抓稳后、LIFT 前 | 2.89° | — | 0.969 / 0.376 mm | 无 | 初始抓持已经不完全对称 |
| LIFT 后 | 1.33° | -1.56° | 1.052 / 0.488 mm | 无 | 抬升本身没有恶化 |
| MOVE_ABOVE_PLACE 后 | 8.56° | **+7.23°** | 1.166 / 0.679 mm | 无 | 第一主要倾斜窗口 |
| DESCEND_TO_PLACE 后 | 6.15° | -2.41° | 0.909 / 1.217 mm | 无 | 本次下降稍微扶正，但两侧负载发生互换 |
| 三轴 PLACE_ALIGNMENT 后 | 11.06° | **+4.91°** | 0.475 / 1.277 mm | 无 | 第二倾斜窗口 |
| RELEASE_SEATING 后 | 18.49° | **+7.42°** | 0.850 / 1.356 mm | 有，约 0.506 mm | 最大放大窗口 |
| OPEN_GRIPPER 前 | 17.73° | -0.75° | 双侧接触 | 有 | 开爪前已经严重倾斜 |

### OBSERVED

- G12 横向搬运、三轴对位和最终落座分别增加约 7.23°、4.91° 和 7.42° 倾角。
- moving pad 原本比 fixed pad 压得更深，下降和对位后变成 fixed pad 明显更深。
- 当前对位一次同时执行 X +5.42 mm、Y +5.91 mm、Z -5.26 mm。
- 随后又执行 Z -6.03 mm 落座，最终杯子最低点进入桌面约 0.38 mm。
- q6 在上述阶段保持闭合；G12 的 release preparation 没有触发重新夹紧，`reseated=false`。
- G12 开爪前倾角为 17.73°；开爪及 +35 mm 撤离后杯子变为直立、桌面支撑且无机器人接触，但中心误差达到 15.45 mm。
- G12 从 LIFT 之后开始多次出现 Planning Scene shadow 与 Gazebo 杯子姿态不一致并重同步。

### INFERRED

- “双侧接触=true”只证明两侧都有接触，不能证明两侧法向力、接触高度和抗扭矩能力对称。
- 杯子在双侧指垫之间发生滚动或旋转；左右接触深度的强弱侧互换是这一过程的重要证据。
- 桌面不是早期倾斜起点，但在落座阶段成为放大器：倾斜杯的最低侧先接触桌面，继续下降形成旋转支点。
- MoveIt attached-object shadow 假设杯子与 TCP 刚性连接，不能表示 Gazebo 中实际发生的夹内滑转；重同步只能更新碰撞世界，不能修正物理抓持。该缺口不是向杯子施力的直接来源，但会让控制策略在单段运动中继续沿用刚性假设。

## 杯子位姿来源与 C10 边界

当前策略明确区分 Gazebo 物理真值与 MoveIt 碰撞 shadow：

| 数据或用途 | 当前来源 |
|---|---|
| 杯子真实位置和姿态 | Gazebo `/world/so101_pick_place/pose/info` |
| 杯子倾角 | Gazebo quaternion |
| 杯底离桌间隙 | Gazebo pose 与杯子几何 |
| PLACE_ALIGNMENT 位置误差 | Gazebo 杯子位置减配置目标位置 |
| 最终直立、支撑和区域验收 | Gazebo 物理样本 |
| TCP 位姿 | TF：`world → so101_tcp` |
| MoveIt world/attached collision object | 使用最新 Gazebo pose 写入的 Planning Scene shadow |
| MoveIt 碰撞规划 | Planning Scene shadow |

`RosGazeboLiveBackend.sample()` 直接订阅 Gazebo 的杯子 pose，同时从 TF 读取 TCP pose；它不会从 MoveIt 读取杯子姿态。程序用这组 Gazebo/TF 同时观测值计算倾角、底部间隙、对位误差和最终结果。

MoveIt shadow 的更新链路是：

```text
Gazebo 杯子 pose + TF TCP pose
→ 计算 object_in_tcp
→ 写入 MoveIt attached collision object
→ MoveIt 在下一段规划中把该 shadow 视为与夹爪刚性连接
```

### C10 当前判断

| 维度 | 判断 |
|---|---|
| 作为杯子倾斜的直接物理原因 | 低 |
| 作为无法在单段运动内发现和修正滑转的控制缺口 | 高 |
| 对 PLACE_ALIGNMENT / RELEASE_SEATING 规划的间接影响 | 中 |
| 当前实验优先级 | 低于 XY/Z 解耦与正间隙落座 |

- `healthy_before_sync=false` 表示物理杯子在同步前已经偏离刚性预测；它是滑转结果，不是滑转起点。
- `LIFT`、`MOVE_ABOVE_PLACE` 和 `DESCEND_TO_PLACE` 使用固定关节 waypoint 并直接发送给 arm controller，因此 Planning Scene shadow 不会决定横移轨迹，不能直接解释 G12 横移阶段增加的 7.23°。
- `PLACE_ALIGNMENT` 和 `RELEASE_SEATING` 使用 MoveIt TCP 平移规划，shadow 会参与碰撞检查并可能间接影响所选关节路径；但真正向杯子施力的仍是 Gazebo 中的指垫、惯性、重力和桌面接触。

## 历史实验对照

| 实验 | 关键变量或状态 | 关键结果 | 支持的结论 |
|---|---|---|---|
| R0 | moving-pad 深度仅 0.238 mm | pre-open tilt 0.902 rad | 浅抓持的抗旋转能力不足 |
| G1 | moving-pad 深度提高到约 0.948 mm | pre-open tilt 从 0.902 降至 0.297 rad | 抓持法向载荷会显著影响倾斜 |
| G3 | 微抬升漂移 0.078 mm、全过程双侧接触 | release-start tilt 0.325 rad | 小漂移和双侧接触仍不足以证明抗扭矩稳定 |
| G8 | 降低搬运/下降速度 | DESCEND_TO_PLACE tilt 从 G7 的 0.472 降至 0.127 rad | 搬运动力学是有效控制变量 |
| G11 manual open | 杯底约 2.23 mm、直接开爪 | 最终倾角 12.58°，fixed-finger 接触残留 | 直接开爪不能解决预先倾斜 |
| G11/G12 +35 mm retreat | 受控垂直撤离 | 完整清除接触并使杯子直立，但中心被推出容差区 | 撤离路径有效；故障边界在开爪之前 |

## 原因矩阵

| ID | 可能原因 | 机制 | 现有证据 | 可能性 | 区分实验 |
|---|---|---|---|---|---|
| C1 | 两侧接触负载不对称 | 杯子在两指之间滚动，接触虽双侧但抗扭矩弱 | G12 两侧侵入深度发生强弱侧互换；倾角同步增大 | 很高 | 记录两侧深度差、接触点高度和倾斜方向 |
| C2 | 横向搬运惯性导致夹内滑转 | 加减速产生水平惯性力，杯子质心形成转矩 | G12 横移增加 7.23°；R0/G3 也在空中搬运阶段倾斜 | 高 | 只降低 MOVE_ABOVE_PLACE 加速度 |
| C3 | 三轴斜向对位拖动杯子 | X/Y/Z 同时修正，改变夹持负载方向 | G12 对位增加 4.91°；当前命令包含 -5.26 mm Z | 高 | 改为高处 XY-only，再单独 Z-only |
| C4 | 倾斜杯子被夹紧压向桌面 | 最低侧先碰桌面，桌面反力让杯子绕指垫或桌面支点转动 | 落座增加 7.42°，且出现桌面侵入 | 很高 | 使用正间隙落座，不允许开爪前桌面穿透 |
| C5 | 抓持高度或横向位置偏离质心 | 接触线离杯子质心较远，重力和惯性转矩增大 | 微抬升漂移小只能排除严重抓偏，不能排除接触高度不合适 | 中高 | 小范围测试抓持高度及横向 offset |
| C6 | 固定指和活动指的摩擦/柔顺性不一致 | 一侧更容易滑，另一侧更像旋转支点 | fixed pad 后期侵入持续更深；开爪后曾长期残留 fixed-finger 接触 | 中高 | 对比接触点、摩擦参数及两侧碰撞几何 |
| C7 | 五自由度与 TCP 姿态自由度耦合 | `position_only_ik=True`，平移规划不能严格保持完整 6D 姿态 | 对位/落座使用 0.15 rad 姿态容差；这些阶段明显增斜 | 中高 | 同时记录 TCP roll/pitch 与杯子倾角 |
| C8 | 关节 waypoint 路径改变夹爪受力方向 | 即使终点相同，中间姿态会改变重力相对夹持面的方向 | G8 降速改善下降倾斜 | 中 | 比较各 waypoint 内的倾角峰值 |
| C9 | 仅用 moving-pad 最大深度代表抓持质量 | 单侧标量无法描述两侧力矩平衡 | G1 加深抓持有效，但 G12 仍出现明显左右不均衡 | 高，策略缺口 | 增加左右深度差和接触点高度差指标 |
| C10 | Planning Scene 刚性 shadow 与 Gazebo 夹内滑转不一致 | 不直接向杯子施力，但规划在单段运动内看不到并修正物理滑转 | 杯姿始终来自 Gazebo；`healthy_before_sync=false` 说明偏差在同步前已发生 | 直接原因低；控制缺口高；规划间接影响中 | 保持 Gazebo 杯姿为真值，并记录 TCP/杯姿在每段运动内的相对变化 |
| C11 | RELEASE_PREPARATION 重新夹紧导致倾斜 | 开爪前 reseat 改变负载 | G12 `reseated=false`，倾斜在此前已形成 | 本次低 | 不作为下一个变量 |
| C12 | 开爪动作造成“开爪前倾斜” | 时间标记或观察误判 | G12 开爪前已达 17.73° | 已排除 | 不再优先修改 release q6 |
| C13 | 桌面碰撞是全部倾斜起点 | 杯子先撞桌面才倾斜 | 横移后离桌约 60 mm 时已经 8.56° | 早期已排除 | 桌面只负责后期放大 |
| C14 | RESET_WORLD 初始位姿波动 | 初始杯姿误差向后传播 | 多次 reset pose error 为微米量级 | 低 | 保持 RESET_WORLD |
| C15 | 控制器 path-tolerance 或进程时序 | 跟踪误差或不均匀停顿激发摆动 | 其他轮次出现过 -4，但 G12 控制器成功仍倾斜 | 中低 | 记录实际关节速度与倾角峰值 |

## 可尝试的落放方案矩阵

| 方案 | 做法 | 主要解决 | 收益预期 | 风险或代价 | 优先级 |
|---|---|---|---|---|---:|
| M1 分离 XY 与 Z | 在安全高度只做 XY 对位；稳定后才单独下降 | C3 | 去掉斜向下压产生的耦合转矩 | 小，改动局部 | 1 |
| M2 两阶段正间隙落座 | 先到杯底离桌 3 mm，稳定；再慢速到 1–2 mm，禁止负间隙 | C4 | 防止最低侧先压桌形成支点 | 小到中 | 2 |
| M3 倾角驱动的恢复 | 对位或落座后若倾角上升，先 Z +5 mm 脱离桌面，再恢复或重试 | C3/C4 | 避免把坏姿态继续压到桌面 | 需要定义恢复次数 | 2 |
| M4 降低横移加速度 | 优先只降低 MOVE_ABOVE_PLACE acceleration | C2 | 减少第一段 +7.23° | 时间增加 | 3 |
| M5 增加横移中间 waypoint | 让重力方向与夹持面变化更平滑 | C2/C8 | 降低姿态突变和惯性峰值 | 规划策略改动中等 | 4 |
| M6 调整抓持高度 | 以当前抓点为中心测试上下小偏移，使接触线更接近质心 | C5 | 降低重力转矩 | 需要小规模参数实验 | 4 |
| M7 调整横向抓持 offset | 让 fixed/moving pad 接触深度更均衡 | C1/C5 | 减少杯子向固定指滚动 | 可能降低抓取成功率 | 4 |
| M8 接触不平衡自适应 | 不把双侧稳定作为 fail-close；用左右深度差选择更慢搬运、重新对位或恢复 | C1/C9 | 符合当前接触数据只用于分析和后续调整的约束 | 需补充接触特征 | 4 |

## 推荐实验顺序（仅覆盖 M1–M8）

每轮只改变一个变量，均使用 `RESET_WORLD`。探索实验不计入五次连续成功；当前计划范围到 M8 为止，不扩展 M9 及之后的路线。

| 实验 | 唯一变量 | 关键观察 | 建议判定 |
|---|---|---|---|
| T1 | PLACE_ALIGNMENT 从 XYZ 同步改成 XY-only | 下降结束到对位结束的倾角增量、左右指垫深度差 | 对位不再增加约 5°，且 XY 误差仍不超过 5 mm |
| T2 | 落座改成两阶段、正间隙、低速 Z-only | 对位结束到落座结束倾角、是否发生桌面穿透 | 不允许负间隙；落座不再增加约 7° |
| T3 | 只降低横移 acceleration | LIFT 后到横移后倾角 | 把当前 +7.23° 明显压低 |
| T4 | 抓持高度或横向 offset 小矩阵 | 初始两侧深度差、横移后倾角 | 找到不发生负载侧互换的抓点 |

## 下一实验建议

下一次实际修改只做 T1：把 PLACE_ALIGNMENT 拆成高处 `XY-only` 对位，保持其他策略不变。

理由：

- G12 直接观察到该阶段增加 4.91°。
- 当前命令混合 XY 和下降。
- 修改局部、信息增益高。
- 不需要改变已经验证的开爪、Planning Scene 顺序和 +35 mm 撤离。
- 完成 T1 后，才能干净判断剩余约 7.42° 是否主要来自最终落座压桌。

## 不应改变的边界

- 不使用 `FULL_RESTART`。
- 不把“双侧稳定接触”恢复为 fail-close 门。
- 不放宽 1.3 mm 硬侵入上限。
- 不放宽最终直立、支撑、无夹爪接触、Gazebo/MoveIt detached 和目标区域契约。
- 暂不修改最终 release q6。
- 冻结 G12 已证明的 +35 mm selective-orientation 受控撤离。
- 在策略冻结且出现一个完整候选成功之前，不开始五次连续成功计数。

## 证据索引

- 持久实验账本：`/data/work/ws_moveit/docs/experiments/so101-physical-five-success-v2-experiment-ledger.md`
- G12 最终证据：`/tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/final-outcome-failure.json`
- G12 50 Hz 原始样本：`/tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/diagnostic/samples.jsonl`
- G12 视频：`/tmp/so101-physical-five-success-v2/phy5-g12-controlled-release-retreat-runtime-001/run/diagnostic/gazebo-gui.mp4`

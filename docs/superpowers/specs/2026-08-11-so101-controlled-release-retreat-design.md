# SO-101 受控释放撤离策略

## 目标

让连续抓取策略在杯子落座后，必然经过同一条可观测、可恢复的释放撤离路径：开爪后使用 MoveIt Cartesian 目标沿世界坐标 Z 轴抬升 35 mm，不再直接执行固定关节 `RETREAT` waypoint，也不以旧路径作为静默回退。

## 默认策略

1. 开爪前做一次只规划预检，验证当前位置能够生成 Z +35 mm 的撤离轨迹。
2. 姿态约束只放宽相对 Y 轴：X/Z 为 0.005 rad，Y 为 0.060 rad；位置目标保持世界 Z +35 mm。
3. 执行开爪并采集最新 Gazebo 杯子姿态。
4. 将 `plastic_cup` 从 MoveIt Planning Scene 临时移除，并回读确认它既不在 attached objects，也不在 world objects。
5. 从开爪后的实时关节与 TF 状态重新规划并执行 Z +35 mm 撤离。
6. 使用最新 Gazebo 杯子姿态，将 `plastic_cup` 恢复为 MoveIt world object，再开始最终稳定性与落点判定。

## 失败与恢复

- 场景临时移除以后，无论规划、执行、采样或验证在哪一步失败，都必须在 `finally` 路径恢复杯子 world object。
- 场景恢复必须使用最新可取得的 Gazebo 杯子姿态，并回读 Planning Scene；恢复失败与原始失败同时写入证据。
- Cartesian 预检或执行失败时，本次运行明确失败，不切回固定关节 waypoint。这样不会把不受控动作伪装成策略成功。

## 验证边界

- 单元/契约测试覆盖：预检先于开爪、开爪后场景临时移除、选择性姿态容差、Cartesian 撤离、成功恢复和异常恢复。
- 构建与包级测试通过后，只使用 `RESET_WORLD` 启动下一次完整样本。
- 实跑必须同时证明：夹爪已打开、TCP 世界 Z 增量约 35 mm、杯子不再接触夹爪、Planning Scene 最终仅含 world `plastic_cup`。
- 这项改动只保证释放撤离路径受控且可执行，不宣称解决上游杯子倾斜或中心落点误差。

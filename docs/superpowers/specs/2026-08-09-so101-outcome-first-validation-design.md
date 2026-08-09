# SO-101 Outcome-First Pick-Place Validation Design

- 日期：2026-08-09
- 状态：用户已批准规则变更；本文覆盖旧方案中与逐步严格物理 gate 冲突的部分
- 目标分支：`codex/so101-gazebo-demo-py`
- 最终目标：在 Gazebo 接触物理驱动杯体运动、禁止 forward Gazebo attach 的前提下，找到完整连续 pick-place 策略，并在冻结版本上完成连续五次成功验证

## 1. 决策摘要

验证从“每个 step 必须满足一组接触几何和执行参数门”改为“中间只检查能否继续，最终严格检查任务结果”。

- penetration、q6、局部姿态偏移、接触深度等是候选参数或诊断遥测，不再单独决定中间 step 成败。
- 中间节点只使用结果性条件：杯体是否仍位于可继续执行的空间包络、杯体是否随预期动作产生了物理位移、机械臂/controller 是否稳定、环境是否有效。
- 最终成功只在 `RETREAT` 后重新采样：杯子进入指定位置容差、姿态正确、持续稳定；夹爪已释放并撤离；机械臂稳定；MoveIt world membership 与 Gazebo 状态一致。
- MoveIt Planning Scene attach/detach 保留为 collision-planning shadow；它不能驱动 Gazebo 杯体运动。

## 2. 不变边界

1. 从闭爪到开爪，杯体真实运动只能由 Gazebo 接触物理产生；禁止任何 forward Gazebo attach。
2. Planning Scene shadow 的 attach/detach 生命周期固定，不作为搜索变量。
3. 物理引擎、几何、质量/摩擦、controller/gains、碰撞规则保持冻结。
4. `penetration_target_m` 若参与候选生成，配置目标范围仍为 `[0.0001, 0.001] m`，`0.001 m` 是目标参数上限；观测到的 solver contact depth 仅作诊断，不再作为逐步 acceptance gate。
5. 最终位置、直立姿态、稳定窗口、线速度/角速度阈值保持冻结，不得为了通过实验而放宽。
6. 每次运行必须保留 source/install/runtime provenance、唯一 session/domain/partition/evidence 路径和 exact owned-PID cleanup。

## 3. 两层验证模型

### 3.1 Continuation Gate（中间可推进门）

每个动作完成后只回答：当前状态是否仍允许安全、连续地进入下一动作。

硬失败仅包括：

- 规划或执行失败，下一动作无法执行；
- controller/arm 未收敛或出现非有限状态；
- 杯体没有发生与命令一致的物理位移，或已离开该节点批准的可恢复位置包络；
- 杯体已经掉落、飞出工作区或处于无法继续搬运/放置的状态；
- RESET_WORLD、进程所有权、domain/partition、scene membership 等环境合同无效；
- 检测到 Gazebo forward attach 或其他绕过接触物理的作弊路径。

以下信息必须记录，但单独出现时不得淘汰候选：

- bilateral/single-side contact；
- contact depth / penetration；
- q6 target、feedback、velocity；
- 中间杯体姿态误差；
- TCP 与 cup 的局部偏差；
- Planning Scene shadow divergence，只要仍在批准的碰撞规划一致性包络内。

### 3.2 Final Outcome Gate（最终结果门）

完整动作序列必须不中断执行到 `RETREAT`。随后建立新的 final epoch，重新采样并同时满足：

- 杯体中心在批准的目标位置容差内；
- 杯体姿态在批准的直立容差内；
- 固定窗口内位置、姿态、线速度和角速度持续稳定；
- 杯体由预期支撑面承托，且无手指残留接触；
- Gazebo attachment 为 detached；MoveIt Planning Scene 中对象已恢复 world membership；
- 夹爪释放、机械臂撤离且关节状态稳定。

预撤离的 `WAIT_RELEASE_SETTLE` 或 `VALIDATE_FINAL_PLACEMENT` 只能作为遥测，不能替代 post-retreat final outcome。

## 4. 连续动作策略

- 正常实验执行完整线性路径，不在 MICRO_LIFT 成功后人为停止并把它当作任务成功。
- `stop_after` 只用于定位“无法继续”的最早失败边界，不用于最终候选排名。
- 候选评分首先看最终是否通过 Final Outcome Gate；通过者再按最终位置、姿态、稳定性、机械臂稳定余量排序。
- 中间遥测用于解释失败和生成下一个候选，不作为结果购物的过滤器。

## 5. 搜索范围

优先搜索直接影响连续物理结果的 motion 参数：grasp TCP translation/orientation、gripper close/preload/release、micro-lift、carry/place/release/retreat pose 与执行时序。所有范围必须来自已批准配置或登记边界；未登记范围保持冻结。

初始搜索采用 RESET_WORLD 加速，同一候选每次都从完整 READY 状态执行到 post-retreat final outcome。找到单次完整成功后冻结 commit 和 policy fingerprint，再进入串行资格验证。

## 6. 成功与生命周期

- `INVALID_ENVIRONMENT`：环境/所有权/复位/provenance 无效，不计入策略结果并结束当前批次。
- `VALID_FAILURE`：环境有效但未通过 Continuation Gate 或 Final Outcome Gate，终止当前 streak。
- `VALID_SUCCESS`：完整连续路径通过 post-retreat Final Outcome Gate。
- 不允许把不同 commit、policy fingerprint、FULL_RESTART 与 RESET_WORLD 生命周期混入同一 streak。

资格顺序保持：先用 RESET_WORLD 搜索并确认单次完整成功；冻结版本后串行 FULL_RESTART 连续五次；随后同一冻结版本串行 RESET_WORLD 连续五次。任一 VALID_FAILURE 清零对应 streak。

## 7. 测试要求

- Contract test：penetration/q6/contact geometry 单独异常只进入 telemetry，不触发中间失败。
- Continuation test：杯体未随 micro-lift 位移、杯体越出可恢复包络或 arm 不稳定必须失败。
- Anti-cheat test：forward Gazebo attach 永远禁止，Planning Scene attach 只影响碰撞规划。
- Final test：预撤离成功但 RETREAT 后杯体偏移/倾倒必须失败。
- Five-run accounting test：生命周期、fingerprint、INVALID/VALID_FAILURE 的 streak 语义不可混算。

## 8. 非目标

- 本轮不实现通用自适应实验规划器基础设施。
- 不搜索或修改冻结的物理、几何、材料、controller、碰撞参数。
- 不以单次随机成功替代连续五次资格验证。
- 不 push、不 merge，直到实现与验证完成后再次取得用户确认。

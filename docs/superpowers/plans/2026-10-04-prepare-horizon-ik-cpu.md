# prepare_horizon CPU IK 优化计划

> 执行方式：用户确认后，由当前 `gpt-6.1-sol/xhigh` 会话 inline 执行并自审，使用 `superpowers:executing-plans`。不启动 dst，不派实现或评审 agent。

**状态：** 用户已明确批准；缓存、FK 复用、最终对照与完整包门禁均已完成。聚合 ratio 为 27.27%。

**目标：** 在 mac-mini 的固定四案例上，将 `prepare_horizon` 完整计算的等权聚合 median 降到冻结 baseline 的 30% 或以下，并保持行为等价。

**需求来源：** [完整交接任务](/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/bootstrap/so101-prepare-horizon-ik-20261004-handoff.md)。

**测量协议：** [protocol-v1.json](/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735/baseline/protocol-v1.json)，SHA256 `4cf8a581b31b9dad23ac1050dd077674de44c09e6436aba9c6478ff0df2c453a`。

## 已完成的 baseline

基线为 `7a62d8e88f4b04fa5f20359649013a16bae909b0` 的 Mac/source 冻结快照。
工作树 `/Users/matianyi/.codex/worktrees/0a4f/moveit-demo` 起初隔离且 clean，现使用任务分支
`codex/prepare-horizon-ik-20261004-01a10735`。旧主 checkout 和已有工作树保留。

主机是 Apple M4，10 核、24 GiB RAM。解释器固定为 `/opt/ros/jazzy/.venv/bin/python`，
CPython 3.11.15、NumPy 2.4.6 / Accelerate；计算和 BLAS 线程预算为 1。
每个案例执行三个独立进程轮次，每轮一次预热、五次正式测量，共 15 个样本。

| 固定案例 | horizon 结果 | median（ms） | p95（ms） |
| --- | --- | ---: | ---: |
| p18_home | 完整 14 步 | 4291.527 | 4329.279 |
| canonical_home | 完整 14 步 | 963.757 | 979.761 |
| outer_boundary | 拒绝 | 2574.903 | 2596.456 |
| unreachable | 拒绝 | 739.347 | 749.293 |
| 四案例等权聚合 | 两个成功、两个失败都计入 | 2145.619 | 2164.032 |

初始 baseline 对应的 30% 是 643.686 ms。最终验收将重跑冻结基线，按协议交错 baseline
与优化版本，使用新鲜对照的 ratio；不得事后替换案例、权重或统计方法。
本指标覆盖实际 `prepare_horizon` 的路点生成、种子搜索、真实 URDF IK、FK 评分、路径
采样、receipt 形成和步骤分组。ROS 等待、MoveIt planning 与外部进度成本未计入。
初始化和首次调用单独报告，每次调用必需的缓存建立仍计入主指标。

599 次 P18 solve 请求中有 260 次精确重复；canonical 同样重复 260 次。
profile 的 `_matrix` 占 10.546/13.719 s，`_rotation_axis` 的 inclusive 时间为 6.850 s。
失败 seed 占 P18 计数运行时间约 74%，所以优化必须保留失败成本和失败案例。
既有 IK、horizon、reachability 定向测试在固定运行时中 14 项通过。首次 sandbox 运行在
pytest 插件的本地 socket 初始化阶段失败；保留了失败日志，使用主机权限重跑后通过。

## 短设计与取舍

先消除单次 horizon 内的精确重复 IK/FK，再减少 FK 内部的恒定计算。
两步分别测量，保留每个中间版本及结果。继续串行执行，保留候选与 receipt 的原顺序。

单靠缓存不能改善没有重复请求的不可达案例。CPU 批量或并行可以作为后续路线，但会
增加调度、资源和浮点等价验证成本，本计划先做上述两个已被 profile 支持的改动。
本轮不引入新依赖或原生扩展。若这两步仍未达到 30%，先报告差额和下一项具体实验，
再确认超出此方案的设计；不得放宽验收条件。

### 任务 1：单次 prepare_horizon 的精确缓存

预计修改：

- `src/so101_demo_py/src/control/moveit/deterministic_horizon.py`：增加 request-local IK/FK 缓存适配器；保留 `solve_horizon` 搜索和评分代码。
- `src/so101_demo_py/src/ros/task_reachability.py`：只在 `prepare_horizon` 内建立和使用适配器；其他 plan、ROS 和执行逻辑不动。
- `src/so101_demo_py/test/test_deterministic_ik_horizon.py` 与 `test_task_reachability_ros.py`：缓存边界和跨调用隔离的回归。

适配器保持 `solve(target, seed, *, position_tolerance_m, orientation_tolerance_rad)`、
`forward(positions)`、`orientation_error_rad` 和 `joint_limits` 接口。只为项目的确定性
`UnderactuatedPoseIk` 启用；注入的其他 IK 实现保留现有行为。

键包含 target 的位置和四元数、完整 seed、两个容差的 IEEE-754 精确值。
FK 键包含完整关节向量。solver、URDF、关节顺序和 TCP 由适配器实例绑定，实例只活在
一次 horizon 调用中。不按小数位舍入，不跨 horizon 或状态复用近似目标。
只重用确定性 `UnderactuatedIkError` 拒绝，保留异常类型、参数和 receipt 错误码；
意外异常不缓存。每个分支仍独立执行评分、连续性与全部 9 点路径检查。

- [x] 先写 RED：相同请求多次出现时只进行一次底层计算；不同容差、seed、target 不碰撞；两个 horizon 调用之间缓存不保留；失败仍逐个形成原顺序 receipt。
- [x] 实现适配器与 `prepare_horizon` 调用适配，跑 GREEN，并用真实四案例逐字比较所有 receipt 和选中步骤。
- [x] 单独测量缓存版本，保存 solve 请求、独立请求、命中、FK 次数及 latency；inline 自审并保存 scoped diff。

### 任务 2：复用 FK 不变量及单次迭代的计算

预计修改：`src/so101_demo_py/src/control/moveit/underactuated_ik.py` 和
`src/so101_demo_py/test/test_underactuated_ik.py`。

在 solver 构造时预计算关节轴的归一化结果、叉乘矩阵及其平方，保留原有矩阵乘法顺序。
同一 solve 中预计算 target 四元数矩阵；同一迭代的 residual 和 gate 共享一次 FK 结果。
保留 200 次上限、有限差分 epsilon、阻尼、步长限制、clip、关节余量、误差 gate 和
异常格式。不得合并改变乘法顺序或改写 Jacobian 算法。

- [x] 先建立 FK 数值与异常边界回归，并保留 baseline 对照；比较随机有限关节向量、上下限和已有 grasp pose。
- [x] 逐项引入不变量复用，每项单独测量，确认真实 fixture 的成功/失败、路径、排序、receipt、评分和误差保持等价。
- [x] 共享 kernel 的调用者包括 `dynamic_mujoco_execution.py` 和 reachability 单阶段 fallback；覆盖它们现有定向回归，业务源码不修改。

任何浮点差异都要记录最大差值及是否改变分支、排序或 gate。固定代表集以逐字等价为
首选验收；出现差异时先报告并讨论边界，不自行把容差比较换成最终通过标准。

### 任务 3：最终对照、包门禁与交付

- [x] 按 protocol-v1 运行三轮 baseline/optimized 交错对照，每案例每版本 15 个正式样本；报告聚合 ratio、逐案例 median/p95、波动、首次调用和初始化。
- [x] 先跑定向测试，再在固定 ROS Python、固定 overlay 顺序下运行完整普通 `src/so101_demo_py/test/`，用 xdist 8 workers；保存 JUnit、收集数、跳过数、退出码和 `colcon test-result` 汇总。不运行感知 benchmark。
- [x] 构建和安装使用任务自有 evidence 子目录，核验 dependency closure 和新安装产物 provenance；不修改共享 venv、overlay 或运行时依赖。
- [x] inline 自审 scoped diff，核验旧工作树仍保留；更新实验账本与 checkpoint，报告 retained、archived、deletion candidates，不删除证据，不 push 或 merge。

普通定向命令使用固定 Python：

```zsh
/opt/ros/jazzy/.venv/bin/python -m pytest -p no:cacheprovider \
  src/so101_demo_py/test/test_underactuated_ik.py \
  src/so101_demo_py/test/test_deterministic_ik_horizon.py \
  src/so101_demo_py/test/test_task_reachability_ros.py \
  src/so101_demo_py/test/test_dynamic_execute.py
```

`test_dynamic_execute.py` 覆盖共享 kernel 的 MuJoCo 调用边界。
实际命令、环境、退出码和证据路径在每轮开始前登记到账本。

## 本次确认范围

用户以“批准计划”确认本范围；本会话已实现和自审上述两步。三轮交错对照的聚合
median 为 2126.475 → 579.948 ms，ratio 27.27%；完整输出逐字一致。完整普通包门禁
3910 项通过、30 项跳过，xdist 8 workers。最终统计和审阅见证据根的 `review/result.md`。
证据始终保存在唯一已注册根目录：
`/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`。

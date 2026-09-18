# SO-101 Head/Wrist RGB ACT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MuJoCo 中实现双 RGB、独立颈部搜索、MoveIt 示教和 ACT 无干预 pick-place，并在单次 120 s 内完成撤离与物理验收。

**Architecture:** ACT 输入仅为双 RGB 和 8 维状态，输出 6 维绝对位置目标。搜索、动作执行和物理监督各自拥有明确接口，ROS/控制器与仿真真值留在 adapter 边界。MoveIt 示教采集复用已合入的自适应多 stack Worker Pool，但以独立的 ACT collection workload、Worker 私有 Recorder 和确定性聚合器接入；先通过 W1/W2 资格验证，再按证据扩大并发。先交付相机与搜索，再交付可重放的数据管线，最后训练、接入执行与封存测试；每一阶段均能独立验收。

**Tech Stack:** Python、ROS 2 Jazzy、MuJoCo、MoveIt 2、ros2_control、C++ CameraPlugin、LeRobot/PyTorch、自适应 Worker Pool、fsync journal、有界 IPC、React/TypeScript/Bun。

**Spec:** [SO-101 双 RGB ACT 设计](../specs/2026-09-10-so101-act-head-wrist-rgb-design.md)。执行者必须先读设计和本计划；校准项由测量工件提供，不把测试示例数值用于实际控制。

## Global Constraints

- 保留 V5-T001～V5-T005 的 Agent、感知与几何规划链路；本计划对应 V5-T006～V5-T010，不写学习者进度。
- 两相机首版统一为 `640×480`、RGB、10 Hz。head/wrist 不创建 Depth topic；task_camera 保留既有 RGB-D。
- `observation.state` 为 `[q1,q2,q3,q4,q5,q6,sin(neck_yaw),cos(neck_yaw)]`；`action` 为 `[q1_target,…,q6_target]`，单位 rad。
- ACT 不读取 `task_camera`、Depth、`/cup_pose`、TF、Planning Scene、物体真值、接触或教师内部阶段。
- neck 独立 controller，不加入手臂 MoveIt planning group；搜索完成后锁定，ACT 运行中不追踪转头。
- `act_timeout_s=120`（2 分钟），从首次推理前开始用单调墙钟计时，包含等待、抓放、撤离和最终检查；不得暂停或刷新计时。
- 非法动作拒绝并留证，不静默裁剪；监督器只批准、拒绝、停止与交接，不替 ACT 生成抓放动作。
- Train 50、Validation 10、Offline Test 10 个成功 episode；Rollout Validation 至少 10 个固定初始条件；Rollout Test 至少 10 个封存初始条件。
- 首版只并行 MoveIt 专家示教采集；ACT 闭环验证和封存测试仍按单场景独立执行。资格/扩容 episode 不进入正式训练数据。
- 现有并行点位验证的 W8 默认值不自动继承。ACT 采集先通过 W1 语义等价和 W2 隔离/吞吐资格；W4/W6/W8 必须逐档测量双 RGB 无损录制、仿真实时因子与资源占用。
- 业务失败形成 scenario 终态，不靠 fallback 重试；只有基础设施失败允许同一 scenario 增加 infra attempt。并发降级不得改变 split、数据契约或成功标准。
- V5-T009 首次无干预成功率至少 70%；V5-T010 至少 20 个共享测试场景。搜索失败进入端到端分母，恢复另计干预。
- 目标平台是 macOS 与 ai-station/Linux，分别验证；实体机械臂迁移属于 V6，本计划不授权实机动作。
- 不运行无关 `benchmark_test`；普通 Python 包测试只收集 `src/so101_demo_py/test/`。
- README 使用英文；中文指南使用 `humanizer-zh`；教学指南放 `docs/guides/`。本计划不改 README、课程或个人进度。
- 不使用 `gh`、force-push、`ament_uncrustify --reformat`；下列 commit 步骤只提交本任务明确列出的文件，不自动 push。

---

## 范围、基线与交付顺序

建议把后续执行拆为三个审阅批次：A 相机/搜索（Task 1–6）、B 执行安全与数据（Task 7、7A、8–11、11A）、C 训练/产品接入/验收（Task 12、12A、13–16）。本总计划保持一份，避免跨文件接口漂移。2026-09-11 根据 Astra high 审查增加 Task 7A 与 Task 12A；2026-09-16 根据已合入的自适应多 stack 实现增加 Task 11A，共 19 个任务。编号后缀保留既有引用。Task 7A 在 Task 8 之前，Task 11A 在 Task 12 之前，Task 12A 在 Task 13 之前执行。A 的输出是可搜索、锁定并生成合格观测的仿真；B 的输出是有安全门控、可重放且完成并发资格验证的示教管线；C 的输出是经过封存测试的 ACT 系统。

原计划编写基线为 `0fbef11441e7eb541854b367a21b38dc354c43ac`。本次并行采集修订基于 `e6c91cb6437f254f65531346bffaec53655e9162`；自适应 Worker Pool 合入提交为 `25d1130a990f34334b20e9ced4bcde4f4ed83aba`。执行时仍需读取实际 HEAD、dirty files 和两远端状态，不能假定这些哈希仍是最新工作树。路径均相对 `moveit-demo` 仓库根。

已核实的集成点：

- `src/so101_demo_py/setup.py` 将 `src/` 映射为 `so101_demo`，自动安装 assets/config/launch；这是 ament_python 包，没有该包的 CMakeLists.txt。
- `src/so101_demo_py/src/runtime/launch_composition.py` 的 `_render_mujoco_robot_description` 和 `_mujoco_stack_actions` 当前读取固定 MuJoCo 资产与配置。增加显式 ACT profile，默认路径保持兼容，不复制整套大 launch 文件。
- `src/so101_demo_py/src/backends/mujoco/reset.py` 的 `MujocoResetClient` 当前要求六维状态；`client.py` 的 `latest_joint_positions`/`joints_converged` 也需要一起检查，不能只去掉长度断言。
- `src/so101_demo_py/config/mujoco/ros2_controllers.yaml` 使用独立的五维 arm 和一维 gripper JointTrajectoryController。
- CameraPlugin 位于子模块 `third_party/mujoco_ros2_control`；依赖锁为 `src/so101_demo_py/config/dependency-lock.yaml`，当前锁定 `71bc9346cf93d6227a6678fcacf63f3e18acfcba`。修改子模块后先提交子模块，再更新父仓 gitlink 和锁，不改写历史 provenance 报告。
- 仿真物理证据来源为 `src/so101_mujoco_support` 与 `src/so101_demo_py/src/backends/mujoco/observer.py`。持物监督复用既有杯子证据；Task 8 在 support 插件增设不经杯子过滤的全机器人接触流。所有真值仍只供监督/审计，不进入 ACT observation。
- `src/so101_demo_py/src/parallel_batch/` 已有自适应 Runner、queue、pool、coordinator、Worker、Broker、资源声明和 fsync journal；`runtime/parallel_*` 提供进程/ROS/IPC 组合。`ParallelWorker` 当前硬编码点位验证阶段，Task 11A 通过 ACT 专用 ports 适配其调用边界，不复制 lease、heartbeat、fallback 或 cleanup 实现。
- `adaptive_contracts.py` 单批最多 20 个 `selected_point_ids`。Task 11A 在外层将冻结的 scenario 清单确定性分 wave，每个 wave 复用 `AdaptiveBatchRunner`，外层 journal 负责跨 wave 恢复和最终数据集顺序；不得放宽现有点位验证上限来容纳整套数据。
- `config/mujoco/parallel_adaptive_workers_v1.yaml` 的 W8/fallback 和共享 Broker C2 来自 MoveIt 点位验证。ACT 使用独立 `config/act/parallel_collection_v1.yaml`，先冻结 W2/fallback W1；只有资格实验通过才更新默认档位。

## 文件结构与职责

新建 `src/so101_demo_py/src/act/` 包，包含 `__init__.py`。它按 ACT 领域职责拆文件，不重新组织既有代码。纯领域逻辑不导入 ROS、torch、MuJoCo；所有 `adapters/act/` 新目录也增加 `__init__.py`。下面各任务 Files 清单给出完整路径及唯一责任，文件首次出现为创建，后续引用为修改。

| 单元 | 主要文件 | 责任 |
| --- | --- | --- |
| 契约与时间 | `act/contracts.py`, `act/deadline.py` | 输入白名单、时间网格、错误与 120 s 截止时间 |
| 控制权 | `act/ownership.py`, `adapters/act/command_broker.py`, `adapters/act/leased_action_client.py` | 唯一仲裁与既有动作客户端接入 |
| 图像与搜索 | `act/synchronizer.py`, `act/search.py`, `act/bearing.py` | 因果取样、扫描/锁定、相机视线方向 |
| 校准 | `act/calibration.py`, `cli/act_preflight.py` | 校准报告、配置冻结、正式采集门槛 |
| 执行与监督 | `act/execution.py`, `act/supervisor.py`, `adapters/act/ros_execution.py`, `adapters/act/physics.py` | 双控制器、路径检查、释放门控和状态机 |
| 数据 | `act/expert.py`, `act/recorder.py`, `act/sampling.py`, `act/collection.py` | 实际 reference、无损记录、划分与单场景采集 |
| 并行采集 | `act/parallel_collection.py`, `adapters/act/parallel_collection_runtime.py`, `adapters/act/parallel_collection_results.py`, `cli/act_collect_parallel.py` | scenario→wave、Worker ports、基础设施降级、原子封存与确定性总 manifest |
| 模型 | `act/bundle.py`, `act/policy.py`, `adapters/act/lerobot.py`, `cli/act_train.py` | 离线模型工件、单次推理、版本隔离 |
| 推理进程 | `adapters/act/inference_process.py`, `cli/act_inference_worker.py` | 指定解释器、模型加载、非阻塞 IPC |
| 离线评估 | `act/offline_evaluation.py`, `cli/act_offline_evaluate.py` | 冻结 Offline Test 与带 mask 的动作误差 |
| 组合与评测 | `act/session.py`, `act/evaluation.py`, `runtime/act_composition.py`, `cli/act_session.py`, `cli/act_evaluate.py` | 运行生命周期、命令入口、封存评测 |
| Teleop | `so101_teleop/act_gateway.py`, `web/src/components/teleop/act-panel.tsx` | 页面操作与后台命令，不承载 10 Hz 循环 |

## 统一接口约定

Python 接口中的 `dict` 均为下列闭合 JSON schema，校验拒绝多余字段；图像 bytes/array 仅存在内存，不把审计侧字典整体传入模型。坐标、时间、单位在字段名中明确。所有时间比较先校验 session/attempt，所有 float 拒绝 bool、NaN、Inf。

| schema | 精确字段 |
| --- | --- |
| `Observation` | `session_id:str, attempt_id:str, sim_time_s:float, head:RGB array, wrist:RGB array, state:tuple[float,...]`（8 维） |
| `ActionPrefix` | `session_id:str, attempt_id:str, sequence:int, observation_time_s:float, target_times_s:tuple[float,...], positions:tuple[tuple[float,...],...]`（每行 6 维） |
| `SearchResult` | `found:bool, status:str, bearing_rad:float|None, frame_id:str, ray_origin_frame_id:str, neck_yaw_rad:float|None, confidence:float|None, timestamp:float, attempt_id:str` |
| `Scenario` | `scene_id:str, split:str, xy:tuple[float,float], arm_q:tuple[float,...]`（6 维）, `search_start_rad:float, seed:int, config_sha256:str` |
| `CollectionScenarioResult` | `scene_id:str, split:str, status:str, business_failure:str|None, infra_attempts:int, episode_root:str, episode_sha256:str, worker_id:str, pool_generation:int, worker_count:int` |
| `RunResult` | `scene_id:str, split:str, search_locked:bool, done:bool, interventions:int, failure:str|None, elapsed_wall_s:float, elapsed_sim_s:float, checkpoint_sha256:str, config_sha256:str` |

`ContractError(ValueError)` 用于输入/工件拒绝；执行状态使用稳定字符串，如 `ACT_TIMEOUT`、`TARGET_AMBIGUOUS`、`TARGET_NOT_FOUND`、`INPUT_STALE`、`COLLISION_REJECTED`、`RELEASE_UNSUPPORTED`、`CONTROLLER_PAIR_FAILED`。错误细节留审计侧，不悄悄转换为成功。

## 执行前准备与测试命令

- [ ] 读取当前根/父仓 AGENTS.md、`so101-dev` 及有关 reference；记录本地和 ai-station 的 pwd、branch、commit、submodule、dirty files。只在执行阶段访问远端。需要隔离 checkout 时使用 `superpowers:using-git-worktrees`，不把用户未跟踪设计丢在原 checkout。
- [ ] 检查已有进程、ROS graph、tmux `codex-cua`，记录所有权；运行阶段不得启动重复 stack。全任务使用一个 evidence root，写入 `docs/experiments/so101-act-head-wrist-experiment-ledger.md`。本次写计划沿用 `/tmp/so101-debug-act-design-review-20260911-01a08e1d/`，执行产生训练数据时另立执行 task，Linux root 使用 `/data/work/so101-evidence/act-head-wrist/<run-id>/`；这里的 run-id 由 `mktemp` 生成，不用字面占位路径。
- [ ] 在执行主机配置一次下面的 shell 环境。Mac 使用当前已加载 ROS 的 zsh；Linux 直接在 ai-station 执行，禁止再次 SSH 自身。

```zsh
if [[ "$(uname -s)" == Darwin ]]; then
  ACT_EVIDENCE=$(mktemp -d /tmp/so101-debug-act-implementation-XXXXXXXX)
  ACT_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python3
  eval "$(direnv export zsh)"
else
  source /opt/ros/jazzy/setup.zsh
  mkdir -p /data/work/so101-evidence/act-head-wrist
  ACT_EVIDENCE=$(mktemp -d /data/work/so101-evidence/act-head-wrist/run-XXXXXXXX)
  ACT_PYTHON=$(command -v python3)
fi
export ACT_EVIDENCE ACT_PYTHON
export ROS_HOME="$ACT_EVIDENCE/ros-home" ROS_LOG_DIR="$ACT_EVIDENCE/ros-home/log"
mkdir -p "$ROS_LOG_DIR"
# 使用依赖锁规定的 fork overlay，然后 project overlay；具体绝对路径记入账本。
source install/setup.zsh
"$ACT_PYTHON" -c 'import sys, rclpy; print(sys.executable); print(rclpy.__file__)'
```

- [ ] 把以下函数留在同一执行 shell。Linux 每次测试创建全新 NVMe scratch，用实际 Python 验证；普通 gate 不收集 benchmark。运行耗时和 scratch 随日志登记，readback 后分类为删除候选，禁止自动删除。

```zsh
act_test() {
  if [[ "$(uname -s)" == Linux ]]; then
    mkdir -p "$ACT_EVIDENCE/scratch"
    ACT_SCRATCH=$(mktemp -d "$ACT_EVIDENCE/scratch/test-XXXXXXXX")
    mkdir "$ACT_SCRATCH/tmp"
    export TMPDIR="$ACT_SCRATCH/tmp" TMP="$ACT_SCRATCH/tmp" TEMP="$ACT_SCRATCH/tmp"
    "$ACT_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve()==Path(os.environ["TMPDIR"]).resolve()' || return 1
  fi
  PYTHONNOUSERSITE=1 /usr/bin/time -p "$ACT_PYTHON" -m pytest -p no:cacheprovider "$@"
}
```

每个 Task 的 RED/GREEN 命令使用 `act_test`。纯 Python 新包通过 `colcon build --packages-select so101_demo_py --symlink-install` 安装后再 source；测试必须出现预期断言失败或缺失的新符号，ROS/dylib bootstrap 失败不能当 RED。Linux package gate 在上述 scratch 环境中执行 `colcon test --packages-select so101_demo_py --pytest-args test`，随后 `colcon test-result --verbose`；Mac 按 `test-and-acceptance.md` 用 `act_test src/so101_demo_py/test -q --junitxml="$ACT_EVIDENCE/package.xml"`，并用 `colcon test-result --test-result-base "$ACT_EVIDENCE" --verbose` 汇总。新增 C++/Teleop 任务各自运行自己的 package gate。

以下代码块给出必须落地的边界测试与关键实现，不是只有正常路径的完整实现。每个任务还列出失败矩阵，逐项补参数化测试；校准、录制和训练是长时间命令，启动、读取报告、判定作为独立步骤，不承诺一次完整训练只需 2–5 分钟。


### Task 1: 闭合 observation/action 契约与 120 s 截止时间

**Files:**

- Create: `src/so101_demo_py/src/act/__init__.py`
- Create: `src/so101_demo_py/src/act/contracts.py`
- Create: `src/so101_demo_py/src/act/deadline.py`
- Create: `src/so101_demo_py/test/test_act_contracts.py`

**Interfaces:** Consumes: 标准库及本计划 schema。Produces: `ContractError`；`validate_action(values: tuple[float, ...]) -> tuple[float, ...]`；`validate_observation(value: dict) -> dict`；`Deadline(started_wall_s: float).expired(now_wall_s: float) -> bool`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.contracts import ContractError, validate_action
from so101_demo.act.deadline import Deadline

def test_nonfinite_action_and_fixed_deadline():
    with pytest.raises(ContractError):
        validate_action((0., 0., 0., 0., 0., float("nan")))
    budget = Deadline(started_wall_s=10.)
    assert not budget.expired(129.999)
    assert budget.expired(130.)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_contracts.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
from dataclasses import dataclass
import math

class ContractError(ValueError):
    pass

def validate_action(values: tuple[float, ...]) -> tuple[float, ...]:
    if len(values) != 6 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ContractError("ACTION_INVALID")
    return tuple(float(v) for v in values)

@dataclass(frozen=True)
class Deadline:
    started_wall_s: float

    def expired(self, now_wall_s: float) -> bool:
        return now_wall_s - self.started_wall_s >= 120.0
```

为每个 schema 实现严格字段白名单、非空 ID、有限时间、向量形状检查。Observation 只允许两张 uint8 RGB 图片与 8 维 state；禁止额外 truth/depth/task_camera 字段。ActionPrefix 目标时间严格递增、步长 0.1 s、首目标为 observation_time_s+0.1；禁止 bool 假冒数值。Deadline 构造和调用拒绝非有限值或倒退的单调时间，计时对象不可重启。常量放 deadline.py，不在训练配置暴露可调 timeout。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_contracts.py -q
```

预期非零测试收集、全部通过。补测 5/7 维 action、8 维 state、错误图像、额外禁止字段、120 s 边界；纯契约导入不能触发 ROS、torch、MuJoCo 导入。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/__init__.py src/so101_demo_py/src/act/contracts.py src/so101_demo_py/src/act/deadline.py src/so101_demo_py/test/test_act_contracts.py
git diff --cached --check
git commit -m "feat: define ACT observation and deadline contracts"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 2: CameraPlugin 逐相机 RGB-only 扩展

**Files:**

- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/test/test_camera_plugin.cpp`
- Modify: `src/so101_demo_py/config/dependency-lock.yaml`

**Interfaces:** Consumes: 既有 CameraData、CameraPlugin 参数与渲染线程。Produces: 相机级 `publish_depth: bool`（默认 true）；false 时不创建 depth publisher、不分配/读取 depth buffer；RGB 与 CameraInfo 保持原语义。

- [ ] **Step 1: 写入边界失败测试。**

```cpp
// 加入现有 test_camera_plugin.cpp，使用已有 camera_plugin.hpp。
TEST(CameraDataContract, DepthRemainsEnabledByDefault)
{
  mujoco_ros2_control_plugins::CameraData camera;
  EXPECT_TRUE(camera.publish_depth);
}
```

- [ ] **Step 2: 验证 RED。**

```zsh
colcon test --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```cpp
// CameraData 新字段；注册相机时从相机级参数读取，默认 true。
bool publish_depth{true};
// render 的像素读取分支：
mjr_readPixels(camera.image_buffer.data(),
  camera.publish_depth ? camera.depth_buffer.data() : nullptr,
  camera.viewport, &render_context);
```

读取 register_cameras 与 render 的实际变量名，将上面的分支放到现有 mjr_readPixels 调用处；深度图转换、buffer resize 和发布也受同一标志约束。不得更改 Linux EGL/macOS CGL 上下文所有权。用现有 CameraPluginTest fixture 建立 RGB-only 与默认 RGB-D 两台相机，实际启动 executor、渲染并验证 topic discovery、RGB 字节数、CameraInfo 与帧时间一致；不能只用结构体默认值测试宣布完成。默认 task_camera 和 macOS lifecycle 测试必须保持通过。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
colcon test --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+
```

预期非零测试收集、全部通过。子模块构建 `colcon build --packages-select mujoco_ros2_control_plugins`，测试 `colcon test --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+`，读取 CTest 结果。修改子模块的实际文件后在该仓 commit；以 `git -C third_party/mujoco_ros2_control rev-parse HEAD` 更新 dependency-lock.yaml 的 fork.commit，父仓显式提交 gitlink 和锁。不得捏造安装 provenance 或发布远端。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git -C third_party/mujoco_ros2_control add mujoco_ros2_control_plugins/src/camera_plugin.hpp mujoco_ros2_control_plugins/src/camera_plugin.cpp mujoco_ros2_control_plugins/test/test_camera_plugin.cpp
git -C third_party/mujoco_ros2_control commit -m "feat: support per-camera RGB-only rendering"
git -C third_party/mujoco_ros2_control rev-parse HEAD
```

先将上述实际 SHA 写入 dependency-lock.yaml，再提交父仓：

```zsh
git add third_party/mujoco_ros2_control src/so101_demo_py/config/dependency-lock.yaml
git diff --cached --check
git commit -m "build: pin RGB-only camera dependency"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 3: ACT 场景、neck controller 与按名称 reset

**Files:**

- Create: `src/so101_demo_py/assets/mujoco/act/scene.xml`
- Create: `src/so101_demo_py/assets/mujoco/act/so101.xml`
- Create: `src/so101_demo_py/assets/mujoco/act/so101.urdf`
- Create: `src/so101_demo_py/config/mujoco/act/ros2_controllers.yaml`
- Create: `src/so101_demo_py/config/mujoco/act/mujoco_plugins.yaml`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/reset.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/client.py`
- Create: `src/so101_demo_py/src/act/joints.py`
- Create: `src/so101_demo_py/launch/so101_mujoco_act.launch.py`
- Create: `src/so101_demo_py/test/test_act_model_reset.py`

**Interfaces:** Consumes: Task 2 publish_depth；既有六关节 reset。Produces: `ordered_positions(values: dict[str,float], names: tuple[str,...]) -> tuple[float,...]`；launch 参数 `act_profile` 默认 false；ACT 入口设 true；neck_yaw_joint 独立于 joints 1–6。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.joints import ordered_positions

def test_neck_does_not_shift_arm_order():
    values = {"neck_yaw_joint": 3., "6": .6, "1": .1}
    assert ordered_positions(values, ("1", "6")) == (.1, .6)
    with pytest.raises(ValueError):
        ordered_positions(values, ("missing",))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_model_reset.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def ordered_positions(values: dict[str, float], names: tuple[str, ...]) -> tuple[float, ...]:
    if len(set(names)) != len(names) or any(name not in values for name in names):
        raise ValueError("JOINT_MAPPING_INVALID")
    return tuple(values[name] for name in names)
```

从现有 XML/URDF 生成显式 ACT 变体，修正 mesh/include 的相对路径；wrist 安装到刚性腕部，head 支架固定于基座，yaw 连续、俯角固定。新增质量/惯量/碰撞体、两相机 640×480 和 neck position actuator；keyframe 用 mj_name2id/jnt_qposadr 按名字构造。安装参数首先为校准输入，Task 6 测量通过后冻结。URDF、MJCF、ros2_control 关节集合一致，SRDF arm group 不加 neck。新增 ACT launch profile 只选择资产/controller/plugin 配置，复用原 launch 组合，禁止另起重复 move_group。MujocoResetClient 新增可选 expected_joint_names，默认保留原六关节；client 的取值与收敛路径接受同一名字列表。ACT reset 要求 7 个关节及 neck controller 的新鲜反馈，不改变旧调用行为。



- [ ] **Step 3a: 把 Scenario 的初始关节状态写入 reset 请求。**

`client.py` 新增 `JointResetOverride(name:str, position:float, velocity:float=0.0)`。`MujocoRosClient.reset_world(keyframe, free_joint_overrides=(), *, joint_overrides:tuple[JointResetOverride,...]=()) -> bool` 和 `MujocoResetClient.reset` 增加同名 keyword-only 参数；旧调用缺省空 tuple。Scenario.arm_q 映射 joints 1–6，search_start_rad 映射 neck_yaw_joint，七个目标都通过同一 reset 事务写入。

```python
from sensor_msgs.msg import JointState

# request 为既有 ResetWorld.Request；joint_overrides 为已校验记录。
request.state_overrides.joint_states = JointState(
    name=[item.name for item in joint_overrides],
    position=[item.position for item in joint_overrides],
    velocity=[item.velocity for item in joint_overrides],
)
```

拒绝重复/未知/非单自由度关节、越界位置和非有限速度；保持旧 keyframe/free_joints 语义。暂停、控制器停用、reset override、atomic snapshot、新 epoch、控制器恢复和新鲜收敛构成一个事务。必须同步控制器保持参考，避免恢复时跳回旧目标。override 不等于 expected state：写入列表和期望读回来自同一 Scenario，但读回必须来自实际消息。

```python
from so101_demo.backends.mujoco.client import JointResetOverride, joint_override_message

def test_joint_override_serializes_both_position_and_velocity():
    msg = joint_override_message((JointResetOverride("1", .15, 0.),
                                  JointResetOverride("neck_yaw_joint", -1.2, 0.)))
    assert msg.name == ["1", "neck_yaw_joint"]
    assert list(msg.position) == [.15, -1.2]
    assert list(msg.velocity) == [0., 0.]
```

将构造提取为 `joint_override_message(items:tuple[JointResetOverride,...])->JointState`，以上测试直接验证真实序列化函数。再用 fake service 捕获完整请求，确认协调器没有丢失参数；live 用两个不同 arm_q/neck 起点重复 reset，断言七关节实测值/零速度/epoch 与清单一致。缺少 neck 或仍停留旧 keyframe 时明确失败。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_model_reset.py -q
```

预期非零测试收集、全部通过。加载 MJCF 与 URDF 检查 joint 集合；打乱 XML joint 顺序后 mapping 仍正确；对旧 6 关节和 ACT 7 关节分别 reset 两次，验证 epoch、位置/速度和相机新帧。`ros2 launch so101_demo_py so101_mujoco_act.launch.py --show-args`，两个平台验证 head/wrist TF 与碰撞几何一致。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/assets/mujoco/act/scene.xml src/so101_demo_py/assets/mujoco/act/so101.xml src/so101_demo_py/assets/mujoco/act/so101.urdf src/so101_demo_py/config/mujoco/act/ros2_controllers.yaml src/so101_demo_py/config/mujoco/act/mujoco_plugins.yaml src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/src/backends/mujoco/reset.py src/so101_demo_py/src/backends/mujoco/client.py src/so101_demo_py/src/act/joints.py src/so101_demo_py/launch/so101_mujoco_act.launch.py src/so101_demo_py/test/test_act_model_reset.py
git diff --cached --check
git commit -m "feat: add ACT scene and named neck reset"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 4: 因果 RGB 同步与 reset 缓存失效

**Files:**

- Create: `src/so101_demo_py/src/act/synchronizer.py`
- Create: `src/so101_demo_py/src/adapters/act/__init__.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_observation.py`
- Create: `src/so101_demo_py/test/test_act_synchronizer.py`

**Interfaces:** Consumes: Task 1 Observation、Task 3 关节名字。Produces: `causal_sample(samples: list[tuple[float,object]], at_s:float, max_age_s:float) -> object`；`RgbObservationSynchronizer.push(stream:str, session_id:str, sim_time_s:float, value:object) -> None`；`.sample(session_id:str, attempt_id:str, at_s:float) -> dict`；`.reset(session_id:str) -> None`。构造参数为 max_age_s、max_skew_s，来自校准工件。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.synchronizer import causal_sample

def test_future_state_is_never_used():
    assert causal_sample([(1., "past"), (1.1, "future")], 1.05, .1) == "past"
    with pytest.raises(ValueError):
        causal_sample([(1.1, "future")], 1.05, .1)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_synchronizer.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def causal_sample(samples, at_s, max_age_s):
    valid = [(t, v) for t, v in samples if 0 <= at_s - t <= max_age_s]
    if not valid:
        raise ValueError("INPUT_STALE")
    return max(valid, key=lambda item: item[0])[1]
```

四个 stream 固定为 head、wrist、arm、neck；用 stamp 和 session 校验新鲜度，双相机优先同一 physics snapshot，否则最大时间差不得超过 max_skew_s。arm 6 维后附 sin/cos yaw；记录原 yaw 只在 audit 输出。相同 stamp 重复拒绝，像素相同允许；有界 ring buffer 不无限增长。ROS adapter 只订阅双 RGB 与 joint feedback；样本时间来自消息 stamp。reset 清空全部 buffer、旧 session 和策略关联，不以墙钟拼接仿真序列。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_synchronizer.py -q
```

预期非零测试收集、全部通过。参数化检查不同相机快照、旧 session、空 buffer、时间倒退、neck 缺失、重复 stamp 与静止像素；模拟缺帧必须让 recorder 拒绝 episode，不能重排帧号伪装连续。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/synchronizer.py src/so101_demo_py/src/adapters/act/__init__.py src/so101_demo_py/src/adapters/act/ros_observation.py src/so101_demo_py/test/test_act_synchronizer.py
git diff --cached --check
git commit -m "feat: synchronize causal ACT observations"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 5: 固定扫描、轻量检测与相机视线方位

**Files:**

- Create: `src/so101_demo_py/src/act/search.py`
- Create: `src/so101_demo_py/src/act/bearing.py`
- Create: `src/so101_demo_py/src/adapters/act/detector.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_search.py`
- Create: `src/so101_demo_py/test/test_act_search.py`

**Interfaces:** Consumes: 新鲜 head RGB、CameraInfo、neck 实测反馈、Task 4 同步策略。Produces: `bearing(ray_base: tuple[float,float,float]) -> float`；`HeadSearchController(config:dict).tick(frame:dict, feedback:dict, now_wall_s:float) -> dict`（输出 neck_target_rad 或 SearchResult）；`detect_head(rgb:object, bundle:dict) -> list[dict]`，检测框精确字段为 xyxy、confidence、class_id、track_id。

- [ ] **Step 1: 写入边界失败测试。**

```python
import math
import pytest
from so101_demo.act.bearing import bearing

def test_ray_uses_base_axes_and_rejects_vertical():
    assert bearing((0., 1., -1.)) == pytest.approx(math.pi/2)
    with pytest.raises(ValueError):
        bearing((0., 0., -1.))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_search.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
import math

def bearing(ray_base):
    x, y, z = ray_base
    if not all(math.isfinite(v) for v in ray_base) or math.hypot(x, y) < 1e-9:
        raise ValueError("BEARING_INVALID")
    return (math.atan2(y, x) + math.pi) % (2 * math.pi) - math.pi
```

状态 SAFE_OBSERVE→SEARCH_CUP→CENTER_CUP→TARGET_LOCKED；先检测起点，粗扫用连续累计 yaw，最大一整圈；步长≤水平 FOV/2。每次移动停稳再用新帧，居中修正受次数/累计角/总时间限制。锁定需同一目标至少 3 帧、水平死区、有效垂直区、最小面积，不能仅按类别关联；歧义返回 TARGET_AMBIGUOUS。失帧停 neck，微调丢失恢复剩余预算扫描。相机视线用去畸变像素 K^-1 后乘实际安装旋转与帧时刻 neck 旋转；不引入距离/桌面交点。无效结果 bearing/confidence 清空。检测器 adapter 只收 head RGB；首个候选复用已安装轻量检测器但必须经 Task 6 head 视角资格验证，权重 hash 和运行依赖单独冻结，失败就不采集。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_search.py -q
```

预期非零测试收集、全部通过。搜索测试使用注入 frame/feedback 序列验证无目标、多目标、左右偏移、±π、垂直视线、锁定漂移、reset、微调预算和超时。加入畸变/俯角/水平偏置几何测试，证明 bearing 是相机光心射线而非基座到杯心角。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/search.py src/so101_demo_py/src/act/bearing.py src/so101_demo_py/src/adapters/act/detector.py src/so101_demo_py/src/adapters/act/ros_search.py src/so101_demo_py/test/test_act_search.py
git diff --cached --check
git commit -m "feat: add bounded head search and bearing"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 6: 相机、搜索与控制参数预检工件

**Files:**

- Create: `src/so101_demo_py/src/act/calibration.py`
- Create: `src/so101_demo_py/src/cli/act_preflight.py`
- Create: `src/so101_demo_py/config/act/calibration-schema.json`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_calibration.py`

**Interfaces:** Consumes: Task 3–5、既有 MoveIt 教师链路。Produces: `require_qualified(report:dict) -> None`；CLI `act_preflight --output PATH`；校准 JSON 含 status、source_commit、config_sha256、measurements、checks，每个检查必须 PASS 才能 QUALIFIED。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.calibration import require_qualified

def test_unmeasured_report_cannot_start_collection():
    with pytest.raises(ValueError):
        require_qualified({"status": "CALIBRATION_REQUIRED", "checks": {}})
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_calibration.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def require_qualified(report):
    required = {"fov", "collision", "search", "synchronization", "execution", "release", "retreat"}
    checks = report.get("checks", {})
    if report.get("status") != "QUALIFIED" or not required.issubset(checks) or any(checks[k] != "PASS" for k in required):
        raise ValueError("CALIBRATION_REQUIRED")
```

注册 act_preflight entry point。测量并输出高度/偏置/俯角、相机内外参、yaw 零位方向、扫描/微调预算、检测阈值、head 锁定有效区、动作限速/限加速度、同步新鲜度、抓取窗口、controller 提交提前量、支撑/释放/撤离阈值；每个值含单位、样本路径与 hash。使用专家全阶段轨迹检查视野和新增几何，分别验证两个平台 RGB 与原 task_camera 回归。执行/释放检查由 Task 7–8 完成后回填新的报告版本，Task 6 本轮可输出 CALIBRATION_REQUIRED 部分报告；禁止提前标 QUALIFIED。试验可以用明确标为 calibration 的候选配置，正式采集只接受完整 QUALIFIED。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_calibration.py -q
```

预期非零测试收集、全部通过。完成 A 阶段时报告相机/搜索实测值及未通过的执行/释放检查。小规模 mock 报告测试缺失项、非有限值、错误单位、篡改哈希；live 校准保留新鲜双视角图像、关节/TF、物理碰撞和检测失败记录。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/calibration.py src/so101_demo_py/src/cli/act_preflight.py src/so101_demo_py/config/act/calibration-schema.json src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_calibration.py
git diff --cached --check
git commit -m "feat: gate ACT capture on measured calibration"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 7: 双控制器定时提交与停止确认

**Files:**

- Create: `src/so101_demo_py/src/act/execution.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_execution.py`
- Create: `src/so101_demo_py/test/test_act_execution.py`

**Interfaces:** Consumes: ActionPrefix、校准执行参数。Produces: `split_positions(rows:tuple) -> tuple[tuple,tuple]`；`ActExecutionAdapter.submit(prefix:dict, permit:dict) -> str`；`.stop(reason:str) -> str`；controller port 为 `send(goal:dict)->str, accepted(goal_id:str)->bool, cancel(goal_id:str)->None, stopped()->bool`，ROS 实现封装 FollowJointTrajectory。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.execution import split_positions

def test_same_rows_reach_arm_and_gripper():
    arm, gripper = split_positions(((1.,2.,3.,4.,5.,6.), (2.,3.,4.,5.,6.,7.)))
    assert arm == ((1.,2.,3.,4.,5.), (2.,3.,4.,5.,6.))
    assert gripper == ((6.,), (7.,))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_execution.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def split_positions(rows):
    return tuple(tuple(row[:5]) for row in rows), tuple((row[5],) for row in rows)
```

ROS adapter 构造 JointTrajectory，两者 header.stamp 相同，点的 time_from_start 根据绝对 target_times_s 转换；不能把当前墙钟作仿真 stamp。必须在共同起始时刻之前取得双方接受；失败取消双方并等待回执+实际速度低于停止阈值。send/cancel 不持有推理线程锁。维护单调动作序号、当前 goal ID 与 attempt；迟到 prefix/过期 permit 拒绝。permit 必须绑定该 prefix 内容 hash、状态 snapshot 和生效期限，不能把上一条的批准复用。替换前缀用 controller 实际插值规则验证，原 reference tap 与部署一致。无原子提交假设，单侧已开始时仍停止双方并记 CONTROLLER_PAIR_FAILED。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_execution.py -q
```

预期非零测试收集、全部通过。注入两个 fake controller：一个接受一个拒绝、一个超时、取消回执但速度未归零、停止后推理返回、旧 goal 回调、新旧前缀衔接。测试必须断言两侧被停止且无后续提交。live 重放同时读 desired/reference 与 joint feedback，证明共同时间、最大时差和停止延迟；不通过则不采集。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/execution.py src/so101_demo_py/src/adapters/act/ros_execution.py src/so101_demo_py/test/test_act_execution.py
git diff --cached --check
git commit -m "feat: coordinate ACT arm and gripper execution"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 7A: 所有已知动作入口共用的控制权仲裁

**Files:**

- Create: `src/so101_demo_py/src/act/ownership.py`
- Create: `src/so101_demo_py/src/adapters/act/command_broker.py`
- Create: `src/so101_demo_py/src/adapters/act/leased_action_client.py`
- Create: `src/so101_demo_py/src/cli/act_command_broker.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/src/ros/dynamic_mujoco_execution.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/descend.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/contact_hold.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/transport.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/place_alignment.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/micro_lift.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/remaining_lift.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/staged_approach.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/release_retreat.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/qualified_phases/policy_lift_waypoint1.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/launch/so101_mujoco_act.launch.py`（Task 3 创建后修改）
- Modify: `src/so101_demo_py/src/adapters/act/ros_execution.py`（Task 7 创建后修改）
- Modify: `src/so101_teleop/so101_teleop/server.py`
- Modify: `src/so101_teleop/so101_teleop/moveit_gateway.py`
- Modify: `src/so101_teleop/so101_teleop/workflow_gateway.py`
- Create: `src/so101_demo_py/test/test_act_ownership.py`
- Create: `src/so101_demo_py/test/test_act_command_broker.py`
- Create: `src/so101_teleop/test/teleop/test_act_ownership.py`

**Interfaces:** Consumes: Task 7 的唯一底层 controller driver；既有 ExecuteTrajectory/FollowJointTrajectory 客户端。Produces: `Ownership.acquire(owner:str, session_id:str, attempt_id:str)->str`（随机 lease token）；`.require(token:str, owner:str, session_id:str, attempt_id:str)->None`；`.revoke(reason:str)->None`；`.release(token:str, stopped:bool)->None`。owner 仅 act/teacher/teleop/recovery；lease 原子覆盖 arm+gripper，neck 仍由搜索独立控制。

运行时只有 `act_command_broker` 进程拥有 Ownership，首版通过 evidence root 下 Unix socket 提供 acquire/submit/cancel/release/revoke/status 协议。请求含 protocol_version=1、request_id、owner、session_id、attempt_id、lease_token、operation；submit 另含 action_kind（execute_trajectory/arm/gripper）与经白名单校验的目标消息字段。响应含 request_id、accepted、error、goal_id；异步 goal feedback/result 也按 goal_id 关联。socket 以独占锁启动，第二实例拒绝；父进程或客户端断开、租约过期时撤销并停止，不能把 lease 存在浏览器里当作控制事实。

- [ ] **Step 1: 写原子互斥与 stale token 的失败测试。**

```python
import pytest
from so101_demo.act.ownership import Ownership

def test_teacher_cannot_acquire_or_reuse_act_lease():
    owner = Ownership()
    token = owner.acquire("act", "s", "a")
    with pytest.raises(PermissionError):
        owner.acquire("teacher", "s", "a")
    with pytest.raises(PermissionError):
        owner.require(token, "teacher", "s", "a")
    owner.revoke("STOP")
    with pytest.raises(PermissionError):
        owner.require(token, "act", "s", "a")
```

- [ ] **Step 2: 运行 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_ownership.py -q
```

预期新增接口缺失或权限断言失败。

- [ ] **Step 3: 实现原子 lease 状态及唯一命令转发进程。**

```python
import secrets
import threading

class Ownership:
    def __init__(self):
        self._lock = threading.Lock()
        self._lease = None

    def acquire(self, owner, session_id, attempt_id):
        with self._lock:
            if self._lease is not None:
                raise PermissionError("CONTROL_BUSY")
            token = secrets.token_hex(32)
            self._lease = (token, owner, session_id, attempt_id)
            return token

    def require(self, token, owner, session_id, attempt_id):
        with self._lock:
            if self._lease != (token, owner, session_id, attempt_id):
                raise PermissionError("LEASE_INVALID")

    def revoke(self, reason):
        with self._lock:
            self._lease = None
```

以上只实现 lease 核心。broker 另有 RUNNING/STOPPING/IDLE 状态：revoke 原子禁止后续转发，然后取消 ExecuteTrajectory 及两个 controller 活跃目标；观察实际停止后才回 IDLE 并允许 acquire。不得因 `_lease=None` 就在 STOPPING 中接受新 owner。release(token, stopped) 只有 driver 已确认无活跃 goal 且速度达停止阈值时有效，否则拒绝。require 和真正入执行队列必须在同一 broker 临界区完成，防止校验后 revoke、旧请求仍排队的竞态。排队目标含 lease generation，出队再次核验。

新增 `LeasedActionClient(node, action_type, action_name, *, broker_socket, owner, session_id, attempt_id, lease_token)`，为既有调用实现 `wait_for_server(timeout_sec)->bool`、`send_goal_async(goal, feedback_callback=None)->Future`；返回兼容 handle 的 accepted、get_result_async、cancel_goal_async。它只序列化和转发，底层 rclpy ActionClient 留在 broker。保留实际 action status/error_code，不把 broker 接受等同于轨迹成功。Task 7 的双 controller driver 移到 broker 内，ACT adapter 通过 broker 提交 prefix；lease 和 permit 均有效才可转发。

- [ ] **Step 3a: 接通教师、qualified phases 和 Teleop 的全部既有入口。**

在列出的 dynamic_mujoco_execution、qualified phases 创建 ActionClient 的位置使用公共 factory `make_action_client(node, action_type, action_name, *, control_context:dict|None)`；ACT profile 必須携带由父运行者取得的 control_context，缺失时拒绝运行；非 ACT profile 保留原 rclpy client，保证原 V5 行为兼容。qualified 子阶段共用整次 teacher lease，不能每阶段 release 再 acquire。recovery 是停止确认后的新 lease，不得与 act 重叠。

Teleop server 的现有服务内 lease 只作为 UI 会话管理；ACT profile 下 joint、gripper、MoveIt execute、workflow 启动及 reset 都调用 broker 授权。moveit_gateway/workflow_gateway 不再直接越过仲裁启动执行。Task 15 的 ActGateway 复用这里的连接，不创建第二个 Ownership。Task 3 的 reset 必须先取得授权并确认双方已停，不能在 ACT 执行时单独 reset。

MoveIt 的 `/execute_trajectory` 只由 broker 转发已授权 teacher/teleop/recovery 命令；其下游发送 controller goal 是同一授权执行链，broker 记录该执行期间控制器 goal，拒绝 ACT prefix。普通规划服务仍可只读运行。启动时清点已知动作客户端并验证实际映射；若发现同一 controller 的未知活跃 goal，停止并拒绝 ACT 资格。此仲裁针对同一受控仿真系统中的已知入口，不宣称能阻止不受控 ROS 节点蓄意绕过；启动了独立旧 stack 时不得进入 ACT execute。

- [ ] **Step 4: 跨入口故障测试与 live 仲裁验收。**

```zsh
act_test src/so101_demo_py/test/test_act_ownership.py src/so101_demo_py/test/test_act_command_broker.py -q
act_test src/so101_teleop/test/teleop/test_act_ownership.py -q
```

broker 集成测试建立 ACT lease，分别通过真实教师 factory 和 Teleop gateway 提交 arm、gripper 与 ExecuteTrajectory，断言 CONTROL_BUSY/LEASE_INVALID 且底层 fake driver 收到零条额外命令。再测试 revoke 与 submit 并发、queued goal 的旧 generation、lease 超时、客户端断开、broker 重启后旧 token、第二 broker 实例。live 在同一仿真中验证 ACT 运行时其他已知入口全部拒绝；停稳释放后教师可执行，旧 V5 profile 的回归 gate 通过。

- [ ] **Step 5: 显式提交本任务文件。**

```zsh
git add src/so101_demo_py/src/act/ownership.py src/so101_demo_py/src/adapters/act/command_broker.py src/so101_demo_py/src/adapters/act/leased_action_client.py src/so101_demo_py/src/cli/act_command_broker.py src/so101_demo_py/setup.py src/so101_demo_py/src/ros/dynamic_mujoco_execution.py
git add src/so101_demo_py/src/backends/mujoco/qualified_phases/descend.py src/so101_demo_py/src/backends/mujoco/qualified_phases/contact_hold.py src/so101_demo_py/src/backends/mujoco/qualified_phases/transport.py src/so101_demo_py/src/backends/mujoco/qualified_phases/place_alignment.py src/so101_demo_py/src/backends/mujoco/qualified_phases/micro_lift.py src/so101_demo_py/src/backends/mujoco/qualified_phases/remaining_lift.py src/so101_demo_py/src/backends/mujoco/qualified_phases/staged_approach.py src/so101_demo_py/src/backends/mujoco/qualified_phases/release_retreat.py src/so101_demo_py/src/backends/mujoco/qualified_phases/policy_lift_waypoint1.py
git add src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/launch/so101_mujoco_act.launch.py src/so101_demo_py/src/adapters/act/ros_execution.py src/so101_teleop/so101_teleop/server.py src/so101_teleop/so101_teleop/moveit_gateway.py src/so101_teleop/so101_teleop/workflow_gateway.py src/so101_demo_py/test/test_act_ownership.py src/so101_demo_py/test/test_act_command_broker.py src/so101_teleop/test/teleop/test_act_ownership.py
git diff --cached --check
git commit -m "feat: arbitrate ACT teacher and teleop execution"
```

Task 7A 通过前，不进行 Task 8 live execute、Task 9 重放或 Task 11 正式采集。Task 7 的初始控制器定时测试只允许独占的校准运行，不宣称跨客户端安全。

### Task 8: 碰撞、持物、释放与撤离监督

**Files:**

- Create: `src/so101_demo_py/src/act/supervisor.py`
- Create: `src/so101_demo_py/src/adapters/act/physics.py`
- Create: `src/so101_demo_py/test/test_act_supervisor.py`

- Create: `src/so101_mujoco_support/msg/RobotContactEvidence.msg`
- Modify: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Modify: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Modify: `src/so101_mujoco_support/CMakeLists.txt`
- Modify: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`
- Create: `src/so101_demo_py/src/adapters/act/contact_evidence.py`
- Create: `src/so101_demo_py/test/test_act_contact_evidence.py`

**Interfaces:** Consumes: Task 7 执行接口、Task 7A 仲裁、Task 1 Deadline、已有 MuJoCo 物理证据。Produces: `release_allowed(holding:bool, opening:bool, supported:bool, fresh:bool)->bool`；`ActSupervisor.check(prefix:dict, snapshot:dict)->dict`（permit）；`.tick(snapshot:dict, now_wall_s:float)->str`；physics port `check_path(prefix:dict,snapshot:dict)->bool`、`snapshot()->dict`。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.supervisor import release_allowed

def test_cannot_open_unsupported_cup():
    assert not release_allowed(True, True, False, True)
    assert not release_allowed(True, True, True, False)
    assert release_allowed(True, True, True, True)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_supervisor.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def release_allowed(holding, opening, supported, fresh):
    if holding and opening:
        return fresh and supported
    return True
```

把 holding 扩展为运行状态 EMPTY/HOLDING/UNKNOWN；上述 bool 函数只用于已明确状态，UNKNOWN 一律停止。snapshot 明确包含 session/reset_epoch/release_epoch/sim_time_s、arm 位置速度、neck 漂移、target_visible、双侧接触、杯子高度/支撑/放置稳定/撤离稳定及证据新鲜度。check_path 在独立 MuJoCo data 上重建 controller 插值与持物体积，沿前缀检查自碰撞、桌面、支架和相机；使用冻结步长与安全距离界定离散近似，实际执行中还有接触 hazard 停止。允许接触按阶段+明确几何对收窄，不把杯子整体从碰撞检查删除。开爪前必须等支撑成立，不得把尚未成立条件的开爪排入不可撤销长队列；首版在潜在释放边界截断前缀，下一 tick 用新证据重新审批。



- [ ] **Step 3a: 增加不依赖杯子过滤的运行接触流。**

现有 `EvidenceBuilder::build()` 仅保留涉及杯子的接触；不能将它作为全机器人 hazard 的数据源。保留旧 SimulationEvidence/PhysicsStepEvidence 供原链路使用，另加 `/so101/simulation/robot_contacts`，消息 `RobotContactEvidence.msg`：

```text
string simulation_session_id
uint64 reset_epoch
uint64 physics_step
float64 simulation_time_s
string[] geom_a
string[] geom_b
float64[] signed_distance_m
float64[] normal_force_n
bool truncated
bool evidence_loss
```

在仿真 physics-step 回调遍历所有 `data->contact`，先按模型缓存的机器人/neck/相机/支架 geom 集合选择“任一端属于受保护集合”的接触；不经过 object_geom 过滤。杯子持物检查继续使用原流。记录所有候选接触而不是预先按允许列表丢弃；监督器根据阶段和冻结配置判定允许接触。数组长度必须一致，几何 ID 映射取实际模型，固定支架与基座等静态合法接触必须显式校准。

使用有界逐 physics-step buffer，发布所有未读记录；溢出/截断置 evidence_loss，并在仿真端保持 hazard latch 至显式 reset 新 epoch，避免短暂撞击在低频订阅中消失。Python `contact_hazard(frame:dict, allowed_pairs:set[tuple[str,str]])->bool` 拒绝失帧、truncated、旧 epoch、未知 geom 和过期样本，触发 Task 7 的双方停止。

```python
from so101_demo.adapters.act.contact_evidence import contact_hazard

def test_non_cup_contact_and_truncation_are_hazards():
    frame = {"geom_a":["arm_collision"], "geom_b":["table_collision"],
             "signed_distance_m":[-.001], "normal_force_n":[2.],
             "truncated":False, "evidence_loss":False}
    assert contact_hazard(frame, set())
    frame.update(geom_a=[], geom_b=[], signed_distance_m=[], normal_force_n=[], truncated=True)
    assert contact_hazard(frame, set())
```

`contact_hazard` 的纯函数检查数组、loss 和接触对；时间/session/epoch 校验在同文件的 `RobotContactObserver.accept(frame:dict)->None` 完成。Observer 使用 Task 4 新鲜度约定，未取得合格新帧之前不可批准路径。

```python
def contact_hazard(frame, allowed_pairs):
    if frame["truncated"] or frame["evidence_loss"]:
        return True
    pairs = list(zip(frame["geom_a"], frame["geom_b"]))
    return any(tuple(sorted(pair)) not in allowed_pairs for pair in pairs)
```

补齐长度/有限数校验后再使用此核心逻辑。C++ builder 的单测构造“不含杯子”的 arm/table、arm/arm、arm/mast 接触，断言新流保留而旧杯子流兼容；buffer overflow、reset epoch 和短暂接触也必须测。Python 接入测试注入这些消息，断言双方 controller 的 stop 被调用且旧 permit 失效。最终在仿真故障注入中确认真实非杯子接触能止动，不能只检验离线路径预测。

```zsh
colcon build --packages-select so101_mujoco_support so101_demo_py --symlink-install
source install/setup.zsh
act_test src/so101_demo_py/test/test_act_contact_evidence.py -q
colcon test --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --verbose
```

Linux 仍先建立全局测试函数规定的 NVMe scratch 并用实际 Python 验证；C++ 消息增加后必须重新构建/source 两个包，记录类型与安装产物 provenance。默认非 ACT profile 可关闭新流，不改变原杯子证据接口。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_supervisor.py -q
```

预期非零测试收集、全部通过。补测抓取前丢失、接触阶段有界遮挡窗口、双侧接触+微抬升+离台确认、neck 漂移、悬空开爪、release epoch 不可复用、退臂碰杯、未知持物停住、120 s 推理阻塞与仿真暂停。detach planning shadow（若存在）先于开爪。状态 RELEASE_CONFIRMED→ACT_RETREAT→VALIDATE_FINAL_PLACEMENT→DONE，只有撤离与最终放置共同通过才能成功。监督器没有生成轨迹接口；MoveIt recovery 单独算干预。完成后重新运行 Task 6 preflight 形成完整 QUALIFIED 报告。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/supervisor.py src/so101_demo_py/src/adapters/act/physics.py src/so101_demo_py/test/test_act_supervisor.py
git add src/so101_mujoco_support/msg/RobotContactEvidence.msg src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp src/so101_mujoco_support/src/simulation_evidence_plugin.cpp src/so101_mujoco_support/CMakeLists.txt src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp src/so101_demo_py/src/adapters/act/contact_evidence.py src/so101_demo_py/test/test_act_contact_evidence.py
git diff --cached --check
git commit -m "feat: supervise ACT collision release and retreat"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 9: 实际 reference 动作标签与无损 episode

**Files:**

- Create: `src/so101_demo_py/src/act/expert.py`
- Create: `src/so101_demo_py/src/act/recorder.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_expert.py`
- Create: `src/so101_demo_py/test/test_act_recorder.py`

**Interfaces:** Consumes: Task 4 Observation、两个 controller desired/reference、goal 接受/替换事件。Produces: `require_grid(times:list[float], dt:float=0.1)->None`；`MoveItExpertActionTap.label(at_s:float)->tuple[float,...]`（取 at_s+0.1 reference）；`EpisodeRecorder(root:Path).append(observation:dict, action:tuple, audit:dict)->None`、`.finish(outcome:dict)->Path`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.recorder import require_grid

def test_missing_tick_invalidates_episode():
    require_grid([1., 1.1, 1.2])
    with pytest.raises(ValueError):
        require_grid([1., 1.2])
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_recorder.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def require_grid(times, dt=0.1):
    if any(abs((b-a)-dt) > 1e-6 for a,b in zip(times, times[1:])):
        raise ValueError("EPISODE_TIME_GAP")
```

controller reference 首选实际发布 desired，离线延后一个 tick 写 action；goal 接受/起始/取消/替换构成有效 reference 区间。若缺目标时刻 reference，只能用经过验证的 controller 同款插值重建；不能从未来实测关节生成 action。独立 gripper goal 同步转换，没有新 goal 保持最后有效 reference；跨取消空洞无有效 hold 时拒绝 episode。原始 RGB 用无损 PNG 或等价无损格式保存，JSONL 保存原 stamp、q、reference、goal、阶段事件、代码/场景/配置/模型 hash、seed。episode 从锁定稳定开始，直到专家撤离+最终检查完成，尾部无足够未来标签的观测留审计侧，不导出伪标签。finish 原子写 manifest，DISCARD 仅排除训练，不删除文件。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_recorder.py -q
```

预期非零测试收集、全部通过。测试夹爪与手臂不同 goal、reference 替换、时间空洞、保持 state==action、重复 stamp、时间尾段、磁盘写入失败与文件 hash。先回放一条完整示教，经 Task 7–8 验证实际物理抓放+撤离；只通过 action 数值误差不能批采。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/expert.py src/so101_demo_py/src/act/recorder.py src/so101_demo_py/src/adapters/act/ros_expert.py src/so101_demo_py/test/test_act_recorder.py
git diff --cached --check
git commit -m "feat: record controller-reference demonstrations"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 10: 可达区域与五集合空间划分

**Files:**

- Create: `src/so101_demo_py/src/act/sampling.py`
- Create: `src/so101_demo_py/src/cli/act_sample.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_sampling.py`

**Interfaces:** Consumes: Task 6 校准和 MoveIt 完整预检。Produces: `assert_separated(a:list[tuple],b:list[tuple],gap_m:float)->None`；`make_manifest(config:dict, seed:int)->dict`（五集合 Scenario 列表、示教候选预算与稳定 `scene_id`）；`project_collection_manifest(split_manifest:dict)->dict`（只含 Train/Validation/Offline Test，并保存总清单 SHA256）；CLI `act_sample --calibration PATH --output PATH --collection-output PATH --seed INT [--qualification-output PATH] [--qualification-load-output PATH]`。两个可选输出分别生成 8 个功能资格场景和 40 个持续负载场景，均与正式五集合互斥且不得进入训练。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.sampling import assert_separated

def test_labels_do_not_hide_near_duplicate_positions():
    with pytest.raises(ValueError):
        assert_separated([(0.,0.)],[(.001,0.)],.01)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_sampling.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
import math

def assert_separated(a, b, gap_m):
    if any(math.dist(x,y) < gap_m for x in a for y in b):
        raise ValueError("SPLIT_DISTANCE_VIOLATION")
```

Scenario 恢复必须调用 Task 3 的 joint_overrides 写入接口，不能只修改期望读回；记录 reset 后实测七关节作为清单实现证据。候选网格逐点检查桌边、碰撞、pre-grasp/grasp/lift/place/retreat IK 与完整规划、搜索可见性和双视角覆盖，输出有效单元而非包围矩形。单元内部采样的实际点重新完整检查；杯子 XY 与小幅初始关节扰动使用显式种子，初始 arm_q 不能在恢复观察姿态时无声覆盖。按距离/左右/边缘/head 锁定角分层配额，记录拒绝原因。五集合空间隔离、种子、初始状态与轨迹去重；固定外观/光照/尺寸/放置区。闭环验证场景保存 Scenario 全字段，测试场景物理失败不能抽掉后补成容易成功的集合。正式采集前按小批实测有效率为 Train/Validation/Offline Test 冻结大于成功配额的候选预算，每项生成与清单顺序无关的稳定 `scene_id`；运行期间不得临时追加随机候选。`collection.json` 必须由已经原子写入的五集合 `splits.json` 确定性投影，记录后者的内容 hash，并把 Rollout Validation/Test 标记为来源清单中的 `NOT_COLLECTION_ELIGIBLE`，不能自行重新采样。候选耗尽仍不足时输出 QUOTA_UNSATISFIED，并在新数据版本中重新采样，不能缩小隔离距离或反复执行业务失败场景暗中凑数。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_sampling.py -q
```

预期非零测试收集、全部通过。参数化检查相邻格边界泄漏、重复 seed/episode、无法达到配额、中心通过但实际点拒绝、manifest 重放、候选顺序变化时 `scene_id` 稳定、collection 投影只含三个示教 split 且总清单 hash 可读回；生成足以覆盖至少 50/10/10 成功示教目标的冻结候选预算与 10/10 闭环场景，另保留 20 个共享路线比较场景。测试清单生成前不得跑 ACT 筛成功位置。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/sampling.py src/so101_demo_py/src/cli/act_sample.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_sampling.py
git diff --cached --check
git commit -m "feat: isolate ACT spatial splits"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 11: 小批 QC 与正式示教采集

**Files:**

- Create: `src/so101_demo_py/src/act/collection.py`
- Create: `src/so101_demo_py/src/cli/act_collect.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_collection.py`

**Interfaces:** Consumes: Task 9 recorder、一个 Task 10 `Scenario`、QUALIFIED 校准、搜索/教师/物理监督。Produces: `training_eligible(record:dict)->bool`；`prepare_scenario(scenario:dict, reset_port:object)->dict`（只做一次 reset、七关节读回与安全就绪证明）；`collect_authorized_scenario(scenario:dict, preparation:dict, root:Path, ports:dict)->CollectionScenarioResult`（从搜索到 QC，不再 reset）；W1 调试 CLI `act_collect --manifest PATH --calibration PATH --root PATH --limit INT [--qualification]`，ports 固定 reset/search/expert/recorder/supervisor。全局候选循环、配额和并发调度属于 Task 11A。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.collection import training_eligible

def test_failure_is_retained_but_not_exported():
    assert not training_eligible({"qc": "PASS", "done": False, "interventions": 0})
    assert not training_eligible({"qc": "FAIL", "done": True, "interventions": 0})
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_collection.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def training_eligible(record):
    return record["qc"] == "PASS" and record["done"] and record["interventions"] == 0
```

W1 CLI 每条 scenario 先调用一次 `prepare_scenario`，再把返回的 reset epoch、实测七关节与场景哈希传给 `collect_authorized_scenario`，完成 search→lock→stable→record→teacher inference→expert→release→retreat→final-check→QC；后半段拒绝再次 reset。先以 W1 调试入口运行 5 条小批，逐条读回无损 RGB、时间网格、reference、物理结果和 hash；动作重放通过后才允许 Task 11A 做并发资格验证。正式模式仅采 Train/Validation/Offline Test 示教；`--qualification` 只接受 qualification 场景并阻止结果进入训练 manifest；两个 Rollout 集合不得运行专家采标签。每条成功示教受 120 s 墙钟预算；搜索、规划、执行或 QC 失败也封存原始证据并返回不可改写业务终态，不在此函数内自动重试。放置失败先保留证据再独立恢复，持物/未知时不能直接 reset。每条记录生命周期、运行产物 provenance 与模型来源。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_collection.py -q
```

预期非零测试收集、全部通过。单测注入失败 reset、搜索歧义、MoveIt 失败、旧 reset epoch/教师 pose、QC 时间洞、Recorder 队列背压、磁盘写入失败和配置中途变化，检查每个 attempt 只 reset 一次，搜索失败成为业务 `FAILED`，不进入训练且原件存在；同一 `scene_id` 的重入不能覆盖既有终态。B 阶段通过条件还包括 Task 11A 并发资格，不包括 ACT 成功率。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/collection.py src/so101_demo_py/src/cli/act_collect.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_collection.py
git diff --cached --check
git commit -m "feat: collect quality-gated ACT demonstrations"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 11A: 自适应多 stack 示教采集与并发资格验证

**Files:**

- Create: `src/so101_demo_py/src/act/parallel_collection.py`
- Create: `src/so101_demo_py/src/act/parallel_collection_recovery.py`
- Create: `src/so101_demo_py/src/adapters/act/parallel_collection_runtime.py`
- Create: `src/so101_demo_py/src/adapters/act/parallel_collection_results.py`
- Create: `src/so101_demo_py/src/runtime/act_parallel_collection_composition.py`
- Create: `src/so101_demo_py/src/cli/act_collect_parallel.py`
- Create: `src/so101_demo_py/config/act/parallel_collection_v1.yaml`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_runtime.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_recovery.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_integration.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_worker.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_cli.py`

**Interfaces:** Consumes: Task 10 冻结候选清单、Task 11 `prepare_scenario`/`collect_authorized_scenario`、`AdaptiveBatchRunner`、`ProductionAdaptivePoolFactory(composition_factory=...)`、现有 coordinator/Worker/Broker/resources/cleanup。Produces: `partition_waves(scene_ids:tuple[str,...], max_wave_size:int=20)->tuple[tuple[str,...],...]`；`ParallelActCollectionRunner(manifest:dict, config:dict, root:Path).run()->dict`；`ActWaveReconciler.reconcile(wave_record:dict)->dict`；闭合枚举 `workload_kind=point_validation|act_collection`；`AuthorizedWorkloadResult(decision, action_may_have_started:bool, terminal_failure:dict|None)`；`ActCollectionWorkload.run_authorized(...)->AuthorizedWorkloadResult`；`ActCollectionWorkerRuntime`（reset/恢复与 ROS 资源 port）；`ActCollectionResultStore`（Worker seal/recovery receipt port）；`ActCollectionResultVerifier.verify/discover`（coordinator result port）；CLI `act_collect_parallel --manifest PATH [--split-manifest PATH] --calibration PATH --config PATH --root PATH [--qualification] [--worker-count INT]`。正式模式要求 `--split-manifest` 并验证 collection 中的来源 hash；资格模式禁止该参数。`--worker-count` 只能选择配置中已声明的资格档位，并写入结果工件。

- [ ] **Step 1: 写外层 wave、终态与恢复的失败测试。**

```python
from so101_demo.act.parallel_collection import partition_waves

def test_manifest_order_is_partitioned_without_duplication():
    scene_ids = tuple(f"scene-{index:03d}" for index in range(45))
    waves = partition_waves(scene_ids, max_wave_size=20)
    assert tuple(map(len, waves)) == (20, 20, 5)
    assert tuple(item for wave in waves for item in wave) == scene_ids
```

增加 fake W2 集成测试：每个 `scene_id` 只有一个业务终态；pool generation 失败后，只把未封存项交给 W1；已封存项不重跑；同一 scenario 的冲突终态拒绝；journal 截断后恢复到最后一个 fsync 事件。测试业务失败 `FAILED` 不进入 fallback，基础设施 `INVALID/INDETERMINATE` 才增加 `infra_attempts`。另模拟父进程在 Worker seal/coordinator commit 之后、AdaptiveBatchRunner 导入之前退出，要求恢复先对账旧 wave，再为剩余项生成新的 continuation batch。

- [ ] **Step 2: 验证 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_parallel_collection.py \
  src/so101_demo_py/test/test_act_parallel_collection_runtime.py \
  src/so101_demo_py/test/test_act_parallel_collection_recovery.py \
  src/so101_demo_py/test/test_act_parallel_collection_integration.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。不得把既有 adaptive tests 的通过当成本任务 RED。

- [ ] **Step 3: 实现确定性 wave 和外层权威。**

`ParallelActCollectionRunner` 只创建 `RunMode.EXECUTE` 请求，并先校验 manifest hash、资格配置、成功配额、唯一 `scene_id` 和 split 白名单；ACT collection workload 不提供 plan-only/validation 映射。正式模式要求同时读取五集合总清单和 collection 投影，核对来源 SHA256、三个示教 split 的逐项身份/顺序，并拒绝投影中出现 Rollout 场景；`--qualification` 模式只接受 `qualification`，禁止 `--split-manifest`，强制写入隔离 root，并禁止生成可供 Task 12 消费的训练 manifest。它按冻结清单顺序切成最多 20 项的 wave，为每个 wave 创建短 ASCII batch id 和独立 `AdaptiveBatchRequest`。外层 fsync journal 记录 `COLLECTION_MANIFEST`、`WAVE_STARTED`、每个 `SCENARIO_TERMINAL`、`WAVE_TERMINAL`、split 配额和最终 summary；恢复时拒绝 manifest/config hash 变化，并从第一个未终态 scenario 继续。

现有 `AdaptiveBatchRunner` 对 `POOL_STARTING` 后未写 `BATCH_TERMINAL` 的批次保持 `CRASHED_BATCH_REPORT_ONLY`；ACT 不能把它原地重启。外层发现未终态 wave 时，`ActWaveReconciler` 先取得该 collection root 的独占恢复锁，读取外层记录的旧 batch id/runtime root、resource/owned-process manifest、adaptive journal 和 coordinator journal；调用现有精确 cleanup/fence，确认旧 Worker/Broker 进程、controller goal、socket 与 Domain 均已停止或释放。任一对象身份不明或无法清理时停止恢复，不能启动新 pool。

完成 fencing 后，对账器先按 coordinator journal 顺序重建每个 lease 的权威裁决，再遍历原 wave 的冻结 `scene_id` 和精确 workspace。已有 coordinator result commit 的位置调用 `ActCollectionResultVerifier.verify`；缺 commit 时，只有 journal 中没有 `LEASE_EXPIRED`、revocation、replacement 或 `LATE_RESULT_REJECTED`，且封存 manifest 的单调完成时间不晚于原 lease deadline，才允许在该 lease 的登记 workspace 调用 `discover`。durable expiry/revocation/replacement 的优先级高于磁盘 seal；迟到封存只保留审计，不能成为终态或配额。身份、workload/config/manifest hash、终态、时间或内容 hash 不匹配就 fail closed。每个验证通过的结果以 `SCENARIO_RECONCILED` fsync 到外层 journal，保留原 worker/generation/attempt 和完成顺序证据；没有有效封存结果的已启动 lease 计一次 infra attempt。对账完成后才写 `WAVE_RECONCILED`，不得修改或续写旧 AdaptiveBatchRunner journal。

剩余 scenario 保持原 wave 顺序，按累计 `infra_attempts` 的剩余额度分组；每组使用新的单字符 continuation batch id 和 `max_infra_attempts_per_point=全局上限-该组累计次数` 创建新的 AdaptiveBatchRunner。已到上限的项直接形成 `INFRA_EXHAUSTED`，不再调度。continuation 的 batch/runtime root、来源 wave 和 prior attempts 在启动前 fsync；若再次崩溃，重复相同 fencing→verify/discover→import 流程。这样总 infra attempt 上限跨 continuation 生效，已封存结果不重复采集。

每个 wave 通过 `ProductionAdaptivePoolFactory` 注入 `ActCollectionBatchComposition`，复用现有 selector、lease、heartbeat、generation fallback、Domain claim、owned-process manifest 和 cleanup。不要复制或修改 `adaptive_contracts.py` 的 20 项上限。将 `scenario_id` 映射为现有 `point_id` 只属于调度适配，终态工件仍使用 collection schema。现有 `PointStatus.PASSED` 表示该 scenario 产生训练合格 episode，`PointStatus.FAILED` 表示已封存的业务失败；两者均是不可改写终态。

正式采集按 split 和冻结顺序分别分 wave，一个 wave 完整终态后才判断配额。每个 split 选择 manifest 顺序中前 N 个训练合格结果；包含第 N 个成功的 wave 中，排在其后的成功 episode 保留为 `SURPLUS_SUCCESS` 但不进入 Task 12，之后的 wave 标记 `UNSCHEDULED_QUOTA_MET`。因此 Worker 完成顺序不会改变数据集成员。资格模式没有成功配额，必须消费完整资格清单。增加乱序完成测试，要求 W1/W2 的选中 `scene_id` 集合一致。

默认 `parallel_collection_v1.yaml` 使用 `worker_count: 2`、`qualification_worker_counts: [1,2,4,6,8]`、独立 Domain 池，以及闭合降级表 `1:[]`、`2:[1]`、`4:[2,1]`、`6:[4,2,1]`、`8:[6,4,2,1]`；并显式包含 `max_wave_size: 20`、Recorder 队列上限、最小持续写入吞吐、帧间隔容差、lease/heartbeat/启动超时、infra attempt 上限、共享教师 Broker executor 数和资源采样周期。`qualification_worker_counts` 只允许显式资格运行，不能直接改变正式默认。运行目录固定为 `<registered-root>/<run-code>/r/<one-char-wave-id>/p/gNNwNN`，`run-code` 仅允许 `s`（W1 smoke）、`u`（完整单 stack 基线）、`q1`/`q2`/`q4`/`q6`/`q8`（资格）或 `d`（正式数据）；wave id 使用单个 ASCII 字符。

`act_parallel_socket_paths(pool_root, worker_count)` 作为 ACT composition 的唯一端点清单，合并现有 `adaptive_socket_paths()` 与每个 Worker 的 Task 7A command broker 短端点 `ipc/<worker-index>/a`。启动预检、owned-process/endpoint manifest、精确 cleanup 和崩溃恢复都读取这一个清单，不能各自拼路径。CLI 在创建进程前用真实 evidence root 和每个候选档位枚举全部端点，最长编码路径超过 107 bytes 立即拒绝。测试断言每个 Worker 的 command broker 均在清单中，启动、清理与恢复使用相同集合；另以完整清单的实际最长端点验证 107 bytes 通过、根路径增加 1 byte 后 108 bytes 且零进程启动。W4/W6/W8 只有在 Step 6 的资格证据通过后才允许改成正式默认值。

- [ ] **Step 3a: 适配现有 Worker ports，不复制调度状态机。**

在 `parallel_batch/worker.py` 增加可选、闭合的 workload port。未指定时构造 `PointValidationWorkload`，逐行封装当前 `_run_authorized` 的既有 inference→admit→execute/plan 逻辑，确保原 CLI 和证据字节契约保持不变；`act_collection` 才构造 `ActCollectionWorkload`。Worker 继续拥有每个危险边界的 lease heartbeat/`_boundary` 检查、异常捕获与 `_safe_stop`；workload 只能通过受控 callback 调用 runtime/Broker，不能自行绕过 coordinator。两类 workload 返回 `AuthorizedWorkloadResult`，保持当前 `_run_authorized` 的 decision、`action_may_have_started` 与 terminal failure 三项语义，再由 Worker 执行既有 seal/commit/recovery。ACT 的搜索/规划/QC 业务失败必须作为正常 decision 返回，不能抛异常进入 `_safe_stop`。

`ActCollectionWorkerRuntime.reset_point` 调用 Task 11 `prepare_scenario`，只做一次 reset、实测七关节读回和 reset epoch 建立；`point_initial_gate` 只验证 controller 无活跃 goal、相机/Recorder/Broker/ROS 就绪和 preparation 身份，不执行 head 搜索，不把业务失败塞进初始门。`ActCollectionWorkload.run_authorized` 在获准阶段一次完成 head 搜索、相机稳定、教师 snapshot/Broker inference、pose 陈旧检查、录制、专家执行和 QC，并调用 `collect_authorized_scenario`，禁止第二次 reset。搜索歧义/未找到、规划/执行失败和 QC 失败返回正常业务 `FAILED`；端口、进程、通信或封存故障才返回 `INVALID/INDETERMINATE` 触发 fallback。所有动作边界继续由 coordinator lease 和 Task 7A 控制权仲裁授权。

Broker 请求/响应必须关联 batch、worker、worker generation、`scenario_id`/point、attempt、lease generation、reset epoch、request sequence 和输入帧时间。现有 LeaseIdentity 已包含的字段直接复用；reset epoch 和 frame stamp 由 ACT runtime 作为请求负载校验。head 搜索检测留在 Worker 进程，head/wrist 训练帧由 Worker 私有 Recorder 直接写盘，不进入共享 Broker。

`mujoco_parallel_batch.py` 的 worker spec 增加闭合 `workload_kind`、scenario manifest/config 绝对路径和哈希；子进程 builder 只从本地注册表选择 point-validation 或 ACT 的 runtime/workload/results factory，不接受任意 import path。`ProductionBatchComposition` 根据同一 `workload_kind` 选择 `_ArtifactResults`/`SealedResultAdapter` 或 `ActCollectionResultStore`/`ActCollectionResultVerifier`，并把选择写入 batch manifest。默认未提供该字段时仍走现有点位验证。resume 时必须从已封存 manifest 读回并拒绝 workload 或 hash 变化。

`ActCollectionResultStore` 在 Worker 私有临时目录写原始 RGB、状态/action、事件、QC 和 provenance；成功或业务失败都先写闭合 manifest、逐文件 hash，以及由 Worker/Coordinator 共用注入时钟产生的 `completed_monotonic_s`，再原子 rename 并 fsync 文件与父目录。它完整实现 Worker 需要的 `seal_attempt`、`write_recovery_receipt`、`verify_recovery_receipt`。`ActCollectionResultVerifier` 完整实现 coordinator 需要的 `verify(lease, location, run_mode)` 与 `discover(lease, workspace)`，只在登记 workspace 内发现身份、状态、hash、完成时间和终态都匹配的封存结果，并拒绝 `completed_monotonic_s > lease_deadline_monotonic_s`。seal 后、terminal ACK 前崩溃时，coordinator 可通过 discover 提交同一结果；冲突或未封存目录 fail closed。Recorder 队列满、持续磁盘吞吐不足、图像缺口或时间网格不连续记为业务 QC 失败，不静默丢帧；调度器可暂停发新 lease。基础设施崩溃留下的未封存临时目录保留作证据，不计业务终态。

- [ ] **Step 4: 验证 GREEN、隔离和故障矩阵。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_parallel_collection.py \
  src/so101_demo_py/test/test_act_parallel_collection_runtime.py \
  src/so101_demo_py/test/test_act_parallel_collection_recovery.py \
  src/so101_demo_py/test/test_act_parallel_collection_integration.py \
  src/so101_demo_py/test/test_parallel_adaptive_runner.py \
  src/so101_demo_py/test/test_parallel_adaptive_pool.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py -q
```

预期非零测试收集、全部通过。故障矩阵至少覆盖：旧 point-validation worker spec 仍构造原 runtime/results/verifier；真实 ACT 子进程 spec 构造 ACT workload；每 scenario 只 reset 一次；搜索失败封存为 `FAILED` 且不 fallback；旧教师 pose/reset epoch 拒绝；两个 Worker 不同 ROS Domain/namespace/root；错误 Worker 或旧 generation 的 Broker 响应拒绝；一个 Worker Recorder 变慢时另一个不串帧；Broker/Worker 进程退出只重派未封存项；seal 后 ACK 前崩溃由 `discover` 恢复；`LEASE_EXPIRED`→迟到 seal→父进程崩溃后对账仍拒绝该结果；coordinator commit 后、外层导入前崩溃可对账导入；未完成旧进程 fencing 时禁止 continuation；累计 infra attempts 跨 continuation 不超限；recovery receipt 身份和 workspace 越界拒绝；重复/冲突终态；wave 20+20+余数；不同完成顺序仍选择相同的 manifest 前 N 个合格 `scene_id`；W8→W6 完成但 W8 资格失败；五集合总清单到 collection 投影再到最终 dataset 的 hash 可贯通；端点清单包含每个 command broker 且启动/清理/恢复集合一致；完整清单最长路径 107 bytes 通过、108 bytes 时零进程启动；SIGTERM 后 owned process、Domain、socket、command broker 和 controller goal 精确清理。

- [ ] **Step 5: 运行 W1/W2 资格批次。**

先生成单独的功能资格 manifest，使用 8 个覆盖不同区域和搜索角的 scenario；这些 episode 永久标记 `qualification`，不进入 Train/Validation/Offline Test。对同一清单分别运行 W1 单条入口、W1 并行入口和 W2。语义等价比较 schema、scene/reset 身份、10 Hz 时间网格、reference 定义、QC/失败分类、封存结构和物理结果，不要求不同运行的像素或 MoveIt 浮点轨迹逐字节相同。

W2 通过条件：8 个 scenario 各有唯一终态；无跨 Worker topic、帧、controller goal 或目录写入；无静默丢帧；所有进程、Domain、socket 与 goal 完成精确清理；`levels_used == [2]`，零 infra interruption/retry、零 fallback、零 crash continuation；有效 episode/分钟高于完整八场景 W1 基线，且物理成功率和 QC 合格率没有超出预先冻结的退化容差。每次运行记录代码/config/manifest/Broker 模型 hash、`levels_used`、每 scenario infra attempts、CPU、RSS、GPU、磁盘写入、仿真实时因子、帧间隔分位数、吞吐与失败分布。发生降级后完成的批次只作为恢复证据，不计 W2 资格或吞吐。功能资格只证明 W2 接线和隔离，不用于选择 W4/W6/W8。

- [ ] **Step 6: 逐档选择正式并发并运行正式采集。**

W2 功能资格通过后，另冻结 40 个 `split=qualification`、`manifest_purpose=load` 的 scenario 作为持续负载清单；它与正式五集合及 8 场景功能清单互斥，确定性分成两个完整的 20 项 wave。扩容依次运行 W4、W6、W8，持续负载配置固定 `initial_points_per_worker=2`，要求每个 wave 中每个 Worker 至少连续完成 2 个 terminal lease；少于 2 个则该档失败，不在运行时追加候选。每个被测档位 Wn 的每个 wave 都必须满足 `levels_used == [n]`、零 infra interruption/retry、零 fallback、零 crash continuation；任何降级完成只进入恢复报告，不参与 Wn 资格、吞吐或资源排名。每一档跑完整清单，不因早期成功停止；任何一档失败时停止升档。候选正式默认档位还需在全新 root 上重复一次完整持续负载，两轮都通过同样的纯档位正确性、资源稳定和吞吐门才算稳定。

选择“满足全部数据正确性门且两轮有效 episode/分钟最高的稳定档位”为正式默认，不能只按 wall time。比较同时检查运行后半段吞吐不持续下降、Recorder 队列高水位可回落、磁盘延迟/帧间隔/RTF/RSS 没有越过冻结阈值。W8 点位验证或 W10 单样本不能代替 ACT 采集资格。正式采集使用冻结候选 manifest 和选定档位；基础设施 fallback 只降并发，业务失败不重试。每个 split 完成包含第 N 个成功的整个 wave 后，聚合器按原 manifest 顺序选择前 N 个合格 episode 并生成总 manifest；候选耗尽不足则返回 QUOTA_UNSATISFIED，并保留失败与 surplus 证据。

- [ ] **Step 7: 审查本任务 diff 并提交。**

```zsh
git add \
  src/so101_demo_py/src/act/parallel_collection.py \
  src/so101_demo_py/src/act/parallel_collection_recovery.py \
  src/so101_demo_py/src/adapters/act/parallel_collection_runtime.py \
  src/so101_demo_py/src/adapters/act/parallel_collection_results.py \
  src/so101_demo_py/src/runtime/act_parallel_collection_composition.py \
  src/so101_demo_py/src/cli/act_collect_parallel.py \
  src/so101_demo_py/config/act/parallel_collection_v1.yaml \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_act_parallel_collection.py \
  src/so101_demo_py/test/test_act_parallel_collection_runtime.py \
  src/so101_demo_py/test/test_act_parallel_collection_recovery.py \
  src/so101_demo_py/test/test_act_parallel_collection_integration.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_batch_cli.py
git diff --cached --check
git commit -m "feat: collect ACT demonstrations across isolated stacks"
```

提交前确认暂存区没有用户已有改动；只有单元/集成测试、W1/W2 资格和所选正式并发档位的现场证据均通过后才勾选。若更高档位未通过，可保留较低的已合格默认值并把失败档位写入账本，不得把计划中的候选 W8 写成运行事实。

### Task 12: LeRobot 导出、训练与模型工件

**Files:**

- Create: `src/so101_demo_py/src/act/bundle.py`
- Create: `src/so101_demo_py/src/adapters/act/lerobot.py`
- Create: `src/so101_demo_py/src/cli/act_train.py`
- Create: `src/so101_demo_py/config/act/training.yaml`
- Create: `src/so101_demo_py/config/act/requirements.lock`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_bundle.py`

**Interfaces:** Consumes: Task 11A 确定性聚合并通过 QC 的 manifest。Produces: `training_rows(rows:list[dict])->list[dict]`；`export_dataset(manifest:dict, output:Path)->Path`；`train_act(config:dict, dataset:Path, output:Path)->Path`；`load_bundle(path:Path)->dict`；`load_policy(bundle_path:Path)->object`（返回具有 `infer(observation:dict)->tuple[tuple[float,...],...]` 与 `reset()->None` 的模型对象）；CLI `act_train --manifest PATH --config PATH --output PATH`。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.bundle import training_rows

def test_normalization_uses_only_train():
    rows = [{"split":"train","state":[1.]}, {"split":"validation","state":[100.]}]
    assert training_rows(rows) == [rows[0]]
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_bundle.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def training_rows(rows):
    return [row for row in rows if row["split"] == "train"]
```

在独立训练 venv 安装 LeRobot/PyTorch，执行时读取所选版本 ACT 配置、数据 API 源码和官方文档，版本解析后生成精确 requirements.lock 与来源 SHA；不在 ROS 环境 pip upgrade，不假设当前 API 名。adapter 负责上述稳定接口与被锁版本映射。load_policy 校验 bundle/依赖/权重哈希，在训练或推理解释器内加载模型并置 eval 模式；infer 在 inference_mode 下完成相同预处理、推理及反归一化，返回物理 rad，不调用任何 ROS API。保存加载 smoke 必须调用真实 load_policy(...).infer(...) 并验证双相机/8维输入到6维动作块，不能只断言权重文件存在。LeRobot 视图仅导出两 RGB、8 维 state、6 维 action 与 episode/frame/task；图像 HWC→CHW、RGB 顺序/resize/归一化一致，统计只拟合 Train。task 文本不是语言输入。冻结 action chunk、执行前缀、是否 temporal ensembling、checkpoint seed 与预处理 hash；首个 smoke config 使用 chunk_size=10、执行前缀=1、temporal ensembling=false，仅作候选配置，变更须经闭环验证及重放门。尾部 chunk 用明确 padding mask，禁止跨 episode 补帧。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_bundle.py -q
```

预期非零测试收集、全部通过。先导出 2 个合格 Train episode，反读 LeRobot schema、像素、timestamp 和 action，完成短训练+保存加载 smoke；再正式 Train、Validation 选 checkpoint。bundle 保存权重/hash、训练源码/依赖、相机键、q 顺序、统计、split manifest、校准配置 hash。测试 tamper hash、错相机/8→7 state、padding、非 Train 统计污染均拒绝。Offline Test 仅配置冻结后运行，不用其 loss 调参。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/bundle.py src/so101_demo_py/src/adapters/act/lerobot.py src/so101_demo_py/src/cli/act_train.py src/so101_demo_py/config/act/training.yaml src/so101_demo_py/config/act/requirements.lock src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_bundle.py
git diff --cached --check
git commit -m "feat: export and train versioned ACT bundles"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 12A: 封存 Offline Test 的只读动作评估入口

**Files:**

- Create: `src/so101_demo_py/src/act/offline_evaluation.py`
- Create: `src/so101_demo_py/src/cli/act_offline_evaluate.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_offline_evaluation.py`

**Interfaces:** Consumes: Task 12 `load_policy`、dataset manifest、bundle 和冻结清单。Produces: `masked_joint_mae(predicted:list, target:list, valid:list[bool])->list[float]`；`evaluate_offline(manifest_path:Path, bundle_path:Path, freeze_path:Path, output:Path)->dict`；`python -m so101_demo.cli.act_offline_evaluate --manifest PATH --bundle PATH --freeze PATH --output PATH`。此入口仅在训练环境执行，不依赖 ROS，也不驱动控制器。

- [ ] **Step 1: 写入 padding 不计入误差的失败测试。**

```python
from so101_demo.act.offline_evaluation import masked_joint_mae

def test_padding_is_excluded_from_joint_metrics():
    predicted = [[1.,2.,3.,4.,5.,6.], [100.,100.,100.,100.,100.,100.]]
    target = [[0.,0.,0.,0.,0.,0.], [0.,0.,0.,0.,0.,0.]]
    assert masked_joint_mae(predicted, target, [True, False]) == [1.,2.,3.,4.,5.,6.]
```

- [ ] **Step 2: 运行 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_offline_evaluation.py -q
```

预期新增符号缺失或 padded 数据污染误差导致断言失败。

- [ ] **Step 3: 实现只读推理、冻结核验和指标。**

```python
def masked_joint_mae(predicted, target, valid):
    if len(predicted) != len(target) or len(valid) != len(target):
        raise ValueError("MASK_SHAPE_INVALID")
    indices = [i for i, keep in enumerate(valid) if keep]
    if not indices:
        raise ValueError("NO_VALID_TARGETS")
    return [sum(abs(predicted[i][j] - target[i][j]) for i in indices)/len(indices)
            for j in range(6)]
```

逐行补齐六维/finite/bool mask 校验，不能因损坏数据静默减少分母。freeze JSON 固定字段为 bundle_sha256、dataset_manifest_sha256、split_manifest_sha256、calibration_sha256、runtime_config_sha256；Task 16 冻结时从实际文件计算，配套同目录 freeze-paths.json 给出逐项绝对路径，文件丢失或 hash 不符拒绝评估。评估前逐项读回核验，并检查至少 10 个成功 Offline Test episode、没有跨 split/episode chunk 或 Train 拟合统计被更新。

调用 load_policy(...).infer(...)，使用训练时同一预处理、action 时间约定和 tail padding mask；每个 episode 开始 reset 模型状态。全部指标用反归一化后的 rad，保存每关节 MAE/RMSE、按预测 horizon 的误差、每 episode 指标、有效目标数和 episode 等权总体均值，避免长 episode 独占总分。输出模型/清单/hash、配置、依赖版本、运行时间和错误；不反向传播、不更新统计、不选 checkpoint。

输出目录必须新建，报告原子写入；失败保存原因，不能把不完整评估标成功。技术故障重跑使用同一冻结 hash、新运行 ID 并保留失败记录；看过结果后改模型不再沿用这批数据的封存资格。

- [ ] **Step 4: 验证 GREEN 和真实模型离线评估。**

```zsh
act_test src/so101_demo_py/test/test_act_offline_evaluation.py -q
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_offline_evaluate --help
```

先在专用 synthetic fixture 上测试错误 split、hash 被改、全 padding、跨 episode、归一化不变和 metric 数值；模型 smoke 用 Validation 数据的独立测试 fixture，不提前打开 Offline Test。真实 10 个封存 episode 的命令留到 Task 16 冻结之后；本任务以接口和 fixture 验证完成，不声称最终离线指标通过。

- [ ] **Step 5: 显式提交。**

```zsh
git add src/so101_demo_py/src/act/offline_evaluation.py src/so101_demo_py/src/cli/act_offline_evaluate.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_offline_evaluation.py
git diff --cached --check
git commit -m "feat: evaluate frozen offline ACT actions"
```

### Task 13: ACT Runner、时间对齐与异步推理隔离

**Files:**

- Create: `src/so101_demo_py/src/act/policy.py`
- Create: `src/so101_demo_py/test/test_act_policy.py`

- Create: `src/so101_demo_py/src/adapters/act/inference_process.py`
- Create: `src/so101_demo_py/src/cli/act_inference_worker.py`
- Create: `src/so101_demo_py/config/act/runtime.yaml`
- Create: `src/so101_demo_py/test/test_act_inference_process.py`

**Interfaces:** Consumes: Task 12 load_policy/bundle 与 `infer(observation:dict)->tuple[tuple[float,...],...]` 模型 port。Produces: `target_times(observed_s:float,count:int)->tuple[float,...]`；`ActPolicyRunner(bundle:dict, infer:object).predict(observation:dict, sequence:int)->dict`（ActionPrefix）；`.reset(session_id:str,attempt_id:str)->None`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.policy import target_times

def test_chunk_keeps_observation_time_origin():
    assert target_times(5., 3) == pytest.approx((5.1,5.2,5.3))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_policy.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def target_times(observed_s, count):
    return tuple(observed_s + .1*(index+1) for index in range(count))
```

Runner 仅接收白名单 Observation，调用 LeRobot adapter 推理，反归一化后校验形状/finite；prefix 保留原 observation 时间，不在推理返回时重锚。temporal ensembling 只合成同一个绝对 target_time；其算法与权重来自已冻结 bundle，不用数组索引猜时间。运行入口从 --runtime-config 读取 inference_python 与 broker socket；eval 组合使用同一配置，拒绝未配置解释器。ROS executor 和 supervisor 看门狗独立于推理 worker；使用有界 IPC 队列，取消/超时使 generation token 失效，迟回预测丢弃。停止立即禁止提交并取消双方；无需等待 torch 调用返回才止动。reset 清理 chunk、ensemble 与模型缓存，不跨 attempt 复用。



- [ ] **Step 3a: 启动独立解释器的真实推理 worker。**

ROS 侧 `InferenceProcess(python_executable:Path, bundle_path:Path, socket_path:Path)` 用 `subprocess.Popen` 的 argv 列表启动：`[str(python_executable), "-m", "so101_demo.cli.act_inference_worker", "--bundle", str(bundle_path), "--socket", str(socket_path)]`。不使用 shell、不用默认 multiprocessing 继承 ROS Python。runtime.yaml 的 `inference_python` 是经过资格验证的绝对路径；不存在或与 bundle 依赖不兼容则拒绝运行。worker 使用 Task 12 的 load_policy，不导入 ROS；ROS 进程不导入 torch/LeRobot。

IPC 使用本机 Unix socket，长度前缀 JSON，单消息上限 4 MiB，两张 640×480 RGB uint8 图按 base64 原始字节传输；审计真值无对应字段。单个 in-flight 请求、最多一个待发送请求，满时返回 INFERENCE_BUSY，不无限排队。精确消息 schema：

| 消息 | 字段 |
| --- | --- |
| READY | kind、protocol_version=1、bundle_sha256、python_executable、requirements_sha256 |
| PREDICT | kind、request_id、generation:int、session_id、attempt_id、sim_time_s、head_rgb_b64、wrist_rgb_b64、state（8维） |
| RESULT | kind、request_id、generation、session_id、attempt_id、sim_time_s、positions（H×6 rad） |
| RESET | kind、generation、session_id、attempt_id |
| ERROR | kind、request_id、generation、code |

客户端接口 `start()->None`、`submit(observation:dict, generation:int)->str`、`poll()->dict|None`、`invalidate(generation:int)->None`、`close()->None`。start 有冻结的启动超时，只在 READY 的协议/hash/解释器匹配后合格；poll 非阻塞。Runner 的同步 predict 仅用于纯逻辑测试，live 组合使用 submit/poll，禁止在 supervisor 线程调用阻塞 infer。停止先本地 invalidate，使所有旧响应失效，再取消控制器；RESET 不要求卡住的 worker 先响应。进程重启与模型重载发生在新 attempt 前，不能重置当前 Deadline。

```python
from so101_demo.adapters.act.inference_process import response_matches

def test_late_worker_response_is_discarded():
    response = {"request_id":"r1", "generation":3, "session_id":"s", "attempt_id":"a"}
    assert not response_matches(response, "r1", 4, "s", "a")

```

核心匹配函数写入 inference_process.py：

```python
def response_matches(response, request_id, generation, session_id, attempt_id):
    return (response["request_id"], response["generation"], response["session_id"], response["attempt_id"]) == (request_id, generation, session_id, attempt_id)
```

测试文件只导入生产函数，不在测试里重新定义。解码另测畸形 JSON、超长包、错误 RGB 字节数、旧 session、worker 退出、队列满。真实进程 smoke 使用 Task 12 的 checkpoint，ROS 环境中 `find_spec("lerobot")` 为 None，worker 环境可加载模型，实际获得 H×6 响应；分别记录两边 sys.executable。再让测试 worker 阻塞结果发送，注入单调时钟推进到 120 s，断言 session 报 ACT_TIMEOUT、双方 controller 停止，不等待 worker 返回；另做真实墙钟 watchdog 验证。

```zsh
act_test src/so101_demo_py/test/test_act_inference_process.py -q
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_inference_worker --help
```

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_policy.py -q
```

预期非零测试收集、全部通过。fake infer 故意阻塞、返回 NaN、错误 q 顺序、在 reset 后返回，测试无动作提交且 Deadline 仍推进；队列满不能无限积压。模型 smoke 与实时推理读回分别记录 p50/p95/p99 和 missed deadline，超过动作时间预算视为当前部署配置不合格。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/policy.py src/so101_demo_py/test/test_act_policy.py
git add src/so101_demo_py/src/adapters/act/inference_process.py src/so101_demo_py/src/cli/act_inference_worker.py src/so101_demo_py/config/act/runtime.yaml src/so101_demo_py/test/test_act_inference_process.py
git diff --cached --check
git commit -m "feat: run timestamped ACT inference"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 14: 搜索到 ACT 的运行组合与命令所有权

**Files:**

- Create: `src/so101_demo_py/src/act/session.py`
- Create: `src/so101_demo_py/src/runtime/act_composition.py`
- Create: `src/so101_demo_py/src/cli/act_session.py`
- Modify: `src/so101_demo_py/launch/so101_mujoco_act.launch.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_session.py`

**Interfaces:** Consumes: Task 3–13，尤其 Task 7A 的公共仲裁和 Task 13 的非阻塞推理客户端。Produces: `retry_allowed(attempt_index:int, holding:str, feedback_ok:bool)->bool`；`ActSession.command(name:str, payload:dict)->dict`；`.tick()->dict`；CLI `act_session --mode dry_run|plan_only|execute --bundle PATH --calibration PATH --runtime-config PATH --evidence-root PATH`。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.session import retry_allowed

def test_no_retry_with_unknown_or_held_cup():
    assert not retry_allowed(0, "UNKNOWN", True)
    assert not retry_allowed(0, "HOLDING", True)
    assert retry_allowed(0, "EMPTY", True)
    assert not retry_allowed(1, "EMPTY", True)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_session.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def retry_allowed(attempt_index, holding, feedback_ok):
    return attempt_index == 0 and holding == "EMPTY" and feedback_ok
```

组合所有 port，在进入 ACT 首次推理前建立 Deadline。搜索只拥有 neck，Runner 没有 neck port；ACT arm/gripper 所有权通过 Task 7A 的原子 acquire 获取，所有已知教师/Teleop 客户端已接入公共仲裁；Task 14 不另建进程内 lease，其他活跃 goal 拒绝交接。dry_run 无控制副作用，plan_only 只检查候选；execute 需要有效校准/bundle/profile。命令白名单 Reset/Search/StartRecording/RunExpert/Keep/Discard/RunACT/Stop；RunExpert 与 RunACT 互斥。Stop 能由独立 callback 抢占。恢复只在 EMPTY+正常反馈+验证路径时交给 MoveIt，单独计干预；自动重搜最多 1 次。ACTIVE→timeout/error 后保留首次 RunResult，不用重试覆盖。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_session.py -q
```

预期非零测试收集、全部通过。全状态 fake ports 测试无控制权、neck 漂移、全部失败终态、120 s、重搜预算、Stop 优先和 reset 旧 token；live 首先 dry_run，再 plan_only，再小前缀仿真 execute。检查原 V5 launch 与 task_camera 行为无回归。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/session.py src/so101_demo_py/src/runtime/act_composition.py src/so101_demo_py/src/cli/act_session.py src/so101_demo_py/launch/so101_mujoco_act.launch.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_session.py
git diff --cached --check
git commit -m "feat: compose ACT session ownership and recovery"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 15: Teleop ACT 操作面板与后台网关

**Files:**

- Create: `src/so101_teleop/so101_teleop/act_gateway.py`
- Modify: `src/so101_teleop/so101_teleop/api.py`
- Modify: `src/so101_teleop/so101_teleop/server.py`
- Modify: `src/so101_teleop/so101_teleop/openapi.json`
- Modify: `src/so101_teleop/web/src/api/schema.d.ts`
- Create: `src/so101_teleop/web/src/components/teleop/act-panel.tsx`
- Modify: `src/so101_teleop/web/src/task-app.tsx`
- Create: `src/so101_teleop/test/teleop/test_act_gateway.py`
- Create: `src/so101_teleop/web/src/components/teleop/act-panel.test.tsx`

**Interfaces:** Consumes: Task 14 ActSession.command。Produces: `ActGateway(session:object).command(name:str,payload:dict)->dict`；HTTP ACT command/status 接口；React ActPanel 展示状态、双相机、剩余时间与操作结果。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_teleop.act_gateway import ActGateway

def test_gateway_rejects_arbitrary_command():
    with pytest.raises(ValueError):
        ActGateway(session=None).command("shell", {"command":"echo bad"})
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_teleop/test/teleop/test_act_gateway.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
class ActGateway:
    def __init__(self, session):
        self.session = session

    def command(self, name, payload):
        allowed = {"Reset","Search","StartRecording","RunExpert","Keep","Discard","RunACT","Stop"}
        if name not in allowed:
            raise ValueError("COMMAND_INVALID")
        return self.session.command(name, payload)
```

沿现有 backend/profile 与 API 错误风格增加 ACT 能力，仅 ACT profile 显示面板。服务端校验所有权与状态，不能仅禁用前端按钮。界面提供 Reset、Search、Start Recording、Run Expert、Keep/Discard、Run ACT、Stop；Keep 必须 QC PASS，Discard 不删除原始证据。浏览器刷新不会启动第二个 session，重复 command_id 幂等；关闭页面不杀监督看门狗。倒计时读取服务端剩余秒数，不用浏览器计时作为超时事实源；不显示训练内部字段充当普通用户操作。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_teleop/test/teleop/test_act_gateway.py -q
```

预期非零测试收集、全部通过。后端定向命令 `act_test src/so101_teleop/test/teleop/test_act_gateway.py -q`；其后整包 gate。前端先 `command -v bun`、`bun --version`，在 web 下 `bun run test -- src/components/teleop/act-panel.test.tsx`、`bun run generate:api`、`bun run build`。UI 测试验证操作→请求、运行中互斥、Stop 可用、QC 不通过不能 Keep；使用 gui-capture 的 snapshot→action→fresh snapshot 完成实际录制按钮验收。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_teleop/so101_teleop/act_gateway.py src/so101_teleop/so101_teleop/api.py src/so101_teleop/so101_teleop/server.py src/so101_teleop/so101_teleop/openapi.json src/so101_teleop/web/src/api/schema.d.ts src/so101_teleop/web/src/components/teleop/act-panel.tsx src/so101_teleop/web/src/task-app.tsx src/so101_teleop/test/teleop/test_act_gateway.py src/so101_teleop/web/src/components/teleop/act-panel.test.tsx
git diff --cached --check
git commit -m "feat: expose ACT controls in teleop"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 16: 封存测试、路线比较与操作指南

**Files:**

- Create: `src/so101_demo_py/src/act/evaluation.py`
- Create: `src/so101_demo_py/src/cli/act_evaluate.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_evaluation.py`
- Create: `docs/guides/so101-act-head-wrist-rgb.md`

**Interfaces:** Consumes: 冻结 checkpoint/config/manifest、Task 12A 离线评估入口与 RunResult。Produces: `summarize(results:list[dict])->dict`；CLI `act_evaluate --manifest PATH --split rollout_validation|rollout_test|comparison --bundle PATH --calibration PATH --runtime-config PATH --root PATH --route act|moveit`，输出 JSON/Markdown 报告及逐场景证据索引。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.evaluation import summarize

def test_search_failure_remains_in_denominator():
    runs = [{"search_locked":False,"done":False,"interventions":0,"elapsed_wall_s":1.},
            {"search_locked":True,"done":True,"interventions":0,"elapsed_wall_s":119.}]
    report = summarize(runs)
    assert report["end_to_end"] == .5
    assert report["locked_denominator"] == 1
    assert report["locked_success"] == 1.
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_evaluation.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def summarize(results):
    locked = [r for r in results if r["search_locked"]]
    def success(r):
        return r["done"] and r["interventions"] == 0 and r["elapsed_wall_s"] < 120.
    return {"end_to_end": sum(success(r) for r in results)/len(results) if results else None,
            "locked_denominator":len(locked),
            "locked_success":sum(success(r) for r in locked)/len(locked) if locked else None}
```

先在 Rollout Validation 反复选择 checkpoint/前缀/监督阈值，每次记录结果而非挑最好一轮；参数改变重跑对应控制/校准门。最终冻结全部 hash，按 Task 12A 入口完成 Offline Test 动作误差评估并读取有效 episode/目标数及各关节指标；Rollout Test 至少 10 个初始条件、首次无干预≥70%，包含 ACT 撤离。路线比较至少 20 个共享场景，每次恢复同一初始物理状态，分布内与空间留出分别报；MoveIt 轨迹封存，不回流训练。报告搜索耗时/成功率/居中误差/方位误差、ACT 条件与端到端分母、timeout/失败分布、干预重搜、推理延迟与物理结果。结果无效与有效失败分开，不能把策略碰撞或超时排为环境问题。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_evaluation.py -q
```

预期非零测试收集、全部通过。两个平台分别运行新增 RGB、neck/reset、录制重放及闭环；保留独立物理 pose/contact、controller、Planning Scene shadow（若维护）与新截图。按 so101-dev 附加要求另做固定 checkpoint/config/lifecycle 的连续 5 次有效仿真运行，不能替代封存测试或混算生命周期。指南覆盖安装/校准→录制→训练→验证→测试命令及证据解读，使用 humanizer-zh，不写已掌握。完成报告列 retained/archived/deletion candidates，未授权不删除。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/evaluation.py src/so101_demo_py/src/cli/act_evaluate.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_evaluation.py docs/guides/so101-act-head-wrist-rgb.md
git diff --cached --check
git commit -m "feat: evaluate frozen ACT runs and document workflow"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

## 运行命令与证据交付

下面命令在相应 Task 实现后才可运行，不是当前已经存在的功能。CLI 输出必须是原子写入的报告文件，异常返回非零退出码；所有入口提供 `--help`。单个长命令启动后由已登记的终端/tmux 持有，读取进度与结果作为下一步，不重复启动第二份。

- [ ] 构建与确认新入口；source 顺序按 dependency-lock，读取 package prefix 与可执行文件路径写入账本。

```zsh
colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
ros2 pkg prefix so101_demo_py
ros2 pkg executables so101_demo_py
ros2 launch so101_demo_py so101_mujoco_act.launch.py --show-args
ros2 run so101_demo_py act_session --help
```

- [ ] 运行独立预检。若报告仍有 `CALIBRATION_REQUIRED`，只执行对应测量任务，不开始正式采集。

```zsh
ros2 run so101_demo_py act_preflight --output "$ACT_EVIDENCE/calibration.json"
ros2 run so101_demo_py act_sample --calibration "$ACT_EVIDENCE/calibration.json" --output "$ACT_EVIDENCE/splits.json" --collection-output "$ACT_EVIDENCE/collection.json" --qualification-output "$ACT_EVIDENCE/parallel-qualification.json" --qualification-load-output "$ACT_EVIDENCE/parallel-load.json" --seed 20260911
```

- [ ] 先用 W1 单条入口运行 5 条小批，读取 QC 和重放证据。`act_collect` 的 limit 是总尝试上限，不是成功数量；这个 smoke 使用独立 root，不并入正式数据集。

```zsh
ros2 run so101_demo_py act_collect --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_EVIDENCE/calibration.json" --root "$ACT_EVIDENCE/s" --limit 5 --qualification
```

- [ ] 在独立资格清单上运行完整八场景的单 stack 基线、W1 并行入口和 W2；结果分别写入不同 root。三次均必须使用相同 manifest/calibration/config hash，且这些 episode 不并入正式数据集。

```zsh
ros2 run so101_demo_py act_collect --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_EVIDENCE/calibration.json" --root "$ACT_EVIDENCE/u" --limit 8 --qualification
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_EVIDENCE/calibration.json" --config src/so101_demo_py/config/act/parallel_collection_v1.yaml --root "$ACT_EVIDENCE/q1" --qualification --worker-count 1
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_EVIDENCE/calibration.json" --config src/so101_demo_py/config/act/parallel_collection_v1.yaml --root "$ACT_EVIDENCE/q2" --qualification --worker-count 2
```

`u` 是完整八场景单 stack 基线；前面的 `s` 只用于尽早检查 5 条记录的内容和重放。W1 并行与 W2 的吞吐、成功率和 QC 都与 `u` 比较，不能用 5 条 smoke 作为性能分母。

W2 通过后才按 Task 11A 在 40 场景、两个完整 wave 的持续负载清单上逐档运行 W4/W6/W8；每档使用 `q4`、`q6`、`q8` 短 root，候选默认档位的第二轮使用一个新的总 evidence root，不能覆盖历史结果。所有入口先打印最长 socket 路径与字节数，超过 107 bytes 时不启动任何子进程。选择档位并把两轮资格报告 hash 写入 config/账本后，用短目录 `d` 执行正式采集：

```zsh
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-load.json" --calibration "$ACT_EVIDENCE/calibration.json" --config src/so101_demo_py/config/act/parallel_collection_v1.yaml --root "$ACT_EVIDENCE/q4" --qualification --worker-count 4
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-load.json" --calibration "$ACT_EVIDENCE/calibration.json" --config src/so101_demo_py/config/act/parallel_collection_v1.yaml --root "$ACT_EVIDENCE/q6" --qualification --worker-count 6
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-load.json" --calibration "$ACT_EVIDENCE/calibration.json" --config src/so101_demo_py/config/act/parallel_collection_v1.yaml --root "$ACT_EVIDENCE/q8" --qualification --worker-count 8
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/collection.json" --split-manifest "$ACT_EVIDENCE/splits.json" --calibration "$ACT_EVIDENCE/calibration.json" --config src/so101_demo_py/config/act/parallel_collection_v1.yaml --root "$ACT_EVIDENCE/d"
```

上面三条扩容命令按顺序执行，前一档未通过就不运行后一档。候选默认的第二轮在新建并登记的 evidence root 中只重跑该档；第二轮未通过则回退到前一个已两轮通过的档位，若不存在则不启动正式批采。

正式采集预算从分层有效率估算后写入冻结清单；不在计划中捏造可达区域或假定所有点一次成功。配额不满则报告不足，不能用复制 episode 或业务失败重跑补齐。并行入口完成时在 `d/manifest.json` 写按冻结候选顺序聚合的结果，其中包含 QC、数据 split、Worker/pool generation、infra attempts、surplus 和未调度原因，不导出 Rollout Validation/Test 示教。

- [ ] 使用独立训练 venv 执行离线入口，记录 `sys.executable` 与完整依赖锁。`ACT_TRAIN_PYTHON` 必须解析为该 venv 的实际 Python，先验证 LeRobot/torch 来源；不能沿用 ROS Python 安装训练依赖。

Task 12 先读取 `so101-dev/references/python-dependency-install.md`，按其中的索引规则创建 Python 3.12 训练环境；LeRobot 若声明不支持该版本，应先更新本计划的环境约定，不向 ROS 环境安装。执行阶段的环境创建与锁定命令为：

```zsh
uv venv --python 3.12 "$ACT_EVIDENCE/train-venv"
export ACT_TRAIN_PYTHON="$ACT_EVIDENCE/train-venv/bin/python"
uv pip install --python "$ACT_TRAIN_PYTHON" lerobot
uv pip freeze --python "$ACT_TRAIN_PYTHON" > "$ACT_EVIDENCE/training-resolved.txt"
uv pip install --python "$ACT_TRAIN_PYTHON" --no-deps -e src/so101_demo_py
```

首次安装用于资格检查，Task 12 在训练前把验证通过的精确依赖写入 `config/act/requirements.lock`；随后用该锁重建第二个干净训练环境并重复 smoke，证明可复现。未通过安装/版本资格不得启动正式训练。训练代码不得 import ROS。
```zsh
"$ACT_TRAIN_PYTHON" -c 'import sys,torch,lerobot; print(sys.executable); print(torch.__file__); print(lerobot.__file__)'
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_train --manifest "$ACT_EVIDENCE/d/manifest.json" --config src/so101_demo_py/config/act/training.yaml --output "$ACT_EVIDENCE/models"
```

Task 12 的 CLI 支持 `python -m`，输出 `models/bundle.json`，引用真实 checkpoint 及其 SHA，不用可变的 latest 链接代替封存工件。

- [ ] 冻结模型前运行闭环验证。`act_evaluate` 使用必需参数 `--split rollout_validation|rollout_test|comparison`，缺省拒绝运行，避免误触封存测试。

```zsh
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split rollout_validation --bundle "$ACT_EVIDENCE/models/bundle.json" --calibration "$ACT_EVIDENCE/calibration.json" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/validation" --route act
```

- [ ] 保存封存清单，并实际调用 Task 12A 的离线评估入口。Task 16 的启动核验需确认这些文件是同一已冻结配置，不重新训练或更新归一化统计。

```zsh
"$ACT_PYTHON" - <<'PY_FREEZE'
import hashlib, json, os
from pathlib import Path
root = Path(os.environ["ACT_EVIDENCE"])
artifacts = {
    "bundle_sha256": root / "models/bundle.json",
    "dataset_manifest_sha256": root / "d/manifest.json",
    "split_manifest_sha256": root / "splits.json",
    "calibration_sha256": root / "calibration.json",
    "runtime_config_sha256": Path("src/so101_demo_py/config/act/runtime.yaml"),
}
freeze = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in artifacts.items()}
with (root / "freeze-paths.json").open("x") as stream:
    json.dump({key: str(path.resolve()) for key, path in artifacts.items()}, stream, indent=2)
with (root / "freeze.json").open("x") as stream:
    json.dump(freeze, stream, indent=2)
PY_FREEZE
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_offline_evaluate --manifest "$ACT_EVIDENCE/d/manifest.json" --bundle "$ACT_EVIDENCE/models/bundle.json" --freeze "$ACT_EVIDENCE/freeze.json" --output "$ACT_EVIDENCE/offline-test"
```

freeze 文件采用上述五个 hash 字段，另由同目录的 freeze-paths.json 记录五项实际文件路径；生成 freeze 时一并保存，evaluate_offline 据此读取并校验五项，而非只比较两个文件。不得为记录训练后的 runtime 配置回写原始 dataset manifest。模型内部的 checkpoint 与预处理 hash 由 load_bundle 继续递归核验。输出报告必须显示至少 10 个 Offline Test episode 和有效 mask 计数，缺失报告则 Task 16 不完成。

- [ ] 冻结 checkpoint、执行参数、场景清单与校准报告后运行封存测试及两路线比较。每次 invocation 创建独立子目录；报告保留每场景的首次结果。测试失败后调参必须更换新的封存批次。

```zsh
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split rollout_test --bundle "$ACT_EVIDENCE/models/bundle.json" --calibration "$ACT_EVIDENCE/calibration.json" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/test" --route act
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split comparison --bundle "$ACT_EVIDENCE/models/bundle.json" --calibration "$ACT_EVIDENCE/calibration.json" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/comparison-act" --route act
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split comparison --bundle "$ACT_EVIDENCE/models/bundle.json" --calibration "$ACT_EVIDENCE/calibration.json" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/comparison-moveit" --route moveit
```

## 执行中必须解决的测量门槛

这些是实验输出，不是可用任意默认值替代的实现空缺。每项均有负责 Task、测量办法与拒绝条件。

| 工件 | 负责 Task | 测量/冻结办法 | 不通过时 |
| --- | --- | --- | --- |
| 相机安装与视野 | 3、6 | 全阶段专家轨迹、新双视角图像、标定投影误差、碰撞几何 | 调整安装后重做预检，不采数据 |
| 轻量检测器与阈值 | 5、6 | head 视角含无杯/多杯/遮挡的独立校准图；冻结模型来源、hash 与误差报告 | 无合格候选则停在搜索资格，不绕到真值检测 |
| controller 定时能力 | 7 | 10 Hz 重放的 reference/joint 对齐、部分接受取消与停止速度测量 | 不放宽标签时间语义、不平移迟到目标 |
| 持物/释放/路径检查 | 8 | 新鲜双侧接触/离台/支撑证据、已知非法路径及悬空开爪故障注入 | 无有效 permit，不交付 ACT execute |
| LeRobot 版本和 GPU/CPU 能力 | 12、13 | 执行时锁版本，导出/训练/推理 smoke 与真实延迟分位数 | 标训练或部署未合格，不报平台通过 |
| 数据空间隔离与规模 | 10、11、11A | 实际 XY 距离、冻结候选预算、分层配额、全轨迹预检和物理结果 | 报 QUOTA_UNSATISFIED，不复用封存位置或重跑业务失败 |
| ACT 采集并发档位 | 11A | 8 场景验证 W1/W2 功能；40 场景两个完整 wave 逐档测 W4/W6/W8，候选默认再独立复测；记录有效 episode/分钟、CPU/RSS/GPU/磁盘、RTF、帧间隔、QC 与物理成功率 | 使用两轮都通过全部门槛的最高吞吐档位；未通过 W2 则只保留 W1，不启动正式并行采集 |

## 自审：设计覆盖与一致性

| 设计章节 | 负责 Task | 检查结论 |
| --- | --- | --- |
| 1–3 目标、分工、输入边界 | 1、12–14 | 双 RGB/8→6、独立搜索与混合监督，原主线保留 |
| 4 模型与视野 | 2、3、6 | RGB-only、neck、名称映射、两平台、原 RGB-D 回归 |
| 5 搜索和方位 | 5、6、14 | 360°预算、身份一致、几何方位、过期失效与控制权 |
| 6 观测/action | 1、4、7、13 | 因果采样、前缀时间、双控制器、异步取消 |
| 7 示教 | 9、11、11A | 实际 reference、10 Hz、释放/撤离尾段、失败保留、并行封存与确定性汇总 |
| 8 随机区域 | 3、6、10 | 每实际点预检、分层拒绝统计与初始关节扰动 |
| 9 数据/泛化 | 10–12、12A、16 | 五集合隔离、冻结候选、资格数据排除、闭环调参、70%与20场景比较 |
| 10 安全/恢复 | 3、7、7A、8、13、14 | 120 s 墙钟、路径碰撞、支撑开爪、release epoch、最多1次重搜 |
| 11 组件/Teleop | 2、3、11A、12、14、15 | 子模块锁、领域/adapter、复用并行基础设施、训练隔离、界面命令 |
| 12 校准顺序 | 6–8、10–13 | 分阶段测量，W1/W2 资格和完整 QUALIFIED 后才正式并行采集 |
| 13 验收证据 | 11A、16及全局 gate | 并发正确性与吞吐分开、各层结果独立、两平台、原始证据与删除约束 |
| 14 本地依据 | 基线、Files 与 Worker Pool 指南 | 已查合入实现和限制，新路径均标 Create |

执行前还需将所选工作树与本计划基线比对；文件有改名时先更新计划路径再实现。每个任务的代码片段只规定核心边界，完整交付必须通过该任务失败矩阵与运行门，不能把 smoke test 通过当作整任务完成。

本次交付仅为实施计划，所有 checkbox 保持未勾选；没有运行相机、示教、训练或机器人验收，也没有提交或推送代码。

## Astra high 审查修订记录（2026-09-11）

| 审查问题 | 修订位置 | 新验收证据 |
| --- | --- | --- |
| P1 全机器人接触缺失 | Task 8 Step 3a：新消息、support plugin、observer | 不含杯子的实际碰撞、截断/丢帧均触发双方停止 |
| P1 公共仲裁缺失 | Task 7A，Task 14/15 复用 | ACT 持有 lease 时教师/Teleop 跨入口提交拒绝 |
| P2 reset 只读不写 | Task 3 Step 3a，Task 10 | 七关节 override 序列化、两个实际初态读回、旧六关节兼容 |
| P2 推理环境断点 | Task 12 load_policy、Task 13 Step 3a | 无 LeRobot 的 ROS 环境与独立 worker 的真实进程 smoke |
| P2 Offline Test 无入口 | Task 12A、Task 16、运行命令 | 冻结 hash、10 episode、padding mask 与动作误差报告 |

## Astra high 并行采集审查修订记录（2026-09-16）

| 审查问题 | 修订位置 | 新验收证据 |
| --- | --- | --- |
| P1 搜索放入 initial gate 会被误判为 infra，且后续重复 reset | Task 11 分阶段接口；Task 11A Step 3a | 每 attempt 一次 reset；搜索失败封存为业务 `FAILED` 且不 fallback；旧 reset epoch/pose 拒绝 |
| P1 production 子进程缺少 ACT ports 与恢复 verifier 注入口 | Task 11A Files、workload factory、result store/verifier | 旧 spec 默认行为回归；真实 ACT 子进程构造；seal 后 ACK 前崩溃由 `discover` 恢复 |
| P2 资格目录超过 Unix socket 长度 | Task 11A 短目录合同、运行命令 | 真实绝对根枚举全部 socket，编码长度不超过 107 bytes，超限零进程启动 |
| P2 配额选择受 Worker 完成顺序影响 | Task 11A 完整 wave 屏障与 manifest 前 N 规则 | 乱序完成仍选择相同 `scene_id`；surplus/unscheduled 有明确状态 |
| P2 qualification schema 与正式 split 冲突 | Task 10、11、11A qualification mode | 两种模式互斥白名单；资格结果不能生成 Task 12 输入 |
| P2 8 场景不足以证明 W8 持续负载 | Task 11A Step 5–6、测量门槛 | 8 场景只验 W2 功能；40 场景形成两个完整 wave、每 wave 每 Worker 至少 2 项、候选默认全新 root 复测 |
| 第二轮 P1：已启动未终态的 AdaptiveBatchRunner 只能报告，外层无续跑协议 | Task 11A `ActWaveReconciler` | 旧资源先 fencing；verify/discover 后导入；累计 infra budget 分组 continuation；外层导入前崩溃测试 |
| 第二轮 P2：五集合总清单与三 split 采集白名单冲突 | Task 10 collection 投影、运行命令 | `splits.json` → `collection.json` hash 贯通；Rollout 集合不调度；正式入口只读投影 |
| 第二轮 P3：preferred 项可被 stealing，不能写成静态保证 | 设计第 7 节、Task 11A Step 6 | 初始优先分配；按每个 Worker 实际 terminal lease 验收 |
| 第三轮 P2：崩溃对账可能导入 durable expiry 后的迟到 seal | Task 11A 对账优先级 | expiry/revocation/replacement/late rejection 优先；seal 完成时间不超过 lease deadline；专门故障测试 |
| 第三轮 P2：降级完成可能误算被测档位资格 | Task 11A Step 5–6 | 每个资格 wave 固定 `levels_used == [n]`，零 infra retry/fallback/continuation；降级只作恢复证据 |
| 第三轮 P2：socket 预检遗漏 Task 7A command broker | Task 11A `act_parallel_socket_paths` | adaptive 与每 Worker `ipc/<index>/a` 共用启动/清理/恢复清单；全清单 107/108-byte 边界测试 |
| 第三轮 P3：缺完整八场景单 stack 命令 | 运行命令 `u` root | 5 条 smoke 与 8 条性能基线分开，W1/W2 都与完整基线比较 |
| 第三轮 P3：Task 14 重复标 Create | Task 14 Files | `so101_mujoco_act.launch.py` 改为 Modify，保留 Task 3 Create |
| 第四轮 P3：无法构造“只有新增短端点超长”的测试 | Task 11A socket 故障矩阵 | 改为端点包含性、三类消费者同集合，以及全清单最长路径 107/108-byte 边界 |

本次修订仅更新设计与实施计划，以上均为待执行要求，不表示相应测试、采集或运行验收已通过。历史审查记录对应各轮修订前的文件 hash，保留原记录，不覆盖历史结论。

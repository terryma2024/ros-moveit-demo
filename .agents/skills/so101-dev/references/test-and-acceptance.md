# 修改、测试与验收

## 修改前

1. 记录本地根仓、`moveit-demo` 子模块和 ai-station workspace 的 dirty files，并把本轮根因绑定到一个拥有该行为的最小代码边界。
2. 先写自动化回归测试并运行到预期失败。缺陷只能 live 重现时，先保存失败复现、退出码和前后状态断言，再补最接近边界的单测或 launch contract。
3. 修改范围只覆盖根因，不顺手格式化、重构或修无关问题；不运行 `ament_uncrustify --reformat`。

测试要证明机器人边界条件，不是覆盖实现细节。典型断言：state success 后必须有对应 attachment evidence；joint trajectory success 必须与目标 joint set 和反馈契约一致；detach 后 Gazebo 与 Planning Scene 各自收敛到正确状态。

## 构建与 package 测试

需要新增或修复同时运行于 macOS 与 Linux 的 Python testcase 时，先读 [`docs/guides/so101-python-test-portability-macos-linux.md`](../../../../docs/guides/so101-python-test-portability-macos-linux.md)，其中记录了临时目录、Unix socket、进程身份、可选 ML 依赖和 xdist 并行隔离的已验证模式。

ai-station 的 Linux 包级测试在 ROS-only zsh 中跑标准 `colcon test`。跑 pytest 或 `colcon test` 之前，必须先按 [测试证据与 scratch 契约](#测试证据与-scratch-契约) 建好 NVMe scratch 并导出 `TMPDIR`/`TMP`/`TEMP`，否则不要开始：

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_cpp --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select so101_gazebo_demo_cpp \
  --event-handlers console_direct+
colcon test-result --verbose
```

修改 CMake/install rules、launch/config 安装内容，或怀疑缓存污染时，加 `--cmake-clean-cache` 重新构建；不要用全 workspace build 掩盖 package 级失败。定向测试先行，包级测试随后，精确测试名从当前 `CMakeLists.txt`、`colcon test-result --all` 或 build 目录发现，不从旧记录猜。确认 `ros2 run` 实际执行安装产物的命令见 [`so101-system-map.md`](so101-system-map.md) 的“安装产物陷阱”。

### 测试范围

- `so101_demo_py` 的普通门禁只收集 `src/so101_demo_py/test/`，不得收集 `src/so101_demo_py/benchmark_test/`。这条路径只属于 `so101_demo_py`，其他模块（例如 `so101_teleop`、`pick_place_common`）按各自 package 声明的测试范围收集。
- `benchmark_test/` 不属于任何普通门禁，只在改动 benchmark 实现、配置、adapter、报告或测试，或选择、比较感知模型时显式运行：`colcon test --packages-select so101_demo_py --pytest-args benchmark_test`。普通功能工作不跑 benchmark。
- 普通门默认排除标记 `explicit_ml` 的 Torch/SAM 集成用例；用本任务登记的精确 Python 单独验证：`"$TEST_PYTHON" -m pytest -m explicit_ml src/so101_demo_py/test/test_sam_decoder_runtime.py`。

## 全量 pytest 并行门禁

每个模块的完整普通 pytest 范围都必须使用 `pytest-xdist`，worker 数固定为 `min(8, os.cpu_count() or 1)`：逻辑 CPU 数大于 8 时用 8 个，不大于 8 时用实际逻辑 CPU 数。先记录逻辑 CPU 数、worker 数、内存和并发负载；资源不足时停止并说明门禁未完成，不能降低并行度来宣称通过。这里的 worker 数与产品 WorkerCount、exact-N 预算及测量或运行授权无关，不能据此宣称产品支持 N=8。

用任务登记的精确 Python 核验 `pytest`、`xdist` 版本和模块来源。定向或串行测试只提供诊断证据，不能代替全量并行门禁；不得忽略失败、删除测试或缩小收集范围。`--dist loadscope` 和 marker 本身不是跨 worker 的锁。

并行前列出共享固定端口或 socket、`ROS_DOMAIN_ID`、`GZ_PARTITION`、外部进程或服务、全局文件或环境、GPU 及其他主机资源的测试；发现冲突时修复隔离，再用相同 worker 数重跑该模块的完整范围。

对实际由 `ament_python` 驱动 pytest 的包，核验子进程 argv 后可用 `colcon test --packages-select so101_demo_py --pytest-args test -n "$workers"`，仍保留普通 `test/` 范围并核验实际子进程 worker 数。`ament_cmake` 的 CTest 和 ament pytest 不保证接收该参数，从 `CTestTestfile.cmake` 和实际命令确认后再选兼容方式，不要让多个 CTest case 各开 8 worker 导致超订阅。直接整包 pytest 可以加速反馈，但在 ai-station 上不替代必要的 CTest 登记、package gate、`colcon test-result` 和 provenance gate。此指引不授权 benchmark 或 live 测量。

macOS 的普通 package test、固定 venv 和 overlay 加载顺序见 [`macos-runtime-environment.md`](macos-runtime-environment.md)；只有失败指向 Python、overlay、package prefix、SIP、`DYLD_*` 或 `@rpath/*.dylib` 时才用它的 dylib/SIP 诊断分支。

## 测试证据与 scratch 契约

这一节是 xdist、NVMe scratch 和 test-evidence 契约的唯一详细出处，`SKILL.md` 和 `macos-runtime-environment.md` 只引用它。

依赖只在已授权的环境里安装并记录版本；缺依赖又没拿到安装权限时报告依赖门，不改共享或 global 环境。macOS 的 `/opt/ros/jazzy/.venv` 是实际运行时契约，不能悄悄换解释器。

**ai-station 专用**：任何会创建 fsync-heavy 临时 fixture 的 pytest 或 benchmark 运行，都必须在本 task 已登记的持久 evidence root 下新建独一无二、此前不存在的 scratch 目录，例如 `/data/work/so101-evidence/<task-family>/<run-id>/scratch/<test-run-id>/tmp`。所有 worker 都要继承该 `TMPDIR`/`TMP`/`TEMP`。下面的示例先设置真实已登记的 `TASK_ROOT` 和 `TEST_PYTHON`，并加载验证过的 ROS、依赖和 task overlay：

```zsh
test -d "$TASK_ROOT/scratch" && test -x "$TEST_PYTHON" || exit 1
logical_cpus=$("$TEST_PYTHON" -c 'import os; print(os.cpu_count() or 1)') || exit 1
test "$logical_cpus" -ge 1 || exit 1
workers=$(( logical_cpus > 8 ? 8 : logical_cpus ))
print -r -- "logical_cpus=$logical_cpus pytest_workers=$workers"
pytest_run_dir=$(mktemp -d "$TASK_ROOT/scratch/pytest-xdist8.XXXXXXXX") || exit 1
mkdir "$pytest_run_dir/tmp" || exit 1
export TMPDIR="$pytest_run_dir/tmp" TMP="$pytest_run_dir/tmp" TEMP="$pytest_run_dir/tmp"
"$TEST_PYTHON" -c 'import os,pathlib,sys,tempfile,pytest,xdist; actual=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); print("python=",sys.executable,"pytest=",pytest.__version__,pytest.__file__,"xdist=",xdist.__version__,xdist.__file__,"temp=",actual); assert actual == expected' \
  > "$pytest_run_dir/tempfile-proof.log" 2>&1 || exit 1
"$TEST_PYTHON" -m pytest src/so101_demo_py/test -n "$workers" \
  --junitxml="$pytest_run_dir/junit.xml"
```

tempfile 证明必须用任务的精确 Python 做，`tempfile.gettempdir()` 不落在 scratch 内就 fail closed。colcon 的每个实际测试 interpreter 都要单独保存带 executable 和 origin 标签的 tempfile proof，不能只验证控制器 Python，也不能复用旧 run 的证明，还要确认 xdist worker 自己的临时目录仍在 scratch 内。

保留 fsync、完整测试覆盖和所有失败 run；不换 `/tmp` 或 tmpfs，不关闭 journaling 或 integrity checks。记录 scratch 路径、elapsed 时间和退出码，读回后把 scratch 树列为删除候选，未获授权不删除。对每个模块分别运行完整普通测试目录，不能因跨包重名模块把两个目录混在一条 pytest 命令里。

evidence root 的路径规则和短任务、长程任务的登记方式见 `SKILL.md` 的“证据根”一节；日志、JUnit、截图和构建产物都放在登记 root 内，不写进源码目录。

## 运行时测试阶梯

按风险从低到高：单元或 contract test → `run_mode:=dry_run` 的全状态与失败恢复 → `run_mode:=plan_only` 的规划证据 → headless Gazebo 或 MuJoCo live test → GUI 仿真 `run_mode:=execute`（只有仿真 stack 与安全门控明确后才用）→ 真实机械臂（仅在用户明确授权和硬件安全门控后）。

常用入口需先 `--show-args` 复核当前版本；execute 调试时先用 `stop_after:=<STATE>` 把动作缩到首个失败边界，不要一上来就反复跑完整 pick-place：

```bash
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py --show-args
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py \
  run_mode:=dry_run start_simulation:=false
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py \
  run_mode:=plan_only start_simulation:=true headless:=true \
  'simulation_session_id:=<unique-id>'
```

## 按状态验收

状态名和转移以当前 `so101_workflow.cpp` 与 `transition_table.cpp` 为准；下表覆盖 normal forward path 和 recovery。

| 状态或边界 | 最小运行时证据 |
|---|---|
| MOVE_ABOVE_OBJECT / DESCEND / LIFT / MOVE_ABOVE_PLACE / DESCEND_TO_PLACE / RETREAT | plan 有效；execute result 成功；目标 joints 完整；`/joint_states` 和 TCP 有符合方向的前后变化 |
| PREPARE_OPEN_GRIPPER / CLOSE_GRIPPER / OPEN_GRIPPER | gripper action result；夹爪 joint feedback；视觉开合状态 |
| WAIT_GRASP_STABLE / MICRO_LIFT / WAIT_MICRO_LIFT_STABLE / VERIFY_PHYSICAL_GRASP | 接触或 physical grasp 证据；micro-lift 前后物体 pose；`VALIDATION_FAILED` 的 force-continue 语义 |
| ATTACH_MOVEIT | 物体从 world collision 集合进入 attached 集合；attached link 和 touch links 正确；attachment 只是 planning shadow |
| DETACH_MOVEIT | attached 集合移除；`WAIT_RELEASE_SETTLE` 与 `VALIDATE_FINAL_PLACEMENT` 只消费当前 release epoch |
| SYNC_WORLD_OBJECT | world object 以最终 Gazebo pose 恢复 |
| DONE | 上述受影响边界全部通过；退出码正确；最终 Gazebo 或 MuJoCo 画面与状态查询一致 |
| ATTACH_GAZEBO / DETACH_GAZEBO | normal forward path 不经过这两个状态；只在 reset 建立 canonical state 的防御性 detach 或异常 attachment 排查时取证 |
| RECOVER_* / ERROR | 失败后只撤销已产生的副作用，最终状态可解释，错误路径返回非零退出码 |

## 视觉验收

截图与 GUI 控制按 `$gui-capture` 路由；tmux 环境、分屏命令、`LAYOUT_OK` 判据和截图新鲜度要求见 [`ai-station-access.md`](ai-station-access.md)，macOS 的启动入口见 [`macos-runtime-environment.md`](macos-runtime-environment.md)。

本轮跑过 GUI 仿真或有其他可见结果时，要有一张本轮 build 对应的 baseline 截图和一张动作后的新截图，都落在本 task 已登记的 evidence root 内，并由 agent 实际查看图像内容。纯 headless、Web 后端或无可见输出的改动不强制截图，但要在报告里写 N/A 和原因；Web 前端等有可见输出的改动仍要新截图。一旦涉及 GUI 验收，截图与数据状态必须共同验收：描述机械臂姿态、夹爪开合、物体初末 pose、是否穿透或掉落、Planning Scene 显示是否一致，同时至少保留一个数值证据，例如物体 6D pose 或关节、TF 前后差值，防止相机角度造成误判。

## 最终报告模板

```text
Root cause: CONFIRMED | NOT CONFIRMED
First bad boundary:
Evidence:
Change:
RED test:
GREEN/package tests:
Runtime command and exit code:
Gazebo proof:
MoveIt proof:
Controller/joint/TF proof:
Visual proof and screenshot path:
Preserved user changes:
Remaining risks / next exact command:
```

任何空白项都表示不能笼统宣布“完整修复”。

## Physical outcome acceptance

Policy 仍含 `CALIBRATION_REQUIRED` 时不得宣称 live success。记录 runtime provenance、隔离的 `ROS_DOMAIN_ID`/`GZ_PARTITION`/overlay、cleanup ownership，以及独立的 Gazebo pose 与 support contact（两者都要，不能用其中一个代替另一个）、MoveIt shadow/detachment/world sync、controller health 和 fresh GUI screenshot evidence。必须有连续五次有效运行；中间随机样本作为 bounded distributions 保留，不要求完全相同。最终失败必须先保存 observed outcome，再开始独立 reset 事务。

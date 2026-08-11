# SO-101 + MuJoCo + ROS 2 集成执行指南

> 更新时间：2026-08-11
> 适用分支：`codex/so101-mujoco-ros2`
> 本文校准基线：`dfc03d3`
> 工作区：由 checkout 决定；`SO101_WORKSPACE_DIR` 只指定其外部工作目录。
> 当前结论：MuJoCo 模型、`ros2_control`、MoveIt 规划/执行、reset 事务、模型可视化、零位稳定保持和四角 viewer debug camera 已分别通过验证；真实夹取接触、最终放置、重复性和 clean shutdown 尚未完成。

## 1. 这份指南解决什么问题

本文说明如何在不污染 `so101_gazebo_demo_py` 的前提下，把现有 SO-101 Gazebo demo 的机器人语义、MoveIt 边界和 pick-place 状态机迁移到 MuJoCo，并总结迁移过程中实际遇到的故障、错误判断和修复方法。

这里的“集成成功”分为四层，不能互相替代：

1. **静态结构通过**：包隔离、URDF/MJCF、配置和 provenance 正确。
2. **仿真运行通过**：MuJoCo、`ros2_control`、关节状态和原子证据能持续运行。
3. **运动闭环通过**：MoveIt 能规划，控制器能执行，TCP 和关节误差满足门限，执行后能稳定保持。
4. **物理任务通过**：左右指尖形成真实接触，杯子被抬起、搬运、释放并稳定落到目标区；无 weld、teleport 或隐藏约束。

目前已经达到第 3 层。第 4 层仍在 Task 13–15 中。

## 2. 不可破坏的迁移边界

### 2.1 Gazebo 包是只读行为基线

迁移实现使用两个独立包：

- `so101_mujoco_demo_py`：`ament_python`，包含 workflow、MoveIt 客户端、MuJoCo observer/reset 客户端、MJCF、URDF、配置和测试。
- `so101_mujoco_support`：`ament_cmake`，包含 `SimulationEvidence`/`ContactSample` 消息和 MuJoCo evidence plugin。

禁止把实现混入 `src/so101_gazebo_demo_py/**`。MuJoCo 包也不能在 package metadata、Python import 或运行时 package-share lookup 中依赖 Gazebo 包。复制或适配的模型和逻辑必须在 `docs/provenance.json` 记录来源 commit、原路径、目标路径、哈希和适配说明。

隔离门：

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git status --short -- src/so101_gazebo_demo_py
git diff --exit-code -- src/so101_gazebo_demo_py
```

任一命令失败就停止，不允许先改 Gazebo 包、以后再补回。

### 2.2 保留上层语义，替换仿真器边界

需要保留：

- 状态机的 state 名称、run mode、failure code、checkpoint 语义。
- MoveIt planning group `arm`、TCP link `so101_tcp`。
- 关节名 `1`–`6`。
- `arm_controller`、`gripper_controller`、`joint_state_broadcaster` 映射。
- Planning Scene attachment 仅作为碰撞 shadow，不能伪造物理抓取。

需要替换：

- Gazebo transport、world pose/contact topic、world reset。
- `gz_ros2_control`。
- Gazebo SDF/URDF 动力学实现。

替换为：

- 提交到仓库的 MuJoCo MJCF。
- 固定版本并打最小 reset hook patch 的 `mujoco_ros2_control`。
- 一帧一个锁内快照的 atomic simulation evidence。
- 有 epoch/session/step 身份的 transactional reset。

### 2.3 严格物理合同

执行阶段禁止：

- `<equality>`、weld、adhesion、mocap-follow。
- 在 execute 期间 teleport 杯子。
- 直接写杯子的 `qpos`/`qvel`。
- 把 MoveIt attached collision object 当成物理附着证据。
- 用单个截图、topic 存在、日志中的 `DONE` 代替真实接触和位姿证据。

## 3. 目标架构

```text
MoveIt 2 / move_group
        |
        | FollowJointTrajectory / ExecuteTrajectory
        v
ros2_control controllers
        |
        v
pinned mujoco_ros2_control 0.0.3 + reset snapshot patch
        |
        +-------------------- MuJoCo MJCF physics
        |
        +--> SimulationEvidencePlugin -- /so101/simulation/evidence
                                             |
                                             v
                                  MujocoWorldObserver

workflow / reset coordinator
        |
        +--> pause/reset services
        +--> fresh joint-state gate
        +--> session + epoch + step evidence gate
        +--> MoveIt planning/execution
        +--> physical outcome evaluation
```

URDF 仍是 MoveIt、TF 和 controller joint semantics 的来源；MJCF 是实际视觉、碰撞、惯性、接触和动力学的来源。运行时从 URDF 自动转换 MJCF 被禁止，因为转换结果会随工具版本变化，也无法精确审查碰撞和执行器参数。

## 4. 固定依赖与环境

### 4.1 当前唯一认可的 fork 依赖

当前运行依赖是项目 submodule 固定的 Gitee fork，不再运行时重放 patch：

- Gitee fork：`git@gitee.com:zjumty/mujoco_ros2_control.git`
- 官方基线：`https://github.com/ros-controls/mujoco_ros2_control.git`，tag `0.0.3`，commit `35ba8174b62d9560093614f981a3d4b978a96036`
- 当前 fork release：以 `dependency-lock.yaml` 的 immutable `so101-0.0.3-r*` tag 和 commit 为准；release commit 必须保留官方基线为祖先。
- 项目 pin：`third_party/mujoco_ros2_control` gitlink 与 schema-3 lock 必须指向同一 fork commit。

不得跟随浮动 branch、覆盖 `/opt/ros/jazzy`、把源码复制进项目包，或只凭 `ros2 pkg prefix` 判断二进制 provenance。

### 4.2 可迁移工作目录和安装

checkout 后只需选择外部工作目录；未指定时，安装器使用当前 repo 根目录的父目录：

```zsh
cd /path/to/so101-mujoco-ros2

# 可选；省略时等价于 repo 的父目录。
export SO101_WORKSPACE_DIR=/path/to/workspace

git submodule update --init third_party/mujoco_ros2_control
zsh scripts/install-mujoco-ros2-control.zsh
```

安装器从自身位置解析 repo 根目录，而不是依赖调用者的当前目录。fork 的 build/install/log 位于
`${SO101_WORKSPACE_DIR:-<repo-parent>}/ws_mujoco_ros2_control_fork/`；lock 只保存逻辑相对路径，
不保存某台机器的 checkout 绝对路径。`--init-submodule` 可让安装器初始化尚未初始化的 submodule。

安装会 fail closed 地验证 Gitee origin、gitlink commit、release tag、官方 0.0.3 ancestry、clean submodule，
然后构建并测试 `mujoco_ros2_control_msgs`、`mujoco_ros2_control_plugins` 和
`mujoco_ros2_control`。当前流程没有 patch replay；`src/so101_mujoco_demo_py/patches/` 下的旧 patch
及 `ws_mujoco_ros2_control_003` 只用于历史审计/回滚，不得计入当前 qualification。

### 4.3 source 顺序和 provenance read-back

从新的 zsh 严格按 underlay → fork overlay → project overlay source：

```zsh
cd /path/to/so101-mujoco-ros2
export SO101_WORKSPACE_DIR=${SO101_WORKSPACE_DIR:-${PWD:h}}

source /opt/ros/jazzy/setup.zsh
source "$SO101_WORKSPACE_DIR/ws_mujoco_ros2_control_fork/install/setup.zsh"
source "$PWD/install/setup.zsh"

for package in mujoco_ros2_control mujoco_ros2_control_msgs mujoco_ros2_control_plugins; do
  ros2 pkg prefix "$package"
done
ros2 pkg prefix mujoco_vendor

python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
```

前三个 package prefix 必须等于
`$SO101_WORKSPACE_DIR/ws_mujoco_ros2_control_fork/install`，`mujoco_vendor` 必须仍来自
`/opt/ros/jazzy`。checker 还会验证接口、头文件、shared libraries、runtime executable 的哈希，
以及项目 package prefix。不要在 ROS generated setup 脚本周围启用 shell `nounset`。

### 4.4 历史 patched-overlay 流程（已废弃，仅供审计和回滚）

以下 `_003` 内容记录旧实现路线，已被上面的 Gitee fork submodule 工作流取代。不得执行旧 build
脚本或 patch replay 来完成当前安装、测试或资格化；需要回滚时也必须在独立新 shell 中明确选择旧
overlay，不能与当前 fork overlay 混合 source。

这里的“替代”是 ROS overlay shadow，不是卸载或覆盖 apt 文件：

```text
project install
      ↓
/data/work/ws_mujoco_ros2_control_003/install   <- patched source 0.0.3
      ↓
/opt/ros/jazzy                                 <- apt underlay 0.0.3 + mujoco_vendor
```

apt 安装继续留在 `/opt/ros/jazzy`，但新 shell 按正确顺序 source 后，`mujoco_ros2_control`、`mujoco_ros2_control_msgs` 和 `mujoco_ros2_control_plugins` 都解析到 patched overlay。`mujoco_vendor` 仍预期解析到 `/opt/ros/jazzy`。不要运行 `apt remove`，也不要向 `/opt` 复制自编译文件。

#### 步骤 1：确认仓库提供的固定输入

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2

git rev-parse HEAD
sha256sum \
  src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch
sed -n '1,180p' src/so101_mujoco_demo_py/config/dependency-lock.yaml
```

本文基线要求：

```text
upstream URL    https://github.com/ros-controls/mujoco_ros2_control
tag             0.0.3
commit          35ba8174b62d9560093614f981a3d4b978a96036
patch SHA-256   fd2869212d40809dca70f4cc971f93215a64812900cc992817305a33dfcf971e
source checkout /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control
install prefix  /data/work/ws_mujoco_ros2_control_003/install
```

这些值以当前 `dependency-lock.yaml` 为准。如果 lock、patch 或脚本发生有意更新，应先审查新值，不要为匹配本文硬改 checkout。

#### 步骤 2：构建 patched dependency overlay

推荐只使用仓库脚本：

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
bash src/so101_mujoco_demo_py/scripts/build_reset_qualified_overlay.sh
```

脚本内部使用 bash 并 source `/opt/ros/jazzy/setup.bash`，所以从 zsh 调用它时仍应写 `bash <script>`。它会自动完成：

1. 如果 checkout 不存在，从官方 URL clone，但不跟随 floating branch。
2. fetch 并 detached checkout 固定 commit。
3. 确认 tag `0.0.3` 正好指向这个 commit。
4. 确认 checkout 为 clean，或者 working-tree diff 恰好等于批准的 patch。
5. 通过 `git apply --unidiff-zero --check` 后应用 patch。
6. 用 `colcon` 构建三个包到独立 merge-install prefix。
7. 运行三个依赖包的测试，并通过 `colcon test-result --verbose` 收口。

脚本会 fail closed。checkout 含 untracked 文件、额外修改、错误 remote、错误 commit、错误 tag 或 patch 无法精确应用时都会退出。遇到这些情况先保存并审查 `git status`/`git diff`；不要用 `git reset --hard`、`git clean` 或重新覆盖目录来强行通过。

#### 步骤 3：理解 patch 增加了什么

patch 只修改 pinned upstream 的三个文件，并包含相应 upstream test：

- plugin base 增加默认 no-op `on_reset()`。
- plugin base 增加默认 no-op `on_pause(bool)`。
- plugin base 增加默认 no-op `on_state_snapshot(model, data, paused)`。
- central reset 成功后通知所有 plugin 的 `on_reset()`。
- `SetPause(true)` 在 `sim_mutex_` 内用 authoritative `mjModel`/`mjData` 调用一次 snapshot hook。
- 幂等的第二次 `SetPause(true)` 仍产生恰好一个新 snapshot；`SetPause(false)` 不产生 snapshot。
- snapshot 路径不得调用 generic `update()`，也不得改变 `qpos`、`qvel`、`ctrl` 或 applied force。
- authoritative model/data 不可用时，pause request 失败且不调用任何 plugin hook。

这正是 Task 10 reset 事务需要、而 apt 0.0.3 缺少的边界。patch 没有改变 MuJoCo physics stepping、controller 算法或 SO-101 模型。

可读回 source provenance：

```zsh
git -C /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control \
  remote get-url origin
git -C /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control \
  rev-parse HEAD
git -C /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control \
  tag --points-at HEAD
git -C /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control \
  status --short --untracked-files=all
git -C /data/work/ws_mujoco_ros2_control_003/src/mujoco_ros2_control \
  diff HEAD --binary --unified=0 | sha256sum
```

最后一个 SHA-256 必须等于 lock 中的 patch hash；`status` 应只显示 patch 对应的三个 tracked-file modifications，不能有 `??` 或第四个修改文件。

#### 步骤 4：在新 shell 中切换 provider

不要在一个已经混合 source 过多个工作区的 shell 中继续叠加。打开新 zsh 后执行：

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh

for package in \
  mujoco_ros2_control \
  mujoco_ros2_control_msgs \
  mujoco_ros2_control_plugins \
  mujoco_vendor
do
  printf '%-36s %s\n' "$package" "$(ros2 pkg prefix "$package")"
done
```

必须得到：

```text
mujoco_ros2_control          /data/work/ws_mujoco_ros2_control_003/install
mujoco_ros2_control_msgs     /data/work/ws_mujoco_ros2_control_003/install
mujoco_ros2_control_plugins  /data/work/ws_mujoco_ros2_control_003/install
mujoco_vendor                /opt/ros/jazzy
```

再检查 overlay 是否出现在 underlay 之前：

```zsh
printenv AMENT_PREFIX_PATH | tr ':' '\n' | \
  rg 'ws_mujoco_ros2_control_003|/opt/ros/jazzy'
```

输出中 dependency overlay 必须位于 `/opt/ros/jazzy` 之前。只看到 apt prefix 表示新 shell 没有 source patched overlay；同时看到两个 prefix 但顺序相反表示 source 顺序错误。

#### 步骤 5：重新构建 SO-101 项目

provider 发生变化后必须清理项目的 CMake cache 并重新构建，否则 `so101_mujoco_support` 可能继续使用之前从 apt 找到的 plugin header：

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_003/install/setup.zsh

colcon build \
  --base-paths src \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --symlink-install \
  --cmake-clean-cache

source install/setup.zsh
```

如果标准 `build/`/`install/` 中有用户工作或不可解释的 artifact，先停止并审查；不要 broad delete。可先按第 5.1 节使用 `/tmp` 隔离 build 验证，但完整 lock checker 有意要求标准 worktree `install/`，最终 qualification 仍需 canonical build。

#### 步骤 6：运行完整 provenance checker

保持三个 overlay 都已经 source：

```zsh
cd /path/to/so101-mujoco-ros2
export SO101_WORKSPACE_DIR=${SO101_WORKSPACE_DIR:-${PWD:h}}
source /opt/ros/jazzy/setup.zsh
source "$SO101_WORKSPACE_DIR/ws_mujoco_ros2_control_fork/install/setup.zsh"
source install/setup.zsh

python3 src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml \
  --check-only
```

该 checker 不只检查 package prefix，还验证：

- upstream URL/tag/commit。
- checkout diff 与 patch SHA-256 完全一致。
- patched header 中三个 hook 确实存在。
- dependency overlay 先于 ROS underlay。
- SO-101 两个项目包来自当前 worktree 的标准 install。
- installed header、两组 shared libraries 和 `ros2_control_node` 的 SHA-256 与 lock 完全一致。

checker 输出一份 JSON 且 exit code 为 0 才算 provider 切换完成。`ros2 pkg prefix` 正确但文件 hash 不匹配仍然是失败，通常表示 install stale 或 build 后 lock 尚未经过资格化更新。

#### 步骤 7：确认运行入口不会回到 apt

在启动仿真前做最后一次 read-back：

```zsh
test "$(ros2 pkg prefix mujoco_ros2_control)" = \
  /data/work/ws_mujoco_ros2_control_003/install

ros2 pkg executables mujoco_ros2_control
stat /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node
sha256sum \
  /data/work/ws_mujoco_ros2_control_003/install/lib/mujoco_ros2_control/ros2_control_node
```

当前 lock 中该 executable 的预期 SHA-256 是：

```text
81fc00e192b572f0ffe866522b384d508a6db561afa647b6f82eb91bf2dd2e3b
```

启动后还应记录真实 PID 的 executable：

```zsh
readlink -f /proc/<ros2-control-pid>/exe
```

期望路径是 patched overlay 下的 `.../install/lib/mujoco_ros2_control/ros2_control_node`。不能只凭 launch 文件或 README 推断运行版本。

#### 回退到 apt 0.0.3

不需要卸载 patched overlay。关闭本任务明确拥有的 runtime，打开全新 shell，只 source apt underlay：

```zsh
source /opt/ros/jazzy/setup.zsh
ros2 pkg prefix mujoco_ros2_control
```

返回 `/opt/ros/jazzy` 即表示当前 shell 已回退。注意：apt runtime 不具备本项目需要的 reset/pause/state-snapshot hooks，所以只能用于 upstream/underlay 对照，不能计入 Task 10 以后资格化结果。

#### 常见替换失败

| 现象 | 原因 | 处理 |
|---|---|---|
| `ros2 pkg prefix` 仍是 `/opt/ros/jazzy` | 漏 source dependency overlay | 新 shell 按 underlay → dependency → project 重做 |
| dependency prefix 正确，但项目编译仍使用 apt header | project CMake cache stale | `--cmake-clean-cache` 后重建项目 |
| build script 报 checkout 有额外修改 | dependency source 不再是 clean-or-exact-patch | 保存并审查 diff；禁止 reset/clean 强行覆盖 |
| patch apply check 失败 | commit/tag 不对或 patch 已非当前批准版本 | 核对 remote、HEAD、tag 和 lock；不要手工改上下文绕过 |
| full checker 报 installed file hash mismatch | install stale、构建结果漂移或 lock 未资格化更新 | 重建并查明差异；不能只更新 hash 消除错误 |
| `mujoco_vendor` 仍来自 `/opt` | 这是预期设计，不是切换失败 | 只 shadow 三个 `mujoco_ros2_control*` 包 |
| 新 shell 能用 patch，旧 tmux 进程仍是 apt | 运行进程继承启动时的环境 | 停止自己拥有的旧进程，用新 shell/正确 overlay 完整重启 |

## 5. 干净构建和质量门

### 5.1 推荐使用隔离构建目录

开发树中曾出现旧 ament Python build artifact 与 `--symlink-install` 冲突。为了不删除用户文件，推荐把 build/install/log 放到 `/tmp`：

```zsh
cd /path/to/so101-mujoco-ros2
export SO101_WORKSPACE_DIR=${SO101_WORKSPACE_DIR:-${PWD:h}}
source /opt/ros/jazzy/setup.zsh
source "$SO101_WORKSPACE_DIR/ws_mujoco_ros2_control_fork/install/setup.zsh"

export SO101_BUILD_ROOT=/tmp/so101-mujoco-guide-build
colcon --log-base "$SO101_BUILD_ROOT/log" build \
  --base-paths src \
  --build-base "$SO101_BUILD_ROOT/build" \
  --install-base "$SO101_BUILD_ROOT/install" \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --symlink-install \
  --cmake-clean-cache

source "$SO101_BUILD_ROOT/install/setup.zsh"
```

`--cmake-clean-cache` 很重要：从 apt 或历史 `_003` provider 切换到 fork overlay 后，旧 CMake cache 可能仍指向旧头文件。

隔离 build 用来证明源码可干净构建和测试；正式 provenance qualification 仍需构建标准
project `install/` 并按第 4.3 节 source。`check_mujoco_runtime.py` 根据 repo 根目录和
`SO101_WORKSPACE_DIR` 解析实际 prefix；不要为了让 checker 通过而把机器绝对路径写回 lock。

### 5.2 Python 和 Ruff 门

Ruff 版本固定为 `0.15.20`，门同时执行 lint 和 format check：

```zsh
ruff --version
bash src/so101_mujoco_demo_py/scripts/check_ruff.sh
```

直接调用系统 Python 可能找不到 Ruff；应使用提供了准确版本的开发环境运行仓库脚本，而不是跳过门。

运行 pytest 时禁止在源码树制造缓存：

```zsh
export PYTHONDONTWRITEBYTECODE=1
python3 -m pytest -p no:cacheprovider -q src/so101_mujoco_demo_py/test
```

`.pytest_cache` 会被 fail-closed isolation scanner 拒绝。日志、coverage、临时 wrapper 和证据统一写入 `/tmp/so101-debug-mujoco-*`。

### 5.3 C++/ROS 包测试

```zsh
colcon --log-base "$SO101_BUILD_ROOT/test-log" test \
  --base-paths src \
  --build-base "$SO101_BUILD_ROOT/build" \
  --install-base "$SO101_BUILD_ROOT/install" \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --event-handlers console_direct+

colcon test-result \
  --test-result-base "$SO101_BUILD_ROOT/build" \
  --verbose
```

必须确认真的发现了两个包和预期测试；`0 packages` 或 `0 tests` 即使 exit code 为 0 也不是通过。

最后再次运行：

```zsh
src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --check
```

本文基线的最新完整结果是：`207 passed, 3 skipped`，Ruff 检查 67 个文件通过，两个包构建完成。

## 6. 模型迁移和几何一致性

### 6.1 URDF/MJCF 双模型职责

- `urdf/so101.urdf`：MoveIt robot model、TF、joint/controller interface。
- `mjcf/so101.xml`：机器人视觉、碰撞、质量、惯性、joint dynamics、actuator。
- `mjcf/scene.xml`：地面/桌面、基座 pedestal、杯子、camera/light、keyframe 和 contact exclusions。
- `config/model-parity.yaml`：关节轴、limits、零位、parent-child transform、mesh hash、TCP pose 的 parity 门。

模型检查：

```zsh
python3 src/so101_mujoco_demo_py/scripts/check_model_parity.py \
  --config src/so101_mujoco_demo_py/config/model-parity.yaml
python3 src/so101_mujoco_demo_py/scripts/check_task_scene.py \
  --config src/so101_mujoco_demo_py/config/task_scene.yaml
```

几何 parity 只说明“两个模型描述相同几何语义”，不自动证明 collision-free、可达、IK 可行或 GUI 真正渲染正确。

### 6.2 最终采用的视觉和碰撞结构

机器人使用从受保护 Gazebo 资源复制并记录 provenance 的 mesh：

- 19 个 visual mesh instances。
- 42 个 collision mesh instances。
- visual 与 collision 保持同一 link/body 的局部变换关系。
- visual geoms 使用 `contype=0 conaffinity=0`，不参与碰撞。
- collision geoms 参与真实 MuJoCo 接触。

杯子不是实心 cylinder，而是与 Gazebo 语义一致的开口 compound cup：

- 12 个薄 box 侧壁。
- 1 个底部 cylinder。
- 高度 `0.09 m`、半径 `0.04 m`、壁厚 `0.002 m`、质量 `0.020 kg`。

场景基准：

- pedestal：中心 `(0, 0, 0.17)`，尺寸 `(0.18, 0.18, 0.10)`。
- table：中心 `(0, -0.20, 0.10)`，尺寸 `(0.50, 0.60, 0.04)`。
- cup/task start：`(0.02, -0.28, 0.165)`。

### 6.3 球形机械臂的真实根因

MuJoCo `<geom>` 的默认 type 是 sphere。仅提供 mesh `file`/`dataid` 不会自动把 geom 变成 mesh。原模型虽然加载了 STL，但 default class 没写 `type="mesh"`，所以 GUI 把每个 link/collision geom 画成球。

修复是在两个 default class 中显式写：

```xml
<default class="robot_visual">
  <geom type="mesh" group="0" contype="0" conaffinity="0"/>
</default>
<default class="robot_collision">
  <geom type="mesh" contype="1" conaffinity="1" group="3"/>
</default>
```

修复后 61 个机器人 geom 全部是 `mjGEOM_MESH=7` 且 `dataid >= 0`。此前误读 enum 也曾影响排查：sphere 是 2，mesh 是 7。

### 6.4 RPY 与 Euler 不是可直接复制的字符串

URDF 的 fixed-axis RPY 和 MuJoCo Euler 的旋转约定不同。特别是 `(1.5708, 1.5708, 0)` 这类组合，直接复制会出现符号/轴顺序错误。最终 MJCF 使用经过矩阵校验的显式 quaternion，并由 world transform/AABB parity 测试约束。

注意：这确实是几何偏差来源，但不是“球形机械臂”的主要原因。

## 7. 动力学和零位稳定性

### 7.1 为什么 39.37° 漂移不是正常重力抖动

旧模型在 planning 的约 `0.296 s` 内物理继续运行了 27 steps，joint 2 从 plan start 漂移 `+0.687 rad`，约 `39.37°`。这不是 plan 后等待太久，也不是“稳定窗口没等够”，而是 plant/actuator 参数无法稳定支撑机械臂。

暂停 plan 再 resume 曾把 planning drift 清零，但恢复后 MoveIt 可能在约 `1.13 ms` 内因 start-state mismatch 拒绝执行；这不是物理正确的通用方案。真实世界也不能为了规划冻结物理。

正确修复是先校准动力学。采用两个公开仓库中具有相同 lineage 的 `so101_new_calib.xml` 参数：

- joint damping：`0.60`
- frictionloss：`0.052`
- armature：`0.028`
- position actuator `kp`：`998.22`
- `kv`：`2.731`
- force range：`[-3.35, 3.35]`

两个仓库不是独立的双重验证来源，它们使用的是基本相同的模型/校准 lineage；因此参数是工程依据，不是两份独立实验共识。

当前 `config/task_scene.yaml` 的 `calibration_status: UNCALIBRATED` 和 `initial_inputs.joint_damping: 0.05` 仍是 Task 7 的历史输入摘要，没有随这次动力学校准更新；实际运行真值是提交的 MJCF（`joint damping=0.60` 等）。在该配置被单独清理前，不要从 `task_scene.yaml.initial_inputs` 生成 actuator/joint 参数。这一不一致应在后续文档/配置清理中修复，但不能混入尚未批准的 Task 13 contact calibration。

### 7.2 mesh collision 生效后出现的新抖动

视觉修复让 detailed collision mesh 真正进入物理计算后，Gazebo home `q1..q6=0` 出现三处 base/shoulder 穿透，深度 `0.022401–0.027882 m`。接触把 joint 1 推到 `1.238513 rad`，残余速度 `19.7272 rad/s`，最终五秒 envelope `0.279879 rad`，actuator 饱和到 `-3.35`。

因果 A/B：

1. 临时禁用所有 robot collision 后，关节运动归零，杯子/桌面接触仍保留。
2. 只排除 `base`/`shoulder` body pair 后也归零。

生产修复只增加一个窄范围相邻体排除：

```xml
<contact>
  <exclude name="exclude_base_shoulder" body1="base" body2="shoulder"/>
</contact>
```

没有全局禁用机械臂碰撞，也没有调低重力、改增益或隐藏运动。

当前稳定门：settle 后最后 5 秒，每个 arm joint：

- position peak-to-peak `<= 0.001 rad`
- absolute velocity `<= 0.01 rad/s`

最新 live 5 秒结果：所有 position envelope 为 0，最大速度约 `1.7069e-17 rad/s`。

### 7.3 杯子“瞬时速度不为零”不等于场景在漂移

刚体 contact solver 可能保留微小瞬时 `qvel` residual。场景稳定性应使用 settle 后窗口内 pose envelope 和净位移/净速度，而不是只读某一个时刻的 free-joint qvel。

杯子 free-joint damping 的试验中 `0.01`、`0.1` 未过门，`1.0` 才通过 10 秒稳定验证。这个值是 MuJoCo 输入，不应伪装成从 Gazebo 直接迁移的参数。

## 8. 原子仿真证据

### 8.1 为什么不能拼接多个 topic

对象 pose、twist、接触和 reset epoch 如果来自不同 callback，可能跨越不同 physics step。最终插件在同一个 MuJoCo mutex 快照中发布：

- object pose/twist。
- `left_fingertip_contacts`。
- `right_fingertip_contacts`。
- `other_object_contacts`。
- minimum signed distance、maximum normal force。
- `simulation_session_id`、`reset_epoch`、`simulation_step`。
- 单调 `publisher_sequence` 和 `paused`。

消费者排序键是：

```text
(simulation_session_id, reset_epoch, simulation_step)
```

无接触也必须发布显式空数组；signed distance 保留 MuJoCo 符号，penetration 是派生值，不能在消息层偷偷取绝对值。

### 8.2 QoS 和 freshness 陷阱

证据 publisher 使用 SensorData/best-effort QoS。默认 reliable subscriber 与它不兼容，会出现“topic 在 graph 中，但 callback 永远为 0”。subscriber 必须使用兼容 QoS。

另外：

- `ros2 topic list` 只证明图上有 topic，不证明收到过消息。
- 一次 `spin_once` 可能消费旧帧。
- callback count 不等于 freshness。
- 高速 subscription 和 service 全塞到同一 rclpy node 可能相互饥饿。

observer 必须验证 session、epoch、step、finite fields、完整 joint names 和消息年龄。只有 typed `EvidenceStale` 可以在原 deadline 内做有界重试，不能无限等。

## 9. Reset 事务

### 9.1 最终顺序

正确事务是：

```text
1. 物理仍运行时 deactivate controllers
2. pause MuJoCo
3. ResetWorld(keyframe=task_start)
4. 有界 resume
5. activate controllers
6. 等待一帧 reset 后新鲜、完整、finite 的 6-joint callback
7. 再 pause
8. 在 sim_mutex_ 下调用 state snapshot hook
9. 发布 paused=true、new_epoch、step=0 的原子证据
10. 独立核对对象证据、关节状态和 controller state
```

reset deadline 保持 10 秒；object tolerance `0.003 m`，每关节 tolerance `0.002 rad`。Task 10 qualification 禁止调用 `StepSimulation(1)`。

### 9.2 为什么不能 pause-first

暂停后 `/clock` 停止，controller manager 的 switch cycle 也会阻塞。实验中运行状态 deactivate 约 `0.003 s`，paused 状态等待约 5 秒后 timeout。因此必须先在 running 状态 deactivate controllers。

### 9.3 为什么 apt ResetWorld 不够

apt 0.0.3 的 ResetWorld 保留 simulation time，也没有插件级 `on_reset()`。因此不能用“时间回退”推断新 epoch；pose jump 和 time equality 同样都不是可靠 reset authority。

项目 patch 给 plugin base 增加默认 no-op hooks：

- `on_reset()`
- `on_pause(bool paused)`
- `on_state_snapshot(model, data, paused)`

成功或幂等的 `pause(true)` 在锁内正好触发一次 state snapshot。`on_reset()` 只推进待发布 generation；普通 running update 不能提前消费它。paused snapshot 才发布 `old+1 / step0 / paused=true`。

### 9.4 为什么不能用 StepSimulation 唤醒证据

早期方案在 reset 后调用一步 physics 来制造新证据。这会让 reset 后状态发生真实漂移，也偏离真实机器人语义。最终改成只读 snapshot hook：不推进 physics，不写 qpos/qvel。

### 9.5 第一帧关节状态竞态

一次实验从 resume 到 re-pause 只有 `3.57 ms`，而 joint state broadcaster 周期约 `10 ms`，所以根本没有 reset 后的新 callback。修复不是 sleep 固定时长，而是在原 deadline 内等待一帧完整、finite、命名正确且接收时间晚于 reset boundary 的六关节消息。

## 10. 启动和运行

### 10.1 只启动 MuJoCo + ros2_control

默认 launch 不启动仿真，必须显式 opt in：

```zsh
export ROS_DOMAIN_ID=138
export SO101_SESSION_ID="so101-$(date +%s)"

ros2 launch so101_mujoco_demo_py so101_mujoco.launch.py \
  start_simulation:=true \
  headless:=true \
  run_mode:=dry_run \
  simulation_session_id:="$SO101_SESSION_ID" \
  readiness_timeout_s:=30.0
```

预期 active controllers：

- `joint_state_broadcaster`
- `arm_controller`：关节 `1`–`5`
- `gripper_controller`：关节 `6`

查看 controller 时，CLI 输出中的 active 状态是最后一列，不是固定第二列。外部 `ros2 control list_controllers` 有时会阻塞，自动化门优先使用有 deadline 的 in-process service client。

### 10.2 运行 MoveIt headless dry-run

```zsh
export SO101_EVIDENCE=/tmp/so101-headless-dry-run.json

ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py \
  run_mode:=dry_run \
  execute:=false \
  headless:=true \
  start_simulation:=true \
  simulation_session_id:="$SO101_SESSION_ID" \
  evidence_file:="$SO101_EVIDENCE"
```

dry-run 必须有非空 MoveIt trajectory，但不能发送 execution goal。

### 10.3 运行经过限制的 safe execute

execute 有双重 opt-in：

```zsh
export SO101_EVIDENCE=/tmp/so101-headless-execute.json

ros2 launch so101_mujoco_demo_py so101_pick_place.launch.py \
  run_mode:=execute \
  execute:=true \
  headless:=true \
  start_simulation:=true \
  simulation_session_id:="$SO101_SESSION_ID" \
  safe_pose:=task12_safe \
  evidence_file:="$SO101_EVIDENCE"
```

当前一键 headless execute 验证的是 `config/headless_execution.yaml` 中的安全 joint target，不是完整抓取。`pick_place_state_machine --mode execute` 目前仍会返回 `LIVE_RUNTIME_NOT_IMPLEMENTED`；ROS-free CLI 只用于状态机和 checkpoint 语义，不能把它当成完整 live pick-place 入口。

### 10.4 GUI 查看规则

在 ai-station 启动 GUI 必须：

1. 使用 tmux。
2. 在 session 内执行 `source ~/gui-env.zsh`。
3. 通过 ai-station 的 Codex CUA 启动/操作并读取真实窗口。
4. 不使用 `ai-station-capture.sh`；它是 Gazebo demo 的截图辅助，不是这个 MuJoCo GUI 的证据入口。

GUI 主要作为 visual/operator evidence。历史上 evidence plugin 曾因 control/read buffer 缺少同一
`sim_mutex_` 边界而在 `mj_contactForce` 中崩溃；fork release `so101-0.0.3-r2` 修复后，GUI、
evidence plugin、三个 active controller 和 camera service 已在同一正常运行生命周期中通过验证。
接触和 reset 结论仍必须使用 atomic evidence，不能由截图或 camera service 成功替代。

CUA 会话过期时要显式 `start_session` 恢复，再用真实 PID/window id 调用 `get_window_state`。HiDPI 下对错误坐标点击 panel 曾触发 `update_sim_display` SIGSEGV，所以无需交互时只观察，不发送 GUI 输入。

### 10.5 四角 viewer debug camera

GUI 运行且已按第 4.3 节 source 后，可列出、应用并独立读回预设：

```zsh
ros2 run so101_mujoco_demo_py camera_preset --list
ros2 run so101_mujoco_demo_py camera_preset table_corner_nw
ros2 run so101_mujoco_demo_py camera_preset --current --format yaml

ros2 run so101_mujoco_demo_py camera_preset table_corner_ne
ros2 run so101_mujoco_demo_py camera_preset table_corner_se
ros2 run so101_mujoco_demo_py camera_preset table_corner_sw
```

四个记录共享实测 `lookat`、`distance`、`elevation_deg` 和 projection，只把 azimuth 依次旋转
90 度。每次应用都要用 `--current --format yaml` 数值核对；视觉 qualification 还要求四张独立、
新鲜的 CUA frame，每张都完整包含机械臂、夹爪、底座、杯子和主桌面，方向明显不同且尺度一致。

这些预设控制的是 MuJoCo 交互式 viewer 的调试相机，不是 MJCF/URDF 中的 RGB-D sensor camera；
不会改变 sensor topic、成像标定或机器人任务状态。Teleop Web UI 集成明确延期，不属于本轮
camera preset 工作流，也不能借本功能改动 Teleop 状态或路径。

## 11. MoveIt 规划和执行验证

### 11.1 必需配置

- group：`arm`
- TCP：`so101_tcp`
- joints：`1`–`5`，gripper 为 `6`
- arm controller：`arm_controller`
- gripper controller：`gripper_controller`
- joint acceleration limits：必须显式提供，否则 Time Optimal Parameterization 会失败。

启动时不能只查询一次 controller 状态。曾出现 arm controller 已 active、gripper controller 仍 activating 的 race；正确做法是在同一 readiness deadline 内轮询三个 controller 精确为 active。

### 11.2 当前通过的 Gazebo 对齐 TCP 验证

起点是 Gazebo reset pose：

```text
q1..q6 = [0, 0, 0, 0, 0, 0]
```

Gazebo `DESCEND` 最终 arm joint target：

```text
[-0.000206491845,
  0.472194274096,
  0.214652624195,
  0.854922375695,
  0.000576703465]
```

通过 live MoveIt FK 冻结出的 `world -> so101_tcp` 目标：

```text
xyz  = [0.02067668378158652, -0.2628210212382375, 0.20063061058386278]
xyzw = [-0.010265991324917133, -0.010262986627481915,
        -0.7067526865362342, 0.7073117563008668]
```

使用 world-frame position box（每轴 half-width `0.0005 m`）和 orientation tolerance `0.01 rad`。结果：

- planning code `1`，trajectory 50 points。
- execution code `1`，action `SUCCEEDED`。
- final TCP translation error `0.0008060601 m`。
- final TCP orientation error `0.00570721 rad`。
- max joint error `0.00407011 rad`。
- 执行后 5 秒 max position envelope `5.2859e-5 rad`。
- max velocity `0.00118313 rad/s`。

KDL 配置仍是 `position_only_ik: true`，但这次 request 另有独立 orientation constraint，而且最终 FK 实测通过方向门限。这个验证没有闭合 gripper，没有 lift 杯子，也不能宣称抓取成功。

### 11.3 `move_group -11` 的含义

Task 11 观察到的 `move_group` 返回 `-11` 是进程在 launch-directed shutdown 阶段收到 SIGSEGV，不是 MoveIt planning error code。功能请求已经可能成功，但 lifecycle/clean shutdown 仍有风险。用户此前指定在 Task 13 后修；Task 13 尚未完成，所以这一项当前仍是 open issue。

## 12. 接触标定：已学到什么，为什么仍未完成

Task 13 不能复制 Gazebo 阈值，必须基于当前 MuJoCo geometry/dynamics 重新采样至少 7 个 regime、每个 20 samples，并在用户明确批准阈值后才能进入 Task 14。

### 12.1 已失败的路径

第一批有效数据有 2126 samples，但没有 fingertip contact。观察到的 force/distance 实际来自 cup/table `other_object_contacts`，不能拿来设指尖阈值。

备用 FK endpoint 出现 16 个 left-only samples：

- max force `11.595 N`
- min signed distance `-0.001047 m`
- 杯子在 close 前已沿 Y 被推约 `58.8 mm`

预先打开 gripper、从杯子上方 approach 能避免最早接触，但 joint-space descent 导致左右指尖不同步：

- 始终未形成 bilateral contact。
- close 前杯子位移 `14.8 mm`，超过 `3 mm`。
- peak force `24.85 N`，超过此前 `11.60 N` hazard reference。
- hold 阶段仍是 left-only。

根因不是“阈值太严格”，而是 approach path 扫过杯壁、末端方向/路径不对。继续盲调 joint waypoint 不安全。

### 12.2 下一步正确方案

1. 从 home 开始，保持指尖姿态的 pose-constrained/Cartesian approach。
2. approach 和 descend 期间禁止提前接触；监控 cup pose envelope。
3. close 阶段采集左右指尖分离 contact arrays、force、signed distance、持续时间。
4. 完成 no-contact、left-only、right-only、bilateral-light、bilateral-heavy、table-only、post-release 等 regime。
5. 生成 threshold proposal，保持 `approved_by_user: false`。
6. 向用户提交表格、原始日志哈希、failure cases 后等待单独批准。

视觉/碰撞几何后来已重建，所以早期所有 contact calibration 数据都已失效，必须在当前 fixed geometry 上重采。

工作树中三个 Task 13 文件目前有意保持 untracked/uncommitted：

- `config/contact_calibration.yaml`
- `scripts/analyze_contact_calibration.py`
- `test/test_contact_calibration_contract.py`

不要误删、覆盖或把未批准阈值混进生产 commit。

## 13. Task 1–15 当前状态

| Task | 内容 | 当前状态 |
|---|---|---|
| 1 | 冻结 rebase baseline、Gazebo 隔离门、实验 ledger | 已实现 |
| 2 | 独立 `so101_mujoco_demo_py` 包 | 已实现 |
| 3 | 固定官方 `mujoco_ros2_control` 依赖 | 已实现 |
| 4 | 原子 `SimulationEvidence` 消息和 plugin | 已实现 |
| 5 | backend-neutral Python contracts 和 provenance | 已实现 |
| 6 | SO-101 MJCF/URDF parity gate | 已实现；后续补齐 detailed mesh |
| 7 | table/cup/keyframe deterministic scene | 已实现；后续补齐 Gazebo 几何一致性 |
| 8 | MuJoCo + `ros2_control` + controllers launch | 已实现 |
| 9 | MuJoCo atomic observer | 已实现 |
| 10A | patched dependency 的 reset/pause/snapshot hooks | 已实现 |
| 10B | transactional reset | 已实现并资格化 |
| 11 | ROS-free workflow 和 MoveIt boundary | 已实现；live state-machine execute 仍非统一入口 |
| 12 | headless ROS 2/MoveIt safe plan + execute | 已通过 |
| 补充 | detailed visual/collision geometry | 已通过，commit `79effd9` |
| 补充 | home-pose self-contact jitter | 已通过，commit `2d39539` |
| 补充 | Gazebo 对齐 TCP plan + execute | EXP-060 已通过 |
| 13 | MuJoCo contact evidence calibration | **未完成**；旧数据因路径与几何变更无效 |
| 13 后 | clean shutdown / `move_group -11` | **未修复** |
| 14 | 强制真实双指接触、抓取、最终放置 | **未开始** |
| 15 | 5 次 FULL_RESTART + 5 次 RESET_WORLD 重复性 | **未开始** |
| 扩展 | RGB-D camera | 不在本轮核心迁移范围，尚未集成 |

## 14. 完整故障目录：现象、根因和解法

| 现象/坑 | 根因 | 已采用解法 |
|---|---|---|
| 把上游写成 `moveit/mujoco_ros2_control` | 仓库来源判断错误 | 固定 `ros-controls/mujoco_ros2_control` tag/commit/hash |
| apt 0.0.3 reset 后无法辨别新 epoch | time 不回退，plugin 无 reset hook | 构建 patched overlay，以 `on_reset()` generation 为唯一 authority |
| 依赖 overlay 已 source，但仍编进 apt header | CMake cache 保留旧 provider | 隔离 build + `--cmake-clean-cache`，检查安装文件 hash |
| zsh source 后环境异常 | 使用 `setup.bash` 或 `nounset` 破坏 ROS setup | zsh 用 `.zsh`；setup 时不要开 nounset |
| `colcon` exit 0 但其实没测任何包 | base path 错或 overlay 未 source | 显式 `--base-paths src`/package select，并检查 discovered package/test count |
| `--symlink-install` 报已存在非 symlink | 旧 ament Python artifact | 使用 `/tmp` 隔离 build；只移动明确归属的 artifact，不 broad delete |
| resolved URDF 仍含 `$(find ...)` | MuJoCo runtime 不解析 Gazebo-era substitution | launch 通过 package share 渲染绝对 MJCF path，并拒绝未解析 token |
| 机械臂不出现 | MJCF 缺 detailed meshes/场景基座，或 camera framing 只看到桌面杯子 | 从 Gazebo geometry/provenance 重建 19 visual + 42 collision，补 pedestal/layout |
| 机械臂显示成球 | geom 默认 type 是 sphere | visual/collision defaults 显式 `type="mesh"` |
| mesh 朝向/符号错 | URDF RPY 与 MuJoCo Euler 语义不同 | 使用矩阵验证后的 quaternion + parity tests |
| 杯子是实心圆柱且形状不一致 | 只用了简化 cylinder | 用 12 壁 + 1 底的 open compound cup |
| detailed mesh 生效后机器人剧烈抖动 | base/shoulder collision mesh 初始穿透 | 因果 A/B 后只 exclude `base`/`shoulder` 相邻 pair |
| joint 2 在 plan 期间漂移 39.37° | plant/actuator 无法抗重力稳定 | 使用校准的 damping/frictionloss/armature/kp/kv/force limit |
| “稳定窗口 + 重新规划”一直等不到 | 根因是 plant 不稳定，不是采样时机 | 先修动力学；稳定后再 plan/execute |
| pause-plan-resume 偶发 start mismatch | resume 后真实物理立刻演进 | 不把冻结物理作为生产策略；修稳定性后正常 plan/execute |
| 杯子瞬时 qvel 非零 | contact solver residual | 用 settle-window pose envelope/净位移判断稳定 |
| 证据 topic 存在但订阅 0 callback | best-effort publisher 与 reliable subscriber QoS 不兼容 | subscriber 使用 SensorData QoS，并要求收到实际消息 |
| 收到 callback 但 observer 判新鲜错误 | 一次 spin 读到旧帧、只数 callback | 检查 session/epoch/step/sequence/age/finite fields |
| reset 时 pause 后 controller deactivate 卡住 | `/clock` 和 controller switch cycle 已停止 | running 时 deactivate，再 pause |
| reset 后没有新的 joint state | resume 只有 3.57 ms，小于 10 ms broadcaster 周期 | 在原 deadline 内等待一帧新鲜完整 6-joint callback |
| 用 StepSimulation 生成 reset evidence | 会推进物理并造成 reset 漂移 | 锁内只读 state snapshot hook，不 stepping |
| running update 提前消费 reset generation | epoch 发布边界设计错误 | pending generation 只由 paused snapshot 消费 |
| patch 脚本重复应用/误插入 | zero-context patch replay 不幂等 | 只接受 clean 或 exact approved diff；比较 patch hash |
| MoveIt Time Optimal Parameterization 失败 | 缺显式 acceleration limits | 在 `joint_limits.yaml` 提供速度和加速度边界 |
| MoveIt 启动偶发 controller not ready | 一次 list 时 gripper 仍 activating | 同一 deadline 内轮询三个 exact active states |
| `ros2 control list_controllers` 解析错 | active 是 `$NF`，不是第二列 | 解析最后一列，自动化优先 in-process service |
| 外部 controller CLI 卡住 | CLI/service/daemon 可能阻塞 | bounded in-process client，不依赖无界 shell CLI |
| `ros2 topic list --no-daemon` 报不支持 | 该 subcommand 没这个选项 | 使用支持的命令或 in-process graph；node list 可用正确 no-daemon 方式 |
| node list 看见已退出节点 | ROS daemon 缓存陈旧 | `ROS2_DISABLE_DAEMON=1` 或 `ros2 node list --no-daemon` |
| launch 把 `--ros-args` 传给 Python CLI 导致 argparse 失败 | ROS launch 自动追加参数 | Python entry point 在 `--ros-args` 前截断 app args |
| shell `tee` 后错误被当成功 | pipeline 返回 `tee` 状态 | `set -o pipefail`/zsh `setopt PIPE_FAIL`，保留真实 exit status |
| wrapper 运行错误参数 | checker 必需 `--lock`，临时 wrapper 漏传 | 先跑 `--help`/检查 argparse，wrapper fail-fast |
| 临时 wrapper 有 literal diff marker/source composition bug | 在线拼脚本未先静态检查 | 先离线 render、compile、diff，再 launch |
| MuJoCo state bit 解析错 | 把 `mjSTATE_CTRL` 当 `1<<6` | 正确值是 `1<<5` |
| GUI evidence plugin SIGSEGV | visualization mode 调 `mj_contactForce` 的不稳定路径 | GUI 只做 visual；headless evidence 才用于接触结论 |
| HiDPI GUI 点击后 `update_sim_display` SIGSEGV | CUA 坐标落到错误 panel | 只观察；需要操作时先读窗口状态和缩放 |
| 本地 capture helper 截不到 MuJoCo | helper 是 Gazebo demo 专用 | 用 ai-station Codex CUA 获取真实窗口 |
| 进程“已清理”但 tmux/PID 仍在 | 只看 wrapper 日志，未读回 ownership | 记录 PID/PGID/tmux，逐个 read-back；禁止 broad `pkill` |
| launch SIGINT 后进程不退出 | 子进程忽略/延迟处理 SIGINT | 只对 task-owned exact PID 有界等待后 SIGTERM，保留其他 session |
| `move_group` 返回 `-11` | shutdown lifecycle SIGSEGV | 不解释成 planning error；Task 13 后单独修 clean shutdown |
| Task 13 force 看似很大却无抓取 | 实际是 cup/table other contact | 左/右/other arrays 分开解释，不能混成 fingertip threshold |
| 只有左指接触、杯子先被推走 | joint-space approach 扫过杯壁 | 改用保持方向的 Cartesian/pose-constrained descent |
| 直接沿用 Gazebo contact threshold | 两个引擎 solver/mesh/material 不同 | MuJoCo 固定几何上重新做七类 regime calibration，并单独审批 |
| source tree 出现 `.pytest_cache`/`__pycache__` | 测试产生运行产物 | `-p no:cacheprovider`、`PYTHONDONTWRITEBYTECODE=1`、证据写 `/tmp` |
| clean clone 又出现球形/抖动 | 远端分支尚缺本地 `79effd9`、`2d39539` | 发布前先审查并 push 当前分支；不要把 `c9ab83d` 当最新 runtime |
| `task_scene.yaml` 与 MJCF damping 不一致 | YAML 仍是 Task 7 历史输入摘要 | runtime 以 compiled MJCF 为准；后续单独修正配置语义，不混入 contact 阈值 |

## 15. 证据、实验和进程管理规则

每个 runtime 实验必须先在 ledger 中登记 `PLANNED`，再执行，最后改成：

- `VALID`：provenance、单变量、证据、清理和门限都成立。
- `INVALID`：即使现象有用，只要 QoS、source、进程 ownership、instrumentation 或合同不成立，就不能作为资格化证据。

原始日志、JSON、截图和临时脚本放在：

```text
/tmp/so101-debug-mujoco-<topic>-<date>/
```

仓库只保存摘要、哈希、决定和 provenance。启动前记录现有 tmux/PID/PGID；结束时只停止任务自己创建且精确记录的进程，不使用 broad `pkill`，不干扰无关 Gazebo、RViz、MoveIt 或 CUA session。

## 16. 接下来执行顺序

### 16.1 Task 13：重新设计 approach 并重做接触标定

1. 保留三个未提交 Task 13 文件，先审查其 schema，不采用旧阈值。
2. 为 Cartesian/pose-constrained approach 写 RED contract。
3. 从 EXP-059 已验证的 Gazebo home 和稳定窗口开始。
4. 计划到 pre-grasp；无接触进入。
5. 保持 TCP/指尖方向 descend；杯子位移超过 `3 mm`、force 超 hazard reference 或单侧接触持续过长即 abort/recover。
6. 完成七种 regime 的新采样和分析。
7. 生成 disabled threshold proposal，向用户单独请求批准。

### 16.2 Task 13 后：修 clean shutdown

把功能成功和进程退出分开验证：

- 捕获 `move_group` backtrace/core。
- 区分 launch event handler、node destruction、plugin unload 和 outstanding action/service callback。
- 要求正常 SIGINT/launch shutdown exit code 0，domain 内无 task-owned node 残留。

### 16.3 Task 14：真实物理抓取和放置

只有 Task 13 阈值经用户批准后才开始：

- bilateral fingertip contact 持续满足门限。
- cup 离开 table，而不是 Planning Scene attachment 造成视觉假象。
- 搬运期间 pose/contact 连续。
- release 后 cup 与 table/目标区关系满足最终放置条件。
- 无 weld/teleport/隐藏约束。

### 16.4 Task 15：重复性资格化

- 5 次 `FULL_RESTART`。
- 5 次 `RESET_WORLD`。
- 每次都要有唯一 session/epoch 证据、clean shutdown、物理抓取和最终放置结果。
- 任一失败必须记录 failure code 和 raw evidence hash，不能只重跑成功样本。

## 17. 参考文件

- 设计：`docs/superpowers/specs/2026-08-09-so101-mujoco-ros2-migration-design.md`
- 实施计划：`docs/superpowers/plans/2026-08-09-so101-mujoco-ros2-migration.md`
- 完整实验 ledger：`docs/experiments/so101-mujoco-ros2-migration-experiment-ledger.md`
- dependency lock：`src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- reset patch：`src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch`
- model/scene：`src/so101_mujoco_demo_py/mjcf/`
- headless launch：`src/so101_mujoco_demo_py/launch/so101_pick_place.launch.py`
- isolation gate：`src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh`
- Ruff gate：`src/so101_mujoco_demo_py/scripts/check_ruff.sh`

这份指南是执行入口；细粒度实验的原始事实仍以 ledger 中的 `VALID`/`INVALID` 记录和 `/tmp` 证据哈希为准。

# macOS SO-101 运行环境排查

本文件是 macOS 上正常 package test 和固定运行契约的出处。dylib 与 SIP 诊断只在失败确实指向 Python、overlay、package prefix、`DYLD_*` 或 `@rpath/*.dylib` 时启用，见文末条件小节。Linux 和 ai-station 不使用这里的命令；macOS 上与环境无关的控制、规划、物理或视觉问题，在 doctor 通过后回到 `so101-dev` 的普通分层取证流程。

## 权威文档和入口

| 内容 | 文件 |
|---|---|
| 完整安装、启动、故障说明和跨 Mac 核对项 | [`docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md`](../../../../docs/guides/macos-apple-silicon-ros2-jazzy-so101-mujoco.md) |
| 统一命令入口、固定环境 doctor、dylib farm 生成器 | [`scripts/so101-macos.zsh`](../../../../scripts/so101-macos.zsh)、[`scripts/so101_macos_runtime_contract.py`](../../../../scripts/so101_macos_runtime_contract.py)、[`scripts/setup-macos-ros-dylib-farm.zsh`](../../../../scripts/setup-macos-ros-dylib-farm.zsh) |
| 实施边界、未完成门禁和当前主机证据 | [`docs/superpowers/plans/2026-09-21-so101-macos-runtime-contract.md`](../../../../docs/superpowers/plans/2026-09-21-so101-macos-runtime-contract.md)、[`docs/experiments/so101-macos-runtime-contract-experiment-ledger.md`](../../../../docs/experiments/so101-macos-runtime-contract-experiment-ledger.md) |

指南是操作说明，实验账本是证据记录；不要把账本中的一次成功当成另一台 Mac 已通过验收。

## 固定契约

所有目标 Mac 使用相同逻辑路径：

| 用途 | 路径 |
|---|---|
| ROS 根目录 / install | `/opt/ros/jazzy`、`/opt/ros/jazzy/install` |
| ROS Python | `/opt/ros/jazzy/.venv/bin/python` |
| 临时目录 / 工作数据根目录 | `/opt/data/tmp`、`/opt/data` |
| 锁定 fork overlay | `/opt/data/so101/runtime/fork/current` |
| 项目 overlay | `/opt/data/so101/workspace/install` |
| dylib farm | `/opt/ros/jazzy/dylib_farm/current` |

物理 ROS 目录可以位于不同用户的 home 下，但 `/opt/ros/jazzy` 这个逻辑入口必须一致。不要把 `/Users/<name>` 写进代码或测试。

## 使用方法

先做只读基础检查和准备，再启动：

```zsh
uname -s
uname -m
ls -ld /opt/ros/jazzy /opt/data /opt/data/tmp
readlink /opt/ros/jazzy
scripts/so101-macos.zsh doctor --base
scripts/so101-macos.zsh prepare
scripts/so101-macos.zsh doctor --json
```

`doctor --base` 失败时先对齐固定路径、CPython 3.11 和写权限，不要启动 ROS stack。需要创建或修改 `/opt` 下的链接时，把准确命令交给用户执行，不要自行假设 sudo 权限。完整 doctor 必须真实导入 `rclpy`、加载关键 dylib，并核对 package prefix；不要用“文件存在”代替加载成功。

启动 task station。`launch` 会 `exec` 成前台 `ros2 launch` 并一直占用当前 shell，所以要为它开一个专用 tmux session、窗口或 pane：

```zsh
scripts/so101-macos.zsh launch \
  so101_demo_py so101_mujoco_task_station.launch.py \
  headless:=false sensor_rendering:=true include_teleop:=false
```

再在另一个 shell、tmux pane 或窗口中检查控制器、MoveIt service 和 action 是否 ready：

```zsh
scripts/so101-macos.zsh run \
  so101_demo_py motion_stack_ready --timeout-s 90
```

外部必需环境变量是 0 个。唯一接受的可选变量是 `ROS_DOMAIN_ID`，范围 0 到 232，默认 0，例如 `ROS_DOMAIN_ID=225 scripts/so101-macos.zsh doctor --json`。不要把裸 `ros2 launch`、direnv 或手工拼接的 `DYLD_LIBRARY_PATH` 当作生产启动前提。

## Python package test

macOS 上的 package test 必须使用固定 Python，并在当前 zsh 内按固定顺序加载 overlay：

```zsh
source /opt/ros/jazzy/install/setup.zsh
source /opt/ros/jazzy/extra_ws/install/setup.zsh
source /opt/data/so101/runtime/fork/current/local_setup.zsh
source /opt/data/so101/workspace/install/local_setup.zsh
export DYLD_LIBRARY_PATH=/opt/ros/jazzy/dylib_farm/current
scratch=$(mktemp -d /opt/data/tmp/jz.XXXXXXXX)
export TMPDIR="$scratch" TMP="$scratch" TEMP="$scratch"

# TASK_EVIDENCE 必须已指向本 task 已登记的唯一 root，例如 macOS 上
# export TASK_EVIDENCE='/opt/data/work/so101-evidence/<task-family>/<run-id>'
: "${TASK_EVIDENCE:?先 export 本 task 已登记的唯一 evidence root}"
test -d "$TASK_EVIDENCE" || { printf 'STOP: TASK_EVIDENCE is not a directory\n' >&2; exit 1; }
mkdir -p "$TASK_EVIDENCE/tests" || exit 1

/opt/ros/jazzy/.venv/bin/python -c 'import os,pathlib,rclpy,tempfile; actual=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); print("rclpy=",rclpy.__file__,"temp=",actual); assert actual == expected'
logical_cpus=$(/opt/ros/jazzy/.venv/bin/python -c 'import os; print(os.cpu_count() or 1)')
workers=$(( logical_cpus > 8 ? 8 : logical_cpus ))
print -r -- "logical_cpus=$logical_cpus pytest_workers=$workers"
/opt/ros/jazzy/.venv/bin/python -m pytest \
  -n "$workers" --dist loadscope \
  --basetemp="$scratch/p" \
  src/so101_demo_py/test \
  --junitxml="$TASK_EVIDENCE/tests/so101_demo_py.xml"
```

`TASK_EVIDENCE` 必须是本 task 已登记的唯一 evidence root，日志、JUnit 和截图都放进去，不写进源码目录；脚本会在写到 `--junitxml` 之前确认它存在并建好 `tests/` 子目录。`/opt/data/tmp` 是 macOS 固定契约里的临时目录，ai-station 的 `/data` NVMe scratch 规则不适用于 macOS。每次运行都换一个尚不存在的短 `--basetemp`，避免并行 worker 复用旧状态，也为长测试名的 Unix socket 留足路径长度。并行门禁本身、`explicit_ml` 和 benchmark 的收集范围由 [`test-and-acceptance.md`](test-and-acceptance.md) 统一规定。

## 依赖：固定 venv 与任务自有环境

macOS 的实际运行时契约是固定 venv `/opt/ros/jazzy/.venv`，它提供 `python`、`colcon` 和项目 `test` extra 里锁定的 `pytest-xdist==3.8.0`。不要悄悄换成系统 Python、用户 site-packages 或另建临时 venv 来跑 package gate，那样测到的不是产品运行时。

先只读核对版本，缺依赖时按项目 extra 补进同一个固定 venv：

```zsh
/opt/ros/jazzy/.venv/bin/python -m pip show pytest-xdist
/opt/ros/jazzy/.venv/bin/python -m pip install 'src/so101_demo_py[test]'
```

第二条命令改的是共享运行时，先取得用户明确授权再执行。任务自有的隔离环境只承载任务专属依赖，例如训练用的 LeRobot 或 Torch，不替代固定 venv 跑普通门禁。安装时选索引和绕过代理的做法见 [`python-dependency-install.md`](python-dependency-install.md)。

## dylib 与 SIP 诊断（条件启用）

只在日志确实指向下面的错误时才读这一节，不要把它当默认启动路径。

- `@rpath/librosidl_typesupport_c.dylib` 通常由 ROS Python、消息或 service 类型支持加载，可能在 launch 文件解析或节点创建前失败。
- `@rpath/libhardware_interface.dylib` 属于 `ros2_control_node` 的依赖链，controller manager 加载 `mujoco_ros2_control/MujocoSystemInterface` 时需要它。

macOS SIP 可能在受保护脚本边界移除 `DYLD_*`。出现上述错误时先运行完整 doctor，不要根据下游的 controller timeout 直接修改控制器代码。

pytest 在收集前就因 `@rpath` 或模块导入失败时记为 runner/environment failure，不记成代码 RED；导入成功后出现 assertion failure 才按测试失败处理。只跑定向契约测试、且 ROS 的 pytest plugin 干扰无关文件收集时，可以为该次定向测试设置 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`；普通整包 package gate 不使用这个选项隐藏已登记的插件或测试。

## 跨 Mac 验证

每台目标 Mac 都保存一次 `prepare`、`doctor --json` 和真实 task-station `READY` 证据，比较时核对 Darwin/arm64、CPython 3.11、逻辑路径、farm manifest、必需 dylib 和 package prefix；`resolved` 路径可以因用户名不同而变化。

同一台 Mac 上运行两套污染 HOME/PATH/ROS/DYLD 的环境，只能验证环境清理逻辑，不能代替第二台物理 Mac。未执行的主机明确写 `NOT_RUN`。

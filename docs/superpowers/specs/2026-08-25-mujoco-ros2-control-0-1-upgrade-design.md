# `mujoco_ros2_control` 0.1.0 完整升级设计

## 目标

将 `third_party/mujoco_ros2_control` 从项目 fork `so101-0.0.3-r11`
（`f19a8cc3af61feccacb22a9f0d16cc972e3b2c08`）升级到以上游
`mujoco_ros2_control` 0.1.0 最新提交
`57fc6744844902d4532160b403fa95840c1d6f96` 为主体的新 fork release。

这不是覆盖式替换。最终版本必须同时满足：

- 保留 fork 从 0.0.3 以来的 SO-101 reset、pause、step、viewer camera、逐物理步证据和
  macOS 兼容能力；
- 将已经被上游覆盖的本地实现迁移到 0.1.0 的新架构，而不是继续维护旧的并行实现；
- 完整保留 0.1.0 新增的核心、插件、消息、扩展、demo、测试和文档；
- 同时兼容 macOS Apple Silicon ROS 2 Jazzy 和 ai-station Linux ROS 2 Jazzy；
- 两个平台都通过最新 RGB-D camera topics 和一次有效的 dynamic cup pick-place execute。

## 当前基线

设计确认时，主项目为干净的
`main@db1b658b4bc34f11c923640e1d188cf11aeebc1b`。该提交已经合入
`codex/macos-mujoco-camera-topics`，并将 thirdparty 锁定为：

- tag：`so101-0.0.3-r11`；
- commit：`f19a8cc3af61feccacb22a9f0d16cc972e3b2c08`；
- RGB-D topics：`/task_camera/color`、`/task_camera/depth`、
  `/task_camera/camera_info`；
- camera contract：10 Hz、640×480、`task_camera_frame`、RGB `rgb8`、depth
  `32FC1`。

上游目标提交属于 0.1.0，不是 1.0.0。其 package version、tag 和 changelog 均以
0.1.0 为准。

## 选定的集成策略

采用“上游优先的双亲合并”：

1. 从上游 `57fc674` 建立 fork 升级分支；
2. 将本地 r11 `f19a8cc` 作为另一条历史合入；
3. 产生同时保留上游和本地 ancestry 的真实 merge；
4. 冲突后的 tree 以 0.1.0 架构为主体，按能力逐项前移本地功能；
5. 完成测试和跨平台运行验收后建立本地 tag `so101-0.1.0-r1`。

不采用逐提交 rebase，因为 r1-r11 中多项功能已经由上游以新架构实现，逐个重放会重复解决
同类冲突并重新引入旧边界。也不以 r11 为主体回移上游功能，因为那无法获得 0.1.0 的核心
架构，后续继续跟随上游的成本仍然过高。

## 上游能力与本地能力的处理矩阵

| 能力 | 0.1.0 升级处理 |
| --- | --- |
| 控制循环与物理线程解耦、双缓冲状态快照 | 采用上游实现，删除本地旧同步路径 |
| `MujocoSimulation` 核心容器 | 采用上游，作为 simulation、viewer 和服务的所有者 |
| ResetWorld state overrides、free-joint state | 完整采用上游并叠加本地 paused gate 和证据通知 |
| `pre_step()` plugin hook | 原样保留上游实现 |
| 逐成功物理步权威证据 | 通过独立 post-step observer capability 前移 |
| reset/pause/state-snapshot 通知 | 通过同一 optional observer capability 前移 |
| viewer camera set/get | 移入 `MujocoSimulation`，保留原子校验和 headless 拒绝 |
| RGB-D CameraPlugin | 采用上游 streaming/polled/disabled 架构 |
| macOS CameraPlugin context 生命周期 | 前移 r11 的独立 rendering capability |
| macOS 主线程 MuJoCo UI | 适配到新的 `MujocoSimulation` 生命周期 |
| viewer 销毁线程 | 在 context 所属线程完成销毁和 join |
| primary monitor/video mode 空值 | 在新 `mujoco_simulation.cpp` 中保留 guard |
| portable heartbeat/CMake/test runtime 修复 | 对 0.1.0 逐项复核，只保留仍有必要的最小差异 |
| 新传感器、transmission、lidar、mobile-base 插件 | 保留完整上游 tree 和 package tests，不给 SO-101 无端启用 |

## 组件边界

### `MujocoSimulation`

`MujocoSimulation` 拥有：

- `mjModel`、权威 `mjData` 和 simulation mutex；
- physics thread 和 MuJoCo viewer；
- reset、pause、step、free-joint 和 viewer-camera ROS 服务；
- pre-step、post-step、reset、pause 和 snapshot callback dispatch；
- macOS/Linux UI 与渲染生命周期协调。

viewer-camera 服务迁入这里，因为 0.1.0 中 viewer camera、selector 和 simulation mutex 已不再由
`MujocoSystemInterface` 直接拥有。

### `MujocoSystemInterface`

`MujocoSystemInterface` 仅负责：

- ros2_control command/state interfaces；
- 使用上游双缓冲快照完成 `read()`；
- staged control input 和 `write()`；
- pluginlib 装载以及 optional capability 发现；
- 将已发现的 callback 聚合后注册给 `MujocoSimulation`。

它不重新承载旧版本中已经拆出的 physics loop、viewer 或服务实现。

### Optional plugin capabilities

保持上游 0.1.0 的 `MuJoCoROS2ControlPluginBase` ABI，不向其追加 SO-101 virtual 方法。

新增独立的可选 simulation observer capability，提供：

- successful post-physics-step；
- after-reset；
- pause-state-changed；
- authoritative-state-snapshot。

`SimulationEvidencePlugin` 同时实现上游 plugin base 和该 observer capability。普通上游插件不实现
该接口时继续按原路径运行。

r11 已验证的 `MuJoCoROS2ControlRenderingPlugin` 继续作为独立能力存在，用于 CameraPlugin 的
平台 context handoff、rendering enable/disable 和有序关闭。公共能力使用
`set_platform_render_context(void*)`：Apple 实现接收主线程创建的 GLFW context，非 Apple 实现接收
`nullptr` 并保持 no-op。它不得添加到普通 plugin base vtable，避免再次出现 legacy plugin ABI 错位。

## 运行时数据流

### 正常物理步

```text
staged controller commands
  -> upstream pre_step plugins
  -> mj_step()
  -> SO-101 post-step observers
  -> refresh upstream control snapshot
  -> publish control state and /clock
```

post-step observer 只在成功完成 `mj_step()` 后消费权威状态。`SimulationEvidencePlugin` 的回调
只能将固定字段复制进有界缓冲区；ROS 发布仍在非物理线程完成。回调不得等待 service、锁住 ROS
executor 或执行磁盘 I/O。

### Reset

```text
require paused simulation
  -> validate keyframe and all overrides without mutation
  -> apply upstream reset
  -> refresh upstream snapshot
  -> notify after-reset observers
  -> publish authoritative observer snapshot
  -> return service result
```

未暂停、未知 keyframe、无效 joint/free-joint 名称或非法 override shape 必须在状态写入前失败。
合法 reset 保留 0.1.0 的 joint/free-joint overrides，并保留 ROS clock continuity。

observer 是只读消费者，不能否决已经完成的 reset。某个 observer 抛出异常时捕获并隔离该
observer，simulation 保持权威 reset 状态；项目 readiness 因缺失证据失败，该运行不得进入成功
统计。

### Pause/Resume

先更新实际 pause state，再通知 observer。进入 pause 后追加一次权威 snapshot。resume 保留上游
timing resync 和 pending-step interruption 语义。

### Viewer camera

set/get 请求在同一 simulation mutex 下校验和应用。非法 fixed camera、非有限数值、非法距离或
不支持模式必须无修改失败。headless 明确拒绝 viewer-camera 请求。viewer preset 只改变 viewer，
不得修改物理 `mjData` 或 sensor camera。

### RGB-D CameraPlugin

三个 task-camera topics 使用同一采样时间戳和 `task_camera_frame`。RGB 为 640×480 `rgb8`；
depth 为 640×480 `32FC1`，包含有限正深度；CameraInfo 的尺寸、frame 和内参必须与图像一致。

Linux 保留上游 GLFW/EGL 路径。macOS 由 process main thread 准备 Cocoa window/context 生命周期，
CameraPlugin 通过独立 rendering capability 获得资源；关闭时先停止 camera worker，再在资源所属
线程销毁 context 和 viewer。

## 错误处理

- optional capability 不存在不是错误；普通 0.1.0 插件继续工作；
- plugin 初始化失败沿用上游 failure boundary，不启动半配置 simulation；
- observer fault 被记录并隔离，不能破坏物理状态，但会使 SO-101 readiness/acceptance 失败；
- reset 的 validation 与 mutation 分离，失败不得留下部分 override；
- viewer-camera 请求失败不得改变 camera 或 physics state；
- CameraPlugin 没有收到有效 context 时不得启动发布线程；
- platform-specific 能力全部通过编译条件隔离，Linux 不链接 Apple framework，macOS 不依赖 EGL；
- shutdown 必须按 producer -> worker -> context -> viewer -> executor 顺序收敛，不遗留可 join 线程。

## 主项目修改边界

主项目从 `db1b658` 建立隔离实现分支。允许修改：

- `third_party/mujoco_ros2_control` gitlink；
- 两份 dependency lock、安装器、backend/provenance contract；
- `SimulationEvidencePlugin` 的 optional observer 适配；
- 0.1.0 ResetWorld message 扩展带来的调用兼容；
- CameraPlugin topic contract、测试、实验账本和升级文档。

不重新调整 dynamic pick-place 的策略、轨迹、碰撞几何、相机外参或抓取参数。只有新依赖造成的
确定兼容问题可以进入修改范围，并且必须先有 RED regression。

## 自动化测试设计

### Fork RED -> GREEN

- post-step callback 严格发生在成功 `mj_step()` 之后；
- upstream `pre_step()` 与 local post-step observer 同时生效且顺序固定；
- paused reset gate 和无修改失败；
- ResetWorld overrides 与 reset 后 controller/observer snapshots 一致；
- pause/resume notification 和 pending-step 中断；
- viewer-camera 原子校验、headless 拒绝、物理状态不变；
- 普通 0.1.0 plugin 和 legacy-compatible optional capability 装载；
- macOS main-thread/context lifecycle、monitor guard 和 shutdown order；
- 完整 fork package tests。

### 主项目 RED -> GREEN

- gitlink、fork tag/commit、upstream tag/commit 和接口哈希；
- 安装器必须构建新 fork，不得回退 apt、r11 或旧 overlay；
- `SimulationEvidencePlugin` 使用 observer capability；
- CameraPlugin 保持 10 Hz、640×480 和三个既有 topics；
- `dynamic_cup_pick_place` entry point、policy 和 launch composition 未发生无关变化；
- `so101_demo_py` 与 `so101_mujoco_support` 全部相关测试。

## macOS 运行验收

使用隔离 build/install，不覆盖 r11 overlay：

1. 构建 fork，运行定向和 package tests；
2. 构建主项目，运行 package 和安装契约；
3. 验证 package prefix、可执行文件、动态库和 source commit；
4. 非 headless GUI 启动与干净关闭；
5. camera probe 收到有效、对齐、重复发布的 CameraInfo/RGB/Depth；
6. `dynamic_cup_pick_place` execute 一次有效成功；
7. 保存 controller、joint/TF、cup pose/contact、Planning Scene 和 fresh screenshot 证据；
8. 验证 task-owned ROS/MuJoCo 进程全部退出。

## ai-station Linux 运行验收

先只读检查 ai-station checkout、tmux、process、ROS graph 和 GPU 状态。不得覆盖
`/data/work/ws_moveit` main、install 或旧 submodule。

向空闲的 ai-station Codex tmux 一次性交付完整 handoff，首行明确：

> 你当前直接运行在 ai-station 上。不要 ssh 到 ai-station；仓库、tmux、进程、CUA 和截图命令都
> 在当前主机直接执行。

通过带 SHA-256 的 Git bundles 传输精确 project/fork commits，在独立 checkout、overlay 和 ROS
domain 中完成：

1. 与 macOS 相同的 fork/project tests；
2. 三个 camera topics 的 frame、尺寸、编码、时间戳、payload 和重复发布验证；
3. 一次有效的 `dynamic_cup_pick_place` execute；
4. MuJoCo physics、MoveIt、controller/joint/TF、Planning Scene 和 fresh GUI screenshot 取证；
5. task-owned stack 干净退出和最终空 graph 验证。

GUI 使用项目 `ai-station-gui` 路由和已有 `codex-cua`，严格执行
`snapshot -> action -> fresh snapshot`。若当前 NVIDIA driver/library mismatch 仍存在，先保存现场
证据；可使用 Mesa software GL 验证 CameraPlugin，但 native GPU 路径必须单列为未通过，不能隐藏。

## 成功判据

macOS 与 Linux 必须分别同时满足：

- 精确 source/install/runtime provenance；
- 全部相关自动化测试无新增失败；
- CameraInfo、RGB、Depth 均有有效消息；
- dynamic cup pick-place 一次有效成功；
- simulator、MoveIt、controller、cup final state 与截图一致；
- task-owned process 干净退出；
- 用户原有 main、r11、overlay、tmux 和 ai-station checkout 未被覆盖。

规划成功、CLI `DONE`、topic publisher 存在、单张截图或 agent 自述均不能单独构成验收通过。

## 证据与实验账本

整个任务登记唯一证据根：

`/tmp/so101-debug-mujoco-control-1-0-upgrade-20260825/`

实施 worktree 中建立
`docs/experiments/mujoco-ros2-control-0-1-upgrade-experiment-ledger.md`。每个实验记录 source commit、
install overlay、runtime executable/package prefix、`ROS_DOMAIN_ID`、`GZ_PARTITION`（MuJoCo 记为
`NOT_APPLICABLE_MUJOCO`）、命令、退出码、结论和证据。

Linux 使用同名 remote staging root，完成后将证据回传到本地根的 `linux/` 子目录，并核验相对
路径、大小、数量和 SHA-256。不得创建另一个 task evidence root，不得删除证据。

## 回滚与发布边界

- 保留 r11 commit/tag 和现有 overlay；
- 新 fork/project 使用隔离 build/install；
- 所有 gate 完成前不替换持久 overlay、不修改 ai-station main；
- 失败时重新 source r11 overlay 即可回滚，不需要 reset、clean 或删除；
- 不删除现有 worktree、tmux session、overlay 或历史证据；
- 本地验证完成后才建立 `so101-0.1.0-r1` tag；
- push、合入 Gitee `origin/main` 和替换正式 overlay由 Superpowers finishing 流程单独决定，不作为
  未授权的自动动作。

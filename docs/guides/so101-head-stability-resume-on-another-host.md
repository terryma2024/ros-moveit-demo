# 在另一台机器恢复 Head search 稳定性调查

这份指南用于调查获准恢复之后的跨主机接续。当前调查仍暂停，正常保持测试的结果为 FAIL/NOT_RUN/NOT_RUN。

先读[暂停交接记录](../experiments/so101-head-file-protocol-1003-handoff-20261010.md)和[实验账本](../experiments/so101-head-file-protocol-1003-experiment-ledger.md)。原机是 AI-STATION-001；新 agent 先记录自己的 hostname 和 cwd，确认直接运行在哪台机器，不能默认仍在原机，也不要 SSH 自身。

源码迁移包已随分支发布，证据迁移包仍在原机的登记根；两者位置与范围见交接记录。迁移清单保留原始绝对路径，所有新路径另行登记。

换机器后的恢复顺序：

1. 从已推送的分支检出代码，初始化 MuJoCo 子模块。读取本文、账本和两个迁移清单，
   核验包 SHA256、相对文件路径、字节数和文件数量。原始清单与 seal 保持只读。
2. 记录新主机、OS、CPU 架构、GPU/CUDA、ROS 发行版和包版本、MuJoCo 版本、Python
   可执行文件及依赖来源。源码基线、子模块、实际路径、工作区改动也要重新记录。
   本轮基于 Linux / ROS 2 Jazzy；其他平台先判定兼容性，不直接推断同等结果。
3. 在新主机登记一个接续任务的证据根。Linux 高频证据用
   `/data/work/so101-evidence/<task-family>/<run-id>/`；macOS 用
   `/opt/data/work/so101-evidence/<task-family>/<run-id>/`。把迁移内容作为只读历史输入保存，
   另写 relocation 清单记录旧绝对路径与新路径的对应关系，不改写历史 JSON 来伪装原机。
4. 在新根下解开源码包，建立平台适用的 ROS underlay，重建隔离 overlay。
   完整依赖闭包包括 `hardware_interface_testing`、`controller_manager`、MuJoCo packages
   和 native 包；还需构建实际使用的 `mujoco_ros2_control_msgs`。确认包前缀、公共 ABI、
   实际可执行文件和每个 DSO。实际回归的 CMake 默认值是旧对照头文件，修复门禁须显式设
   `-DCYCLE_INCLUDE_ROOT=<new-staging>/coherent/overlay-source/mujoco_ros2_control/include`。
5. 对需要引用历史文件的脚本建立新工作副本，重绑输入、模型、package prefix、解释器与
   动态库路径；保存新哈希和变更理由。先核验解析、实际 resource-plan 环境和 schema。
   原机 guardian/admission 的哈希绑定与 `/proc` PID/start identity 不适用于新主机，
   不能直接复用。macOS 没有 Linux `/proc`，须完成平台对应的身份与 retirement 证明。
6. 重跑实际边界和受影响包的完整门禁，重新做启动审查。Linux 的 fsync-heavy pytest 使用
   新 NVMe scratch，设置 `TMPDIR/TMP/TEMP`，由实际解释器证明路径；macOS 不套用 `/data`
   规则。普通 pytest 仍用 `min(8, CPU数)` 个 xdist worker，不能套用旧机器的通过结论。
7. 原机 nominal3 保持 `FAIL/NOT_RUN/NOT_RUN`。新主机使用新的 session/generation、
   ROS domain/GZ partition、IPC、输出与 scratch，先做区分真实漏步边界的有限诊断。
   新主机结果单独计数，记录主机和生命周期，不拼入原机连续成功率。

证据缺失或环境不能重建时，写清缺失项，先做源码与历史证据分析，暂不启动仿真。
本次交接只准备恢复材料；没有在其他机器启动调查。

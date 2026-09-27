# SO-101 控制器目标预留传输实施计划

> **For agentic workers:** Use `superpowers:executing-plans` inline. This plan does not authorize a second executor or subagent.

**Goal:** 在不发送 action goal 的条件下，验证 broker 进程能通过私有 Unix socket 将一个完整目标预留到控制器本地门控，并在存储后收到有界 ACK。

**Architecture:** C++ 协议解析器先把有界帧转换成原生 UUID、generation 和 typed `FollowJointTrajectory.Goal`。独立的 socket 服务端检查路径、peer 和 capability 后调用现有 `ControllerGoalAdmission`。Python 脚本作为真实跨进程客户端验证线协议；生产 broker 接入另列 EXP-517。

**Tech Stack:** C++17、ROS 2 Jazzy `rclcpp::Serialization`、Linux `AF_UNIX`/`SO_PEERCRED`、Python 3 标准库、GTest、CTest。

**Spec:** `docs/superpowers/specs/2026-09-27-so101-controller-reservation-transport-design.md`

## 全局约束

- 当前 worktree、branch 和 evidence root 不变；现有 dirty/untracked batch 不进本轮提交。
- `SOURCE_ONLY`：不启动 ROS/MuJoCo stack，不发送 action goal，也不操作真实机械臂。
- `arm` 保持控制器本地操作；socket 只支持 `RESERVE=1`。
- 请求最大 `1,048,640` 字节；ACK 是规格中的固定 16 字节，应答只在预留存储后发出。
- 每次 pytest/CTest 均使用当前 evidence root 下唯一 NVMe scratch，验证实际 Python 的 `tempfile.gettempdir()`；保留所有 RED/GREEN 证据。

## 复核重点

- 截断的长度前缀或持续滴入的小片段：在绝对期限内关闭连接并拒绝。
- 错误 PID、UID 或进程出生标识：在读取 capability 和 CDR 前拒绝。
- 正确 peer、错误 capability：不发 ACK，关闭本代预留，日志不含 capability。
- 非法 CDR、空目标、超过原语容量：不越界、不接受、不发送 action。
- 旧代、重复预留以及 ACK 写入失败：不能留下可重试的活动授权。

---

### 任务 1：有界协议与字段解码

**文件：**
- 新建 `src/so101_mujoco_support/include/so101_mujoco_support/controller_reservation_protocol.hpp`
- 新建 `src/so101_mujoco_support/src/controller_reservation_protocol.cpp`
- 新建 `src/so101_mujoco_support/test/test_controller_reservation_protocol.cpp`
- 修改 `src/so101_mujoco_support/CMakeLists.txt`

**接口：** `parse_controller_reservation_frame(bytes, capability) -> ReservationRequest`，返回 generation、UUID、typed Goal；异常或显式拒绝时调用方关闭 gate。`encode_controller_reservation_reply(status, generation) -> std::array<uint8_t,16>`。生产代码命名只用业务含义。

- [ ] 写独立字面量帧的 RED：正确帧字段齐全；错误魔数、版本、操作、长度、capability、UUID、CDR 分别失败，能力比较不提前退出。
- [ ] 运行定向 C++ 编译/测试，确认 RED 到达协议边界。
- [ ] 实现最小解析与固定应答，使用已安装 ROS C++ typesupport 解码 CDR。
- [ ] 定向 GREEN，记录命令、退出码、JUnit 与 scratch；只提交本任务文件。

### 任务 2：私有 socket 与跨进程 ACK

**文件：**
- 新建 `src/so101_mujoco_support/include/so101_mujoco_support/controller_reservation_socket.hpp`
- 新建 `src/so101_mujoco_support/src/controller_reservation_socket.cpp`
- 新建 `src/so101_mujoco_support/test/test_controller_reservation_socket.cpp`
- 新建 `src/so101_mujoco_support/test/controller_reservation_client.py`
- 修改 `src/so101_mujoco_support/CMakeLists.txt`

**接口：** `ControllerReservationSocket(path, gate, capability, expected_peer, deadline)` 绑定唯一安全路径；成功请求在 gate 存储后返回 ACK；关闭服务线程有界。测试客户端只发送预留帧，不持有 action client。

- [ ] 写 RED：不同进程的 Python 客户端在正确 PID/出生标识与 capability 下取得一次 ACK，门控只允许相同 UUID/Goal；错误 peer、capability、截断、超长、重复和超时均拒绝。
- [ ] 跑定向 RED，区分缺少实现与测试环境错误。
- [ ] 实现 socket 路径检查、`SO_PEERCRED`、绝对期限读写、协议解析、预留与应答；服务端不提供 `arm`。
- [ ] 跑定向 GREEN；确认无残留进程、无 action request，提交本任务文件。

### 任务 3：整包门禁和账本

**文件：**
- 更新 `docs/experiments/so101-act-data-experiment-ledger.md`
- 写入当前 evidence root 的 `experiments/exp516-controller-reservation-transport/result.json`

- [ ] 在现有完整依赖 overlay 构建并运行 `so101_mujoco_support` 完整 CTest；按普通范围跑受影响 Python 包的 xdist8 门禁及安装包门禁。
- [ ] 只读运行 `ament_uncrustify`，核对安装产物、退出码、JUnit、scratch 和 SHA256。
- [ ] 如实写入结论、未证明的生产启动/teacher/停止边界，提交 checkpoint；保留所有证据，不删除。

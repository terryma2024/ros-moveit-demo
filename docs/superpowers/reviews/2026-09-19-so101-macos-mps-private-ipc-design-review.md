# SO-101 macOS MPS 与私有 IPC 设计审查

## 审查信息

- 审查模型：GPT-6 Astra / High
- 审查方式：独立静态审查
- 设计文件：`docs/superpowers/specs/2026-09-19-so101-macos-mps-private-ipc-design.md`
- 最终设计 SHA-256：`480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b`
- 基线提交：`bf1b609157826bbcc18985959239c718c724d09e`
- 结论：`PASS`

本次审查没有修改源码或文档，也没有运行测试。`PASS` 只表示设计可以进入实施计划阶段，
不代表功能已经实现、macOS W2 已验收、Linux 回归已执行或具备发布资格。

## 首轮问题与修订

首轮结论为 `REVISE`。审查指出六类问题：

1. Coordinator 的推理结果准入没有定义一次性 consume、请求唯一性和旧 Broker 结果失效；
2. Broker 使用新随机 socket 重启后，存活 Worker 无法从启动参数获得新路径；
3. `input_descriptor` 没有可执行的数据传输、上限和生命周期契约；
4. 仅检查 `runtime_device=mps` 不能排除
   `PYTORCH_ENABLE_MPS_FALLBACK=1` 触发的模型算子 CPU fallback；
5. MPS start guard 的 claim 顺序、固定阈值和 2 秒 deadline 边界不完整；
6. Coordinator 异常退出时，旁路 keeper 无法可靠成为 Broker/Worker 的 reaper，且 spawn 到登记
   之间存在未闭合窗口。

设计随后增加了以下约束：

- Coordinator 分配 campaign 内不复用的 `request_id`，绑定 slot、point、attempt、model、输入
  SHA、deadline 和 owned Broker PID/出生身份；Worker 取得一次性 consume 后才能进入 pose 和
  动作门；
- Broker 故障时停止并重建整个 W2 pool，不让存活 Worker 动态切换 endpoint；
- 推理输入使用 task-owned 不可变 snapshot，校验相对路径、size、SHA、shape/dtype 和独立数据
  上限；
- Broker 在 import PyTorch 前固定并读回
  `PYTORCH_ENABLE_MPS_FALLBACK=0`，unsupported MPS operator 必须显式失败；
- `mps_minimum_headroom_bytes` 使用固定、非 per-N 的 1 GiB 启动下限，claim、probe、评估和 helper
  cleanup 共用 2 秒 deadline；
- `CampaignSupervisor` 成为 Broker 和两个 Worker 的实际 parent、spawner、reaper；spawn 前先
  持久写入 `SPAWNING` intent，child 取得 registered ACK 前不得运行，未决 intent 和
  Supervisor 异常都阻止下一 campaign。

审查还要求把放宽后的信任边界说清楚。最终设计已明确：同 UID 进程只要能访问私有 socket，
就可以提交推理请求、占用队列，或调用当时状态机允许的控制操作。状态机仍保留操作顺序、
active point、一次性结果准入和 controller 安全条件，但不承担调用方认证。该方案只适用于
受控的单用户 macOS 仿真环境。

## 最终复审

最终复审确认：

- Client 和 Server 都没有恢复 token、generation 或 lease 校验；
- macOS 使用私有短路径 AF_UNIX，权限边界为目录 `0700`、socket `0600`；
- exact W2、跨模型单一 MPS execution lane 和共享模型集合的责任边界一致；
- 五次连续有效 `FULL_RESTART` 的点集、commit、参数、成功契约和 lifecycle 必须冻结；
- INVALID 或提前终止批次不计入 5/5；
- Linux gate 正确标记为 `DEFERRED_ENVIRONMENT`，没有被写成 PASS、SKIP 或 N/A；
- Linux 回归完成前不能宣称跨平台或发布资格完成。

因此，最终结论为 `PASS`，下一步可以编写实施计划。实施计划仍需接受独立 GPT-6 Astra / High
审查后，才能进入实现。

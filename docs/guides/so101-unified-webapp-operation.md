# SO-101 单 Web 服务操作指南

这份文档说明怎么启动和使用合并后的 Web 服务，以及哪些事情现在还不能做。它只描述已经实现并验证过的部分，未验证或需要单独授权的部分会明确标出来。

## 一个服务，一个端口

统一入口是 `so101_unified_web_server.py`，默认监听 `127.0.0.1:8000`。旧的两个脚本 `so101_teleop_server.py` 和 `so101_expert_validation_server.py` 现在只打印弃用提示并转发到同一个入口，它们不再各自打开端口。所以不会出现两个 Web listener 抢同一个页面的事情。

启动方式：

```
python3 <install_prefix>/so101_teleop/lib/so101_teleop/so101_unified_web_server.py
```

绑定地址只接受回环地址或 `100.64.0.0/10` 里的地址，其它地址会直接报 `BIND_ADDRESS_UNSAFE`。

`/health/live` 表示 Web 事件循环还活着，它总是返回 200。`/health/ready` 表示启用的域是否满足各自的 readiness，不满足时返回 503。想看单个域的情况读 `/health`，它的 `domains` 字段分开列 Teleop、Tasks 和 Validation，不会把 Validation ready 变成 Teleop ROS ready。

## 控制权来自实例，不来自页面

每个浏览器 document 打开时先登记自己，拿到服务器生成的 instance ID 和 proof。proof 只留在那个页面的内存里，不写 localStorage、不写 URL、不进日志。随后这个 document 在 `/control/instances/{id}/channel` 上完成握手，服务器记住实际活跃的连接和 revision。

登记本身不授予控制权。要控制还得显式 acquire 域 lease，服务器会在同一个事务里验证这个实例真的有活跃通道，然后把该域绑定到唯一 controller。之后每个 mutation 请求都要带四个头：

```
X-SO101-Instance-ID
X-SO101-Instance-Proof
X-SO101-Channel-Revision
X-SO101-Execution-Generation
```

少了这些头，或者复制了别的页面的 lease、session、generation，服务器返回 `CONTROLLER_INSTANCE_REQUIRED` 或 `CONTROLLER_INSTANCE_MISMATCH`。旧客户端没有豁免路径。

复制另一个标签页的 storage 不会带来执行权。硬刷新、新标签是新的 document，只恢复只读快照；同一 document 断网重连可以用内存里的 proof，但服务器会递增 channel revision 并关掉旧连接。切换页面不会重新登记，也不会停止续约。

## 只读的原因会写清楚

读操作一直可用：telemetry、历史快照、campaign 结果、已有证据都能看。写操作被拒绝时会给出具体原因，而不是笼统的"请获取控制权"：

- `CONTROLLER_INSTANCE_REQUIRED`：请求没带实例 authority。
- `CONTROLLER_ALREADY_BOUND`：这个域已经有别的活跃 controller。
- `GLOBAL_MUTATION_BUSY`：另一个域正持有全局 mutation reservation。
- `BLOCKED`：有未收敛的 owner、renew fence、cleanup 或恢复 fence。
- `TELEOP_UNAVAILABLE` / `TASKS_UNAVAILABLE` / `VALIDATION_UNAVAILABLE`：该域没有组成，原因在 `/health` 里。
- `BACKEND_CAPABILITY_UNAVAILABLE`：当前 backend 不支持这个能力。

Validation 从 admission 到终止和 cleanup 完整收敛期间，Teleop 和 Tasks 只读；反向也一样。默认就是全局互斥，不按 ROS domain 或 worker 身份放开并行。

## 安全取消

取消不走普通命令队列。浏览器 cancel、lease maintenance cancel 和 owner watchdog cancel 共用一条独立的有界安全 lane，在 Web 和 child 两侧都有自己的处理任务，不等待普通的 `CommandCoordinator` 锁，也不排在普通 IPC backlog 后面。

取消的目标来自服务端保存的 action registry：每个 arm、gripper 和 parent-child 都记着真实的 ROS goal UUID、operation ID、冻结的 execution generation 和进程身份。不存在用一个 latest goal 指针或客户端自报 ID 选目标的路径。

需要知道的是：cancel accepted 只表示目标登记了取消请求。reservation 会一直保留到对应 action 真的终止、停止反馈和清理证据都齐了为止。delivery 超时、stop 超时或反馈缺失都会记成 unknown/blocked，HTTP 200 不代表物理已停。安全 lane 不会替你开夹爪、reset 或给不属于自己的进程发信号。

## 复合操作是一个 parent

Execute All 是一次服务端复合操作：`POST /plans/{plan_id}/execute-all` 一次冻结 plan ID、gripper target、canonical payload、runtime identity 和 execution generation，先持久建立 parent ID 和全局 reservation，再由受控 sequencer 走 arm 和 gripper。

arm 的终态和 gripper 派发之间不会回到 IDLE，所以别的域插不进来。arm 失败就不派发 gripper；第二步失败保留部分完成记录。这条路径上重复的 parent command ID 返回原记录，payload 变了则拒绝。

home 和 workflow 也是同样意义上的 parent。workflow 到达可续的 pause checkpoint 不算 parent 终态，reservation 还留着；resume 必须由绑定的 controller 用当前 authority 显式请求，能调用的只有 backend 原本就支持的续跑能力。backend 不支持 workflow stop 时，界面就显示不可用，不会用新的取消通道补出这个能力。

## 显式恢复，没有自动接管

Web 重启会建立新的 service epoch，让旧的 authority 失效。它只恢复可读投影和 blocked 原因：不自动接管还活着的 executor、不重发未确认命令、不启动仿真、不自动恢复 campaign。

人工恢复要确认新的 ownership、现有恢复 fence、安装来源和 cleanup，然后按显式授权改状态。旧 journal、receipts 和证据哈希保持不变，新的恢复记录追加进去。"换个页面"或"重启服务"都不能清掉 fence。

多标签场景下，如果原 controller 的连接真的没了，也不能靠复制 lease 自己接手。要么当前合法 controller 明确 handoff，要么先证明没有未收敛的 owner 再走 operator 恢复路径。

## worker 资格按 exact N 看

Worker selector 只显示 N2 到 N8。每一档的 available、unknown、rejected 和原因都来自预算 provider 的只读 view，界面不自己算，也不缓存成执行许可。未知或未达标的档位直接禁用启动，不会默认降到 N2，也不会换成 ADAPTIVE。

点位数量保持 4 到 20，包含四个固定点。PARALLEL 的 worker 数就是选中的 exact N，每批固定；点位少于 N 时仍然按 N 启动，允许部分 worker idle，不会把较低的实际并发显示成 N。SEQUENTIAL 是 1。人工失败 retry 是独立的 FULL_RESTART 单点、1-worker batch。

界面里没有 K，也没有 max-points-per-worker 或它的变体输入。

预算 provider 还没接入之前，所有档位都是 `UNKNOWN / BUDGET_PROVIDER_NOT_READY`，这期间不能 dispatch 真实批次。新 runtime 的 R 变了以后旧预算不能复用，即使 N 和抓取算法没变，也要重新测量、独立审查和 operator promotion。

## 证据查询

Validation 地图按 accepted manifest 的真实几何绘制：桌面边界、机械臂底座轮廓、杯足迹和目标 tolerance 都按实际尺寸，X/Y 用同一个 `pixels_per_m` 等比投影，响应式缩放只做整体变换，不重新随机点位。状态圈半径统一，与业务状态、worker 和成功率无关，每个圈都有编号、图标和可读状态文字，所以不靠颜色区分。

红色状态里 `FAILED`、`INDETERMINATE`、`INVALID_BLOCKED`、`INFRA_FAILED_REMAINDER` 分开显示，不会合并成一个"抓取失败率"。证据 Sheet 按 artifact registry 读真实图片、事件和物理证据；缺失或读不出来时说明原因，不会用渲染图冒充物理证据。

旧 evidence、manifest 和 receipts 保持原版本、路径和哈希。

## 现在还不能做的事

下面这些事情没有完成或需要单独授权，不要按已完成来操作：

- 本机没有完成 Task 11 的完整 configure/安装门控和 copied-install Chrome 验收，页面级浏览器证据（1400×900 与 390×844 无横向溢出、键盘焦点、读屏状态）还没有产出。
- preset 的组件级 registry 数据和自托管字体没有抓到：固定的 CLI 在本环境里连不上 `ui.shadcn.com`（curl 能拿到 200，bun 和 node 都报 other side closed），所以 `design-system.lock.json` 里只记了已验证的 preset manifest，字体列表为空，并写明 `PENDING_REGISTRY_ITEMS`。
- `ros_child.py` 的 ROS driver 还没有可运行的接线，`RclpyActionDriver` 会明确报 `ROS_DRIVER_NOT_PROVISIONED`；socket、协议、runtime、ownership 和取消路径已经验证，ROS 部分没有。
- 新 R 的资源测量、资格判定和 profile promotion 属于 Stage B，live 服务替换属于 Stage C，都需要单独授权，本指南不代替这些授权。
- 真实机械臂动作仍需要独立的急停、限速、限位与净空授权。默认停在 plan-only。

## 出问题时先看哪里

| 现象 | 先查 |
| --- | --- |
| 页面能打开但操作全被拒 | `/health` 的 `domains` 和 `blocked_reason` |
| 报 `CONTROLLER_INSTANCE_REQUIRED` | 请求是否带四个 authority 头；旧客户端需要升级 |
| 报 `CONTROLLER_ALREADY_BOUND` | 是否还有另一个标签页持有该域 controller；需要显式 handoff |
| 报 `BLOCKED` | 是否有未收敛 owner、renew fence 或 cleanup 未完成；不要用重启清 fence |
| Teleop 不可用但历史能看 | ROS child 或 IPC 是否断了；它只降低 Teleop readiness |
| cancel 返回成功但机械臂没停 | 看是否记成 unknown/blocked；accepted 不等于停止 |
| 点位图和预期不符 | manifest 的 source/geometry hash 是否匹配；失配时禁止新执行 |

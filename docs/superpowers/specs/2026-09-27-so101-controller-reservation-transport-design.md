# SO-101 控制器目标预留传输规格

## 目的和边界

ACT broker 与轨迹控制器位于不同进程。控制器现在只接受本地预留过的原生 UUID 与完整 `FollowJointTrajectory.Goal`，但 broker 没有注册通道。此规格为注册增加一条私有 Unix socket 通道。它只负责把已选定的目标交给控制器并取得“预留已存储”的确认；broker 的所有权检查、PathProof、物理停止证明和动作发送仍由各自边界负责。

注册通道不进入 ROS graph。每个运行使用唯一的 socket 路径，位于该任务 evidence root 的 `ipc/` 目录。目录权限为 `0700`，socket 为 `0600`；已有路径、符号链接、错误 owner 或权限均使启动失败。服务端在 Linux 上核对 `SO_PEERCRED`，并核对本轮 32 字节随机 capability。capability 不出现在 ROS 参数、日志或命令行中。单机同 UID 进程仍属于本轮信任域；若以后需要抵御恶意同 UID 进程，必须改用隔离用户或启动时继承的私有文件描述符，不能把现有文件权限说成强隔离。

## 请求与应答

连接使用 Unix stream socket。请求前四字节为网络序 `uint32`，表示后续帧长；帧最长 `1,048,640` 字节。帧依次包含固定魔数 `SOGR`、版本 `1`、操作、32 字节 capability、网络序 `uint64` generation、16 字节原生 UUID，以及按操作要求附加的 CDR payload。`RESERVE=1` 必须带非零 UUID 和完整 `FollowJointTrajectory.Goal` CDR。空 payload、零 UUID、未知操作、额外版本、长度不符和超过上限都拒绝。应答固定为 16 字节：魔数 `SOGA`、版本 `1`、状态 `ACK=0` 或 `REJECT=1`、两个保留零字节、网络序 `uint64` generation。CDR 只作为跨进程载体；控制器反序列化为 `FollowJointTrajectory.Goal`，由 EXP-512 的字段级准入原语比较目标。原始 CDR 填充字节不参与身份。

服务端收到完整且授权的帧后才调用 `ControllerGoalAdmission::reserve`。成功 ACK 必须在预留存储之后发出；失败不返回“已预留”。Linux peer 的 UID、PID 和进程出生标识必须与本轮已配置的 broker 身份一致；只检查 UID 不够。连接、完整读写和服务线程退出都有单调时钟期限，不能靠客户端持续发送小片段延长等待。调用方还要受剩余 commit window 限制，服务端期限不得扩展该窗口；具体时限由后续首次和尾部测量确定。异常和不完整请求关闭本代预留，不进入 action callback。capability 比较采用固定长度且不按首个不等字节提前返回。

本通道不提供 `arm` 操作。控制器必须先由独立的停止与所有权门控进入对应 generation，注册请求才可能成功。EXP-516 只以测试进程预先 arm 的控制器运行；生产启动、broker 发送和老师 MoveIt 路线留给后续实验。

### EXP-517 安全修订：已 ACK 预留的显式关闭

broker 在收到预留 ACK 后仍可能遇到动作发送异常。原先只有 `RESERVE=1`，broker 无法确认控制器已撤销这一代的预留，因此不能把发送异常直接当作已关闭。增加 `CLOSE_GENERATION=2`：请求的帧体恰好 62 字节，UUID 为 16 个零字节，不带 CDR；capability、peer 身份和截止时间沿用预留请求。控制器只在请求的 generation 等于当前代时关闭该代，并在关闭后回 ACK。旧代关闭请求返回 REJECT，不改变新代。格式错误、身份错误和超时仍按既有规则拒绝；broker 收不到关闭 ACK 时必须保留发送结果不确定状态，并等待预留有效期届满及独立停止证明，不能开始下一代动作。

### EXP-517 多目标租约修订

`Ownership` 的 generation 覆盖整个租约。ACT 同一租约可以提交多个前缀；控制器在这个 generation 内接收多个**顺序**预留，每次仍只存一组 UUID/完整 Goal。前一组必须先经 action callback 消费，下一组才可预留。已用 UUID 在本代不可再用，记录数量有固定上限；达到上限就关闭本代，不回绕、不清空记录继续接收。新 generation 只能在独立停止与所有权证明后 `arm`，`RESERVE` 和 `CLOSE_GENERATION` 均不得代替它。

broker 仍先登记本地票据，再取得当前目标的预留 ACK，最后发送同一 UUID 和 Goal。任何预留、发送或配对失败都关闭当前所有权 generation，取消已发目标并确认物理停止。新前缀还须重新取得其停止起点、完整 PathProof 和 commit window；控制器能接收下一个 UUID 并不授予新路径权限。当前插件没有生产 `arm` 路径，故保持默认关闭，直到两种启动顺序下的身份交付和本地停止证明通过测试。

## 后续提交顺序

broker 将先确定 UUID、目标和本地 goal ID，并在自己的所有权锁内登记票据；然后请求控制器预留并等待有界 ACK。收到 ACK 后，它才调用 `ActionClient.send_goal_async(goal, goal_uuid=...)`。预留超时、失败或发送结果不确定时，整代关闭并走取消与停止证明，不自动重试。MoveIt 老师目标需要单独的预注册代理，不得靠开放控制器 action 入口完成。

## 验证

EXP-516 使用独立进程做 C++ 服务端与 Python 客户端回归：正确 capability 与预先 arm 的 generation 可取得一次 ACK；错误凭据、错误 peer、截断帧、超长帧、过期 generation、前一预留未消费时的重复请求、变更目标和超时均拒绝。测试断言 ACK 后控制器确有一次预留，且没有 action 发送。完整 C++ 包门禁和普通 Python 测试门禁使用各自唯一的 NVMe scratch。此规格不授予运动或正式采集资格。

EXP-517 追加同代顺序目标回归：第一 UUID/Goal 消费后，第二个不同 UUID/Goal 可预留并消费；旧 UUID 重放、前一预留未消费时重叠预留、超出数量上限均关闭本代。broker 回归使用同一所有权票据发送两段，核对两个本地票据均先于各自的 ACK 和 action send。仍不启动 live 控制器目标。

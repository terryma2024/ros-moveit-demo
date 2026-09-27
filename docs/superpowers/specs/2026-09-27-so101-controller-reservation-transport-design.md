# SO-101 控制器目标预留传输规格

## 目的和边界

ACT broker 与轨迹控制器位于不同进程。控制器现在只接受本地预留过的原生 UUID 与完整 `FollowJointTrajectory.Goal`，但 broker 没有注册通道。此规格为注册增加一条私有 Unix socket 通道。它只负责把已选定的目标交给控制器并取得“预留已存储”的确认；broker 的所有权检查、PathProof、物理停止证明和动作发送仍由各自边界负责。

注册通道不进入 ROS graph。每个运行使用唯一的 socket 路径，位于该任务 evidence root 的 `ipc/` 目录。目录权限为 `0700`，socket 为 `0600`；已有路径、符号链接、错误 owner 或权限均使启动失败。服务端在 Linux 上核对 `SO_PEERCRED`，并核对本轮 32 字节随机 capability。capability 不出现在 ROS 参数、日志或命令行中。单机同 UID 进程仍属于本轮信任域；若以后需要抵御恶意同 UID 进程，必须改用隔离用户或启动时继承的私有文件描述符，不能把现有文件权限说成强隔离。

## 请求与应答

连接使用 Unix stream socket。请求前四字节为网络序 `uint32`，表示后续帧长；帧最长 `1,048,640` 字节。帧依次包含固定魔数 `SOGR`、版本 `1`、操作 `RESERVE=1`、32 字节 capability、网络序 `uint64` generation、16 字节原生 UUID，以及剩余的 CDR payload。空 payload、零 UUID、未知操作、额外版本、长度不符和超过上限都拒绝。应答固定为 16 字节：魔数 `SOGA`、版本 `1`、状态 `ACK=0` 或 `REJECT=1`、两个保留零字节、网络序 `uint64` generation。CDR 只作为跨进程载体；控制器反序列化为 `FollowJointTrajectory.Goal`，由 EXP-512 的字段级准入原语比较目标。原始 CDR 填充字节不参与身份。

服务端收到完整且授权的帧后才调用 `ControllerGoalAdmission::reserve`。成功 ACK 必须在预留存储之后发出；失败不返回“已预留”。Linux peer 的 UID、PID 和进程出生标识必须与本轮已配置的 broker 身份一致；只检查 UID 不够。连接、完整读写和服务线程退出都有单调时钟期限，不能靠客户端持续发送小片段延长等待。调用方还要受剩余 commit window 限制，服务端期限不得扩展该窗口；具体时限由后续首次和尾部测量确定。异常和不完整请求关闭本代预留，不进入 action callback。capability 比较采用固定长度且不按首个不等字节提前返回。

本通道不提供 `arm` 操作。控制器必须先由独立的停止与所有权门控进入对应 generation，注册请求才可能成功。EXP-516 只以测试进程预先 arm 的控制器运行；生产启动、broker 发送和老师 MoveIt 路线留给后续实验。

## 后续提交顺序

broker 将先确定 UUID、目标和本地 goal ID，并在自己的所有权锁内登记票据；然后请求控制器预留并等待有界 ACK。收到 ACK 后，它才调用 `ActionClient.send_goal_async(goal, goal_uuid=...)`。预留超时、失败或发送结果不确定时，整代关闭并走取消与停止证明，不自动重试。MoveIt 老师目标需要单独的预注册代理，不得靠开放控制器 action 入口完成。

## 验证

EXP-516 使用独立进程做 C++ 服务端与 Python 客户端回归：正确 capability 与预先 arm 的 generation 可取得一次 ACK；错误凭据、错误 peer、截断帧、超长帧、过期或重复 generation、变更目标和超时均拒绝。测试断言 ACK 后控制器确有一次预留，且没有 action 发送。完整 C++ 包门禁和普通 Python 测试门禁使用各自唯一的 NVMe scratch。此规格不授予运动或正式采集资格。

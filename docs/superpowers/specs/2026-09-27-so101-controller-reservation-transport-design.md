# SO-101 控制器目标预留传输规格

## 目的和边界

ACT broker 与轨迹控制器位于不同进程。控制器现在只接受本地预留过的原生 UUID 与完整 `FollowJointTrajectory.Goal`，但 broker 没有注册通道。此规格为注册增加一条私有 Unix socket 通道。它只负责把已选定的目标交给控制器并取得“预留已存储”的确认；broker 的所有权检查、PathProof、物理停止证明和动作发送仍由各自边界负责。

注册通道不进入 ROS graph。每个运行使用唯一的 socket 路径，位于该任务 evidence root 的 `ipc/` 目录。目录权限为 `0700`，socket 为 `0600`；已有路径、符号链接、错误 owner 或权限均使启动失败。服务端在 Linux 上核对 `SO_PEERCRED`，并核对本轮 32 字节随机 capability。capability 不出现在 ROS 参数、日志或命令行中。单机同 UID 进程仍属于本轮信任域；若以后需要抵御恶意同 UID 进程，必须改用隔离用户或启动时继承的私有文件描述符，不能把现有文件权限说成强隔离。

## 请求与应答

连接使用 Unix stream socket。请求前四字节为网络序 `uint32`，表示后续帧长；帧最长 `1,048,640` 字节。帧依次包含固定魔数 `SOGR`、版本 `1`、操作、32 字节 capability、网络序 `uint64` generation、16 字节原生 UUID，以及按操作要求附加的 CDR payload。`RESERVE=1` 必须带非零 UUID 和完整 `FollowJointTrajectory.Goal` CDR。空 payload、零 UUID、未知操作、额外版本、长度不符和超过上限都拒绝。应答固定为 16 字节：魔数 `SOGA`、版本 `1`、状态 `ACK=0` 或 `REJECT=1`、两个保留零字节、网络序 `uint64` generation。CDR 只作为跨进程载体；控制器反序列化为 `FollowJointTrajectory.Goal`，由 EXP-512 的字段级准入原语比较目标。原始 CDR 填充字节不参与身份。

服务端收到完整且授权的帧后才调用 `ControllerGoalAdmission::reserve`。成功 ACK 必须在预留存储之后发出；失败不返回“已预留”。Linux peer 的 UID、PID 和进程出生标识必须与本轮已配置的 broker 身份一致；只检查 UID 不够。连接、完整读写和服务线程退出都有单调时钟期限，不能靠客户端持续发送小片段延长等待。调用方还要受剩余 commit window 限制，服务端期限不得扩展该窗口；具体时限由后续首次和尾部测量确定。异常和不完整请求关闭本代预留，不进入 action callback。capability 比较采用固定长度且不按首个不等字节提前返回。

监听器没有收到连接时，单次等待超时只返回空闲。每次空闲返回前还要核对已绑定 broker 的 PID 与进程出生标识；broker 已退出、成为尚未回收的 zombie，或身份无法读取，就关闭门控。broker 存活时不改变当前 generation。接到连接后另起完整读写期限；错误 peer、残帧、慢帧、监听器错误和服务退出也关闭门控。生产服务须以可中断、可 join 的有界循环调用监听器，生命周期结束后先关闭门控，再停止线程并移除自己的 socket。

截至 EXP-516，本通道不提供 `arm` 操作。那一轮只用测试进程预先打开的 generation 检查传输；它没有给生产控制器授予动作权限。后续 `arm` 的条件见下文。

### EXP-517 安全修订：已 ACK 预留的显式关闭

broker 在收到预留 ACK 后仍可能遇到动作发送异常。原先只有 `RESERVE=1`，broker 无法确认控制器已撤销这一代的预留，因此不能把发送异常直接当作已关闭。增加 `CLOSE_GENERATION=2`：请求的帧体恰好 62 字节，UUID 为 16 个零字节，不带 CDR；capability、peer 身份和截止时间沿用预留请求。控制器只在请求的 generation 等于当前代时关闭该代，并在关闭后回 ACK。旧代关闭请求返回 REJECT，不改变新代。格式错误、身份错误和超时仍按既有规则拒绝；broker 收不到关闭 ACK 时必须保留发送结果不确定状态，并等待预留有效期届满及独立停止证明，不能开始下一代动作。

### EXP-517 多目标租约修订

`Ownership` 的 generation 覆盖整个租约。ACT 同一租约可以提交多个前缀；控制器在这个 generation 内接收多个**顺序**预留，每次仍只存一组 UUID/完整 Goal。前一组必须先经 action callback 消费，下一组才可预留。已用 UUID 在本代不可再用，记录数量有固定上限；达到上限就关闭本代，不回绕、不清空记录继续接收。新 generation 只能在独立停止与所有权证明后 `arm`，`RESERVE` 和 `CLOSE_GENERATION` 均不得代替它。

broker 仍先登记本地票据，再取得当前目标的预留 ACK，最后发送同一 UUID 和 Goal。任何预留、发送或配对失败都关闭当前所有权 generation，取消已发目标并确认物理停止。新前缀还须重新取得其停止起点、完整 PathProof 和 commit window；控制器能接收下一个 UUID 并不授予新路径权限。当前插件没有生产 `arm` 路径，故保持默认关闭，直到两种启动顺序下的身份交付和本地停止证明通过测试。

### EXP-517 每轮身份与 capability 交付

两种启动顺序共用一个文件合同。standalone 先启动 simulator，broker 就绪后写文件；worker 先启动 ROS child，文件可以在 simulator 启动前写好。控制器从本轮私有目录读取，不假定 broker PID 在自身构造时已知。目录路径可以作为非秘密配置传递；32 字节 capability 只存在于 broker 内存和权限受限的文件中，不放入 argv、环境变量、ROS 参数或日志。arm 与 gripper 各有独立文件和 capability，进程身份可相同。文件就绪只能创建仍处于关闭状态的注册服务，不能调用 `ControllerGoalAdmission::arm`。

交付文件使用固定二进制头，按顺序为 `SOPR`、版本 `1`、角色 `arm=1|gripper=2`、session 字节长度、一个零保留字节、网络序 `uint32` UID、网络序 `uint32` PID、网络序 `uint64` `/proc/<pid>/stat` start ticks、32 字节非零 capability，随后是 1–64 字节 ASCII session ID。session ID 只允许字母、数字、`_` 和 `-`，首字节必须是字母或数字。文件总长度必须恰为 `56 + session_length`；额外字节、截断、错误角色或 session 均拒绝。本文件不含 ownership generation；generation 只能经后续独立的停稳与所有权门控进入控制器。

broker 在自己的 PID/start ticks 确定后生成每个角色的随机 capability，把完整文件写入同目录的私有临时文件，再以不覆盖目标的原子方式发布。目录和文件分别要求当前 UID 拥有、权限 `0700`/`0600`；祖先目录不得是符号链接。控制器用 `O_NOFOLLOW` 打开并用 `fstat` 核对常规文件、owner、权限、单链接与长度，读回后再次核对预期 session/角色和本轮进程身份。文件缺失或尚未发布时保持关闭；文件无效、broker 已退出或读取超时则拒绝本轮交付。注册服务关闭时撤销门控并移除自己的 socket；凭据文件在拥有它的 broker 退出时作为运行时秘密清除，只保留非秘密哈希与生命周期证据。单 UID 信任域的限制仍适用。

两条启动链用同一目录算法定位文件：`<reservation_root>/ipc/<session_sha256前16个十六进制字符>/`。standalone 把 task station 根作为 `reservation_root`。worker 的 campaign 根若路径较深，启动方须通过非秘密环境变量 `SO101_ACT_RESERVATION_ROOT` 指定本任务已登记的短 evidence root；它必须是已准入 campaign 根的绝对、规范化祖先。worker 子进程和随后启动的 stack 使用同一根和同一目录，stack 在构图前拒绝两者不一致的配置。启动方还须把目录作为 `SO101_ACT_CONTROLLER_RESERVATION_DIR` 交给 broker 和 simulator，并在启动 simulator 前设置 `SO101_SIMULATION_SESSION_ID`。目录名只用于定位；读方仍要核对文件内的完整 session、角色和 broker 进程身份。私有目录由 broker 创建。文件尚未发布时，控制器保持关闭；Linux `AF_UNIX` socket 路径超过 107 字节时，本轮运行失败。

## 后续提交顺序

broker 将先确定 UUID、目标和本地 goal ID，并在自己的所有权锁内登记票据；然后请求控制器预留并等待有界 ACK。收到 ACK 后，它才调用 `ActionClient.send_goal_async(goal, goal_uuid=...)`。预留超时、失败或发送结果不确定时，整代关闭并走取消与停止证明，不自动重试。MoveIt 老师目标需要单独的预注册代理，不得靠开放控制器 action 入口完成。

## 验证

EXP-516 使用独立进程做 C++ 服务端与 Python 客户端回归：正确 capability 与预先 arm 的 generation 可取得一次 ACK；错误凭据、错误 peer、截断帧、超长帧、过期 generation、前一预留未消费时的重复请求、变更目标和超时均拒绝。测试断言 ACK 后控制器确有一次预留，且没有 action 发送。完整 C++ 包门禁和普通 Python 测试门禁使用各自唯一的 NVMe scratch。此规格不授予运动或正式采集资格。

EXP-517 追加同代顺序目标回归：第一 UUID/Goal 消费后，第二个不同 UUID/Goal 可预留并消费；旧 UUID 重放、前一预留未消费时重叠预留、超出数量上限均关闭本代。broker 回归使用同一所有权票据发送两段，核对两个本地票据均先于各自的 ACK 和 action send。仍不启动 live 控制器目标。

### EXP-520 停稳代次握手，尚未授予生产目标

增加 `ARM_STOPPED_GENERATION=3`。帧体恰好 62 字节：沿用 `SOGR`、版本、capability 和非零 generation，UUID 为 16 个零字节，没有 CDR。只有交付文件绑定的 broker PID、出生标识和 capability 同时匹配，控制器才处理该请求。控制器还须处于 active/hold、没有待处理或活动目标，并从自身 update 循环读到同一角色的 51 个连续 2 ms 样本；位置、速度、参考值、接收时间和 0.2 s 新鲜度按 `ControllerStopWitness` 核对。通过后才调用本地 `ControllerGoalAdmission::arm(generation)`，随后回 ACK。缺样、丢样、时钟倒退、运动、参考变化、旧代或重复代均拒绝并保持关闭。`CLOSE_GENERATION` 不要求停稳证明，任何时候都能撤销当前代。

每次 `RESERVE` 还要重新取得新鲜本地停稳证明。action 入口一旦收到请求，即使最后拒绝，也清掉旧窗口；下一段前缀须由后续 51 次原生 update 建立新窗口。这个检查只保证控制器本地的关节与参考状态，不能代替 broker 的七关节停机、负向取消、PathProof、现场状态或提交窗口。

所有权代次由同一进程内的 `Ownership` 决定。broker 先确认 `driver.stopped()`，取得当前 ticket，再在该 ticket 的锁内向 arm、gripper 两个私有 socket 分别发 `ARM_STOPPED_GENERATION`。两边都 ACK 后才能保留本代；任何一边拒绝、超时或结果不确定，都向两边发送 `CLOSE_GENERATION`，撤销 ticket，走取消与独立停机。释放、撤销、租约到期和客户端断开也须关闭两边；关闭 ACK 不确定时，不能确认新的运动租约。发 `RESERVE` 前仍要重新核对 ticket。控制器只认证 broker 进程及其代次声明，无法直接读取 Python 内存中的 `Ownership`；因此 broker 的票据检查和撤销关闭是这个信任边界的必需部分，不能把控制器本地样本说成独立验证了 broker 内部租约。

先分别用 C++ socket 与 Python client 测试帧格式、错误 peer/capability、旧代、重复代、局部停稳拒绝、双角色部分 ACK 和撤销关闭。再测 controller 插件 active/hold 的本地 `arm`，以及 broker 两种启动顺序的完整 ticket→双 ACK→预留→发送顺序。老师 MoveIt 仍需单独的预注册代理。以上门禁未通过前，生产构造函数不传可用的 `arm` 回调，也不发送 live goal。

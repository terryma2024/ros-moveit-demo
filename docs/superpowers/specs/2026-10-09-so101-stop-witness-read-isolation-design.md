# SO-101 停止证明读取隔离设计（2026-10-09）

## 目的与现状

本设计修订已批准的 [Head 预 ARM 准备状态设计](2026-10-09-so101-head-prearm-readiness-design.md) 中的停止证明读取方法。目标是在 500 Hz 采样时，让 `PREARM_STATUS`、ARM 前证明和 ARM 后证明读取同一控制器的最新一致窗口，同时不因读取持有写者互斥锁而丢失一次 `observe()`。保留 51 个连续样本、2 ms 仿真步长、200 ms 接收时间上限、测量与参考速度绝对值不超过 0.002 rad/s、参考位置逐项严格相等、一次 ARM 及其前后两次独立证明。准备状态仍只读；任何读取结果都不能代替 ARM 当次的证明。既有启动截止时间、125 ms 轮询间隔、身份绑定和 scoped close 契约继续适用。

已记录的 `live20-acceptance002` 在第 7 轮第 2 次尝试先得到 `READY`（evaluation 1、lock losses 0），约 659 µs 后于 ARM 的 `STOP_BEFORE` 得到 `WITNESS_REJECT / LOST / OBSERVATION_LOCK_LOSS`（evaluation 2、lock losses 1）。`observe()` 的 `try_lock` 失败是当前代码设置该原因和计数的唯一途径；证据没有记录当时持锁者。现有 `checked_proof_with_clock()` 在写者互斥锁内扫描窗口并取时钟，因而证明读取是能阻塞采样的持锁者。具体是哪一次读取碰撞仍属推断。失败批次为 6 轮通过、1 轮失败、13 轮未运行；全部 14 次尝试的 scoped close、物理 Stop 和拥有进程退出均已验证。历史原始 `900009` 的具体原因仍为 `NOT_CONFIRMED`，本修订不更改它。

## 方案选择

| 方法 | 结果与代价 |
| --- | --- |
| 缩短当前读锁或错开 125 ms 查询 | 碰撞概率下降，但任何读者持有写者锁的时间仍可使 `observe().try_lock()` 失败；已出现的 READY→ARM 边界不能靠时序假设消除。 |
| 双缓冲或普通 seqlock | 双缓冲在读者固定旧槽时可能没有写槽。对普通 `Observation` 使用无锁 seqlock，即便读后重试，写读重叠仍构成 C++ 数据竞争。把每个载荷字改成原子量可以消除未定义行为，但会改变采样写入成本，并需要逐项处理窗口和重置元数据的一致性。 |
| **预分配三槽发布，读者单独固定槽** | 一个写者、至多一个短时固定槽的读者下，总能找到第三个写槽。读取不接触写者互斥锁。代价是每次采样复制固定的 64 槽窗口；这项成本须在目标控制器上测量，不能凭设计推定满足 2 ms 预算。 |

选择第三种。所有槽预分配，读者的局部副本也有固定容量；实时路径不分配内存、不格式化日志、不做套接字或磁盘 I/O。目标平台须在编译时确认所用 64 位原子量无锁。写者每次的工作有固定上限：验证一个样本、更新 64 项环、选一个槽、复制固定大小状态并发布一次。这里没有声称已测得实时耗时。

## 状态、发布与读者固定

`ControllerStopWitness` 保留只供写者使用的环、计数、`next`、历史 reset 原因及样本。`observe()` 与 `reset()` 仍由原写者互斥锁串行；`observe()` 只尝试获取它，真正的 `reset()`/另一写者冲突仍计为采样丢失。三个预分配 `WindowState` 槽各含完整 64 项环和上述元数据，读者从不访问写者私有环。一个 `published` 64 位原子描述符同时含槽号及严格递增版本，版本耗尽时永久拒绝证明，不回绕。槽的载荷是普通 C++ 对象；只有其发布规则允许读者读取。

读者之间用一个**仅供读者**的互斥锁保证同一时刻最多一个槽被固定。读取用 `try_lock`；读者锁忙时直接给出“快照不可用”，不等待、更不影响实时写者。持锁读者以顺序一致原子操作读取 `published`、设置目标槽的 pin、再读 `published`。两次描述符不一致便解除 pin 并重试；一致才复制整槽到调用栈，随后解除 pin 和读者锁。后续取时钟、51 项扫描、包装器检查和回复编码都在槽外完成。

写者只从非当前发布槽中选取 pin 为 false 的槽，复制完整私有状态后以顺序一致原子操作发布新描述符。一个当前发布槽加至多一个被固定槽，三槽中至少还剩一个。读者可能在写者选中旧槽后才设置旧 pin；此时它的第二次描述符读取必发现发布版本已变化，因而不会读该槽。反过来，读者若完成了第二次读取，写者在选旧槽时必看到 pin，不能覆盖它。这一顺序一致关系排除了对普通载荷的并发读写。不能用“读后比较版本”来补救对正在写入的普通载荷的读取。

写者选择和复制不取得读者锁，也不等待 pin；若“三槽必有空槽”的不变量被破坏，设置永久的内部不可用标志并拒绝证明，不重用可能被读取的槽。读者锁只覆盖固定、复制和解除固定，不覆盖用户提供的时钟回调。写者发布描述符之前完成载荷写入；获取描述符且成功固定的读者据此看到完整状态。读者锁竞争或槽发布连续变化不会记入 `OBSERVATION_LOCK_LOSS`。

## 失效、重置与证明的线性化

单独使用现有 `lost_.exchange(NONE)` 不够：写者清除它、尚未发布清空窗口时，读者可能看到旧的有效槽。因此改为一个顺序一致的 64 位失效字，原子地携带递增事件代、最近失效原因和饱和的观察锁丢失计数。具体位分配为 32 位事件代、24 位饱和计数、8 位原因；原因保持现有枚举值。旧计数上限为 `uint32_t` 的 4294967295，新计数在 16777215 (`0xFFFFFF`) 饱和且永不回绕；这是用诊断范围换取一个一致的无锁原子字。饱和值只表示实际丢失次数的下界，线上的字段仍为 `u32`。每次新的丢失仍独立推进事件代，因此饱和不影响证明谓词。`invalidate_nonblocking()` 最多尝试 8 次 CAS 发布新的事件代和 `NONBLOCKING_INVALIDATION`，不等待任何锁。`observe().try_lock()` 失败用同样至多 8 次 CAS 在一个原子更新内递增事件代及计数、记录 `OBSERVATION_LOCK_LOSS`；不写窗口。CAS 预算耗尽或事件代即将回绕时设置永久内部不可用标志并立即返回，禁止旧证明通过。此故障处理与正常观察锁丢失分开记因。

取得写者锁的 `observe()` 在开始时取得一个失效字。如果事件代未由私有窗口处理，先清空计数并记录该字的失效原因，然后按现有顺序验证样本、处理序列/时间间隙及写入环。发布槽携带**这次实际处理的失效字**；写者绝不因随后发生的失效而声称已处理。`reset()` 在写者锁内先发布 `EXPLICIT_RESET` 新事件代，再清空私有环并发布空槽。若失效发生在写者复制期间，新槽携带较早代；读者仍因当前失效字不匹配而拒绝。后续有效采样先处理该失效，并从零重新累计 51 个样本。这样 reset 与无阻塞失效都不能让旧窗口复活。

每次证明最多尝试 3 次；pin 后描述符改变和评估时状态改变都消耗一次尝试。取得一致槽副本并解除 pin 后，依次读取发布描述符 `D1`、失效字 `I1`、内部不可用标志 `F1`，再取单调时钟 `C`，随后读取 `F2`、`I2`、`D2`。只有 `D1=D2=固定时的版本`、`I1=I2` 且两个内部标志都未置位，才用 `C` 按原顺序计算 `LOST`、`INCOMPLETE`、负时间、连续性、未来/过期样本、参考位置变化和 `Proof`；否则重试。由于版本、事件代不回绕，内部不可用标志也只会从 false 变成 true，这些相等检查证明窗口及失效状态在 `C` 时一致；`C` 才是这次证明和 `evaluated_ns` 的线性化点。固定时间重载只供确定性测试；带时钟重载每次尝试重新取 `C`，保证它晚于这次窗口捕获。暂停生产者后若读者在取 `C` 前被延迟，旧窗口按 `C` 判定过期；若调用线程在 `C` 之后才被延迟，记录仍只证明 `C` 时刻的状态与年龄，并不证明任意更晚的返回时刻仍新鲜。主通道既有 50 ms 交换上限及 2.0 秒启动绝对截止时间负责拒绝超时回复，不能把先前的 `evaluated_ns` 当作重新取时钟。并发操作若在 `C` 后发生，可由 ARM 的下一次证明或后续失效检查发现；不承诺消除任意返回后的竞态。

若稳定失效字与槽携带的已处理字不同，返回真正的 `LOST`，原因与累计锁丢失计数取自该原子字，窗口首尾来自同一槽副本。若发布版本变化，重试读取新状态；新状态可能是安全的下一样本，也可能是清空、参考变化或运动超限。有限次仍无法取得稳定版本，或读者锁忙/内部故障，返回“快照不可用”：它不是 `LOST`、`INCOMPLETE`、速度超限或一次物理 Stop。任何不可用结果都没有证明。单次成功捕获也必须通过最后的版本和失效字检查，不能以较早的 READY 快照授权 ARM。

现有合法窗口谓词和索引算法保持逐项一致：正序列与有效时间、1/5 关节范围、holding 且无 active goal、所有被监控关节的有限数值、测量及参考速度绝对值 `<= 0.002`、51 次序列与仿真时间各精确递增 1 和 2 ms、每个参考位置与首样本逐项严格相等。`Snapshot.sample_count` 仍报告最多 64 个已存样本，`Proof` 始终使用最新 51 个；首尾、失败样本/关节索引和历史 reset 来源从这次副本生成。取时钟后的年龄计算保持 `now - received > 200000000` 才过期；未来样本比较仍为 `received > now`，暂停的仿真不能靠反复读取生成新窗口。通过后的包装器仍按原顺序复查 controller active 与目标/holding 状态。一个并发更新只能在所述线性化点前被当前评估检测，或由下一次独立的 ARM 前/后证明检测；不缓存准备状态证明。

## 不可用结果与协议兼容

`CheckedProof` 明确区分 `AVAILABLE`（含现有 `Snapshot` 和可选 `Proof`）与 `SNAPSHOT_UNAVAILABLE`（两者均无）。现有 `proof()`、`proof_with_clock()` 与固定时间重载投影该结果，不可用时只返回空 `optional<Proof>`。不能造一个零计数 `Snapshot`，也不能把不可用伪装成 `LOST`。`evaluate_controller_stop()` 对不可用返回新的 `StopWrapperReason::SNAPSHOT_UNAVAILABLE = 8`，保留本次非零 evaluation ID，`allowed=false`，无 witness snapshot/proof；外层 active/scope/goal 的前后检查顺序不变。可用时，`StopProofRecord` 仍仅由同一次 `CheckedProof` 和其 evaluation ID 生成，后续更新不能改写该诊断。`BrokerOwnedTrajectoryController::StopFailureReason` 增加显式分支，移除依赖 `wrapper_reason - 1` 的盲转型，失败日志标明 `snapshot_unavailable` 且不补读见证状态。

80 字节 `ProofRecord`、`SOPR`/`SOAR` 帧长度、opcode、ABI 版本和旧 opcode 3 的回复外形保持不变，**诊断枚举契约发生扩展**。C++ 与 Python 的严格 codec 同步允许 wrapper 8，且仅接受非零 evaluation ID、`flags=0`、`witness_rejection=0`、`last_reset_reason=0`、计数/时间字段为零、索引为 -1 的无快照记录。wrapper 8 只能出现在 `NOT_READY` 或 ARM 的 `STOP_BEFORE`/`STOP_AFTER` 拒绝；不能构成 `READY`、ARM `ACK` 或 `GATE_ARM` 成功前证明。旧解析器看到 8 必须拒绝；复制安装时需核对 native/Python 版本同批来源。Head startup 对有效的 `NOT_READY / SNAPSHOT_UNAVAILABLE` 视为该尝试的终止性可用性失败，不再轮询、更不发送 ARM；若 ARM 拒绝，维持一次 ARM 上限并走既有独立 Stop 与 scoped close。真实的 `LOST` 与其他见证拒绝继续使用原有代码和轮询规则。

## 实现边界与验证门槛

实现需集中于 `controller_stop_witness.hpp`、`controller_stop_evaluation.hpp`、`broker_owned_trajectory_controller.cpp/.hpp`、`controller_reservation_protocol.cpp/.hpp`、`head_control_protocol.py` 与 Head startup 消费不可用状态的最小分支，并修改紧邻的 native/Python 协议测试。现有测试中 `ClockReadSharesTheObservationWindowLock`、`CheckedProofRecordsLossFromForcedObservationLockCollision`、`aligned_500hz_queries_recover_after_125ms`、`sustained_aligned_starvation_stays_not_ready` 故意断言读者造成采样丢失；这些断言应改为读者与 500 Hz `observe()` 对齐时采样连续、计数不增加，并分别测试真实 reset/写者锁冲突产生的 `OBSERVATION_LOCK_LOSS`。替换测试不能删除 51 样本恢复、年龄与停止安全边界。

先写会在现有实现失败的确定性交错测试：读者在时钟回调暂停时持续观察仍能发布；旧有效槽被新无效样本、参考漂移、显式 reset 或并发 `invalidate_nonblocking()` 取代时，本次评估重试或拒绝；旧槽固定后多个读者与写者连续轮转也不覆盖固定槽；失效在写者取字后、发布前到达不会丢失；读者锁忙或有限重试耗尽返回 wrapper 8；真正写者锁冲突仍为 `LOST / OBSERVATION_LOCK_LOSS`；失效事件代或发布版本接近耗尽时只会 fail closed，不发生 ABA。还要覆盖 1/5 关节、51 与 64 样本、严格速度界限、未来/过期边界、暂停窗口、每个 reset 原因、原生和 Python 对 wrapper 8 的接受及对伪造字段的拒绝、READY 到 ARM 前/后的新鲜证明。锁丢失计数用测试专用的近边界状态注入覆盖第 16777214、16777215、16777216 次事件，无需实际循环千万次：数值停在 16777215，失效事件代仍逐次推进；原生和 Python codec 都须往返检验饱和值，而原有 `uint32_t` 范围用例仍验证旧布局兼容。生产者暂停、读者在取 `C` 前延迟跨过 200 ms 时须得到 `STALE_SAMPLE`；在 `C` 后延迟越过通道或启动截止时间时须由客户端拒绝迟到的结果。

并发门槛使用 ThreadSanitizer 或实际等效的数据竞争检测器验证普通载荷；单独通过 ASan/MSan 不足以支持无数据竞争结论。实施计划须在测试前冻结准确的 500 Hz 负载、持续时长、单/多读者数量、对齐与故意停顿时序、测时方法，以及见证发布、完整 controller `update()`、读者证明和整条 50 ms 主通道交换的通过判据。记录发布函数体耗时与实际控制周期/调度延迟，不能用后者替代前者。真实目标上的单次见证发布及完整 `update()` 都必须装入现有 2 ms 更新周期；正常单启动读者的冻结 500 Hz 压力场景须有零次读者造成的采样锁丢失、零次意外 `SNAPSHOT_UNAVAILABLE`，且每个有效主通道交换在原有 50 ms 上限内完成。故意锁住读者或耗尽 3 次捕获的用例则必须产生 wrapper 8，并与正常场景分开统计。若写入超时或正常场景出现终止性不可用，该方案不得进入 live gate，应重新审查发布方法。2.0 秒启动截止时间和 125 ms 轮询间隔保持不变。

全 native package case 身份与既有基线、定向 Python 协议用例、普通 Python gate 的历史 176 个既存失败/错误均须比对；新复制安装的 native/Python 映射与运行进程来源也须验证。所有门槛通过后才开新的冻结 20 次 `FULL_RESTART` 批次，并在首个拒绝时停止；全部 20 次通过后才启动单独的冻结 40 case。失败的原 20 次批次不续跑、不改写。

本文件是设计，不构成已实现或已验证的修复。原预 ARM 设计及实施历史保持原样，实施计划须在本文件书面审查后另行修订。

## 证据与保留

注册的唯一持久证据根为 `/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`。本次设计读取了该根下 `head-file-protocol-1003/head-camera-yolo-optimization-20261009-001/optimization-fix-20261009-001/protocol-implementation-ivicy38d/live20-acceptance002/closure001/failure-analysis.json` 与既有账本 checkpoint；未运行测试或服务。保留原批次与本设计；本次未归档、未删除证据。现有 scratch 和已结束 IPC 路径仍只是待授权删除候选。

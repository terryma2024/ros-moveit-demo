# Head Search 40 点：生产曝光身份绑定修订提案

状态：revision 4 提案，未批准、未实施。revision 3 的 Astra 审查指出，默认 allocator 不能提供 serialized buffer 的 native 硬上限；本版撤去该保证，分别规定 take 后复制上限与 native 内存准入。revision 2 的 stock-rclpy GID 接口已被实际诊断否定，其有条件审查不适用于本次新增收件适配。V1 配对与 V2 首帧条件对照的批准继续有效。本次只处理初始化期间 Reset 前后同时间戳的生产原件归属。

## 已确认的失败

当前 native `ResetWorld` 保留仿真时间；`CameraPlugin::on_reset` 清除相机发布水位并触发新的暂停曝光。复制当前生产库的真实 640×480 测试中，Reset 前后 RGB 的 source stamp 都是 `200000000 ns`，像素不同；Info 的原始 CDR 完全相同。V2 的第一条 FRAME 含第二次曝光的 RGB/Info，sequence 为 1。

当前 collector 在 stack.start 前订阅生产 topic，使用贯穿准备阶段的 source 水位。因此第二个真实 RGB 被拒绝，错误为 `HEAD_TRUTH_PRODUCTION_ORDER_INVALID`。实际 native CDR 的离线回放也在这一边界失败。native 测试覆盖实际 observer/render/publisher，未调用完整 ResetWorld 服务；离线回放不是运行时收件，也不能计入 pilot。

原件及失败位于注册根 E 下的 `head-file-protocol-1003/head-search-40-20261006-001/native/initial-reset-source-diagnostic001/` 和 `diagnostics/native-cdr-consumer002/`。第一轮回放的 C++/Python CDR 字节重复前置检查未通过，未到达 consumer，标记 INVALID。第二轮保留 native CDR 不变，按字段解码回放，Python 重序列化产物明确标为回放证据。

仅允许重复 source stamp 会留下另一处歧义：相同 stamp、相同 Info 字节不能证明收到的是 Reset 后的生产发布。恢复准备阶段的原件归属需要发布者身份与真实发布序号，不能用接收时间猜测，也不能从 V2 内层重序列化制造生产原件。

## 新的最小合同

新增 `CameraTruthFrameV3.msg`，保留 V1/V2 定义及已保存 CDR 的解码。V3 包含：

```text
uint32 schema_version
CameraTruthFrameV2 original
uint8[16] production_rgb_publisher_gid
uint8[16] production_info_publisher_gid
uint64 production_rgb_publication_ordinal
uint64 production_info_publication_ordinal
```

FRAME 的外层 schema 为 3，嵌套 V2/V1 约束不变。两个 GID 取自现有生产 publisher 的 `get_gid()`，创建后固定。ordinal 是同一 owned publisher 自创建起完成的 publish 调用计数，从 1 开始；它不是从仿真时间推算的序号，也不声称由通用 RMW publish API 返回。计数覆盖准备阶段，不能在 on_reset 清零。任一发布异常或计数溢出均不生成可验收 FRAME。当前 Jazzy 的 `RMW_GID_STORAGE_SIZE` 为 16；要求完整 16 bytes 且非全零，不填充、截断或变换 GID。

本版本只准入已冻结、实际验证的 `rmw_fastrtps_cpp`，且要求实际 RMW 支持 publication sequence。producer ordinal 与 subscriber 的真实 MessageInfo publication sequence 相等，是必须检查的合同。不能假定任意 RMW 的起始序号、GID 跨 context 表示或计数语义；首个实际 raw 收件序号必须为 1，每个 channel 后续必须连续递增，且 native FRAME 与实际 raw GID/序号逐项一致。缺首件、未知 publisher、unsupported 序号、间隙、倒退或不相等立即锁存故障，不估算 offset，不做其他 middleware 的兼容回退。

实现门必须用真实 native publisher 和独立进程的 rclpy subscription 验证上述映射。当前同 context 的 native MessageInfo 诊断仅检验可行性。即使它通过，也不能替代跨进程门；跨进程或发布计数不满足合同，停止这一方案，保留失败，不切换到另一方案继续执行。

FINAL 保持旧末尾水位，新增 GID 与 ordinal 全为空/0，禁止冒充生产曝光。每条 FRAME 的身份字段跟随整条不可变条目，队满丢整帧、锁存 loss。沿用当前容量 2（含 DDS 发布中条目）、best-effort/depth 1、唯一 sender、render lock 内不等待与 50 ms retirement。

原生产 RGB/Info 的 bytes、header、topic、发布顺序、发布 cadence 和原 publisher 均保留。没有附加生产发布、重建 publisher、额外 topic、服务、sender、物理 step 或仿真时钟修改。仅开启本 campaign 的 schema 3 时维护这组身份字段；默认关闭不创建 truth state、V3 publisher、订阅、计数缓存或线程。V1/V2 路径仍可运行并解码。

## 可选的 RCL raw 收件适配

实际 antzb 的 rclpy 为 `7.1.11`，普通 raw callback 的 MessageInfo dict 只含 source/received timestamp 与 publication/reception sequence，未暴露 publisher GID。直接读取该字段会失败。[官方 Jazzy take 实现](https://github.com/ros2/rclpy/blob/jazzy/rclpy/src/rclpy/subscription.cpp)也显示这四个字段；该链接只是接口佐证，不能替代本机 ABI/安装 SHA 的核验。因此 revision 2 不能按 stock-rclpy callback 接口实施。

新增 opt-in `head_campaign_raw_take.py`，在原 owned executor 的收件点直接调用同一个公开 `rcl_take_serialized_message`，同时取得原始 CDR 和该次 take 的完整 `rmw_message_info_t`。只为 V3 collector 的既有三个 raw subscriptions 使用此适配；physics subscription 和所有其他 subscriptions 仍走标准 rclpy。保持已有 node、context、subscription 数量、CallbackGroup、waitset、executor 和线程数量，不另造 collector 或 ROS 接收进程。

接口为 `CampaignRawTake(abi_ref, max_cdr_bytes=16777216).take(subscription) -> tuple[bytes, dict] | None`，以及 `create_campaign_executor(node, collector)`。provider 只在该 node 拥有 schema 3 collector 时构造 `SingleThreadedExecutor` 的 scoped 子类，覆盖 `_take_subscription` 的这三条已登记 subscriptions；其他 entity 调用 super()，默认使用原 class。adapter 的 tuple 是内部 take 结果；executor override 必须返回 async callable 或 None，保持 rclpy 的调用合同，不能直接返回 tuple。这里保留现有实体的 CallbackGroup/等待机制；不能在正常 `_take_subscription` 已取走消息后再读取一次，也不能从其他消息或 ROS graph 拼接 sender GID。

安装版 executor 在保护 `ending_execution` 的 try/finally 之前调用 take，因此 override 必须收拢 adapter 的普通异常，锁存故障并返回一个在原 handler 内执行的 async callable，不能让异常从 take 点直接逃出。即使关闭发生在 callback 排队后，也要经过原 handler 的 CallbackGroup 收尾；实际 no-data 返回 None 的路径仍走原机制。回归必须使用真实 installed executor 验证 take 异常、fini 异常、排队后关闭、无数据四条路径的 `beginning_execution`/`ending_execution` 与后续 entity 可调度状态，不能只检查 adapter 返回值。

使用 `with subscription.handle` 保持真实 rclpy handle 生命周期，pointer 只来自已登记的同一 live subscription 的公开 `.pointer` 属性。拒绝无注册、非 raw、错误 node、关闭状态或空 handle；不得接受输入文件、任意整数或旧 registry 中的地址。只在真实 take 返回 OK 时复制其 bytes 和 metadata，unsupported sequence 不估值。take-failed 返回 None，其他错误立即锁存 collector 故障，不伪造缺件或静默回退。rmw allocation 为 NULL；serialized buffer 使用真实 rcutils 默认 allocator 初始化，成功初始化后所有退出路径 finally 调用 fini，失败则拒绝 retirement。

ctypes ABI 必须先由本机编译的只读 header probe 验证：结构大小、alignment 与每个字段 offset、GID data 长度均逐项一致，不靠平台名称猜布局。当前诊断的 gid struct 为 24 bytes，其中实际 GID data 为 16 bytes；message info 为 64、serialized array 为 64、allocator 为 40。禁止把 struct 大小 24 当成 GID data 长度。

本版使用 rcutils 默认 allocator，不承诺 native serialized buffer 的硬上限。`rcl_take_serialized_message` 在预分配不足时会扩容；16 MiB 的 `max_cdr_bytes` 只在 take 成功后、`ctypes.string_at` 或任何 Python bytes 复制前检查 `buffer_length`，同时限制后续落盘 artifact。超限立即锁存故障并 fini，不复制、不解码、不写原件，也不声称已经阻止此前的 native 分配。preallocation、depth 1 和 writer 上限均不能替代这一分配边界。不新增 allocator callback、native 包装库或隐式内存限额。

Task5 的内存准入另行计算并保存：冻结 publisher 的固定 640×480 生产字段、各字符串/数组的实际生成上限、首帧最大参考与 V3 封装，生成每条 channel 的最大合法 CDR；用实际 serialized size 和 allocator 的实际 buffer_capacity 回读核验，计入 take 扩容期间旧/新 buffer 并存、middleware 接收缓存、Python 复制、collector 缓存、sender 两槽和 RSS 高水位。该数字是冻结 owned producer 合同内的资源预算，不是 RCL 分配器的强制上限。任何字段没有可验证上限、实际 capacity 超出预算或峰值未留余量，保持 NOT_ADMITTED；不能仅靠正常帧的平均大小宣称准入。未知 publisher 或异常超大原件可能在 GID/长度校验前已经造成 native 分配，本版不能保证其内存硬封顶；它们仍须拒绝验收。若任务要求这种硬保证，应停止本版并另提限额分配设计，不在实施时补造 allocator。

新增定向回归要证明长度上限的真实位置：保留一次默认 allocator 接收超限 serialized bytes 的 native capacity 记录，断言发生扩容后 adapter 才拒绝，并验证没有调用 Python bytes 复制/解码/writer、fini 已完成、故障锁存及原退出预算。分配失败或 fini 失败也要保留真实失败码，禁止转成正常无数据。该诊断只能验证 take 后合同，不计入 campaign 原件或 runtime 准入。

ABI receipt 通过 fixture 的 `lighting.native_take_abi_ref` 作为普通 sealed bytes/SHA 引用提供，不新增顶层业务 CLI 参数。它包含实际架构/Python/rclpy/RMW/FastDDS 版本、完整 C header 和已解析 shared-library refs、rclpy native module/executors.py SHA、probe 源/可执行 SHA、实际 sizeof/alignment/offsets 和执行 rc。prepare_case_fixture 只消费已有验证 receipt，不在 runtime 或 fixture 准备函数里隐式编译。factory 在 stack.start 和任何 pointer take 前回读所有 pin；变更或闭包不足 fail closed。ABI probe 属于 Task5 的 copy-install/freeze 门，生成物保留于注册证据根。

默认路径不 import ctypes backend、不 dlopen、不创建 adapter/registry/原始复制缓冲。无 fixture 或 logging-off 的原资源/日志边界保持。该 adapter 在本次冻结的 Linux x86_64/Jazzy/rmw_fastrtps_cpp 上验证，不能据此宣称其他平台支持。

retirement 先关闭 registry 新 take 准入，使用现有 callback condition 同时追踪 take-in-flight 和 callback-in-flight。持有 handle 的真实 take 未返回时，不能销毁 subscription 或宣称退休；仍在原 50 ms 预算内返回 unconfirmed 并锁存失败，保留资源供原 owned 退出流程处理。callback 已排队、关闭期间 handle destroy、失效 handle、writer 锁阻塞、native take 未返回、异常/fini 失败都需回归；不能以 ctypes 释放 GIL 为由允许另一个线程无保护地销毁底层 handle。

C-only 诊断已用编译 header probe 验证布局，实际 RCL take 从独立 native 进程收到 Info 的 GID/sequence 1、2 与 raw FINAL。完整 RGB/初始 V2 原件尚未通过：原始 raw 和标准 typed rclpy 都未收到 RGB，保持 native 进程直到收件的 2 s 屏障仍失败，具体原因未确认。单改测试子进程为 LARGE_DATA 也未通过（该轮连 Info 也缺失）。所有失败、原件、进程终止记录保留；这些证据只能支持小消息 API 可行性，不能证明完整身份合同、实时路径或初始化已修复。

本提案不包含传输/QoS/缓冲调优、RMW 切换、增加发布等待或扩大超时。实施前必须先让默认传输下真实 640×480 native→stock-rclpy 的 baseline 在实际 DDS matched subscriptions 证明后通过，才能验证 adapter 的同一路径。matched endpoint 必须是 producer 的实际 DDS publication-matched 状态，ROS graph count 不能冒充连接已完成。若 baseline 或 adapter 原件/GID/序号门仍不成立，停在该门，保存 UNKNOWN，不应用 transport 替代方案；需要其他变更时另写合同和审查。

## collector 的准备阶段

V3 的 Image/Info 与 paired subscription 使用 rclpy `raw=True`：callback 接收的 bytes 直接保存为实际接收 CDR，先保存再按固定消息类型解码。禁止 typed-message 重序列化冒充接收 CDR。raw 收件同时保存同一次 RCL take 获得的完整真实 rmw_message_info（见下方可选适配），以 dict 传入 callback，含 GID、publication sequence、middleware 时间与 callback 入口实际接收 UTC/monotonic 时间。不得合成 MessageInfo。外层 V3 的实际 raw CDR 整体保存；V2/V1 内层只解码，不标为独立收件原件。V1/V2 历史路径和 CDR 仍保留，不能回写其来源标签。

每个 channel 保留最多两条最近 raw 消息及其小型身份记录，用于等待首帧不同 topic 的到达顺序。文件原件全部保留，内存不累积帧历史。必须检查类型、布局、有限值、source 大于 0、实际 publication sequence 连续和 publisher 固定；source 倒退仍立即故障。

准备状态为 `PREPARING → INITIAL_PAIR_COMMITTED`。reset receipt 到达或调用 bind_reset 只保存事实，不能提前关闭窗口、清空暂存的相等事件或跳过绑定。直到 reset receipt、V3 第一帧、两路精确身份及原件全部匹配且提交 readiness，才进入 `INITIAL_PAIR_COMMITTED`。receipt/raw/paired 三类到达可任意交错，RGB/Info 两路也可任意交错。

在 `PREPARING` 状态，最多允许每 channel 一次相邻 raw source 相等，状态为未归属准备原件。这不代表 readiness，也不消除已有故障。它只有在以下全部成立时才能被解释为合法 reset 边界：

- 已收到并校验真实 paused/step-zero reset receipt，session/epoch/model 与封存输入一致。
- native 第一条 V3 FRAME sequence 为 1、source 与 reset receipt 完全相同。
- FRAME 的两个 GID/ordinal 分别与收到的第二条同 source raw 消息的真实 MessageInfo 完全一致。
- RGB/Info 类型、header、尺寸、所有字段和 bytes 与该 FRAME 的原生产输入相同；首帧参考仍满足 V2 的所有门。

缺失或超时保持 UNKNOWN，重复次数超限、身份/原件不匹配立即锁存故障。第一次曝光没有 source 重复时也要做同样的 GID/序号原件绑定。全部暂存相等事件必须由此次 reset 对应的第一帧消解；有任何遗留就拒绝提交。进入 `INITIAL_PAIR_COMMITTED` 后，所有生产 source 必须严格递增；后续同 stamp 即使 publisher 序号增加也立即故障。V1/V2 的既有 source 检查保持严格。

HeadSearchController、真实相机 SDK、tracker 与 motion admission 的无效或不递增输入故障逻辑不改。本条准备原件合同只用于初始化事实证明，不把未归属原件或 native 真值送入控制/感知，也不扩大 detector、相机新鲜度、失帧、executor、搜索或 Stop 预算。

## builder、接线与内存

V3 绑定的是 native 出口 MessageInfo。collector 订阅 topic 仍从封存 native camera config 获取；当前无 relay 时它就是直接生产输入。原计划 Task3 接入 CameraRelay 后，native 出口改为已批准的 `/hs40/raw/color`、`/hs40/raw/camera_info`，这些 native GID/ordinal 只用于 raw source 原件绑定。relay 向 `/head_camera/color`、`/head_camera/camera_info` 的重新发布有独立 GID/sequence，不得拿 native GID 去匹配 relay publisher，也不得以 native 原件存在宣称 SDK 已收到。

Task3 沿用原 relay 合同，保留 native 收件、实际转发、relay publisher 身份、source/receipt 水位和 SDK 输入字节接线的证据。转发内容必须与 native 原件逐字段、像素 bytes、stamp/frame_id 一致，SDK 也必须有实际收件及内容匹配证明；缺证据判 UNKNOWN。仍用同一 owned collector 与 owned relay，不创建第二 collector，本次不提前实施 relay。

fixture/render-config 显式选择 schema 3，`lighting.native_take_abi_ref` 提供相同冻结 ABI receipt，保留 V2 reference 配置。provider 仍创建一个 owned collector，接线时选择 V3 类型；没有第二套 collector。builder 从 V3 解出原 V2/V1，校验生产 GID/ordinal 与封存 raw 原件记录；初始条件和每张运动帧的动态 truth 都需要此绑定。动态 truth 继续 exact join 实际 physics chunk 的 session/reset/step 与 source ns，不能借首帧参考或 publication ordinal 替代物理原件。

变更文件范围：msgs 的新 V3 及 CMake；camera_plugin.cpp/.hpp 与必要 native 依赖/测试；head_search_campaign_scene.py、head_search_campaign_truth.py、head_campaign_truth_collector.py、新增 head_campaign_raw_take.py、必要 provider/executor 接线及对应普通测试、只读 native ABI probe/匹配状态测试。source/profile/input 有变更后创建新 copy-install freeze，旧冻结及所有 CDR 均保留。

固定字段为每 FRAME 48 bytes 的有效数据，另加 schema/封装和 CDR 对齐；sender 两槽与最大合法 CDR 按真实类型重新计算，默认 allocator 的扩容及峰值按上面的独立内存准入记录。collector 的第二份 RGB 为 640×480×3 = 921600 bytes，两个 channel 的实际对象/CDR/Info 和最大 record 元数据也必须计入。不能只计算像素或把 writer 的内容寻址当作预算折扣。

本提案不新增 attempt：仍为 7 pilot + 48 formal = 55 attempt，formal 分母 40 case，Search 终态后仅 local Stop/owned retire/seal/exit audit。完整容量、10 Hz、新鲜度、Stop 与退出准入均需重新回读。当前可用空间不足，提案批准也不解除 runtime NOT_ADMITTED。

## 实施与验收顺序

1. 保留同 stamp native 原件和 consumer RED。先完成默认传输下实际 native DDS publication-matched baseline、完整 ABI receipt 与 retirement RED，再新增独立进程 native/可选 RCL raw take 门，包括 publisher GID、首序号、连续序号、实际 reset 相邻曝光和原生产 bytes；跨进程映射失败即停止本方案。
2. baseline/ABI 门实际通过后建立 V3 与 scoped raw-take RED（旧标准 callback 缺 GID 的实际失败保留），然后最小实现固定身份字段与原件 exact join。覆盖首件丢失、raw/paired 到达乱序、间隙、未知 GID、unsupported 序号、假 offset、计数不符、receipt/raw/paired 与双 channel 任意交错、未消解的相等事件、raw CDR 逐字节保存、native/relay 身份混淆、仅一个 channel 重复、第二次重复、绑定后的重复、缺原件/参考、FINAL 非空和 retirement；补上真实 executor 的 CallbackGroup 收尾与 take 后超限/分配/fini 失败门。普通路径不收集新增资源。
3. 用实际 640×480 native 测试验证原 RGB/Info 不变、V1/V2 历史 CDR、V3 整帧 loss/容量、默认关闭及原 50 ms retirement。再做 initial-condition 与 dynamic-physics exact join 的定向 RED/GREEN。
4. 完成 msgs/plugins 的完整依赖闭包及 native package gate；demo 普通 test/ 与实际 colcon package 各使用 8 worker，不收集 benchmark。copy-install 后逐项回读 source/install SHA、真实 msg 类型与环境。实施结果 inline 自审。
5. 固定六条任务只更新状态；本补充属于 Task2，不提前标完成。Task3–6 继续执行原已批准计划，不增加可见任务文本。运行前仍需完整容量和所有准入门，保留全部失败。

设计需独立 GPT-6 Astra High 审查，实施仍由当前 Codex 唯一执行并 inline 自审。

## 批准范围

此前批准的 V2 增加首帧条件参考，但没有这一组生产发布身份字段、可选 RCL raw take/ABI 接口，也没有准备阶段一次同 source 绑定的规则。因此需要单独批准本次 V3 合同，不能从 V2 批准推定授权。

本提案不授权硬件、pick-place、ACT collection、dst、第二执行器、新 worktree/branch、simulation restart、commit/push 或删除证据；旧 goal 保持暂停。没有修改实现，也没有启动 pilot/formal。

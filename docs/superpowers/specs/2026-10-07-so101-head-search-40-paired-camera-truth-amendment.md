# Head Search 40 点：相机真值最小合同修订

状态：提案，尚未批准。原 40 点执行计划已获批准；本文只补充其中被实际复现阻塞的 Task 2 真值路线，不扩大到 pick-place、硬件或 qualification。

## 已确认的问题

原计划试图按相机 source ns，从完整 physics qpos/qvel 离线重建实例 mask。native 在 `mj_step` 后通知 observer；相机复制当时的派生渲染状态，而 physics 原件记录积分后的 qpos。离线 `mj_forward` 会更新派生几何，因而可能重建出另一幅图。

本轮独立 MuJoCo 3.12.0 复现使用 F022 的实际封存 Head scene、相机和初始姿态。缓存副本与重建副本的 time、qpos、qvel 完全相同。颈部实际速度为 0、0.00874459 和 -0.08558559 rad/s 时，分割分别有 5、34、249 个像素不同；RGB 分别有 915、3650、16824 个像素不同。前两个样本的颈部速度低于原 Stop 阈值，仍不能建立逐帧等价性。

复现是独立模型与渲染诊断，未启动 ROS stack，也不声称采到了正式相机 publisher 原件。其结果结合已核对 native 调用顺序，足以否定“同时间戳 qpos 天然足够”的前提。第一次诊断的 actuator enum 类型比较导致初始 control 未正确设置，保留为诊断辅助错误；结论使用修正后的 `render-phase002`，不以第一次样本证明停稳。

证据：`E/head-file-protocol-1003/head-search-40-20261006-001/diagnostics/render-phase002/result.json`；E 沿用原计划唯一根。

## 推荐的补充：同一次原生渲染产生 RGB 与实例真值

在 CameraPlugin 增加一个默认关闭、只供声明的开发 campaign 使用的真值出口。启用时，在原 RGB 已渲染的同一 `mjvScene`、同一 render lock 和同一 stamp 下，再渲染实例 ID。直接保留这次实际视角的 mask，不再从 post-integration qpos 猜回相机几何。

此功能只产生测试验收证据，不能把 mask、场景实例 ID 或真值送入 HeadSearchController、tracker 或 CUDA detector。现有生产 RGB/Info 的内容、topic、header 和发布顺序保持原合同；不调用 `mj_step`、不对 live `mjData` 调用 `mj_forward`，也不修改 JTC、搜索策略、安全阈值或 Stop 预算。

### 原件合同

拟新增 `mujoco_ros2_control_msgs/msg/CameraTruthFrame.msg`，由 CameraPlugin 在本轮私有 topic 发布一个完整配对记录。使用现有 msgs 包可避免依赖 `so101_mujoco_support` 造成包依赖环。记录包含：

- `schema_version`、本轮冻结的 capture identity、严格递增的 frame sequence；
- 原 RGB `sensor_msgs/Image`、原 `sensor_msgs/CameraInfo`、实例 ID image；
- 三者共享的原 camera stamp/frame_id，以及明确的 camera/model/render-config 引用；
- 与该实例图对应的 segmentation ID → geom ID/type 映射。模型 closure 中的 geom → cup/distractor/support 实例映射另以封存 fixture 引用绑定。

配对记录直接携带此次原 RGB 和 Info 的原始内容，collector 必须逐字节核对它们与真实生产输入相同；不得用三个独立消息的“最新值”拼接。接收端记录 UTC/monotonic 接收时间、原始记录和 SHA；严格核验 image 编码、尺寸、步长、endianness、ID 有效范围、模型及配置 SHA、frame sequence 和原始 source ns。

capture identity 只说明本轮 publisher 来源，不能代替真实 native session/reset epoch。collector 仍按 exact source ns 关联 lossless physics 原件以绑定实际 session/epoch；须证明 publisher/process/config ownership 和 reset 后启用顺序。时间回退、重置或身份冲突立即结束该流，不能把上一轮同时间戳的真值用于新 attempt。缺完整原件、映射、身份或生产输入字节核对时判 UNKNOWN，阻塞正式运行。

ID-color 原件按 `R + 256*G + 65536*B` 解码，其值为 `segid+1`；0 是背景。只允许使用本次同一 `mjvScene.geoms` 的 `segid → (objid,objtype)` 映射，不能把色值当 geom 数组索引。输出实例图固定为 `32SC2`，每像素依次是 signed int32 object ID、object type，小端、`is_bigendian=false`、`step=width*8`。背景编码为 `(-1,-1)`；非 geom 对象保留真实 ID/type，目标归属只使用冻结 fixture 声明的 geom。重复/缺失 segid、越界值或无法解释的映射拒绝该帧。实例图按原 RGB 同样垂直翻转，不能插值或缩放。边缘像素必须证明分类 ID 没有颜色混合；核对冻结 MuJoCo 3.12.0 segmentation 标志及实际 offscreen readback，不预先假定必须新增第二 GL context。

### 渲染与退出边界

使用 MuJoCo 已有的 segmentation/ID-color 渲染标志，构造对应的 geom ID/type 图。标志修改仅作用于本次已构造的可视 scene，第二次渲染后恢复原标志；异常路径同样恢复。不能在第二次渲染中重建 scene、推进模拟或换用更新的 mjData。记录真实渲染阶段和映射，不直接把 ID-color 色值当作未经解析的实例 ID。

默认关闭时不创建真值 publisher、mask buffer 或额外渲染任务，原相机测试及日志关闭路径照旧。启用时使用容量固定为 2 的预分配不可变 frame 队列，内存上限由冻结的分辨率、两图字节数、Info 和有界映射条数计算；单条超限拒绝。render/data lock 内只深拷贝当前配对原件并 `try_enqueue`，不得等待消费者；队满丢弃新条目并锁存 loss/watermark。专用 sender 在锁外发布，QoS 固定 best-effort、keep-last depth 1，不在 render/data lock 中执行 DDS publish 或写盘。ROS 发布时间仍要实测有界；慢接收者不得延长原相机和 Stop 预算。

原 RGB/Info 的实时发布不等待 truth receiver。真值丢失使验收 UNKNOWN，不能篡改已有原 RGB 或检测结果。保留未修改的 10 Hz/freshness/Stop 门；额外渲染、深拷贝或 sender 无法满足时此方案拒绝准入。退出保存最终 generated/enqueued/published/dropped sequence 与计数、loss 标记及 receiver 最终水位，特别检查最后一条丢失，不能只靠下一条 sequence gap 检测。

退出时停止接收新条目，按本轮封存的有限 retirement deadline 尝试发送剩余条目；未发送部分记 dropped，不无限 drain。必须证明所有本轮真值 subscriber/publisher、线程和缓冲区已退休。若 DDS publish/线程无法在原退出合同内结束，记录未证明的退出并阻塞下一 attempt，不能强杀并报 PASS。原受控 signal/失帧的停车仍由 Head 本地运行时承担；真值出口不能充当 Stop ACK。

## 拟修改文件与验收

只有本文获批准后才修改以下 native 文件；目前未修改 submodule：

- 新增 `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/msg/CameraTruthFrame.msg`，调整该包的接口生成依赖。
- 修改 `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.cpp`、`camera_plugin.hpp`，及必要 CMake 依赖；为现有相机测试增加同帧 RGB/实例图、标志恢复、默认关闭和退出边界回归。
- 在 Task 2 的 collector/truth builder 中，验证并使用完整 native paired record；离线 builder 负责映射、遮挡/目标归属和 SHA 原件回读，不再以 qpos 重建 mask。保留 physics 原件用于实际 session/epoch 和场景安全事实。
- 在每个 campaign 的冻结插件副本中显式开启私有 truth topic。默认插件配置保持关闭，不改变普通 Head 的运行路径。

实现前新增 RED：运动与停稳帧的同帧原件等价、第二渲染时相机快照/已构造 scene 被替换或修改的拒绝、RGB24 解码及背景/非 geom/边缘 ID、错误映射/翻转/字节序、重复或跨 epoch frame、原 RGB 字节不符、遗漏配对、慢接收者/末尾丢失/退出期间队满、异常恢复及默认关闭无额外渲染。允许独立物理线程继续推进；同帧合同绑定冻结快照、scene、stamp 与原 RGB，不要求暂停 live simulation。实现后 GREEN，再完成 msgs/plugins 依赖闭包 build/package/native gates、demo 完整 ordinary/package 8-worker gates、copy-install 和源/安装 SHA 回读。

新的 freeze 先验证原五个 pilot，并额外用有实际颈部运动及 quiet feedback 的帧证明真值不再依赖 post-qpos 渲染阶段。所有 40 条正式用例的三帧锁定、双杯/无杯、低照度及遮挡条件仍按原矩阵检查；分母仍为 40 case/48 attempt，pilot 分开。

重新计算完整磁盘预算并通过 ownership/CUDA 准入后才能进入正式批次。不得通过减少原件、降低 worker、关闭 fsync、放宽 freshness 或删除历史证据解决资源不足。

## 本轮交付边界

原计划 Task 1 已进入实现和回归；Task 2 的 qpos 重建路线 BLOCKED。本文是可审查的最小提案，没有应用 native 补丁，没有执行 pilot 或正式 40 点。需要本文的明确授权后，才将其作为原计划 Task 2 的合同替换并继续依赖它的任务。

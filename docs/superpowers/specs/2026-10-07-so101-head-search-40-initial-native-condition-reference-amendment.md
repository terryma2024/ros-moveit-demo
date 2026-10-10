# Head Search 40 点：初始条件对照原件修订提案

状态：提案，未批准、未实施。已批准的原生 RGB/实例 ID 配对继续保留。本提案只补齐低照度和部分遮挡的条件证据，搜索、安全与 Stop 合同不变。

## 为什么需要补充

上一份修订解决了运动帧的实例真值：原 RGB 和 ID 图来自同一个冻结 `mjvScene`。但低照度还需要同姿态的正常光照对照，部分遮挡需要同姿态的无遮挡杯子 mask。现有配对消息没有这些原件。

尝试从实际暂停 reset 的完整 qpos/qvel 独立渲染对照时，RGB 的逐字节准入门未通过。实际离线复现中，qpos/qvel 差异均为 0，实例 ID 图完全相同；RGB 有 34 个颜色分量相差 1。同一 context 的连续 RGB 渲染也不逐字节相同。当前证据说明 RGB readback 不可假定按字节重复；尚未证明具体 GL 或驱动原因。

复现使用真实封存场景和 MuJoCo 3.12.0，但原件是离线测试生成的 CDR，不是新 native ROS 实跑。它否定了本次离线参考的字节重复前提，不能证明正式场景或原生发布已通过。

证据位于注册根 E 下的 `head-file-protocol-1003/head-search-40-20261006-001/diagnostics/initial-equivalence001/`。13 项新增初始参考测试先因能力缺失 RED；候选实现后的组合回归为 68 PASS、4 FAIL，四项都在 RGB 等价门拒绝。整个候选的源文件、测试和失败记录已封存，源代码恢复到 freeze/007 的完整字节清单。这是撤回未验收的候选能力，不是以删除失败测试宣称修复。

继续采用字节差阈值会改变已批准合同。推荐让 native 在第一次真实 reset 后的暂停曝光内直接生成条件对照原件，避免将独立重建图当作原件。

## 最小变更

只在声明的开发 campaign 中开启，且仅在实际 reset 后的第一条 FRAME、激活控制器之前生成一次条件参考。类别为互斥的 `none`、`normal_light`、`amodal_cup`，由封存 fixture 和 render-config SHA 指定。

新增 `mujoco_ros2_control_msgs/msg/CameraTruthFrameV2.msg`。保留原 `CameraTruthFrame.msg` 的定义与历史 CDR 解码；V2 封装原 V1 配对记录，另含 schema version、reference kind 和有界的参考 RGB/实例图。新 campaign 统一用 V2 私有 topic；已有 V1 配对路径仍受原合同约束。默认相机功能关闭时不创建这些消息缓冲、publisher 或线程。

V2 的普通 FRAME 携带原 RGB/Info/实例 ID。仅第一帧允许一个额外参考图：

- `normal_light`：在同一冻结可视 scene 中恢复封存的基准 light diffuse/specular，ambient、headlight、相机、材质和几何保持原值，额外渲染一次 RGB。基准系数来自场景变体准备前的已校验模型，进入 fixture/render-config SHA。必须证明 model light 到 scene light 的实际映射，包含 active/headlight 的区别；映射含糊即拒绝，不能靠数组下标猜测。只改私有可视 scene，禁止修改 live model 或 live data。
- `amodal_cup`：在同一冻结可视 scene 中仅隐藏 fixture 声明的遮挡物可视 geom，额外渲染一次实例 ID，保留其余 geom、segid/object 映射、相机和帧时间。杯子不移动，其他遮挡物不能顺带消失。

所有修改以作用域保护器恢复，异常同样恢复。记录原 scene/camera/light/geom 映射与修改范围，第二次及参考渲染期间验证冻结几何和相机未变；禁止重建 scene、调用 `mj_step` 或对 live data 调用 `mj_forward`。实际物理线程可以继续推进，参考只绑定这一张冻结曝光。

原生产 RGB/Info 在这些参考渲染之前按原顺序发布，内容不变。正常照度参考是私有验收用的反事实渲染原件，不是当前生产输入；无遮挡实例图也不是 detector 的输入。保留原 RGB、可见 ID 和参考图的各自原件、SHA、接收时间与来源标记。

FRAME sequence、水位与 generated/enqueued/published/dropped 仍按完整 FRAME 计数。第一帧的参考属于同一个不可变队列条目；队满丢弃整条 FRAME 并锁存 loss，不能只丢参考而保留成功标记。FINAL 与后续 FRAME 的 reference kind 必须为 `none`，参考图必须为空。缺参考、重复参考、错误类型、错误 stamp/frame_id 或身份冲突判 UNKNOWN 并阻塞正式批次。

队列容量仍为 2，包含正在 DDS 发布的条目。按冻结的 640×480 和最大参考图重新计算预分配内存及 CDR 上限；保留 best-effort/depth 1、render lock 内不等待、锁外 sender、原有限 retirement 和最终水位检查。无新的实时写盘、服务、控制通道或额外 sender。首次额外渲染的耗时也必须符合原 10 Hz、新鲜度和 Stop 预算；不能因“只发生一次”豁免。

## 离线判据

collector 保存实际 V2 CDR 与生产 Image/Info 原件。builder 从 V2 中解析 V1 配对及参考图，保存外层原始 CDR SHA，不把重序列化的内层消息冒充原件。原 V1、历史日志、普通 provider 和日志关闭路径保持兼容。

所有后续转头帧继续使用原生可见实例 ID，加同 source ns、实际 native session/reset epoch 的 lossless physics exact join。初始参考不能替代后续 mask，也不能进入 tracker、HeadSearchController 或 CUDA detector。

低照度要求实际编译系数为原基准的 0.35 倍，ambient/headlight/相机/材质不变，第一帧实际低照度 RGB 的平均像素亮度低于 native 正常光照参考。两图尺寸、布局、来源与共同冻结曝光都需成立；不引入新的检测阈值。

部分遮挡按同帧可见杯子 mask 与 native amodal mask 计算。可见 mask 必须是 amodal 的子集，amodal 像素数大于 0，且 `0 < occluded_fraction < 1`。零遮挡、全遮挡、投影冲突或缺原件不能作为条件已施加。初始化参考只证明初始遮挡条件，后续锁定的三帧归属仍由各自原生真值证明。

无杯仍需完整有界搜索覆盖；双杯仍需实际搜索期间存在同时可见的原始帧。新增参考不改变这些判据。

## 实施文件与门禁

批准后拟修改范围：新增 V2 msg 及 msgs CMake；camera_plugin.cpp/.hpp 和必要插件依赖；native 相机/队列测试；head_search_campaign_scene.py、head_search_campaign_truth.py、head_campaign_truth_collector.py 及对应普通测试。必要 provider 改动只用于同一 owned collector 的类型接线。代码、输入或 profile 变化均需新 freeze。

先建立真实 RED/GREEN：V1 历史 CDR 仍能解码；V2 完整同帧引用；light/headlight 映射拒绝；作用域恢复；无遮挡/全遮挡/投影冲突；参考仅一次；默认关闭无额外渲染或分配；队满与末尾丢失；阻塞 sender 的有限退出；原生产 RGB/Info 字节不变。native 测试使用实际 640×480 渲染，记录首次 RGB+ID+参考的耗时，不用低分辨率结果代替准入。

随后完成 msgs/plugins 依赖闭包、native/package gate、demo 完整 ordinary/package 8-worker gate、copy-install、源/安装 SHA 回读和 inline 实现自审。保留全部失败；不降低 worker、关闭 fsync 或扩大超时。

提议将独立 pilot 从 5 次扩为 7 次，增加 low_light 900006 和 partial_occlusion 900007，验证这两条新 native 分支。正式清单保持 40 case/48 attempt，无第三次重试；pilot 不进入正式分母。总预算因此按 7 pilot+48 formal，即 55 个 attempt 计算。这一变化仅为提案，当前没有新增或执行任何 pilot。

运行仍到搜索终态，然后本地 Stop、owned retire、seal 和 exit audit。没有 pick-place、硬件、ACT collection、dst、第二执行器、新 worktree/branch、commit/push 或证据删除。

## 当前资源限制

现有 53-attempt 合同仅计 30 秒搜索的 native 配对图与 collector RGB、两轮最大实测测试 scratch 和 20% 余量，容量下界已是 97,149,561,346 bytes；观测 free 为 75,063,156,736 bytes。它还没包含启动、物理原件、SDK RGB、Stop、报告及最终构建。

按当前代码允许的 90 秒 detector 配置等待和 30 秒搜索计算，相同已知项的 53-attempt 容量下界为 343,327,353,346 bytes。这仍只是所需上限预算的下界，不是完整预算或预计实际用量。本提案的 55-attempt 准入必须重新计算全部项目。即使提案批准，容量未满足时仍不启动 pilot 或正式批次，不以提前锁定、压缩、降采样或删除证据减少预算。

## 审查与授权边界

本提案改变条件原件协议并增加两次独立 pilot，需要新的明确批准。此前对 V1 原生配对真值的批准不自动覆盖这些变更。当前已获授权的 V1 实现、初始真实 reset 原件接线、实例归属和全部旧证据保留；正式 40 点未运行，qualification 仍为 false。

# Grounded DINO Tiny + SAM 2.1 Hiera Tiny 与 YOLO-Seg 双平台 Benchmark 设计

**日期：** 2026-09-02

**状态：** 已批准，待实现

**范围：** 离线 RGB 实例检测与分割评测

**平台：** Linux CUDA、macOS MPS

## 1. 背景与目的

V5-T004 已提供微调后的 YOLO-Seg，V5-T005 Task 11 又对 Grounded DINO Tiny + SAM 2.1 Hiera Tiny 做了现场能力探查。两组结果目前不能直接比较：使用的图片、阈值、指标、运行平台和证据格式都不相同。

本 benchmark 用同一份冻结数据、同一套实例匹配规则和同一个安全目标，对以下两条链路做 A/B 评测：

1. 微调 YOLO-Seg；
2. `Grounded DINO Tiny + SAM 2.1 Hiera Tiny`，逐帧无状态推理，不启用 SAM 2.1 视频跟踪。

评测要回答三个问题：

- 哪条链路在 `plastic_cup` 多实例检测与分割上更准确；
- 两条链路能否在 `0/1/2+` 目标决策中找到不产生危险唯一选择的阈值区间；
- 同一模型在 Linux CUDA 与 macOS MPS 上的准确率、预测差异和性能差异有多大。

Task 11 的 `MODEL_CAPABILITY_NOT_MET` 在本 benchmark 完成前只记为 **provisional**。现有探查没有保存足够完整的低门槛候选，尚不能证明不存在安全阈值区间。

## 2. 非目标

本任务只评测 RGB 图像上的实例检测与分割，不声称证明以下能力：

- RGB-D 对齐、深度采样或三维反投影；
- TF 变换、`/cup_pose` 的空间正确性；
- `TargetSelector` 之后的运动规划或执行安全；
- MoveIt、夹爪、真实机器人 Pick & Place 成功；
- 对真实相机域、遮挡域和仓外物体类别的泛化能力。

本任务不在 test 集上调参，也不拿未经数据、实现和指标口径对齐的 Ultralytics 历史 mAP 当作 A/B 结论。

## 3. 固定资产与来源

### 3.1 数据集

正式评测只使用以下归档：

- 文件：`datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz`
- SHA-256：`c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1`
- `val`：200 张；
- `test`：200 张；
- 每个 split 都包含 `no_cup`、`one_cup_distractors`、`two_cups`、`cup_near_bottle` 四种场景，每种 50 张。

程序必须先验证归档 SHA，再解包到只读工作目录；失败时停止正式评测。

真值来自 MuJoCo segmentation rendering 的 object-ID：渲染器先通过 geom/body 身份确定实例，再把可见像素转换成标注。它不是按 RGB 颜色阈值生成的伪标签。

归档中的 YOLO-Seg 多边形是真值可见像素的凸包，不是原始逐像素 object-ID mask。凸包会填平孔洞，也可能包含凹形物体外的背景。因此，mask AP、IoU 和 Dice 衡量的是“对归档凸包标注的拟合”，不能扩大解释为对真实物体轮廓的精确恢复。归档也没有 bottle 的实例 mask；`cup_near_bottle` 只能报告相对 cup 真值凸包的非 cup 泄漏，不能宣称测得了精确的 bottle overlap。

### 3.2 YOLO-Seg 权重

- `best.pt` SHA-256：`f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`
- 推理精度：FP32；
- Linux：CUDA；
- macOS：MPS；
- `imgsz=640`，除阈值标定项外不改预处理、后处理和模型结构。

### 3.3 Grounded-SAM 资产

- manifest SHA-256：`838c5154ae7587e01dc437c2e1d5da2572b9265951677731bc9c7793fbebb8b3`
- Grounding DINO：`IDEA-Research/grounding-dino-tiny@a2bb814dd30d776dcf7e30523b00659f4f141c71`
- SAM：`facebook/sam2.1-hiera-tiny@de431c4043854a71d8101e17995dfe596bf101a5`
- 固定 prompt：`plastic cup.`；
- 推理方式：逐帧无状态；
- 推理精度：FP32；
- Linux：CUDA；
- macOS：MPS；
- `fallback_used=false`；
- 正式运行时 `offline=true`，不得临时联网解析 revision 或替换权重。

每个运行记录都要保存模型 ID、精确 revision、manifest SHA、实际设备、dtype、依赖锁文件 SHA、仓库 commit 和工作树状态。只写 `tiny`、`latest` 或本地缓存目录名不算可复现来源。

## 4. 评测边界与组件

### 4.1 组件职责

| 组件 | 职责 | 明确禁止 |
| --- | --- | --- |
| `DatasetArchiveVerifier` | 校验归档 SHA、split、场景计数、图片与标签可读性，生成冻结 inventory | 修复、补齐或跳过坏样本 |
| `TruthSample` | 把一张图的实例真值、场景、图片 SHA 和标注限制表示为不可变对象 | 从预测反推或修改真值 |
| `DetectorBenchmarkRunner` | 调用模型适配器，保存 raw candidates、production decision、时延和错误 | 用 `TargetSelector` 删除或改写 raw candidates |
| `InstanceMatcher` | 按类别和 mask IoU 做实例匹配 | 用 confidence 替代几何匹配 |
| `ThresholdCalibrator` | 只读取 val 记录，按共同目标为每个模型选阈值 | 读取 test 标签或正式 test 指标 |
| `MetricsAggregator` | 从冻结记录计算准确率、安全决策、错误、性能和跨平台差异 | 丢弃失败样本或改变分母 |
| `ReportWriter` | 输出机器可读 JSON/CSV、人工报告和证据索引 | 只写结论而不保留逐样本来源 |

组件名和记录 schema 一经实现并登记，正式运行期间不得随意改变。确需变更时，要生成新的 schema version 和新的 run，而不是覆盖已有记录。

### 4.2 `DetectorPort` 的复用边界

现有 `DetectorPort` 继续承担生产调用边界，production 配置的正式 test 必须通过这一边界运行。benchmark 还需要一个只读诊断出口，用更低阈值保留模型原始候选。该出口可以是适配器旁路或 benchmark-only diagnostics hook，但不得改变 `DetectorPort` 的生产语义。

raw candidates 在进入 `TargetSelector` 前落盘。随后用同一份 raw candidates 另行计算：

- production 配置下的 decision；
- val 标定后冻结配置下的 decision；
- 仅供分析的 `ORACLE_DIAGNOSTIC` test sweep。

`TargetSelector` 不能回写候选、置信度、mask 或实例数量。正式报告必须同时给出 raw 检测指标和 production decision 指标。

## 5. 不可变输入输出 schema

### 5.1 `TruthSample`

每个样本至少包含：

- `schema_version`；
- `split`、`scenario`、`image_relpath`、`image_sha256`；
- `image_width`、`image_height`；
- 每个实例的 `instance_id`、`label=plastic_cup`、polygon、lossless rasterized mask SHA；
- `truth_count` 和派生的 `truth_decision_class`：`0`、`1` 或 `2+`；
- 数据集归档 SHA 和 inventory SHA。

栅格化规则必须固定，包括坐标舍入、边界包含关系和输出尺寸。否则，同一 polygon 在两个平台上可能产生不同真值 mask。

### 5.2 `PredictionRecord`

一张图片、一个模型、一个平台、一个配置对应一条记录，至少包含：

- `run_id`、`schema_version`、`record_status`；
- 图片 SHA、split、scenario 和正式样本序号；
- 模型 ID、revision 或权重 SHA、manifest SHA、代码 commit、依赖锁 SHA；
- OS、CPU、GPU、驱动、CUDA/MPS/PyTorch 版本、device、dtype；
- production 配置 SHA 或 calibrated threshold-lock SHA；
- 所有达到低门槛采集线的 raw candidates，不能只保存最终选中的一个；
- 每个候选的稳定 `candidate_id`、`label`、box、lossless mask、mask SHA、像素数；
- YOLO 候选的 class confidence；
- Grounded-SAM 候选的 Grounding DINO box confidence、text confidence、SAM quality；
- 用于 AP 排序的 `ranking_score` 和它的来源字段；YOLO 固定使用 class confidence，Grounded-SAM 固定使用 Grounding DINO grounding score，SAM quality 只做质量门禁，不与 grounding score 相乘；
- `preprocess_ms`、`dino_or_yolo_ms`、`sam_ms`、`postprocess_ms`、`selector_ms`、`total_ms`；
- raw count、production decision、selected candidate ID 和拒绝原因；
- 错误类型、异常摘要、是否超时、是否 OOM、是否 fallback。

不适用字段写 `null`，不能写成 `0`。mask 可以保存 COCO RLE，也可以保存无损二值文件；两种方式都要有 SHA-256。只保存 overlay、压缩 JPEG 或凸包不能代替预测 mask。

逐图异常必须 fail closed：decision 写 `ERROR`，该图仍进入总样本分母、错误统计、决策混淆矩阵和吞吐统计。程序不得静默跳样本，也不得在失败后用另一设备或另一模型补结果。

## 6. 实例匹配规则

1. 只匹配 `plastic_cup`。其他 label 一律计入非目标预测。
2. 对一张图的真值 mask 和预测 mask 建立 mask IoU 矩阵。
3. 使用 Hungarian assignment 最大化总 mask IoU。
4. 分数相同时依次按更高 IoU、更高 confidence、更小 `candidate_id` 做确定性排序。
5. 在 IoU `0.50:0.05:0.95` 上分别确定 TP、FP、FN。

mask AP 使用冻结的 `ranking_score` 对全数据候选排序，采用 101 点 recall 插值，报告 `mask_AP50` 和 `mask_AP50_95`。这里采用 COCO-style IoU 阈值和插值，但实例配对固定为上述 Hungarian 规则，所以不能宣称与未经对齐的 `COCOeval` 数值逐位兼容。

empty truth 的处理必须明确：

- 真值为空、预测也为空：该图的 count 和 decision 正确，不人为添加 IoU=1 的实例；
- 真值为空、存在预测：预测全部为 FP；
- 真值非空、预测为空或发生错误：真值全部为 FN；
- 全数据 precision 分母为零时记为 `undefined`，JSON 写 `null`，报告同时给出计数，不把它改写成 1。

## 7. 正式指标

### 7.1 实例检测与分割

每个平台、每个模型、每种配置都要报告：

- `mask_AP50`、`mask_AP50_95`；
- IoU=0.50 下的 precision、recall、F1；
- 匹配 TP 的 mean/median mask IoU；
- 匹配 TP 的 mean/median Dice；
- exact count accuracy；
- FP/image、FN/image；
- error count、error rate、timeout count、OOM count；
- 按四个场景拆分的同口径指标和 95% bootstrap confidence interval。

bootstrap 以图片为抽样单位，固定 seed，至少 10,000 次重复；同一组跨模型比较使用配对抽样。

### 7.2 `0/1/2+` 决策与安全

真值分为 `0`、`1`、`2+`，输出分为 `NOT_FOUND`、`UNIQUE`、`AMBIGUOUS`、`ERROR`。报告完整 `3 x 4` confusion matrix，并计算：

- decision macro-F1；
- unique-selection success rate：真值为 `1` 且输出正确 `UNIQUE`；
- unsafe unique-selection rate：真值为 `0` 或 `2+`，却输出 `UNIQUE`；
- no-cup FPR：`no_cup` 中出现任意 `plastic_cup` 候选的图片比例；
- two-cup both-instance recall：`two_cups` 中两个真值杯子都在 IoU>=0.50 被匹配的图片比例；
- `cup_near_bottle` 的 non-cup leakage ratio：预测 cup mask 落在 cup 真值凸包之外的像素占预测 mask 像素的比例；
- decision error rate，其中推理错误独立保留为 `ERROR`，不并入 `NOT_FOUND`。

`cup_near_bottle` 指标受“无 bottle 真值 mask”限制，只描述超出 cup 凸包的泄漏，不命名为 bottle IoU 或 bottle false-positive rate。

### 7.3 性能与资源

每个平台、模型和配置都报告：

- cold end-to-end latency 的 p50/p95/p99；
- warmed end-to-end latency 的 p50/p95/p99；
- 各 phase latency 的 p50/p95/p99；
- images/s throughput；
- peak RSS；
- Linux peak CUDA allocated/reserved memory；
- macOS 可获得的 MPS allocated memory 与进程 peak RSS；
- 模型加载、首轮编译或图优化耗时，单列而不混入 warmed latency。

分位数按逐图原始记录计算，不用批次均值代替。发生错误的图片进入吞吐和错误率统计；其成功阶段耗时照常保留，缺失阶段写 `null`。

### 7.4 跨平台一致性

对同一模型、同一图片、同一冻结配置，按稳定候选顺序比较：

- candidate count 是否一致；
- matched confidence 的 absolute/relative delta；
- mask IoU 和 box IoU；
- production/calibrated decision 是否一致；
- 错误类型是否一致。

报告 mismatch 图片清单和分布，不只写总体均值。平台差异是 benchmark 结果的一部分，不能用“浮点误差”概括后略过。

## 8. 阈值公平性

### 8.1 两套正式配置

每个模型都保留两套正式 test 结果：

1. `production`：原有生产配置不变，完整 test 只运行一次；
2. `calibrated`：只用 val 标定，生成 threshold-lock，冻结后完整 test 只运行一次。

Grounded-SAM 当前 production 参数原样记录：

```text
grounding_box=0.35
grounding_text=0.25
duplicate_iou=0.85
max_candidates=16
sam_quality=0.75
min_mask_pixels=64
max_mask_area_ratio=0.50
target_confidence_threshold=0.50
```

YOLO-Seg 的 production `conf`、NMS IoU 和 selector 参数必须从当前配置文件读取并写进配置快照，不能根据历史评测猜测。

### 8.2 低门槛采集

为避免反复运行模型，val 原始候选按以下采集下限保存：

- YOLO：`conf=0.01`；
- Grounding DINO：`grounding_box=0.01`、`grounding_text=0.01`；
- SAM：`sam_quality=0.00`；
- selector：关闭，只保存 raw candidates。

如果某个候选在模型内部已被不可逆裁剪，报告必须说明这个限制。低门槛采集不是 production 结果，也不能直接进入 Pick & Place。

### 8.3 搜索空间

Grounded-SAM 的 val grid：

- `grounding_box`：0.05 到 0.90，步长 0.05；
- `grounding_text`：0.05 到 0.50，步长 0.05；
- `sam_quality`：0.50 到 0.95，步长 0.05；
- `target_confidence_threshold`：0.05 到 0.90，步长 0.05；
- `duplicate_iou=0.85` 固定；
- `min_mask_pixels=64`、`max_mask_area_ratio=0.50` 固定。

YOLO-Seg 的 val grid：

- `conf`：0.05 到 0.95，步长 0.05；
- NMS IoU：0.30 到 0.90，步长 0.10；
- `target_confidence_threshold`：0.05 到 0.95，步长 0.05；
- `imgsz=640` 固定。

两条链路可以各自标定阈值，但必须使用相同目标函数。Grounded DINO 的 box/text、SAM quality、selector 阈值和 YOLO 的 conf/NMS IoU 含义不同，不能合并成一个叫“confidence”的共同旋钮。

### 8.4 双平台共同标定与确定性 tie-break

每个模型用 Linux val 200 张与 macOS val 200 张的合并记录标定一套共同阈值，不能为平台单独挑最有利配置。候选配置按以下顺序比较：

1. 两个平台 `unsafe unique-selection rate=0`；
2. 最大化两平台中较低的 decision macro-F1；
3. 最大化合并 val 的 decision macro-F1；
4. 最大化合并 val 的 `mask_AP50_95`；
5. 最大化两平台中较低的 two-cup both-instance recall；
6. 优先更高的检测、分割质量和 selector 安全阈值；YOLO NMS IoU 再优先较低值；
7. 仍相同时，按规范化配置 JSON 的字典序选第一个。

如果不存在满足第 1 条的配置，标定结果为 `UNSAFE_CALIBRATION_NO_FEASIBLE_POINT`。此时仍可冻结一个按第 2 条以后选择的 characterization 配置用于研究，但必须标成不可部署，不能称为 safe calibrated 配置。

threshold-lock 文件要包含 grid、目标、tie-break、val inventory SHA、输入 prediction-record inventory SHA、选定值和自身 SHA。生成 threshold-lock 后才可解封 test 标签。

任何 test sweep 只能标为 `ORACLE_DIAGNOSTIC`，必须与正式结果分区展示，不得用于选择阈值、排名模型、修改摘要结论或回填 production 配置。

## 9. 双平台执行协议

### 9.1 完整运行矩阵

每个平台、每个模型必须完成：

- val 低门槛采集 200 张；
- production test 200 张；
- calibrated 或 characterization test 200 张。

因此，Linux 和 macOS 都对每个模型完整处理同一 val/test inventory。没有“只在 Linux 测准确率、Mac 只测速度”的缩减路径。逐图错误可以发生，但样本不得从 inventory 和分母消失。

正式顺序固定为：资产和环境校验、两平台 val 采集、合并 val 标定、threshold-lock 冻结、两平台 production/calibrated test、聚合与报告。test 标签和正式 test 预测在 threshold-lock 前都不可用于人工判断。主准确率表只列每个平台的完整 test 结果；val 结果留在标定附录中。

Linux 或 macOS 任一平台发生 fallback、缺少正式样本或 run 为 `INVALID`，整体双平台 A/B 验收就不通过。仍可报告另一个平台已完成的事实，但不能把它提升为双平台结论。

### 9.2 warmed 与 cold

warmed 测量满足以下条件：

- 模型只加载一次；
- 使用正式输入 shape 至少 warm-up 5 次；
- warm-up 图片不进入 200 张正式样本；
- CUDA 在计时边界调用 device synchronize；MPS 使用等价同步；
- 排除加载、权重读取、首轮编译和 warm-up；
- 保存每张图的各 phase 原始时延。

cold latency 使用至少 3 个全新进程，每次包含加载到首张结果的总时间。cold 样本与 warmed 指标分开，不能混算。

### 9.3 顺序与热偏差

准确率正式运行使用预注册、按 `image_sha256` 固定的图片顺序。性能运行采用配对的交错顺序：一半重复先跑 YOLO-Seg 再跑 Grounded-SAM，另一半反过来。每次记录开始时间、设备温度/功耗可用值、后台负载和顺序。

两模型不得同时占用同一 GPU 做吞吐比较。若因内存或框架限制必须分进程运行，要保持图片顺序、资源采样频率和同步方式一致。正式 accuracy 只取预注册运行，不从多次重复中挑最好结果。

### 9.4 资源采样

资源采样要覆盖加载、warm-up 和正式推理，至少记录：

- 进程 RSS；
- GPU/MPS memory；
- CPU 使用率；
- GPU utilization、温度和功耗（平台可用时）；
- 采样频率、工具版本和采样缺口。

不可获得的指标写 `unavailable` 并解释平台限制，不能填 0。

## 10. 证据根与实验账本

本 benchmark 使用新的 task family，不占用尚未注册的 V5 task 编号：

```text
/data/work/so101-evidence/grounded-sam-yolo-seg-benchmark/{run_id}
```

普通调试日志先放在唯一目录：

```text
/tmp/so101-debug-grounded-sam-yolo-benchmark-{run_id}
```

Linux 可以直接把高频、无损证据写到 durable root。macOS 先写 `/tmp`，运行结束后生成 immutable inventory，再传到上述 durable root；传输后必须逐文件或按 inventory 做 SHA readback。上传前的临时文件不能作为最终证据来源。

实现阶段新建独立账本：

```text
docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md
```

本设计不改现有 ledger。新账本的状态机只能使用：

- `PLANNED`
- `RUNNING`
- `VALID`
- `INVALID`

能力结论、失败原因和发布判断放在独立字段，不能拼进 status。每个 run 必须登记证据根、平台、模型、配置 SHA、inventory SHA、开始/结束时间和 retained/archived/deletion-candidate 分类。未经用户明确授权，不删除证据。

最终报告必须列出：

- retained runs；
- archived runs；
- deletion candidates；
- Mac 临时证据是否已完成 durable readback；
- 无法保留的证据及原因。

## 11. Task 11 整改与回流条件

### 11.1 先规范状态机

在把 benchmark 结论回填到 Task 11 前，先以 append-only 附录说明现有复合状态如何映射到 `PLANNED/RUNNING/VALID/INVALID`，把 outcome 单独列出。不得静默重写原记录或抹去时间线。

### 11.2 补充低门槛记录

对 Task 11 r9 的 no-cup 与 two-cup 保留源 RGB 图做一次低门槛离线重放，保存未截断的：

- Grounding DINO box score；
- text score；
- SAM quality；
- 完整 candidates、box、mask 和 mask SHA；
- 图片 SHA、prompt、模型 revision、平台和配置。

现有记录能确认：r8 no-cup 的两个 false candidate score 为 `0.6970663071`、`0.5767329931`；r9 在 `grounding_box_threshold=0.70` 时，one-cup score 为 `0.7215305567`，no-cup 没有候选，two-cup 只保留了一个 score `0.7670135498`。这些数字没有给出 r9 no-cup 被阈值截断前的完整 scores，也没有给出 two-cup 第二个真杯子的 score，因而不能证明阈值区间是否存在。低门槛重放必须补齐这一缺口。Task 11 探查图片只有在图片 SHA 与正式数据 inventory 相同时，才可计入 benchmark；否则它是独立的 domain probe，不进入正式 200 张分母。

### 11.3 回流门槛

只有同时满足以下条件，才允许回到 Task 11 做完整矩阵：

- val 上两个平台 `unsafe unique-selection rate=0`；
- 冻结 test 上两个平台 `unsafe unique-selection rate=0`；
- Task 11 no-cup、one-cup、two-cup probe 存在不冲突的安全阈值区间；
- 完整来源、raw candidates 和 mask 证据可读回。

如果任一条件不满足，结论应是“当前模型/提示词/阈值组合没有可接受安全区间”。更换 prompt、模型或做 fine-tune 都要先写新的 design，再运行新的实验；不能在 Task 11 现场边试边改。

## 12. 失败、安全与中止规则

以下情况使单图记录进入 `ERROR`，但不允许跳过该图：

- 图片、标签或 mask 无法读取；
- 非有限 confidence、box 或 latency；
- mask 尺寸与图片不一致；
- OOM、timeout、设备同步失败；
- 模型 revision、权重 SHA 或 manifest 不符；
- 发生 CPU fallback 或其他设备 fallback；
- 输出 candidate ID 重复、记录缺字段或 mask SHA 不匹配。

以下情况使整个 run 为 `INVALID`：

- 数据集归档 SHA 不符；
- inventory 少于 200 张、场景计数不是 50/50/50/50；
- 发现跳样本、重复样本或 test 泄漏到标定；
- 正式运行中修改模型、代码、prompt、阈值或依赖；
- `fallback_used` 不是 `false`；
- prediction schema 或 threshold-lock 无法校验；
- durable 证据 readback 失败且无法恢复。

遇到硬件过热、持续 OOM 或资源采样异常时，停止 run，标 `INVALID`，保留已经生成的证据并另起新 run。不得续写一个已经失去可比性的 run。

## 13. 测试策略

实现阶段至少覆盖以下自动化测试，但本设计阶段不编写或运行这些测试：

### 13.1 单元测试

- SHA、inventory、split 与场景计数校验；
- polygon 栅格化的确定性；
- RLE round-trip 与 mask SHA；
- Hungarian assignment，包括等分 tie-break；
- empty truth、empty prediction、错误样本分母；
- IoU、Dice、AP、decision confusion 和 safety 指标；
- grid 枚举、tie-break 与 threshold-lock SHA；
- `null` 与 `0` 的 schema 区分。

### 13.2 组件测试

- 两个模型适配器输出同一 `PredictionRecord` schema；
- raw candidates 在 selector 前完整落盘；
- production 和 calibrated decision 不改 raw 记录；
- CUDA/MPS 同步边界和 phase latency 加总；
- 单图异常 fail closed 后仍产生一条记录；
- offline 模式缺资产时停止，不联网下载。

### 13.3 端到端 dry run

先用每个场景固定 2 张、共 8 张做 non-formal dry run，验证 schema、证据路径和报告生成。dry run 不进入正式指标，也不能用于调阈值。dry run 通过后创建新的正式 run ID。

## 14. 验收标准

benchmark 只有在以下条件全部满足时才能标记 `VALID`：

1. 归档、YOLO 权重、Grounded-SAM manifest 和精确 revisions 的 SHA/ID 全部匹配；
2. Linux 与 macOS 对两个模型都完整处理 val 200 和 test 200；
3. 每个 split 的四场景各 50 张，没有跳样本、重复样本或隐藏补跑；
4. 每张图都有可校验的 `TruthSample`、`PredictionRecord`、raw candidates、mask SHA 和错误状态；
5. production 与 calibrated/characterization test 结果分开，test 没参与标定；
6. 指标覆盖第 7 节全部 accuracy、decision、安全、错误、性能和跨平台项目；
7. warmed 至少完成 5 次正式 shape warm-up，cold 至少 3 个新进程，资源采样可追溯；
8. threshold-lock、配置、inventory、报告和 evidence index 的 SHA 可以 readback；
9. 自动化测试和 8 图 dry run 通过；
10. 新账本状态合法，retained/archived/deletion candidates 已报告。

结果可以是 YOLO-Seg 更优、Grounded-SAM 更优、各有所长，或两者都找不到安全阈值区间。设计不预设胜者。即使 accuracy 很高，只要冻结 test 的 unsafe unique-selection rate 非零，也不能把该配置标成可用于 Pick & Place 的安全配置。

## 15. 实现阶段建议文件范围

后续实现应把变更限制在独立 benchmark 包和文档，不侵入 production detector 的语义。建议范围：

```text
src/so101_demo_py/src/perception_benchmark/
src/so101_demo_py/test/test_perception_benchmark_*.py
src/so101_demo_py/config/perception_benchmark/
docs/experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md
docs/reports/grounded-sam-yolo-seg-benchmark-report.md
```

实际路径要在 implementation plan 中结合仓库结构确认。本设计不授权修改现有 ledger、production launch、机器人控制、MoveIt 配置或模型资产。

## 16. 发布与运行边界

本设计提交只包含本文件。它不授权：

- push 或 merge；
- 模型下载、依赖安装或正式 benchmark 运行；
- 修改现有实验账本；
- 启动真实机器人、相机、MoveIt 或 Pick & Place；
- 根据本文直接宣称 Depth、TF、`/cup_pose` 或物理抓取已验证。

实现、执行、分析和 Task 11 回流应分别经过 plan、证据登记和验收。

## 17. 相关文档

- [V5-T004 YOLO-Seg RGB-D 感知设计](2026-08-31-v5-t004-yolo-seg-rgbd-perception-design.md)
- [V5-T005 Grounded DINO + SAM 2.1 Hiera Tiny 设计](2026-09-01-v5-t005-grounded-dino-sam2-rgbd-perception-design.md)
- [SO-101 YOLO-Seg RGB-D 多实例感知 PickPlace 教学与源码导读](../../guides/so101-yolo-seg-rgbd-perception-pick-place-source-guide.md)
- [SO-101 Grounded DINO + SAM 2.1 Hiera Tiny 教学与源码导读](../../guides/so101-grounded-sam-rgbd-perception-pick-place-source-guide.md)
- [V5-T004 实验账本](../../experiments/v5-t004-yolo-seg-rgbd-experiment-ledger.md)
- [V5-T005 实验账本](../../experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md)

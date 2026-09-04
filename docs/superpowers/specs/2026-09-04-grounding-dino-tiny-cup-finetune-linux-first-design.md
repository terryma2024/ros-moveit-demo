# Grounding DINO Tiny 通用杯子微调与 Linux-first PickPlace 设计

**日期：** 2026-09-04

**任务：** `V5-T005` 后训练整改

**代码范围：** `src/so101_demo_py`、训练脚本、数据转换、评测与运行文档

**第一验收平台：** ai-station Linux CUDA

## 1. 背景与结论

冻结的 Grounding DINO Tiny + SAM 2.1 Hiera Tiny 在合成评测和 COCO 杯子图片上都暴露了明显短板。COCO 100 张外部基线共有 247 个 `cup` 实例，固定配置得到 `TP/FP/FN=145/48/102`，Precision 为 `75.13%`，Recall 为 `58.70%`，F1 为 `65.91%`。小目标和多杯场景漏检较多。当前模型可以继续作为基线，不能直接用于无人值守 PickPlace。

本轮不再同时推进 Linux 与 macOS。先在 ai-station 上完成候选映射修复、Grounding DINO Tiny 微调、冻结评测和四个预置点位 PickPlace。Linux 验收通过以后，才把同一模型包、配置和生产接口迁移到 macOS。

## 2. 目标与非目标

本轮目标：

- Grounding DINO 只检测通用 `cup`，不判断塑料、玻璃、金属或纸质；
- SAM 2.1 Hiera Tiny 保持逐帧无状态，只接受当前帧的 box prompt；
- 微调 Grounding DINO Tiny，优先复用已有 YOLO-Seg 合成数据；
- 生产评测保存真实生产批次生成的 SAM mask；
- ai-station 上完成四个预置点位的 MuJoCo RGB-D PickPlace；
- 用冻结的 COCO100 外部集合检查微调后是否损伤通用杯子能力。

本轮不微调 SAM，不启用视频跟踪，也不把 MuJoCo truth、颜色阈值或物体 ID 接入生产推理。真实机械臂执行不在本设计授权范围内。

## 3. 候选身份与 mask 契约

Grounded-SAM 的原始采集和生产 detector 可能以不同候选批次调用 SAM。同一个 DINO proposal 的 SAM mask 可能出现少量确定性边界差异，不能再要求 mask 字节完全一致。

候选映射分两层完成：

1. 使用规范化类别 `cup`、边界框和 Grounding DINO box score 确认 proposal 身份。浮点比较沿用已冻结的 float32 读回规则；多个候选同时满足时 fail closed。
2. 对原始与生产 SAM mask 计算 IoU，要求 `IoU >= 0.98`。该值是统一几何阈值，不写“允许差 1 像素”之类的特例。

映射成功后，`PredictionRecord.raw_candidates` 中被生产 detector 实际采用的候选必须改写为生产批次的 bbox、score、SAM quality、mask RLE、像素数和 mask SHA。原始低门槛 mask 只用于映射验证，不得冒充生产输出。映射失败继续使用 `PRODUCTION_CANDIDATE_MAPPING_INVALID`，整次正式 run 标为 `INVALID`。

`0.98` 必须出现在显式配置、运行 expectation、threshold-lock 或等价不可变清单中。正式运行不能依赖源码中的隐藏默认值。

## 4. 通用 cup 语义

生产查询从 `plastic_cup -> plastic cup.` 调整为单类 `cup -> cup.`。Grounding DINO 不负责材质分类。后续 RGB-D 定位、`/cup_pose` 和 MoveIt 继续消费被选择实例的 mask，不关心材质。

多杯场景不能把“置信度最高”误写成安全选择。没有点位、任务指令或其他确定性目标依据时，多个合格杯子保持 `TARGET_AMBIGUOUS`。四点位 PickPlace 的每轮场景必须给出唯一任务目标；如果场景里放置多个杯子，需要预注册确定性的点位或空间选择规则。

## 5. 训练数据

训练数据优先使用仓库中的 YOLO-Seg 合成数据。转换器读取 YOLO segmentation polygon，计算 Grounding DINO 所需 bbox，并把所有杯子类别归一为文本标签 `cup`。原图、polygon 和转换后 bbox 都写入 inventory，保留源归档 SHA、图片 SHA、标签 SHA 和转换器版本。

先统计现有数据对尺度、遮挡、光照、背景和单杯/多杯的覆盖。如果小杯、远距离多杯、暗光或遮挡样本不足，再从 MuJoCo 重新采样。新采样必须使用新的 dataset version，不能覆写已有归档。

SAM 仍使用冻结的 `facebook/sam2.1-hiera-tiny`。YOLO polygon 可以继续作为分割真值评测 SAM，但不参与 SAM 权重训练。

## 6. 数据划分与泄漏边界

数据分为三层：

- 合成 train：训练 Grounding DINO Tiny；
- 合成 val：选择 checkpoint、训练轮次和检测阈值；
- 新冻结合成 test：所有训练和选择完成后才打开，用于最终内部能力评测。

旧 benchmark test 已经打开，只保留为历史基线，不再用于新的超参数、数据配比或 checkpoint 选择。

COCO100 交付物位于 `/private/tmp/so101-grounded-dino-cup-100-handoff-20260904`。它是外部非劣化集合，不加入训练，也不参与 checkpoint 选择。最终候选在合成 val 上冻结后，才允许对 COCO100 运行一次。逐图结果即使不理想，也不得据此继续调参后重跑同一 run ID。

## 7. COCO100 非劣化门槛

基线固定为：

| 指标 | 基线 |
| --- | ---: |
| Precision@box-IoU0.5 | 0.7513 |
| Recall@box-IoU0.5 | 0.5870 |
| F1@box-IoU0.5 | 0.6591 |
| 至少检出一个真杯子的图片 | 85/100 |
| 肉眼可见的非杯 UNIQUE | 0 |

微调模型通过外部非劣化检查需要同时满足：

- F1 不低于 `0.6391`；
- Recall 不低于 `0.5670`；
- 至少检出一个真杯子的图片不少于 `83/100`；
- 不新增肉眼可见的非杯 UNIQUE 选择；
- 推理错误数不高于基线的 `1/100`。

这些是回归保护线，不是训练目标。正式报告同时给出 Precision、Recall、F1、TP/FP/FN、尺度分层和单杯/多杯分层，不用单一门槛掩盖退化。

## 8. 微调方案

只微调 Grounding DINO Tiny，SAM 权重冻结。训练采用可追溯配置，至少记录基础 revision、训练代码 commit、数据 inventory SHA、随机种子、优化器、学习率、batch size、epoch、混合精度、GPU 型号、checkpoint SHA 和中断恢复信息。

checkpoint 只能按合成 val 的预注册目标选择。建议主目标为 cup box F1，tie-break 依次使用 Recall、小目标 Recall、多杯 Recall和较少 FP。COCO100 不进入该排序。

如果现有 YOLO-Seg 数据转换后无法覆盖失败分层，才启动 MuJoCo 增量采样。重新采样前先写清缺口和配额，不进行无边界扩容。

## 9. Linux-first 执行顺序

1. 保留已经完成的 macOS 旧模型结果，标为 baseline/superseded，不继续跑新的 Mac 实验。
2. 修复并验证候选映射契约，在 ai-station 重新构建相同 commit 的 Linux overlay。
3. 导入并校验 COCO100 交付物；转换 YOLO-Seg 数据，生成训练/val/新 test inventory。
4. 在 ai-station 微调 Grounding DINO Tiny，按合成 val 冻结 checkpoint 和阈值。
5. 对新合成 test 与 COCO100 各运行一次正式评测。
6. 只有安全决策门和 COCO100 非劣化门同时通过，才进入 Linux PickPlace。
7. ai-station 四个预置点位分别执行一次完整 MuJoCo PickPlace。每次都需要 RGB-D、`/cup_pose`、TF、MoveIt、controller、MuJoCo 物体位姿/attachment 与新截图证据。
8. Linux 四点位全部成功后，发布不可变模型包并迁移 macOS。Mac 使用相同 prompt、阈值、模型 SHA 和接口语义，另做平台兼容与四点位验收。

Linux 失败时停在首个失败边界，不提前启动 macOS 迁移。

## 10. 证据与验收

本轮继续使用已经登记的证据根：

```text
/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
```

新增训练、数据、评测和 PickPlace run 都要先在实验账本登记为 `PLANNED`，再转为 `RUNNING`。无效运行保留原始证据并使用新 run ID 重试，不续写已失效目录。

Linux 阶段完成的最低标准：

- 候选映射 RED -> GREEN，包级普通测试与显式 benchmark 测试通过；
- 训练数据和 COCO100 inventory、SHA 与许可信息可读回；
- 新合成 test 的安全门通过；
- COCO100 非劣化门通过；
- 四个预置点位各有一次新的、可追溯的完整 PickPlace 成功证据；
- 没有 CPU fallback、混入 test 调参或复用无效 run。

未满足上述条件时，不宣称 Grounded-SAM 可部署，也不启动 macOS 迁移。

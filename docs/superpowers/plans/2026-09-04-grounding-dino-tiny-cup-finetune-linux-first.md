# Grounding DINO Tiny 通用杯子微调与 Linux-first PickPlace Implementation Plan

> **执行方式：** 当前任务 inline 执行，按任务逐项完成；每项代码变更遵守 RED -> GREEN。不得启用 subagent。

**Goal:** 在 ai-station 上微调 Grounding DINO Tiny，使通用 `cup` 检测达到内部安全门、COCO100 不明显退化，并完成四个预置点位的 MuJoCo RGB-D PickPlace；Linux 通过后再迁移 macOS。

**Architecture:** Grounding DINO Tiny 提供单类 cup boxes，冻结的 SAM 2.1 Hiera Tiny 生成逐帧实例 mask。benchmark 用 DINO proposal 身份和 `mask IoU >= 0.98` 映射原始与生产候选，保存生产实际 mask。训练选择只看合成 val；COCO100 是最终 checkpoint 的一次性外部非劣化检查。

**Spec:** `docs/superpowers/specs/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first-design.md`

## 全局约束

- 继续使用 `exp-079` 已登记的临时和 durable evidence roots，不删除旧证据。
- ai-station 是第一执行平台；Linux 四点位成功前，不启动新 macOS 训练、评测或 PickPlace。
- 旧 test 只作历史基线。新训练实验使用新的 train/val/test inventory，新 test 在 checkpoint 和阈值冻结前保持 sealed。
- COCO100 固定为 `/private/tmp/so101-grounded-dino-cup-100-handoff-20260904` 的 inventory；只对最终冻结候选运行一次。
- Grounding DINO prompt 固定为 `cup.`，SAM 2.1 Hiera Tiny 冻结并保持逐帧无状态。
- 正式运行禁止 CPU fallback。每个 run 记录 exact commit、overlay、runtime、device、配置 SHA、数据 SHA、模型 SHA 和 evidence path。
- 普通快速测试不收集 `benchmark_test/`；修改 benchmark 后才显式运行 benchmark suite。

### Task 1: 固化新设计、基线和 Linux-first checkpoint

**Files:**
- Create: `docs/superpowers/specs/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first-design.md`
- Create: `docs/superpowers/plans/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first.md`
- Modify: `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`

- [x] 记录 COCO100 来源、指标、manifest、prompt 偏差和非劣化门槛。
- [x] 记录旧 Mac runs 已完成、Linux r3 mapping invalid 以及用户批准的 Linux-first 顺序。
- [x] 将 Linux mapping fix r4、数据转换、训练、测试和四点位验收预登记为 `PLANNED`。
- [x] 运行链接、标题、路径、`git diff --check` 和 humanizer-zh 自检。

### Task 2: 用 IoU 门修复 Grounded-SAM production candidate mapping

**Files:**
- Modify: `src/so101_demo_py/src/perception_benchmark/runner.py`
- Modify: `src/so101_demo_py/src/perception_benchmark/contracts.py`
- Modify: `src/so101_demo_py/src/perception_benchmark/calibration.py`
- Modify: `src/so101_demo_py/config/perception_benchmark/benchmark.yaml`
- Test: `src/so101_demo_py/benchmark_test/test_perception_benchmark_runner.py`
- Test: related contract/config/CLI tests

- [x] 保留已得到的 RED：相同 proposal、生产 mask 边界变化时旧实现报 `PRODUCTION_CANDIDATE_MAPPING_INVALID`。
- [x] 增加显式 `production_candidate_mask_iou_threshold=0.98` contract 和序列化验证。
- [x] Grounded identity 先匹配 `cup + bbox + DINO box score`，随后计算 raw/production mask IoU；低于阈值或多重匹配时 fail closed。
- [x] 写入生产实际 bbox、score、SAM quality、mask RLE 和 SHA；YOLO 映射语义保持不变。
- [x] 定向运行一像素差异、阈值边界、低于阈值、歧义、YOLO 回归测试，再运行 runner 测试文件。

### Task 3: 同步 ai-station 并通过 Linux 测试门

**Files:** source commit and isolated Linux overlay only

- [ ] 提交并 push 最小 mapping 修复；ai-station 的隔离 checkout 从 Gitee 普通 pull，不改 canonical dirty workspace。
- [ ] 创建新 Linux build/install/log overlay，确认 installed package prefix 与 source commit。
- [ ] 先运行普通 package gate，再显式运行 `benchmark_test/`；记录测试数、耗时和 JUnit。
- [ ] 归档 Linux production r3 invalid evidence，不删除；用新 run ID 只重跑失效或尚未开始的矩阵，不重跑有效 raw 结果。

### Task 4: 导入 COCO100 并转换 YOLO-Seg 训练数据

**Files:**
- Create: dataset conversion and inventory scripts under the existing training tool area
- Create: focused tests for polygon-to-box, class normalization, split sealing and SHA

- [ ] 校验 COCO100 `MANIFEST.sha256`、100 张固定图片、247 个 cup 实例与基线指标。
- [ ] 把交付物复制到 durable evidence root，逐文件 readback；仓库只保存必要 metadata，不提交 COCO 图片副本，除非另有数据发布决定。
- [ ] 校验 YOLO-Seg 数据归档及同目录 SHA，转换 polygon 为 bbox，类别统一为 `cup`。
- [ ] 统计尺度、遮挡、光照、背景和单杯/多杯覆盖，生成 train/val/new-test immutable inventories。
- [ ] 若覆盖不够，先登记 MuJoCo 增量采样配额，再生成新版本归档和 SHA；不覆写旧数据。

### Task 5: 实现并验证 Grounding DINO Tiny 微调容器

**Files:**
- Create/Modify: Grounding DINO training container script, frozen config, training entrypoint and tests
- Modify: dependency/model manifest generation as required

- [ ] 用官方/当前锁定 Transformers 接口做最小训练 smoke test，验证 label/text token、bbox 格式、loss 非空和 checkpoint 可重载。
- [ ] 固定基础 model revision、seed、optimizer、scheduler、batch、epoch、precision 和数据 inventory SHA。
- [ ] 在 ai-station 运行训练；实时记录 epoch、loss、val box Precision/Recall/F1、小目标 Recall、多杯 Recall、显存与 ETA。
- [ ] 仅按合成 val 的预注册排序选择 checkpoint，生成 checkpoint SHA 和不可变模型 manifest。
- [ ] 训练中断时从最新完整 checkpoint 恢复，不覆盖已完成 run。

### Task 6: 冻结模型后做 Linux 内部 test 与 COCO100 非劣化评测

**Files:** benchmark config, report inputs and evidence only

- [ ] 在模型、prompt 和阈值锁定后解封新的合成 test，运行一次 Grounded-SAM production test。
- [ ] 验证 selection safety、box/mask 指标、错误数、fallback 和完整分母。
- [ ] 对 COCO100 运行一次相同预处理和固定阈值评测，不读取结果后调参。
- [ ] 检查 `F1>=0.6391`、`Recall>=0.5670`、至少命中 `83/100`、非杯 UNIQUE 为 0、错误不超过 1。
- [ ] 任一门失败，标记模型不可进入 PickPlace；基于 train/val 或新增训练数据另起实验，不续写正式 test run。

### Task 7: ai-station Linux 四点位 PickPlace

**Files:** installed runtime/config and evidence only unless出现新的最小代码缺陷

- [ ] 预检 ai-station commit、overlay、ROS graph、tmux、GPU、`ROS_DOMAIN_ID`、`GZ_PARTITION` 和重复 stack。
- [ ] 以唯一 simulation session 逐点执行四个预置点位，不混用生命周期证据。
- [ ] 每点保存 detector candidates、生产 mask、Depth、TF、`/cup_pose`、MoveIt plan/execute、controller feedback、MuJoCo attachment/pose/contact 和 fresh GUI screenshot。
- [ ] 每点必须确认杯子从对应起点移动到目标区域，状态机 `DONE` 不能单独算成功。
- [ ] 四点全部成功后生成 Linux acceptance inventory；失败则停在首个证据分叉并按 TDD 修复。

### Task 8: Linux 通过后迁移 macOS并完成报告

**Files:** macOS model bundle/config, report, guide and ledger

- [ ] 从 Linux durable bundle 复制同一 checkpoint、SAM 权重、prompt 和阈值到 Mac，逐文件 SHA readback。
- [ ] 新建 Mac overlay，验证 MPS、无 fallback、production contract 和候选映射。
- [ ] 完成 Mac 四点位 PickPlace；不得用 Linux 成功替代 Mac 运行证据。
- [ ] 更新 benchmark 报告和教学文档，并使用 humanizer-zh；明确旧基线、新模型、未通过项和平台差异。
- [ ] 运行最终普通测试、显式 benchmark 测试、文档检查和 `git diff --check`；报告 retained、archived、deletion candidates，未经授权不删除。

# Grounding DINO Tiny 通用杯子微调与 Linux-first PickPlace Implementation Plan

> **执行方式：** 由 ai-station 上现有的 `tmux` Codex 会话接手，按本文逐项完成；每项代码变更遵守 RED -> GREEN。不得另外创建 subagent，也不得恢复与本任务争用 GPU 的 Microduck 训练。

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

- [x] 提交并 push 最小 mapping 修复；ai-station 的隔离 checkout 已从 Gitee 快进到 `f6f03b645c44b10a212f81047da304fc63a6c214`，未改 canonical dirty workspace。
- [ ] 创建新 Linux build/install/log overlay，确认 installed package prefix 与 source commit。
- [ ] 先运行普通 package gate，再显式运行 `benchmark_test/`；记录测试数、耗时和 JUnit。
- [ ] 归档 Linux production r3 invalid evidence，不删除；用新 run ID 只重跑失效或尚未开始的矩阵，不重跑有效 raw 结果。

### Task 4: 导入 COCO100 并转换 YOLO-Seg 训练数据

**Files:**
- Create: dataset conversion and inventory scripts under the existing training tool area
- Create: focused tests for polygon-to-box, class normalization, split sealing and SHA

- [x] 校验 COCO100 `MANIFEST.sha256`、100 张固定图片、247 个 cup 实例与基线指标。
- [x] 把交付物复制到 durable evidence root并逐文件 readback；仓库只保存必要 metadata，不提交 COCO 图片副本，除非另有数据发布决定。
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

## ai-station 接手检查点

接手会话只在下面这个隔离 checkout 工作：

```text
/data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11
```

当前已确认的基线：

- 分支：`codex/v5-t004-yolo-seg-rgbd`；
- mapping 修复提交：`f6f03b645c44b10a212f81047da304fc63a6c214`；
- Gitee 远端同分支已经指向该提交；
- ai-station checkout 已快进到该提交；
- checkout 中仅有旧的 `build-task14-runner-access-r11/`、`install-task14-runner-access-r11/`、`log-task14-runner-access-r11/` 未跟踪目录，不删除、不提交；
- COCO100 durable 副本：`/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/external/coco100-baseline-handoff-r1`；
- COCO100 的 419 条 `MANIFEST.sha256` 已全部通过，目录共 420 个文件；
- r21-r26 都属于环境定位，不是业务代码回归。r26 用同一 overlay 构建 7 个包后，普通测试为 `1158 passed, 9 failed`；9 个失败均因普通安装后的 Python 文件不在 Git 工作树内，`resolve_installed_execution_identity()` 无法读取 source commit；
- r27 使用相同 7 包和 `--symlink-install`，但卡在 lodepng FetchContent 克隆，超过 5 分钟没有 CPU 和新输出，现已停止并保留现场。r26 的 `_deps/lodepng-src` 是完整本地 Git checkout；接手后先验证该缓存，再用新的 r28 目录重建，不能续写 r27。

证据根保持不变：

```text
temporary=/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079
durable=/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079
```

## ai-station 详细执行 Runbook

### 阶段 A：收口 r27 和 Linux 代码门禁

1. 先检查是否已有 `colcon`、`pytest`、训练或 benchmark 进程，以及当前 GPU 使用者。确认 r27 相关进程已经停止；若仍有残留，只停止精确匹配 r27 路径的进程，不使用宽泛 `pkill`。Microduck 必须继续暂停。
2. 只读校验 r26 缓存中的 `_deps/lodepng-src`：Git worktree 完整、HEAD 可解析、关键源文件存在。把它复制或通过 CMake 的本地 source 参数提供给新的 r28 构建；不要修改 r26，也不要访问公网临时拉取依赖。若构建系统没有现成参数，先查 CMake cache/FetchContent 变量并做一个最小 dry-run，禁止拍脑袋改第三方源码。
3. r28 的完整构建集合固定为：

   ```text
   mujoco_ros2_control_msgs
   mujoco_ros2_control_plugins
   mujoco_3d_lidar
   mujoco_ros2_control
   so101_mujoco_support
   so101_teleop
   so101_demo_py
   ```

4. r28 成功后 source 其 `install/setup.zsh`，逐项读回：

   - `git rev-parse HEAD` 必须为 `f6f03b645c44b10a212f81047da304fc63a6c214`；
   - `python -c 'import so101_demo; print(so101_demo.__file__)'` 必须解析到该 checkout 的 symlink source，而不是 `/opt/ros/jazzy` 或旧 r20-r26；
   - `ros2 pkg prefix` 对上述 7 个包都必须指向 r28；
   - `runner.py` 和 `benchmark.yaml` 的 SHA 分别必须为 `919ac8f5c8d724de146b4ee9c144c2c41b9da6b822ced4efb44bafeaa1aac3ec`、`511e0e6472cb774f521783982b2833c790ddc85d1cf3bad03112100ee2896a92`。

5. 先运行普通门禁，只收集 `src/so101_demo_py/test/`。预期测试数为 1167；若失败，先按“代码、安装来源、运行环境、测试声明”四层分类，不要直接改业务逻辑。
6. 普通门禁通过后，再显式运行 `benchmark_test/`。这是 mapping 与 benchmark contract 的变更，允许且只需完整运行一次。把输出放进 r28 独立 test log，保留 JUnit 和 `colcon test-result --verbose`。
7. 两个门都通过后，在账本新增 checkpoint，记录命令、测试数、耗时、overlay、commit 和证据路径。失败的 r21-r27 继续保留，不删除。

阶段 A 的退出条件：普通门禁与显式 benchmark 都通过，来源追踪能读回 exact commit。未满足时不得进入训练。

### 阶段 B：只重跑受 mapping 修复影响的旧模型 production 验证

1. 复用 Linux r3 已验证的 raw records，不重复执行 Grounding DINO 或 SAM raw inference。
2. 用新的 run ID 重新生成 production candidates，验证相同 DINO proposal 在 mask IoU `>=0.98` 时能够映射，并保存 production 阶段实际生成的 SAM mask。
3. 校验样本 `images/test/000900012.png`：历史 raw/production mask 像素为 4698/4699，预期映射通过，但不能写任何“一像素例外”。
4. production 验证通过后再生成 calibrated 结果；若 production 失败，calibrated 不启动。
5. 本阶段只是确认 mapping 修复，不把旧模型重新宣称为可部署，也不重复已经有效的 Mac baseline。

阶段 B 的退出条件：旧模型 Linux production mapping 为 `VALID`，记录中可读回 production 实际 mask、IoU 门和完整分母。

### 阶段 C：构建可复现的数据转换链

1. 验证仓库训练归档及旁置 SHA：

   ```text
   datasets/so101-v5-t004-yolo-seg-synthetic/
   so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz
   archive_sha256=c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1
   ```

2. 解包到新的 durable 数据版本目录，不能覆盖旧目录。先读取 `dataset-manifest.json`、`dataset.yaml` 和 `truth/`，再决定转换输入；不要只依赖文件名猜测 split。
3. 先写失败测试，再实现转换器。最低测试覆盖：

   - YOLO 归一化 polygon 到规范化/绝对 `xyxy` box；
   - 多实例、贴边 polygon、非法空 polygon、退化 box；
   - 原类别统一为 `cup`，训练文本固定 `cup.`；
   - 原图 SHA、标签 SHA、源归档 SHA 和转换器 commit 写入 inventory；
   - train/val/test 成员不交叉，test 在模型和阈值冻结前不可读取；
   - 重复运行得到相同成员和 inventory SHA，目标目录已存在时 fail closed。

4. 生成数据画像：每个 split 的图片数、实例数、box 面积分层、遮挡、单杯/多杯、背景和光照。能从 truth 可靠读取的字段才可计数；推断项标为未知，不能伪造标签。
5. 只在画像证明小目标、多杯或遮挡覆盖不足时新增 MuJoCo 采样。先在账本登记缺口、数量、随机种子和新版本号，再采样；新数据另打包、另写 `.sha256`，旧归档不改。

阶段 C 的退出条件：转换器测试通过，train/val/new-test inventories 固定且 SHA 可读回，test 保持 sealed。

### 阶段 D：实现 Grounding DINO Tiny 微调容器

1. 先检查 ai-station 已锁定的 Transformers、PyTorch、CUDA 版本和本地模型目录。训练 API 以当前锁定版本及官方文档为准，不复制未经验证的示例。
2. 新增独立的 Grounding DINO 训练容器入口，不复用 YOLO CLI 名称。容器必须：

   - 只读挂载数据和基础模型；
   - 输出目录必须不存在；
   - 禁止联网训练，模型和 tokenizer/processor 从本地加载；
   - 只启用 CUDA，CPU fallback 立即失败；
   - 固定 seed、基础 revision、optimizer、scheduler、batch、epoch、precision；
   - 写出 resolved config、环境清单、数据 inventory SHA、逐 epoch 指标和 checkpoint SHA；
   - 支持从“完整且通过 SHA 校验”的 checkpoint 恢复，不覆盖旧 run。

3. 先用极小 fraction 和 1 个短 epoch 做 smoke：processor 能生成文本 token，box 标签格式正确，loss 有限，反向传播成功，checkpoint 能在全新进程中重载并完成一张图推理。
4. smoke 通过后才启动正式训练。训练期只看 synthetic train/val，不挂载 COCO100，也不打开 sealed test。
5. checkpoint 选择排序固定为：val cup box F1；并列时依次比较 Recall、小目标 Recall、多杯 Recall、较少 FP。把排序代码和测试写进仓库，不能人工挑图选择。
6. 训练日志至少每个 epoch 给出进度、ETA、loss、val TP/FP/FN、Precision/Recall/F1、小目标 Recall、多杯 Recall、显存峰值。长任务在 tmux 内持续运行，失败时保留最后完整 checkpoint。

阶段 D 的退出条件：一个只由 synthetic val 选出的 frozen checkpoint、模型 SHA、processor/config SHA 和不可变 manifest。

### 阶段 E：冻结后的双评测

1. 先把模型 SHA、`cup.` prompt、DINO box/text threshold、SAM 模型 SHA、SAM 阈值、mapping IoU `0.98` 和 selector 规则写入 threshold lock。
2. 解封新 synthetic test，只运行一次正式 raw -> production -> calibrated 流程。要求：无 CPU fallback、无缺失样本、无 mapping error，实际 SAM mask 全量落盘。
3. synthetic test 通过后，才允许把同一个 frozen checkpoint 对 COCO100 durable 副本运行一次。不能根据这 100 张的结果改阈值后重跑。
4. COCO100 同时满足：

   - `F1 >= 0.6391`；
   - `Recall >= 0.5670`；
   - 至少检出一个真杯子的图片 `>=83/100`；
   - 肉眼可见非杯 `UNIQUE <=0`；
   - inference error `<=1`。

5. 报告完整 TP/FP/FN、Precision/Recall/F1、图片命中数、selection 分布、小/中/大目标和单杯/多杯分层。结果差也要保留，不用删分母或只展示成功样本。
6. 任一安全门或非劣化门失败：模型不得进入 PickPlace。另开实验，只能根据 train/val 和已登记的数据缺口调整；COCO100 保持只读历史结果。

阶段 E 的退出条件：synthetic test 安全门和 COCO100 非劣化门全部通过。

### 阶段 F：Linux 四个预置点位 PickPlace

1. 四次运行使用独立 run ID 和 `FULL_RESTART` 生命周期。每次开始前检查唯一 ROS/Gazebo/MuJoCo stack、GPU 进程、`ROS_DOMAIN_ID`、`GZ_PARTITION`、模型 SHA 与 overlay。
2. 每个点位必须从 RGB-D 帧开始，经 Grounding DINO `cup` boxes、SAM production mask、唯一目标选择、深度反投影、TF 变换、`/cup_pose`、MoveIt plan/execute、controller feedback，最终到 MuJoCo 对象状态。
3. 每次保留：候选 JSON、production mask、深度统计、TF、`/cup_pose`、规划与执行结果、controller、attachment/contact、起终点对象位姿、run manifest 和 fresh GUI 截图。
4. 成功判据是杯子确实从该预置起点移动到目标区域；仅状态机出现 `DONE`、仅机械臂运动或仅生成 `/cup_pose` 都不算成功。
5. 在首个失败证据分叉停下：感知、选择、深度、TF、规划、控制、抓取或放置。按 RED -> GREEN 修复后，只重跑受影响点位和必要回归，不无差别重跑前面耗时阶段。

阶段 F 的退出条件：四个预置点位各有一次新的、完整且可复核的 `VALID` 成功证据。

### 阶段 G：发布 Linux 成果，再迁移 Mac

1. 汇总 Linux 模型 bundle、配置、processor、SAM 权重引用、threshold lock、代码 commit 和四点位 acceptance inventory，逐文件 SHA readback。
2. 提交文档和必要代码前，运行相关快速测试、`git diff --check` 和来源检查；普通 fetch/rebase、commit、push，最后读回 Gitee remote SHA。不得 force-push。
3. 只有 Linux 阶段 F 通过后，才创建 Mac 迁移 checkpoint。复制同一 bundle 并逐文件校验 SHA，不在 Mac 重新选择 checkpoint 或阈值。
4. Mac 使用独立 overlay 和 MPS 门禁，重复四点位完整 PickPlace。Linux 证据不能替代 Mac 证据。
5. 最终更新 benchmark 报告、教学文档和实验账本。教学文档放在 `docs/guides/`，中文段落使用 `$humanizer-zh`；准确列出通过项、失败项、平台差异和保留证据。

## 执行纪律与状态回报

- 每完成一个阶段，先在账本写 checkpoint，再进入下一阶段。
- 每 30 至 60 分钟，或阶段状态变化时，在 tmux Codex 会话中留下简短进度；不要因为任务耗时就重复启动同一 run。
- production、训练、评测和 PickPlace 都要使用唯一 run ID。目录已存在时停止并分配新 ID，禁止续写失效 run。
- 不删除历史证据。完成时列出 retained runs、archived runs 和 deletion candidates，等待用户另行授权删除。
- 发生需要改变数据范围、非劣化门槛、训练目标、真实机械臂授权或平台顺序的情况时停止，并向用户请求决定。
- Microduck 训练只在本任务全部完成且用户允许后恢复。

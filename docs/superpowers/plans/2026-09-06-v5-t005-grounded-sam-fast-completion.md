# V5-T005 Grounded-SAM 数据重建、训练与双平台 PickPlace 快速收口 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` and the project-local `so101-dev` skill. Execute inline and serially in the existing ai-station Codex session. Do not create execution subagents.

**Goal:** 停止继续扩展低概率 fsync 故障注入测试，立即完成无穿透数据合成、Grounding DINO Tiny 微调、冻结 SAM 联合评测、ai-station Linux 四个预置点位 PickPlace，再把同一模型包迁移到 macOS 并完成相同四点验收。

**Architecture:** Grounding DINO Tiny 只检测通用 `cup`，用类别、bbox 和 DINO score 标识候选；冻结的 SAM 2.1 Hiera Tiny 以 box prompt 逐帧无状态生成实例 mask。唯一近工作区目标通过 RGB-D 反投影和 TF 生成 `/cup_pose`，MoveIt 只消费通过几何与安全门的 pose。训练、阈值选择只使用新合成 train/val；独立 test 用于冻结候选的最终验证，COCO100 只保留为一次性历史诊断证据，不再是晋级门。

**Primary spec:** `docs/superpowers/specs/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first-design.md`

**Prior plan:** `docs/superpowers/plans/2026-09-04-grounding-dino-tiny-cup-finetune-linux-first.md`

**Handoff:** `/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079/coordination/generator-r443-r1/codex-session-handoff-cp402.md`

## 1. 本计划覆盖和取代的内容

本计划只改执行顺序和工程投入，不改已冻结的模型语义、指标口径和机器人安全边界。

- 用户已决定接受 CP-402 中两项低概率持久化异常的残余风险。本轮不做 r536，不再增加 fsync/date 故障注入、mutation、通用 harness 或重复 Astra 评审。
- r535 的 `281/281`、r499 的 benchmark、r470 的真实 GPU 渲染验证和已有普通测试结果继续复用，不重复运行。
- 正常路径仍保留 fsync、文件系统日志和完整性校验；ai-station 上 fsync-heavy 任务仍按 `AGENTS.md` 使用 `/data` NVMe scratch，并用实际 Python 验证 `TMPDIR/TMP/TEMP`。
- CP-402 的 `NO_GO` 由新的账本 checkpoint 显式解除，解除范围仅为本计划的正常路径。不能把它改写成“r535 已经证明所有异常路径”。
- 用户于 2026-09-07 移除 COCO100 的 pass/fail 门控。r595/r760 的失败结果和 CP-476 原样保留，不重跑 COCO100，也不依据该结果调阈值、重选 checkpoint 或继续训练；这项政策只解除其对四点 smoke、bundle promotion 和 PickPlace 的阻断作用。
- Microduck 继续暂停，直到 Linux、macOS 四点 PickPlace 和最终报告全部完成，或用户另行允许恢复。

## 2. 当前可信起点

- ai-station checkout：`/data/work/so101-grounded-sam-yolo-benchmark-ab-v1-task14-runner-access-r11`
- 分支：`codex/v5-t004-yolo-seg-rgbd`
- 制订本计划时本地与 Gitee 均为：`da894db07432311a9470623ae9915119e0533889`
- 保留未跟踪目录：`build-task14-runner-access-r11/`、`install-task14-runner-access-r11/`、`log-task14-runner-access-r11/`
- 临时证据根 `T`：`/tmp/so101-debug-v5-t005-grounded-sam-20260901/remediation/exp-079`
- 持久证据根 `D`：`/data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869/remediation/exp-079`
- 已接受包源码 commit：`07dcd29ae496e54f3fcb70092a6613db52fc7b27`
- 正式生成输入：CP-402 记录的 private driver、shell、r535 harness 与 launcher；启动前必须按交接文档 SHA 读回。
- 已冻结语义：class `cup`、prompt `cup.`、mask truth IoU `0.80`、candidate mapping IoU `0.98`、SAM 逐帧无状态。

如果 HEAD 或交接文件发生变化，先读账本最新 checkpoint。只有来源不明、哈希不符或输出发生碰撞时才停止；不要因为旧计划中的 r536 未执行而停止。

## 3. 时间预算和停止规则

- 接手与启动门：目标 30 分钟内结束。不得重新通读全部历史账本；读 CP-311 至 CP-402 的关键 checkpoint、CP-402 handoff 和本计划即可。
- 正常路径预检：只做静态/hash/collision/GPU/Python/NVMe/进程检查，不再造新 harness。目标 15 分钟。
- 数据生成：启动后至少每 60 秒或每 25 张更新一次 `完成数/1500、当前 split/scenario、重试数、速度、ETA`。有持续进度就等待，不以固定墙钟时间误杀。
- 训练：每个 epoch 输出 loss、val TP/FP/FN、Precision/Recall/F1、近工作区 Recall、显存峰值和 ETA。
- 某一阶段 30 分钟没有新增样本、epoch、日志或 GPU 活动时，先判断是卡死还是正常 I/O；确认卡死才精确停止对应 PID。不得宽泛 `pkill`。
- 一个失败只修最靠近产品路径的根因。不得再开多层 runner/harness/reviewer 链；一次最小修复、一次定向测试、一次重跑。

## 4. 阶段 A：接管并解除 CP-402 的正常路径阻塞

**Files:**

- Modify: `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`
- Verify: CP-402 handoff and the four private generation inputs

- [ ] 确认当前 repo、branch、HEAD、Gitee SHA、tracked clean、三项既有 untracked 目录、GPU 与进程状态；不得清理或切换工作区。
- [ ] 读回 CP-402 handoff SHA，以及 driver、shell、r535 harness、launcher 的 SHA；确认四个正式输出根在 `-e` 和 `-L` 下均不存在。
- [ ] 新增 checkpoint，原样记录用户决定：接受 real-driver operation mismatch 与 dead `date` read 在异常路径上的残余风险；取消 r536 和后续 fault-injection；不宣称问题已修复。
- [ ] checkpoint 只授权正常路径的 1500 张 train/val 生成、转换和训练。保存失败证据、输出防碰撞、fsync 与完整性检查仍然有效。
- [ ] 提交计划和 checkpoint，普通 push 到 Gitee并读回远端 SHA；之后立刻进入阶段 B。

**Exit:** 新 checkpoint 明确覆盖 CP-402 的生成 `NO_GO`，且没有启动新的故障注入工作。

## 5. 阶段 B：生成 1500 张无穿透 train/val

**Inputs:** CP-402 锁定的 private driver/shell，以及已批准的 `so101-nonpenetrating-train-val-v1` 配置。

**Fixed dataset contract:**

- train `1200`，val `300`；每个 split 覆盖六种 scenario；
- train 每场景 `200`，val 每场景 `50`；
- seed：train `450000000..450001199`，val `460000000..460000299`；
- all-scenario 保留 `small_far_cup`，primary near-workspace 报告仅排除该 scenario；
- 不生成、读取或转换 test；不挂载 COCO100；
- 所有场景启用 `task-visual-nonpenetration-v1`，truth 使用 categorical visible mask/RLE，不能退回 convex hull 当 mask truth。

**Outputs:**

1. `D/training-data/yolo-seg-nonpenetrating-train-val-v1`
2. `D/training-data/archives/so101-v5-t005-cup-nonpenetrating-train-val-v1.tar.gz`
3. `D/training-data/grounding-dino-cup-nonpenetrating-train-val-v1`
4. `D/training-data/grounding-dino-cup-nonpenetrating-train-val-v1-repro`

- [ ] 为本次正式生成分配新的 run ID、evidence root 和 `/data/.../scratch/<run-id>/tmp`；验证实际 Python 的 `tempfile.gettempdir()` 精确指向该目录。
- [ ] 只做一次启动前检查：配置结构、计数、seed、渲染器/MJCF SHA、NVIDIA EGL、目标不存在、无 sealed/COCO 路径。复用 r470 的真实 GPU 验证，不再做故障注入预演。
- [ ] 启动正式 1500 张生成。进度写入持久日志；若进程失败，保留 partial root，换新 dataset version/run ID，不续写旧目录。
- [ ] 完成后一次性读回 1500 张图片/标签/truth/geometry receipts、split/scenario/seed 配额、RLE、非穿透距离、文件模式和 SHA。生成确定性 tar.gz 及旁置 `.sha256`。
- [ ] 用现成 converter 转成 Grounding DINO train/val，类别归一为 `cup`、prompt 固定 `cup.`。再生成 repro 副本并验证 inventory 与 payload byte/hash 一致。
- [ ] 冻结三个数据根为只读；生成 all-scenario 与 primary-near-workspace 数据画像。不要因为 `small_far_cup` 低指标而修改训练样本或报告分母。

**Exit:** 1200/300 数据、archive、primary conversion、repro conversion 均完整，SHA 和 inventory 可独立读回。

## 6. 阶段 C：复用现有训练栈微调 Grounding DINO Tiny

**Files:** 只有发现产品路径缺陷时才修改训练代码。优先复用：

- `scripts/grounding-dino-training-container.sh`
- `src/so101_demo_py/docker/grounding-dino-training/Dockerfile`
- `src/so101_demo_py/config/perception/grounding_dino_training.yaml`
- `src/so101_demo_py/src/cli/train_grounding_dino.py`
- `src/so101_demo_py/src/cli/verify_grounding_dino_checkpoint.py`

- [ ] 读回现有训练镜像、base model、旧 formal DINO checkpoint、训练代码和 container SHA。镜像与当前代码兼容时直接复用，不 rebuild。
- [ ] 用 6 train + 6 val、1 个短 epoch 做一次 smoke；确认 CUDA、有限 loss、反向传播、checkpoint 完整和新进程 reload。smoke 不挂载 test、COCO100 或 SAM。
- [ ] 第一轮正式训练从已验证的最新 DINO 微调 checkpoint warm-start，在新 1200/300 数据上训练 4 个 epoch；固定 seed、optimizer、scheduler、batch、precision 和 inventory SHA。
- [ ] checkpoint 只按 val 排序：近工作区 cup box F1、Recall、近工作区小目标 Recall、多杯 Recall、较少 FP；同时完整保存 all-scenario 指标。
- [ ] 如果 4 epoch 后没有超过训练前 checkpoint，或近工作区 Recall 仍不满足后续 mask/定位要求，最多追加一轮：从官方 pinned base 开始训练原冻结 8 epoch recipe。不能用 sealed test 或 COCO100 选模型。
- [ ] 冻结胜出 DINO checkpoint、processor、config、prompt、阈值和 SHA manifest。

**Exit:** 一个只由新 synthetic val 选出的 frozen DINO candidate。最多执行两轮正式训练，避免无边界试验。

## 7. 阶段 D：冻结 SAM 联合验证；只在证据要求时补训 SAM

- [ ] 先把胜出 DINO 与当前已验证的 SAM checkpoint 组合。SAM 保持逐帧无状态，候选映射继续使用 `cup + bbox + DINO score` 和 mask IoU `>=0.98`。
- [ ] 在新 val 上运行一次完整 DINO -> SAM -> production candidate -> mask truth 评测。近工作区为进入 PickPlace 的主门，all-scenario 作为完整能力报告。
- [ ] 如果 DINO box 门已通过而 mask IoU `>=0.80` 仍是主要失败来源，才允许复用现有 decoder-only trainer，在 train 上补训 SAM decoder；encoder 冻结，最多 5 epoch，仍按 val 选 checkpoint。否则不训练 SAM。
- [ ] 冻结最终双模型 bundle 和 threshold lock。运行时近距离资格必须由 depth、可达性和投影 bbox/mask 几何判断，不能读取 scenario 名称。

**Exit:** frozen Grounded-SAM candidate 在新 val 的近工作区 cohort 通过候选唯一性、mask、深度与无 fallback 门。

## 8. 阶段 E：一次性内部 test 与 COCO100 历史诊断

- [ ] 在 bundle 和阈值冻结后，用同一非穿透协议、独立 seed 生成 `300` 张只用于最终评测的 test（六场景各 50）。先登记成员/seed/输出协议，生成后立即封存；任何结果都不能回流训练或调阈值。
- [ ] 对 test 只运行一次完整 Grounded-SAM production 评测并保存实际 SAM mask。报告 all-scenario 和排除 `small_far_cup` 的 primary near-workspace；历史指标不能改写。
- [x] frozen candidate 的唯一一次 COCO100 运行已由 r595 完成，r760 只做身份绑定与结果裁决。历史结果为 F1 `0.0`、Recall `0.0`、命中图片 `0/100`；保留该结果和原保护线，不再运行第二次。
- [x] 2026-09-07 起，COCO100 不再参与模型晋级，也不阻断四点 smoke、bundle promotion 或 PickPlace。它仍不得用于调阈值、挑 checkpoint、决定训练数据或启动新训练。

**Exit:** 非穿透 test 的 near-workspace 安全门通过；COCO100 历史结果已完整保留并与冻结身份绑定。

## 9. 阶段 F：ai-station Linux 四个预置点位 PickPlace

- [ ] 先用已冻结的四点 carrier、threshold lock `b02e3be…` 和 bundle `b55bb6…` 完成一次 acceptance-only perception smoke。四点 truth 只能用于本次验收，不得进入训练、阈值选择或生产候选生成。
- [ ] 四点分别验证唯一 cup、生产 SAM mask truth IoU `>=0.80`、candidate mapping IoU `>=0.98`、有效深度、world `/cup_pose` 误差 `<0.01m`、source freshness 和 warmed latency `<=2000ms`。四点全部语义正确后才进入 PickPlace。
- [ ] 建立新 Linux overlay，仅在源码有变化时运行相关 ordinary tests；只有 benchmark 代码/配置或模型选择发生变化时才显式运行 benchmark suite。禁止每个 checkpoint 都全量测试。
- [ ] 四个点位各用独立 run ID 和 `FULL_RESTART`。每次确认唯一 ROS/MuJoCo stack、CUDA、bundle SHA、`ROS_DOMAIN_ID`、`GZ_PARTITION` 和 controller 状态。
- [ ] 每个点位保存 RGB、DINO candidates、production SAM mask、depth 统计、TF、`/cup_pose`、MoveIt plan/execute、controller、attachment/contact、杯子起终位姿和 fresh GUI 截图。
- [ ] 成功必须同时满足：近距离唯一杯子被选中、发布新的 `/cup_pose`、机械臂完成抓放、MuJoCo 杯子从预置起点进入目标区。只有 `DONE` 或机械臂动作不算成功。
- [ ] 首次失败只沿 `检测 -> 分割 -> 深度 -> TF -> 规划 -> 控制 -> 抓取/放置` 的第一个断点修复，随后重跑受影响点位和必要回归。

**Exit:** Linux 四个预置点位各有一份新的 `VALID` 完整成功证据。

## 10. 阶段 G：同一 bundle 迁移 macOS并完成终止目标

- [ ] 发布 Linux acceptance bundle：DINO、SAM、processor、prompt、threshold lock、代码 commit、模型/配置 SHA 和四点 inventory。
- [ ] 把同一 bundle 复制到 Mac 并逐文件读回 SHA；不在 Mac 重选 checkpoint 或阈值。
- [ ] 在 Mac 新 overlay 验证 MPS、FP32、无 CPU fallback、逐帧无状态和相同 `/cup_pose` 接口。
- [ ] Mac 四个预置点位逐点 `FULL_RESTART`，使用与 Linux 相同的端到端成功判据和证据结构。
- [ ] 更新实验账本、benchmark 报告和 `docs/guides/` 下的教学文档。中文教学文字使用 `$humanizer-zh`，技术事实、命令、SHA 与路径保持原样。
- [ ] 对拥有的变更运行相关测试、文档链接/路径检查和 `git diff --check`；fetch/rebase、commit、普通 push 到 Gitee并读回远端 SHA。
- [ ] 最终报告 Linux/Mac 四点结果、模型指标、保留证据、归档证据和 deletion candidates。未经用户授权不删除任何证据，也不自动恢复 Microduck。

**Terminal exit:** Linux 4/4 与 Mac 4/4 PickPlace 都有新的、可复核的端到端成功证据，最终代码/模型/配置已同步，报告和账本已提交到 Gitee。

## 11. ai-station 状态汇报格式

每 30 至 60 分钟，或阶段发生变化时，用下面六行汇报，避免再次陷入长时间“准备 harness”而没有产品进展：

```text
阶段：A/B/C/D/E/F/G
当前动作：一句话
进度：样本数或 epoch 或点位数
最近有效证据：run ID + 关键结果
当前阻塞：无 / 精确错误
下一步与 ETA：一句话
```

只有下列情况需要停下来问用户：改变模型家族、恢复或重跑 COCO100 门控、扩大到真实机械臂、删除证据、恢复 Microduck，或出现无法用一次最小修复解决的安全问题。其他正常执行步骤直接继续。

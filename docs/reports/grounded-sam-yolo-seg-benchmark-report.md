# Grounded DINO + SAM 2.1 Benchmark 与生产验收报告

## 当前结论（2026-09-07）

当前生产候选已经不再是最初的零样本组合，而是 `Grounding DINO Tiny epoch 1 + SAM 2.1 Hiera Tiny decoder epoch 4`。冻结 bundle manifest 的 SHA-256 为 `b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05`，阈值锁 SHA-256 为 `b02e3be2814d03b954bdcb73b2f79f8b91d1227c6476fcc82695cabb91f50278`。

这组模型在 300 张 nonpenetrating synthetic val 上完成了实际的 `DINO -> SAM -> production candidate` 联合评测：DINO box 和 SAM mask 的 precision、recall、F1 均为 `1.0`；最低 matched box IoU 为 `0.8180`，最低 mask IoU 为 `0.9258`，最低 production/raw mapping IoU 为 `1.0`。这只是当前 MuJoCo 数据分布内的结果，不等于通用图像能力。

Linux 端随后用四个预置点各做一次独立 `FULL_RESTART` MuJoCo PickPlace，结果为 `4/4`：

| 点位 | DINO | SAM quality | `/cup_pose` 误差 | 杯子位移 | 最终 XY 误差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `task_start` | 0.8290 | 0.9887 | 0.000482 m | 0.103874 m | 0.001791 m |
| `cup_test_forward_5cm` | 0.8526 | 0.9856 | 0.000453 m | 0.129248 m | 0.001194 m |
| `cup_test_left_5cm` | 0.8523 | 0.9859 | 0.001918 m | 0.056960 m | 0.003473 m |
| `cup_test_right_5cm` | 0.8191 | 0.9871 | 0.000495 m | 0.151997 m | 0.001942 m |

四次运行都有一个 cup candidate、有效深度、CUDA 推理、19 次状态迁移、双侧接触、实际抬升、稳定桌面释放、Planning Scene 回读、controller 成功和新鲜 MuJoCo 窗口截图。独立复核重新校验了清单内 276 个普通文件、7 个 symlink 和四份摘要；四张最终截图也逐张检查过。日志中的 `Attached body 'plastic_cup' not found` 出现在初始化或已 detach 后的幂等场景同步附近；同一运行的权威回读为 `attached=[]`、`plastic_cup` 在 world，后续执行和最终落点均通过，因此把它保留为已知的非阻塞 MoveIt 日志噪声，不把它隐藏成“零报错”。

模型和训练数据已经发布到私有 Hugging Face 仓库 [zjumty/so101-grounded-sam-cup-pickplace](https://huggingface.co/zjumty/so101-grounded-sam-cup-pickplace)，固定 revision 为 `52b8334358e5ff11f94f10f7c14b1697ef44d964`。训练数据只以一个 `tar.gz` 上传，SHA-256 为 `c4b9624e9f68a96087f58ff961c67bfa10ceb28f4ea821e501e9fd16a0e00dbe`；远端新目录下载后，22 个 payload 和 9036 个归档成员均已回读通过。

当前跨平台终态仍未完成：本机 macOS 和 `ssh mac-mini` 的四点 PickPlace 尚待执行。本文后面的旧 benchmark `INVALID` 结论仍按原意保留，它描述的是修复前 raw adapter 的实验，不能拿来否定或证明当前冻结 bundle。

## 历史 benchmark 结论（修复前）

本轮 benchmark 的总体状态是 `INVALID`。现有证据不能支持 Grounded-SAM 与 YOLO-Seg 的正式优劣排序，也不能支持任何一方可部署或可进入 Pick & Place 的结论。

问题出在 Grounded-SAM benchmark raw adapter：同一个 Grounding DINO proposal 在低门槛后处理时被还原为 `plastic cup.`，在 production 阈值后处理时被还原为 `plastic cup`。`GroundedSamRawAdapter._grounding()` 只接受后一种字符串，因此漏掉了 production detector 实际保留的候选。正式 test 的 production/replay 一致性检查在第 1 张图上以 `PRODUCTION_CANDIDATE_MAPPING_INVALID` 终止，这是正确的 fail-closed 行为。

这份报告只记录已完成的工作、失败边界和后续整改条件，不生成不完整的正式指标表，也不从局部结果中选出 winner。

## 这轮完成了什么

数据、模型和运行来源均已固定；val 在 Mac MPS 与 Linux CUDA 上完成了两模型各 200 张的 raw 采集；两份 val-only threshold-lock 已生成并验证；test 只解封过一次；跨主机读取与 exact-source overlay 均完成了验证。

正式 test 开始后，以下结果可以作为工件完整性证据：

| Run | 状态 | 样本 | ERROR | Raw candidates | 说明 |
| --- | --- | ---: | ---: | ---: | --- |
| Mac YOLO `TEST_RAW_FROZEN` R12 | artifact-valid | 200 | 0 | 215 | 完整 evidence index 和独立 loader 均通过 |
| Mac Grounded-SAM `TEST_RAW_FROZEN` R12 | structurally artifact-valid | 200 | 0 | 11,117 | raw adapter 语义缺陷使其不能进入模型能力排名 |
| Mac Grounded-SAM `TEST_PRODUCTION` R12 | `INVALID` | 0 | — | 首帧写出 55 个低门槛 mask | 第 1 个正式样本即发生 production/replay 映射失败 |

剩余 9 个 R12 run 均为 `NOT_RUN_AFTER_INVALID`，不是零分结果。Task 15 的 performance 输入门槛也没有满足，因此 cold latency、warmed latency、per-phase timing、资源采样和 cross-platform mismatch 都没有正式结果。

## Val 标定结果：仅作诊断

四个 R8 val raw run 都覆盖 200 张图，每个场景 50 张，且为零 `ERROR`：

| 平台 / 模型 | Record inventory SHA-256 | Raw candidates |
| --- | --- | ---: |
| Mac MPS / YOLO-Seg | `6132811915a4ceb87b6c9069a5d437bdc74816c1462be89d3d0765ff9f8afd7d` | 210 |
| Mac MPS / Grounded-SAM | `adea204f310aa728083a3fdf422d6315837abd9d4f8f1c2532c6881d7bedef0c` | 10,966 |
| Linux CUDA / YOLO-Seg | `393e88ba0b8cd2b1592d7e934eb357041c54cfda705fa1e31f213bfb2d431014` | 210 |
| Linux CUDA / Grounded-SAM | `ad86669b77abd60b06256ccbf86f3efcbd7a888a56f9807b430197107247f8f7` | 11,007 |

YOLO-Seg R9 的冻结 characterization point 为 `conf=0.95`、`nms_iou=0.40`、`imgsz=640`、`target_confidence_threshold=0.95`。两端各 200 张、零错误，macro-F1 为 `0.9949746218402935`，two-cup both-matched recall 为 `0.98`，unsafe-unique 为 `1/100`（`0.01`），合并 mask AP50-95 为 `0.9398685972265695`。它的结果是 `UNSAFE_CALIBRATION_NO_FEASIBLE_POINT`，`deployable=false`。

Grounded-SAM R9 的冻结点为 `box_threshold=0.05`、`text_threshold=0.05`、`sam_quality=0.85`、`target_confidence_threshold=0.05`、`duplicate_iou=0.85`、`min_mask_pixels=64`、`max_mask_area_ratio=0.50`。当时记录的两端 macro-F1 为 `0.14046946863361034`，two-cup both-matched recall 为 `0.0`，unsafe-unique 为 `0/100`，合并 mask AP50-95 为 `0.006242535319651717`。

后一组数值在文件层面可复现，但不能代表 production detector 的实际候选空间，因为它的输入已经受到 raw adapter 漏候选问题影响。原先的 `SAFE_CALIBRATED` 和 `deployable=true` 只表示该错误候选空间满足 unsafe-unique gate，不能再解释为可部署结论。

## 为什么没有正式 test 指标

正式矩阵要求 Mac/Linux × YOLO/Grounded-SAM × raw/production/calibrated-or-characterization 全部完成，并且 production `DetectorPort` 结果与 frozen raw replay 对同一张图逐项一致。当前只有两个 Mac raw 工件完整；Grounded-SAM production 在第 1 张图上失败，Linux formal test 尚未开始。

因此，本报告不提供以下内容：

- 正式 test 的 AP、F1、decision confusion、unsafe-unique 或 95% CI；
- test raw-capability ranking；
- production 与 calibrated/characterization 的正式比较；
- cold/warm/per-phase/resource 性能指标；
- Mac 与 Linux 的逐图一致性结论；
- winner、deployability 或 Pick & Place 安全结论。

本轮没有运行 `ORACLE_DIAGNOSTIC`，也没有在 test 上扫阈值或把 test 结果回填到配置。

## 首个无效边界

失败链条如下：

1. `test/mac/grounded-sam-raw-r12` 完成 200 张 raw 采集，文件结构与 SHA 均通过。
2. `test/mac/grounded-sam-production-r12` 在第 1 张图调用真实 production detector。
3. production 返回的一个候选无法在同图 raw 候选中做一对一映射，runner 返回 `PRODUCTION_CANDIDATE_MAPPING_INVALID`。
4. 固定使用既有 val record `val/mac-grounded-sam-r8/records/000044.json` 做不读取 truth 的复现。两项候选精确匹配；score 为 `0.7195684313774109` 的 production 候选没有 raw 对应项。最近的 raw mask 完全相同，但 bbox IoU 为 `0.9893957909706307`，score delta 为 `0.7033657338470221`。
5. 第二个 val-only 诊断复用同一次 DINO forward：在 `.01/.01` 低门槛后处理下，该高分 proposal 的 label 是 `plastic cup.`；在 `.35/.25` production 后处理下，label 是 `plastic cup`。另外两个 proposal 在两组阈值下都是 `plastic cup`。
6. `GroundedSamRawAdapter._grounding()` 使用 `label != "plastic cup"` 做精确过滤，带句点的真实候选被提前丢弃。

这个结果说明当前 benchmark adapter 有缺陷，不说明 Grounded-SAM 在正式 held-out test 上弱于 YOLO-Seg。反过来，两个完整 raw run 也不足以说明 Grounded-SAM 更强，因为其中一个 run 的候选语义已经失真。

## 固定资产与证据锚点

| 项目 | 固定值 |
| --- | --- |
| 数据集归档 | `datasets/so101-v5-t004-yolo-seg-synthetic/so101-v5-t004-yolo-seg-synthetic-20260831-f09cf88.tar.gz` |
| 数据集 SHA-256 | `c0a837b0457c13d83160b1843137e0a85d6e8a6d98eb45ddf97cb9812e2cf3f1` |
| Val inventory SHA-256 | `343fca2d5c57c1698fdf4113c68c49a264222db46e0889e7b17d8df5016cd8df` |
| Test inventory SHA-256 | `8c9a1df65a9c65e32bdfa5c187fc9a2fbff0e6e4207abd7543a026330ab5e3f9` |
| YOLO `best.pt` SHA-256 | `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781` |
| Grounded-SAM bundle manifest SHA-256 | `0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775` |
| Grounding DINO revision | `a2bb814dd30d776dcf7e30523b00659f4f141c71` |
| SAM 2.1 revision | `de431c4043854a71d8101e17995dfe596bf101a5` |
| Dependency lock SHA-256 | `0fe23f19596eeaa1e0770ff39f41b63f1c4312db9a8b68e154fd9a5c7c421ec8` |
| Benchmark config SHA-256 | `52d7686168ecaeff933eb5a0fac38f0fefd13a52ebc88b33d655ab4a67b39f99` |
| Formal inference source commit | `93665011fa84abd75dd609b96d423228387e4596` |
| Test access event identity | `8f3fe61e2e9bcd33479a7c794d59e2d6e168cf83bb61482b2c84e5f08e99d0c3` |
| YOLO threshold-lock identity | `c8d25e4db18ddc769f805bb07b54d7c04aba26b65cbbf44002f03a352e696d34` |
| Grounded-SAM threshold-lock identity | `fbe3b4cd18d8b18402815e8de3851e97203d98fd70ba0e6bb1b5836baf205554` |

相关 test 工件：

- Mac YOLO raw manifest：`391871443179c014d93955bd36a3e7b212c7a1b9c4d340fd8f21bd60e14f6fd4`；evidence index：`22e02f26624d1442494d5a5d3ac324c5c5df63c4954512c2ff261c4bf49ef177`。
- Mac Grounded-SAM raw manifest：`fb5104e0bfb0fc4aab0cf7e74b41124f14a76dc3fce42e9a90dbe894cd06a228`；evidence index：`3ee5b639b2f9e7deba770b0572de58885ddc62a3a3dbd30175276e1a057aeac9`。
- Mac Grounded-SAM production invalid manifest：`e4026318319d576c547125fe981eb66f0f04ac0849531ee7de2271b269cb579e`。
- 映射诊断脚本：`45af73218133511c1dda2380935285ce0ba01d215f79c663a1aa2c152b2ebf6a`；label/threshold 诊断脚本：`edd516aaa05401bf38dbe01d5258e74cbe1bd5d862c09cd86f33ccd1df9ecfde`。

完整运行记录见 [benchmark experiment ledger](../experiments/grounded-sam-yolo-seg-benchmark-experiment-ledger.md)，设计与停止规则见 [benchmark design](../superpowers/specs/2026-09-02-grounded-sam-yolo-seg-benchmark-design.md)。由于 Task 15 输入门槛未满足，未创建 `/final/` 机器聚合结果或伪造 JSON/CSV。

## 数据集和任务边界

这套数据是合成 RGB 数据，实例 mask 来自凸包近似，不是像素级人工精标；bottle 没有实例 mask。它适合检验当前四类场景中的 2D 候选、实例数和 fail-closed decision，但不能替代真实相机数据。

本轮也没有输入 depth、camera intrinsics 或 TF，不产生 `/cup_pose`，没有启动 MoveIt 和 Pick & Place。因此，这份 benchmark 报告不能作为 Mac/Linux 四个预置点位成功的证据，更不能外推到真实 SO-101。

## Task 11 回流说明

旧 Task 11 使用过组合状态。为了与本 benchmark 的四态合同对齐，建议按下面方式解释，不改写旧记录：

| 旧状态 | 四态映射 | 结果字段 |
| --- | --- | --- |
| `VALID_SUCCESS` | `VALID` | acceptance=`PASS` |
| `VALID_FAILURE` | `VALID` | acceptance=`FAIL`，保留首个失败原因 |
| `INVALID` | `INVALID` | 不进入结果分母 |
| `NOT_RUN_*` | `PLANNED` | not_started_reason 保留原后缀 |
| 已启动但未结算 | `RUNNING` | 保留 run ID 与已写证据 |

Task 11 r8 的 no-cup 假阳性 scores 为 `0.6970663071` 和 `0.5767329931`。r9 将 `grounding_box_threshold` 从 `0.35` 改为 `0.70` 后，task_start 真杯 score 为 `0.721530556678772`，no-cup 正确返回 `TARGET_NOT_FOUND`，但 two-cup 只留下一个 score 为 `0.7670135498046875` 的候选，错误发布新 pose。因此原结论 `MODEL_CAPABILITY_NOT_MET` 仍成立。

Task 11 probe 的 `source_rgb_sha256=3881885fe5bcc69fa03c007aff0c8251f7eb214dedb0ff56f0f1bde62bd15953` 不属于本 benchmark 的正式 val 或 test inventory。对 val inventory `343fca2d5c57c1698fdf4113c68c49a264222db46e0889e7b17d8df5016cd8df` 和 test inventory `8c9a1df65a9c65e32bdfa5c187fc9a2fbff0e6e4207abd7543a026330ab5e3f9` 的 `image_sha256` 集合查询均为 0 个匹配。

以后若要把 low-floor replay 用作 Task 11 证据，每个候选至少要保留 `bbox_xyxy`、mask SHA/尺寸/像素数、`ranking_score` 与来源、`grounding_box_score`、`grounding_text_score`、`sam_quality`、规范化 label、prompt、阈值、模型 revision、图像 SHA、平台/device/dtype/offline/fallback provenance。production 候选必须能与 raw 候选一对一映射；不能只凭最终 label 字符串或最高分补配。

### 建议追加到旧账本的内容

以下仅为 proposal，没有写入 `docs/experiments/v5-t005-grounded-sam-rgbd-experiment-ledger.md`：

```yaml
benchmark_remediation_proposal:
  source_benchmark_status: INVALID
  first_bad_boundary: GROUNDED_SAM_RAW_LABEL_NORMALIZATION
  observed_low_floor_label: "plastic cup."
  observed_production_label: "plastic cup"
  effect: production_candidate_missing_from_raw_replay
  prior_task11_conclusion: MODEL_CAPABILITY_NOT_MET
  prior_task11_conclusion_changed: false
  next_experiment:
    id: EXP-TASK11-GROUNDED-SAM-RAW-TOKEN-MAPPING-R1
    method: TDD_then_new_val_calibration_then_new_sealed_test
    acceptance:
      - raw candidate retention is independent of punctuation in reconstructed text_labels
      - every production candidate maps one-to-one to a frozen raw candidate
      - no-cup yields TARGET_NOT_FOUND
      - one-cup yields exactly one fresh pose
      - two-cup yields TARGET_AMBIGUOUS and no pose
      - Mac MPS and Linux CUDA use the same prompt, revisions, thresholds and FP32 contract
  authorization: required_before_old_ledger_append_or_task11_rerun
```

## 整改条件

下一轮先用 TDD 修复 raw adapter。候选保留应依据固定 prompt 的 token positions 和 text score，不依赖 `text_labels` 重建结果里有没有句点；同时补一条 production/raw 一对一映射回归，覆盖 `plastic cup.` 与 `plastic cup`。

修复后必须从头重跑双平台 val raw 和 val-only calibration。由于本轮 held-out test 已经解封，不能继续拿它做“新方案”的正式 test；需要生成并登记一个新的 sealed test split/archive，先冻结新 lock，再一次性打开。旧 test 可以保留作已公开的诊断集，但不能再承担无偏 held-out 评测角色。

只有新一轮完整通过 Mac/Linux × 两模型 × raw/production/calibrated-or-characterization 矩阵、性能门槛和 evidence readback，才可以讨论模型排名或返回 Task 11。四场景感知通过之后，还要另做 RGB-D 深度定位、TF、`/cup_pose`、MoveIt 和四个预置点位 Pick & Place 验收。

## 证据生命周期

- Retained：本轮所有 val/test、threshold-lock、test access、模型/数据资产、source bundle、build/install/log、诊断脚本和失败工件；另保留 Linux 四点 `r769-r773`、不可变发布包 `r774-r775`、HF 发布目录 `r778`、失败的私有仓库无认证回读 `r779` 和成功的远端 commit 回读 `r780`。
- Archived：none。
- Deletion candidates：先前 ledger 已列出的失败 checkout、superseded overlay、invalid dry-run、R10/R11/R12 失败目录，以及 HF 回读 cache；全部需要用户明确授权后才能删除。
- 本报告没有删除、覆盖或重写任何 evidence，也没有修改旧 Task 11 ledger。

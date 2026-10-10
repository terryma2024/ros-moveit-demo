# Head Search Functional 40 Implementation Plan

> **For agentic workers:** 使用 `superpowers:executing-plans`，由当前执行者逐项实施并自行检查代码。用户已授权该设计内执行；不另派实现者。

**Goal:** 完成检测帧保存开关，并以实际终帧和不超过 5° 的 yaw 误差执行 40 个 Head Search 场景。

**Architecture:** 保留实际 MuJoCo/CUDA/原生控制链及安全预算，在 RGB callback 与实际检测入口分别控制保存。场景 fixture 使用现有真实 reset，功能验收关闭 paired-truth collector，独立计算最终 yaw 并保存实际图片，串行 launcher 汇总全部结果。

**Tech Stack:** ROS 2 Jazzy、MuJoCo 3.12.0、Python 3.12、pytest-xdist、已有有界 Head writer。

**Spec:** `docs/superpowers/specs/2026-10-07-so101-head-search-functional-40-design.md`

## Global Constraints

- 当前 worktree、`codex/so101-head-file-protocol-1003` 分支、唯一 E/C 证据根；保留所有已有改动。
- `save_all_rgb_frames` 为严格 bool，按用户后续要求默认 false；显式 true 仍保存逐帧 RGB。正式与 pilot 输入 false，event log true。
- 几何 yaw 误差 ≤5°；原图由当前 agent 查看，无像素或过程指标等价要求。
- 搜索、相机新鲜度、失帧、观察预算和 Stop 时间不放宽。
- 无 pick-place/hardware/dst/第二执行者/new worktree/push；不自动 commit。按用户后续授权，磁盘空间不足时可清理 `/data/work/so101-evidence` 下已核对的历史数据，保留清理记录和本轮验收证据。
- 普通全量 pytest `src/so101_demo_py/test/ -n 8`，不收集 benchmark；每轮新建 NVMe scratch，核验实际解释器及 worker 临时目录。
- 在本计划执行期间每个回合末只更新既有六项可见任务的状态，文字保持原样。

## Review Focus

- 日志总开关 false 时，新图片保存开关不能重新创建 writer 或图片 artifact。
- 空检测帧、检测异常帧要保留；尚未进入检测的过期帧不能混入检测帧集合。
- wrap 分支、相机轴、杯子实际 pose 和模型身份不能从 bbox 或 reset 声明推断。
- no-cup 不能把超时当作正常完成；中断必须发生在实际首次 SDK 返回之后、锁定之前。
- 每个正式失败都进入汇总，调试成功不替换失败；缺视觉判断的行不能自动 PASS。

## Task 1: 保存模式

**Files:** `src/so101_demo_py/src/act/head_execution_inputs.py`、`src/so101_demo_py/src/cli/head_execution_runner.py`、`src/so101_demo_py/src/adapters/act/head_live_exposure.py`、对应 composition 与普通测试。

**Interfaces:** 输入 `HeadExecutionInputs.save_all_rgb_frames -> bool`；原始 RGB 保存回调供 `HeadLiveExposures` 的实际 `detector.detect` 入口使用，使用原始 metadata 与 bytes。

- [x] 写输入默认值/非法类型测试及 callback-vs-inference 保存行为测试，覆盖 Review Focus 前两项；定向运行得到正确 RED。
- [x] 全帧 true 沿用 capture callback；false 仅在检测入口记录原图；总日志 false 两路均不绑定保存回调。
- [x] 定向 GREEN，检查 source stamp/hash/接收时间、空检测/异常/过期、默认行为与无 writer 路径。

## Task 2: 功能 fixture 与独立终态验收

**Files:** `src/so101_demo_py/src/act/head_search_campaign_scene.py`、`src/so101_demo_py/src/adapters/act/head_execution_provider.py`、`src/so101_demo_py/src/act/head_execution_inputs.py`；新增 `src/so101_demo_py/src/act/head_search_functional_acceptance.py` 及普通测试。

**Interfaces:** `prepare_case_fixture(..., paired_truth_enabled: bool=True)` 保持旧默认；输入可选 `campaign_truth_enabled` 默认 true，仅 false 时跳过可选 collector/native paired-truth。`calculate_final_yaw(model, state, actual_yaw) -> dict` 和 `classify_functional_case(case, attempts) -> dict` 独立于旧严格 classifier。

- [x] 写不创建 collector/不启用 paired truth 的 RED，以及真实杯子 pose 几何、角度分支、5°边界、缺图/缺视觉/错杯/无杯超时的 RED。
- [x] 保留 fixture reset/schema/source closure；功能模式 native truth false，不安装 V3，不修改 SDK 相机故障策略。
- [x] 实现几何真值及简化分类，缺证据 UNKNOWN；真实失败 FAIL；不改写任何原始终态或退出码。
- [x] 定向 GREEN；低照度/遮挡的配置仍保留，运行时用实际图与 pose 判定场景。

## Task 3: Head-only 中断和终态

**Files:** runner、owned search、provider；需要时新增 `src/so101_demo_py/src/adapters/act/head_campaign_camera_relay.py` 和普通测试。

**Interfaces:** SIGTERM handler 只设置 stop_requested，主执行线程走现有本地 Stop，结束时恢复原 handler。相机中断只在封闭的 fixture injection 下启用：真实 Image/Info 经拥有的 relay 交付搜索，在首次实际 SDK 返回后关闭该交付，Clock/Joint 不断。

- [x] 写 SIGTERM 安全退出、原 handler 恢复、实际 SDK 先于相机切断、无中断资源默认路径的 RED。
- [x] 实现正常 NOT_FOUND/AMBIGUOUS 原样记录；中断记录真实故障/Stop，锁定前发生才计入该场景。
- [x] 定向 GREEN，保证相机源仍真实、不重打时间戳，未重试或延长任何预算。

## Task 4: 串行 launcher 与 postflight

**Files:** 新增 `src/so101_demo_py/src/cli/head_search_functional_campaign.py` 和对应普通测试、必要安装入口。

**Interfaces:** 每 attempt 独立 execution inputs 与实际进程 receipt；每 case 原始 attempts、图片/pose/yaw 结果及视觉审核字段；40 行汇总，pilot 单列。

- [x] 写保留失败、独立身份、实际 OS 返回后 postflight、Stop/子进程失败阻断后续、缺视觉 UNKNOWN 的 RED。
- [x] 建立 serial runner；生成 session hash 私有路径，运行安装 CLI，读取最小终态/Stop，校验实际模型，导出检测原图及 final result。
- [x] 保留每 attempt 的实际逻辑字节/分配空间和剩余空间。结果不依赖逐帧 mask 或旧完整过程 audit 全通过。
- [x] 定向 GREEN；输入与模型封闭引用 readback，初末实际图片供当前 agent 审核。

## Task 5: 安装和准入

**Files:** 仅更新已有 guide 中开关说明及本计划完成项，运行证据放 C。

- [x] 重新核验精确 Python/colcon、完整 native underlay；在新 freeze copy-install 中安装修改过的 demo 包，校验安装字节与 source。
- [x] 新 NVMe scratch，普通 pytest 全量 `-n 8`；实际 `colcon test --packages-select so101_demo_py --pytest-args test -n 8`，保留 JUnit/rc/时间/tempfile worker proof，`colcon test-result` 成功。
- [x] Native source 未改则保留此前 73 PASS 的证据并核验 source/install identity；若更改则执行相应 native 完整 gate。
- [x] 重新核算 55 个新模式 attempt 的保留预算、模型 closure 和全量 scratch，核验当前空闲空间后准入；初步余量不作为通过证明。

## Task 6: Pilot、40 点与交接

**Interfaces:** 冻结原 matrix 40 cases；五种 pilot/seven attempts，正式 48 attempts。

- [x] 以 false 保存模式运行 pilot，核验实际保存集合为进入检测的帧；当前 agent 查看锁定和条件图片。
- [x] Pilot 通过后，串行执行全部正式 40 点，安全边界失败则保留后续 NOT_RUN，不启动第二栈。
- [x] 每个 LOCKED 行记录实际 yaw、真值/error、原图及 agent 判断；两杯/无杯/低光/遮挡等实际场景逐一审核。
- [x] 需要调试时独立新 ID 开启全帧保存，正式失败保留；修复后定向回归及必要新安装验证。
- [x] 汇总 40 行 PASS/FAIL/UNKNOWN/INVALID/NOT_RUN 和分场景计数、全部保留路径、归档 NONE、删除候选。更新账本、progress、partial handoff 和固定六项状态，不宣称 pick-place 或 qualification。

## 授权和实施记录

用户本轮已授权上述设计内执行，盲搜前提已通过。计划先完整呈现，再实施，不增加重复确认。计划/代码 self review、RED/GREEN、偏离理由及真实运行结果写入同一实验账本。技能默认 commit、源码目录 scratch、清理流程由用户和证据规则覆盖。

执行记录：CP-HFP-864。pilot009 五类通过；formal002 全部 40 点、48 次 attempt 已执行，37 PASS、3 FAIL，功能验收未全部通过。实际图片审核、结果与完整磁盘口径见登记证据根中的 `head-file-protocol-1003/head-search-40-20261006-001/functional-formal002/acceptance-summary.md`。调试全帧保存是条件项；本次保留已有故障证据完成离线边界核对，没有为了覆盖正式失败再开全帧重试。所有正式失败保留，qualification=false。

# Head Search 第二阶段离线审核实施计划

> 执行者：现有 GPT-6.1 Sol / High Codex，唯一写入者，inline self review。用户在 dispatch `a5db094a-be81-4e66-b183-ed2c65bbb265` 中已授权先展示本计划再实施。沿用当前 worktree 和 branch；本计划不包含 commit、push、dst、第二 agent、仿真重启、硬件或删除证据。

**Goal:** 实现并安装单 run 串行、CPU-only 的 `so101_head_search_audit`，从只读原件分别计算 integrity、search.outcome、execution_checks、stop、exit_cleanup 和 coverage。

**Spec:** [已批准的简化设计](../specs/2026-10-06-so101-head-search-stage-two-offline-audit-design.md)，46547 bytes，SHA256 `5feb7f199f9cf899063fb4c0321af04f71e3b98ca66aea917cadae19832081b8`。设计是范围和数值合同的依据。

**Architecture:** 纯磁盘 reader 先检查所有 sealed bytes 和格式，再以两遍 JSONL 流建立有界的 UUID、frame、job、motion_epoch 索引并计算 HFA-001～011。报告模块从同一份结果生成 JSON/Markdown 和指标，用最后发布的 completion 标志证明输出完整。CLI 只负责参数、调用和工具退出码，审核结果不进入生产准入。

**Tech Stack:** Python 3.12 标准库；必要 YAML 用现有 PyYAML safe loader；pytest/xdist；ament_python/colcon copied install。审核入口不导入 ROS、MuJoCo、Torch、CUDA、Ultralytics、provider 或 producer。

## 当前基线与变量

以下赋值均为本任务局部变量，不修改全局配置：

```zsh
stage2_work=/data/work/ws_moveit/.worktrees/so101-head-file-protocol-1003
stage2_e=/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m
stage2_n=$stage2_e/head-file-protocol-1003
stage2_r=$stage2_n/stage2-basic-20261006-a5db094a
stage2_python=/data/work/venvs/so101-v5-t004-perception/bin/python3
stage2_f021=$stage2_n/freezes/event-log-switch-20261006-021
stage2_f022=$stage2_n/freezes/event-log-switch-20261006-022
```

HEAD 为 `fcee299deb6953e683f81176052edd97b003b2df`；submodule 为 `495c3d6f512b5301405fc0955576bc231e344a7f`；branch 为 `codex/so101-head-file-protocol-1003`。CP-HFP-782 的日志开关已完成，18 个生产文件、4 个测试文件和 guide 等现有 dirty 工作归用户所有。`inherited-baseline.json` 已保存 78 个现有文件的哈希并核对上一轮 12 个交接引用。本阶段只修改 setup.py、新增审核模块/测试和本计划及账本，不改控制、阈值、配置、模型或日志生产端。

唯一证据根为 `stage2_e`，本阶段批次为 `stage2_r`。普通低频临时日志仍在 `/tmp/so101-debug-head-file-protocol-1003/`。新测试 scratch 必须逐次在 `stage2_r/scratch/` 下创建，保留 fsync，回读后仅列删除候选。当前 goal 工具状态 complete；保留历史，不创建冲突 goal，不擅改 budget。

F015 profile 显式绑定 source-manifest `63f3dc2b950c2d7b7be7f294db5b1b0b23184b40d55bf658a4a7d331452c17b5` 和 freeze `a5fb3450da59e2bfff452de5823efdf0bb070f71f7ff59a129b541e163a7fecc`。F022 profile 绑定 source-manifest `780f1719d52af0df73ba3eebb4c70f493bf45b0571e2620b254d6eb189bdf993` 和 freeze `25f2bec71a0fee9288f019432335ce5cb788b5ac360510bbf1f47fefb72d7c95`。二者协议均为 file-v1，普通 record_schema_version 可为 null。typed goal 位于 HEAD_PREPARED_DISPATCH_TRACE.inventory_record.typed_goal；真实 SDK/Status/服务 originals 分支按各自实际发生条件检查。未知版本仍做字节完整性检查，不能套用已知 profile 的语义通过。

on016 使用本阶段新写的 `inputs/on016-execution-index.json`，仅索引原有实际 launcher、inputs、seal、postflight 文件；原件保持不变。off017 已批准关闭日志，runroot 不存在，不能因此更改默认开关或伪造事件。

## 固定任务 1：恢复基线与离线边界

此项已在 CP-HFP-783 完成。保留 handoff 中六项可见任务原文，后续只改 status。验收依据是实际 update_plan 回执、dispatch.receipt、设计 SHA、inherited-baseline 和 original-corpus-index；主机检查仅恢复执行归属，审核器本身只读历史文件。codex tmux 保留，dst/测试/runtime 栈当前不存在。

## 固定任务 2：计划及内联自审

逐项对照设计 §2～7，重点审查：两种时钟分开、UNKNOWN 不遮盖已证实违规、合法丢弃不误判、外部路径归一化不能接受 run 内 `..`、工具 rc 与语义结果分开。自审记录写 `stage2_r/plan-inline-review.json`，保存本计划和设计的真实 SHA。先展示本计划及命令/状态矩阵，再开始任务 3；本次授权允许随后连续执行。

接口预检：reader 向 rules 提供已验证文档、事件迭代器、带 SHA/行号的证据引用和输入前后清单；rules 向 report 提供五类独立结果、每条 HFA 的适用条件、findings 和 metrics；report 向 CLI 提供最后完成标志，CLI 从 integrity 决定 rc。任意路径不确定只影响对应规则 UNKNOWN，不将整体降成误导性通过。

## 固定任务 3：只读 reader 与 HFA 规则

新增文件：

- `src/so101_demo_py/src/act/head_run_reader.py`：strict JSON、路径与只读文件句柄、流式 hash、seal/manifest/counts/引用、profile、两遍事件流、输入 readback。
- `src/so101_demo_py/src/act/head_run_audit.py`：有界索引、独立 HFA 计算、证据定位、分类结果和计时指标。
- `src/so101_demo_py/test/test_act_head_run_reader.py`、`test_act_head_run_audit.py`：使用独立手写的微型 sealed 语料及原始结构 fixture，避免生产 writer 自证。

reader API：`RunReader(run_root, execution_receipt, execution_receipt_sha256)`；`load()` 返回读取状态；`events()` 是每次重新打开的流；`readback()` 重新验证已读取文件和 run 清单。规则入口 `audit_run(reader)` 返回无 overall audit status 的 dict。所有可读文件保留原始路径、规范路径、size、SHA256 和 stat identity，前后改变标为 INPUT_CHANGED/INCOMPLETE，变动文件不支持语义 PASS。

定向 RED 先实现调用期缺 API/错误行为的真实 testcase，再运行验证失败；缺环境或 collection 错误不算 RED。随后逐边界 GREEN：

| 边界 | 定向用例及预期 |
| --- | --- |
| HFA-001 | 完整 seal PASS；缺 seal/文件 INCOMPLETE；未改 seal 的字节改变 FAIL；sealed 格式/sequence/count/refs/writer-loss 违规 FAIL；unsealed 截断只保留可证明前缀 |
| 安全读取 | 重复键、NaN/Infinity、bool 充整数拒绝；symlink/FIFO/device/escape 拒绝；外部 `..` 归一化但留原路径；输出冲突不写输入；读取中换文件/新文件 INPUT_CHANGED |
| 有界资源 | 行 1MiB、文档 16MiB、深度 64、2,000,000 events、100,000 artifacts、100,000 goal/observation；超限工具 rc3；二进制 artifact 分块 hash，不加载 RGB/CDR |
| HFA-002/003 | run 四元组、source/config/model/policy、必要 controller boot；同 UUID typed/send/accept/result/status 对齐；不同 UUID、重复发送和条件服务错配 VIOLATED；缺 PID/thread 仅 diagnostic |
| HFA-004/005 | neck joint scope、finite/向量长度/递增点时间/关节范围和终点偏差；独立匹配真实 terminal 与 advancing quiet JOINT；Image/Info/TF/joint 及接收时间晚于本次 settled floor |
| HFA-006/007 | request/result/consumption 按 job/frame/motion_epoch 匹配；过期结果不能用于 target/track/lock；总期限不重置；重观察上界取已批准 policy；合法 EXPIRED/discard/reobserve 不失败 |
| HFA-008 | 独立 bbox center 与 image dimensions/center_deadband 重算；三个不同递增 VALID 帧、同 track/epoch；按冻结 profile 检查 miss/track change/new motion epoch 重置；合法 EXPIRED/SHORT_DROP 未消费时保留已提交 lock，不增加 lock |
| HFA-009 | Stop/fault origin、真实 native close、conditional cancel/get-result/terminal、连续 quiet raw JOINT及批准 budget；ACK/raw_stop_confirmed 字段不能单独证明；缺原件 UNKNOWN |
| HFA-010/011 | actual OS/business rc、owned children/退出前 retirement、带 saved ps/graph 的 owned postflight；forced kill/leftover 违规；completion 必须有 LOCKED/notfound/refused/fault 事件支持 |

不要重做 CDR payload equivalence、轨迹 extrema/碰撞/clearance、完整 pointing、模型/source/install 闭包、全机清空或 owner 锁原子性。三类能力用 NOT_ASSESSED 明示。历史 float mono 转换保留精度区间，边界无法定案 UNKNOWN；不新增更严阈值。

每次定向命令以证据 runner 实现下面合同（runner 本身保存 exact argv/环境选择、source/test snapshots、rc/elapsed/JUnit）：

```zsh
test -x "$stage2_python" || exit 1
stage2_scratch=$(mktemp -d "$stage2_r/scratch/reader-red-XXXXXXXX") || exit 1
mkdir "$stage2_scratch/tmp" || exit 1
export TMPDIR="$stage2_scratch/tmp" TMP="$stage2_scratch/tmp" TEMP="$stage2_scratch/tmp"
"$stage2_python" -c 'import os,pathlib,tempfile; assert pathlib.Path(tempfile.gettempdir()).resolve()==pathlib.Path(os.environ["TMPDIR"]).resolve()' || exit 1
"$stage2_python" -m pytest src/so101_demo_py/test/test_act_head_run_reader.py src/so101_demo_py/test/test_act_head_run_audit.py -n 8 --junitxml="$stage2_scratch/junit.xml"
```

Expected: RED testcase 的实际断言或明确缺 API 调用失败，rc1；GREEN 全部适用用例 PASS/rc0。每轮 scratch 新建；两份测试属于同一 demo 模块，不能与 Teleop 混收集。第一次未创建的后续测试文件不传入 pytest，否则 collection 失败不能算 RED。

## 固定任务 4：报告、CLI、发布与权限

新增 `src/so101_demo_py/src/act/head_run_audit_report.py`、`src/so101_demo_py/src/cli/head_search_audit.py`、`test_act_head_run_audit_report.py`、`test_cli_head_search_audit.py`，setup.py 新增唯一 console script `so101_head_search_audit = so101_demo.cli.head_search_audit:main`。

报告合同：audit_schema_version=1/ruleset_id=head-file-postrun-basic-v1；integrity、search.outcome、execution_checks、stop、exit_cleanup、coverage 分项；不输出 overall audit PASS/FAIL、qualification 或 episode 准入。rule verdict HOLDS/VIOLATED/UNKNOWN/NOT_APPLICABLE；先保留 VIOLATED，再归 UNKNOWN。findings 带稳定 code/category、受影响字段、原件 SHA、行号/event sequence、关联 ID、expected/observed/calculation。Markdown 和 stdout 使用同一结果，明确 rc0 时可能 execution/stop FAIL。

RED/GREEN 包括 rc0/1/2/3 真正边界、sealed 语义违规仍 integrity PASS/rc0、无动作才允许 Stop NOT_APPLICABLE、失效输入不支持 PASS、未知 profile、原子发布中断/fsync 错误没有 completion。仅允许新 output-root；不覆盖已存在目标，不落到任何 run/外部依赖所在目录内，不写输入。输出 regular files 用临时文件/fsync/replace/directory fsync，`audit-completion.json` 最后发布，列前四文件 size/hash。

权限回归：新解释器拦截 runtime import、socket/network、subprocess、动态插件、在线 /proc/ROS/GPU 访问，实际运行 CLI/完整微型语料；审核实现仅纯磁盘。测试拦截为 oracle，不允许审核器捕获后静默继续副作用。所有 producer/config/policy baseline 哈希不变。

```zsh
"$stage2_python" -m pytest src/so101_demo_py/test/test_act_head_run_audit_report.py src/so101_demo_py/test/test_cli_head_search_audit.py -n 8 --junitxml="$stage2_scratch/junit.xml"
```

Expected: 所有报告/权限/退出码边界 PASS/rc0；每轮仍需此前未存在的新 scratch 和 tempfile proof。工具 rc3 是不完整工具运行，不冒充 HFA FAIL。

## 固定任务 5：冻结、安装、正式入口和真实/变造语料

最终验收使用 `stage2_r/freeze-008`。初始计划的 freeze-001 和随后五个自审版本保留；修复审核器后采用新目录，不覆盖旧安装。冻结步骤：独立复制 demo package、记录 source manifest/HEAD/dirty/test/spec/plan SHA；非 symlink install。直接依赖的 native/Teleop 使用现有 F021/F022 完整 underlay，先检查每个 package setup/local_setup 和实际 Python 原点。colcon 新 build/install 只选 demo 时必须有依赖闭包，构建环境失败和源码失败分开记。

```zsh
source /opt/ros/jazzy/setup.zsh
source "$stage2_f021/install/local_setup.zsh"
source "$stage2_f022/install/local_setup.zsh"
cd "$stage2_r/freeze-008/source"
/usr/bin/colcon --log-base "$stage2_r/freeze-008/log" build --base-paths src/so101_demo_py --packages-select so101_demo_py --build-base "$stage2_r/freeze-008/build" --install-base "$stage2_r/freeze-008/install" --allow-overriding so101_demo_py
```

Expected: build rc0；安装 `freeze-008/install/so101_demo_py/lib/so101_demo_py/so101_head_search_audit` 存在且可执行，四模块字节与 frozen source 相同，imports 来自这个 install。现场已验证精确 P 没有 colcon_core，使用 `/usr/bin/colcon`；build/package 实际解释器和精确 P 分别保存 tempfile proof，不安装全局依赖。

安装审核器的正式 CLI 以 exact P 调用新 console script，PYTHONPATH 仅新 demo install（审核运行不 source runtime overlay，不导入 runtime）；先执行 `--help`/rc0，随后精确调用以下五行：

```zsh
stage2_cli=$stage2_r/freeze-008/install/so101_demo_py/lib/so101_demo_py/so101_head_search_audit
"$stage2_python" "$stage2_cli" --run-root "$stage2_n/runs/hfp1006-astra-normal013" --execution-receipt "$stage2_n/astra-fixes-20261006-001/normal013-G-acceptance.json" --execution-receipt-sha256 4850cb2e666b11896aafa7c228802166ecd0383e3a30fbf55383802fdbb70d30 --output-root "$stage2_r/reviews/hfp1006-astra-normal013/audit-008"
"$stage2_python" "$stage2_cli" --run-root "$stage2_n/runs/hfp1006-astra-camera006" --execution-receipt "$stage2_n/astra-fixes-20261006-001/serial-probes/hfp1006-astra-camera006/acceptance.json" --execution-receipt-sha256 f85fce11dbf35a193653baa8de981eb368c2a4601354670625fc67c9cfcb224d --output-root "$stage2_r/reviews/hfp1006-astra-camera006/audit-008"
"$stage2_python" "$stage2_cli" --run-root "$stage2_n/runs/hfp1006-astra-feedback005" --execution-receipt "$stage2_n/astra-fixes-20261006-001/serial-probes/hfp1006-astra-feedback005/acceptance.json" --execution-receipt-sha256 719250a6f240651872a0dbdb0fd12a356dd67f37a6c50bbf59a09726a51d100d --output-root "$stage2_r/reviews/hfp1006-astra-feedback005/audit-008"
"$stage2_python" "$stage2_cli" --run-root "$stage2_n/runs/hfp1006-astra-unknown006" --execution-receipt "$stage2_n/astra-fixes-20261006-001/serial-probes/hfp1006-astra-unknown006/acceptance.json" --execution-receipt-sha256 fe05bf20ba3906ec847f896d67cfd54f41e64efb9cdb329fdf44c4e4400f9eec --output-root "$stage2_r/reviews/hfp1006-astra-unknown006/audit-008"
"$stage2_python" "$stage2_cli" --run-root "$stage2_n/runs/hfp1006-els-on016" --execution-receipt "$stage2_r/inputs/on016-execution-index.json" --execution-receipt-sha256 61a86877039a26e63153acf6e97ddfa9369d50a7540794e553737359b41ba3ae --output-root "$stage2_r/reviews/hfp1006-els-on016/audit-008"
```

实际 runner 存完整 argv、executable/Python/module origins/auditor digest、stdout/stderr/elapsed/OS rc 和五份报告回读；seal、全部 artifacts、必要外部文件在读取前后按 size/hash/identity/run list 对比。不是重哈希整个 evidence root。若修复审核器，创建新的 freeze/audit 目录；保留失败尝试，不覆盖完成报告。

| 输入 | integrity | search.outcome | execution_checks / stop / exit_cleanup | audit OS rc |
| --- | --- | --- | --- | --- |
| normal013/on016 | PASS | LOCKED | 证据足够则各 PASS；确实缺字段对应 UNKNOWN 并说明 | 0 |
| camera006/feedback005/unknown006 | PASS | FAILED | 原始受控故障不等于合同违规；逐规则验证，Stop/退出足够则 PASS，缺口 UNKNOWN | 0 |
| 独立副本缺 seal/必要原件 | INCOMPLETE | 只保留可证明部分，必要结论 UNKNOWN | 已证实违规仍保留 | 2 |
| 独立副本字节篡改、原 seal 不变 | FAIL | 变动文件不能支持语义 PASS | affected UNKNOWN/FAIL | 1 |
| 独立副本语义违规且重新 seal | PASS | 由事件独立判断 | execution_checks 或 stop FAIL 必须在 JSON/MD/stdout 明示 | 0 |
| 合法 expired→有限 retry/缺 PID-thread 诊断/缺全模型闭包 | PASS | 按原始消费证据 | 保留适用 HOLDS，不因已移出能力失败 | 0 |
| 已批准 logging-off off017 没有 run | INCOMPLETE | UNKNOWN | 必要原件缺失 UNKNOWN；N/A 仅有分支依据 | 2 |
| 输出冲突/越权路径/资源上限/发布失败 | 无有效完成发布 | 不作通过声明 | AUDIT_NOT_COMPLETED | 3 |

独立变造语料在 `stage2_r/derived/` 用 regular copy，无 writable hardlink；保存 derived_from 原始 refs、精确变更及 expected matrix。缺 seal、缺文件、原 seal 下的 byte mutation、重 seal wrong UUID/stale consumption/false lock/Stop budget 超限分别测试。正例含合法丢弃与 bounded reobserve、thread/PID 缺失、无模型/全 source 闭包和无关 host 服务条目。重复运行同原件时，仅 audit 元信息可变，语义结果/统计/coverage 相同；不新增 semantic digest 合同。

## 固定任务 6：完整普通门禁、内联自审及交接

本阶段影响 demo 的审核模块和 setup 安装；Teleop/native/生产执行器字节不变，不重复其已通过的旧门禁。审核模块定向通过且集成冻结后，跑一次 demo 完整普通 test/ xdist8 和实际 demo package gate/test-result。两轮分别新 scratch；24 逻辑 CPU 使用 8 worker，记录内存、并发负载、worker tempfile proof，不能降 worker 或收集 benchmark。

```zsh
cd "$stage2_work"
"$stage2_python" -m pytest src/so101_demo_py/test -n 8 --junitxml="$stage2_scratch/junit.xml"
cd "$stage2_r/freeze-008/source"
/usr/bin/colcon --log-base "$stage2_r/freeze-008/test-log" test --base-paths src/so101_demo_py --packages-select so101_demo_py --build-base "$stage2_r/freeze-008/build" --install-base "$stage2_r/freeze-008/install" --pytest-args test -n 8
/usr/bin/colcon test-result --test-result-base "$stage2_r/freeze-008/build" --verbose
```

Expected: 普通 gate 与 package test/test-result 各 rc0、零 fail/error；旧 skip 原因保持，新增纯审核边界不整模块 skip。colcon test 工作区采用已验证与 frozen source 等字节的实际 worktree，若 copied-tree 丢失 repo-layout fixture 环境，先恢复仅测试上下文依赖并记录，不能把未执行边界当 RED。每个实际解释器保存 tempfile proof；不得用 source gate 代替 installed-origin 证据。

最终独立于实现过程再做一遍作者 inline review：逐规则证据够不够、格式/路径 TOCTOU、输出碰撞、阈值来源、条件服务、浮点边界、三帧锁独立 centererror、Stop原件与owned退出、failure 优先级、输入变更、所有 HFA coverage、rc0语义FAIL可见、未评估能力和纯离线导入。发现实质问题补有意义的 RED/GREEN，再只重跑受影响定向及当前完整门禁；不掩盖失败。

最终交接写 `stage2_r/final-handoff.json`、`inline-self-review.md` 和 `retention.json`；回读 refs 真实 SHA/size，baseline producer/config/policy 保持不变。更新账本 latest checkpoint/next NONE_STAGE_TWO_SCOPE_COMPLETE；六个可见任务只更新真实状态。报告 retained 批次、archived NONE、未删除 scratch 候选及 NOT_ASSESSED 能力。历史 normal014 根因、阶段一完整性、Head/ACT 资格和完整 pickplace 均不能由本阶段宣布完成。


最终原件核对发现，五份真实 postflight 的 ps/graph 只有 argv、rc 和耗时，没有实际采样起始 UTC ns。原始 OS 退出时间已保存，但 phase 标签和文件 mtime 不能证明采样晚于退出。因此最终预期将这五例及其复制语料的 exit_cleanup 改为 UNKNOWN；其余分项和 rc 合同不变。这个覆盖缺口交给后续阶段一的外层证据协议修复，本次不修改或补造原件。完整原始采样时间存在时才核对退出后顺序，缺失为 UNKNOWN，明确的时间矛盾为 VIOLATED。

# Head search 调查接续记录（2026-10-10）

用户已要求暂停调查，保存文档与代码，再将 `codex/so101-head-file-protocol-1003`
合并到 `codex/so101-act-data-0917a` 并推送。调查目标当前为 `paused`。
Head search 稳定性尚未解决。恢复时先读本文和任务账本的 `CP-HFP-1028` 至 `CP-HFP-1030`，
不要重启旧批次。后续调查可能在另一台机器进行，先完成下方的跨主机恢复检查。

## 当前停止位置

最新批次是三次无注入、每次 120 秒的 `FULL_RESTART` 保持测试。
第一轮完成了 120.000065023 秒，但原始检查返回 `TimingPeriod`，批次随即停止。
第二、三轮均为 `NOT_RUN`。三个控制器的保持窗口更新数都是 59,999，原始要求是至少 60,000。

在保持开始约 107.81435 秒处，arm、gripper、neck 共同从仿真时间 108.546 秒跳到
108.550 秒。每个控制器恰有一次 4 ms 更新周期，其余均为 2 ms；没有 0 ms 周期。
三个原始流的记录数、写入数一致，没有 overflow、IO fault 或耗时达到 2 ms 的记录。
原始封存的 owner `CLOCK` 记录在这一邻域也缺少 108.548 秒。

这些事实说明正常运行仍会漏掉一次控制时间点。当前批次关闭了可选时钟和退出观察器，
因此尚不能分辨是物理步、时钟发布、DDS/ROS 时钟传递还是控制循环唤醒造成的。
不能把 owner 没看到一个时钟值解释成物理步没有发生。

原始 Stop、native close ACK、四文件封存校验和三个 stack 子进程的 rc0 均通过。
外层检查确认 owner、跟踪的子进程均已退出，ROS domain 228 的 graph 为空。
Guardian 没有取消、强制清理或内部错误；rc1 是测试失败的正常返回。
当前没有这项任务的运行中 stack 或测试。

## 已验证修复及其范围

隔离副本中，MuJoCo 控制循环在 `use_sim_time` 下把同一次真实采样时间传给
`read/update/write`；固定版本 `controller_manager` 在模拟时钟路径也使用调用者传入时间
计算 period 和触发 native controller。非模拟时钟路径保持原行为，公共 ABI 没有改变。
没有钳制 period、伪造时间戳或放宽原始时序判据。

修复前后的同一真实时钟推进诊断已完成。修复前在指定的实际调度边界产生共同的
4 ms → 0 ms；修复后原始 120 秒检查通过，三个 native 流全为 2 ms，Stop 和封存也通过。
独立审查接受了这项局部因果修复。但最新无注入失败说明它没有覆盖循环间真实时钟跳步。

修复及新 nominal harness 仍在隔离的 `C` 副本中，尚未提升到仓库生产源码或共享安装。
本次代码提交保存现有仓库工作，并附上隔离补丁、脚本和证据摘要的原样快照。
快照脚本保留原始绝对路径，仅供接续与核验；不要直接从快照目录运行它们。

## 测试与剩余验收

| 验证 | 已记录结果 | 解释 |
| --- | --- | --- |
| 实际 CM/native 回归 | 9 PASS | 包括真实丢步、回退/复位和非模拟时钟边界 |
| 共用生产 dispatch 回归 | 15 PASS | traced/untraced 共用实际头文件，保留异常和探针拒绝行为 |
| 四个隔离包的 CTest | 540 leaf cases，537 PASS、3 SKIP | 37 个 CTest 包装项另计；不是 577 个独立用例 |
| 隔离普通 Python 门禁 | MuJoCo 116 PASS、3 SKIP；CM 2 PASS | xdist8，精确解释器与 NVMe scratch 已记录 |
| 新 nominal contract | 68 PASS | 旧边界测试适配器 41 FAIL、27 PASS；只是离线比较，不是旧 nominal 生产运行 |
| 修复后的注入诊断 | 120 秒 PASS | 单独的因果证据，不计作 nominal 成功 |
| 无注入 nominal3 | 1 FAIL、2 NOT_RUN | 已停止，不能重跑或替换成成功记录 |
| 原先 live20/case9 | 6 PASS、1 FAIL、13 NOT_RUN | 14 attempts；旧失败与结论保留 |
| 新 live20、fresh40/48 attempts、视觉与模型比较 | 未执行 | 正常保持稳定后按冻结方案继续 |
| 根仓普通测试既有基线 | 110 FAIL、66 ERROR、152 SKIP；8,522 PASS | 8,850 cases，既有 176 个失败/错误未豁免，不声称普通包全绿 |

本次暂停保存和合并不启动新实验，也不改变上述验收结论。
旧 evidence-close 超时和历史最初异常的具体原因仍未确认。

## 证据位置与版本

登记的持久根为 `/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m`。
普通低频日志根为 `/tmp/so101-debug-head-file-protocol-1003/`。

下面两个变量是路径缩写，便于接续时使用；定义变量本身不会启动任务。

```bash
TASK_PARENT=/data/work/so101-evidence/act-data/20260930-antzb-head-search-krIv681m/head-file-protocol-1003/head-camera-yolo-optimization-20261009-001/optimization-fix-20261009-001/protocol-implementation-ivicy38d
COHERENT_COPY=$TASK_PARENT/clock-diagnostic-yrcfff3b/probe001/exit-probe001/coherent-repair001
```

| 名称 | 路径 |
| --- | --- |
| `C`，隔离修复与 harness | `$COHERENT_COPY` |
| `R`，原始产品与 native 安装 | `$TASK_PARENT/stop-witness-isolation-fpfvhl3p` |
| 修复前实际诊断 | `$TASK_PARENT/clock-diagnostic-yrcfff3b/probe001/exit-probe001/checkpoints/holding001` |
| 修复后实际诊断 | `$COHERENT_COPY/checkpoints/holding001` |
| 最新失败批次 | `$COHERENT_COPY/checkpoints/nominal-holds001` |
| 最新原始 native 流 | `$COHERENT_COPY/checkpoints/nominal-holds001/001/output/controller-records` |
| 原始封存 | `$COHERENT_COPY/checkpoints/nominal-holds001/001/runtime` |
| 原始失败概要 | `$COHERENT_COPY/checkpoints/nominal-holds001/001/native-failure-summary.json` |
| 具体启动审查 | `$TASK_PARENT/clock-diagnostic-yrcfff3b/review/coherent-nominal-launch001` |
| 暂停发布、目标工作区保存与推送回执 | `$COHERENT_COPY/publication-pause-20261010-001` |

仓库中的小型快照目录为
[so101-head-file-protocol-1003-pause-20261010](so101-head-file-protocol-1003-pause-20261010/)。
`snapshot-manifest.json` 保存每个原始路径、快照路径、字节数和 SHA256。
高频原始流、构建、完整复制安装和 scratch 留在持久证据根。

本轮运行的源码基线是 `de70d83ed1e599c5dbb26843e06bd1af574f0a93`，
MuJoCo 子模块基线是 `495c3d6f512b5301405fc0955576bc231e344a7f`。
本次保存提交会前移 Git HEAD，原始运行 provenance 仍指向当时基线和冻结文件哈希。
CM 固定版本为 4.45.2；实际修复 DSO SHA256 为
`0aac6debf9a82b06543a3a7218484b2180ca173492265fe43e32191cccc7b020`。
Owner Python 是 `/data/work/venvs/so101-v5-t004-perception/bin/python3`，测试 Python 是
`/usr/bin/python3`；本轮 ROS_DOMAIN_ID 为 228，GZ_PARTITION 为 `hfp1010-nominal-001`，
generation 为 109960001。下一轮需重新验证具体路径与环境，不能直接照抄旧配置。

## 在另一台机器接续

Git 分支保存仓库源码和小型快照；高频原始证据、模型权重、虚拟环境与复制安装不在 Git 中。
原机的 `C/R` 路径是历史坐标。新机器若没有这些文件，不能用不存在的路径或旧 SHA 声称
原始安装已恢复。也不能直接复制 Linux `.so` 到 macOS，或搬运原机 venv 作为新环境。

为避免仅凭补丁无法复原隔离副本，快照目录还保存了 `isolated-build-source.tar.gz`：
包含完整隔离 overlay 源码、固定的官方 ros2_control 4.45.2 源码、实际 CM/native 回归、
旧 dispatch 对照头文件和 `R` 的 native 包源码。`portable-source-manifest.json`
保存包 SHA256、每个文件的 SHA256 和字节数，打包后已逐项读回核验。
Git 提交中的 Python 源码也要与原机 `R` 的冻结来源核对，不能默认为旧安装的逐字副本。

原机另外准备了 `C/publication-pause-20261010-001/portable-evidence.tar.gz` 和
`portable-evidence-manifest.json`。这个迁移包保留最新修复前/后真实诊断、失败 nominal3
及两行 `NOT_RUN` 输入、独立审查、隔离门禁与 harness，以及十个受控引用和模型。
它不包含完整历史任务或编译安装，也没有上传到 Git。需要完整旧审查链时，再迁移原始
登记根中的对应文件；不要把最小迁移包当成全部历史。恢复前先从原机取得迁移包和清单。

具体恢复顺序见[跨主机接续指南](../guides/so101-head-stability-resume-on-another-host.md)。
迁移包的完整文件清单也随本次提交保存，实际证据包仍需从原机取得。

## 恢复后的第一步

先验证原始 seal、完整 native 流、实际进程身份和冻结来源，确认旧批次已终止。
在新证据目录中写一条有限的诊断计划，区分真实物理 commit、publisher admission、
ROS 时钟传递和控制循环起点。优先解释这一次共同的 4 ms 跳步，保留原始
60000 更新、2 ms 周期、1 s Stop/finish、native grace 和完整证据判据。

这份记录没有批准全局步协调器、补造时间戳、放宽门槛或自动重复直到变绿。
新的修改先建立会失败的边界回归，再做隔离构建、包级门禁和独立审查。
后续 inline 执行的用户授权保留；调查要等用户明确恢复。

## 保留内容

所有成功、失败、setup-invalid 和 `NOT_RUN` 记录继续保留。未迁移归档，未删除证据。
已读回的测试 scratch 与第一轮已退出的 IPC 仅列为可删除候选；后两轮预备输入和 IPC 也保留。
52 个自动生成的 `head-model-*` 权重副本以及两个根目录临时接续便笺保留在原工作区，
不作为源码发布。目标分支已有未提交的用户工作另行保存，合并时保留它们。

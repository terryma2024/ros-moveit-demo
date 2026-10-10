# Head Search 最终结果验收与检测帧保存

## 目标与执行前提

搜索结束时，head camera 能看见靠近中央的真实杯子，并返回 head 实测角度。该角度与实际场景中杯子位置、颈部轴和相机安装关系推导的居中角度相差不超过 5°。

用户要求先用 on016 的安装链验证初始看不见杯子的单杯搜索。HS40-030 已完成：初始图片看不见杯子，前两次 CUDA 检测为空，随后粗转发现杯子，精调后锁定。实测角度 43.5113°，真值 44.4213°，误差 0.9100°。原始终帧已由当前 agent 查看，杯子靠近中央，部分被机械臂遮挡。原生 Stop 确认、主进程和六个子进程退出均通过。证据在已登记根下的 `head-file-protocol-1003/head-search-40-20261006-001/preliminary/blind-single002/`。

## 最终验收

| 场景 | 预期结果 |
|---|---|
| 单杯、三个方向、干扰物、低照度、部分遮挡 | 正确杯子 `TARGET_LOCKED`；实际终帧看得见杯子且靠近中央；实际 yaw 与几何真值误差 ≤5° |
| 两个杯子 | `TARGET_AMBIGUOUS`，无锁定 |
| 没有杯子 | 实际完成有界搜索，返回 `TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL`；超时或观察预算耗尽不能替代完成搜索 |
| 相机中断 | 在首次实际 SDK 返回后切断 Image/Info 的搜索侧交付，在锁定前安全停止；独立新 attempt 恢复后锁定 |
| Stop 后重新获取 | 首次实际 SDK 返回后向本次拥有的执行进程发送 SIGTERM，在锁定前安全停止；独立新 attempt 锁定 |

保存实际终态、head 实测 yaw、实际 SceneState 中的杯子 pose、已加载模型身份，以及原始终帧及当前 agent 的视觉判断。几何计算使用独立 MjData 和 `mj_forward`，不调用 `mj_step`。相机右轴与杯子几何中心的投影为零时求得居中 yaw，选择与结果相邻的正确角度分支，检查杯子位于相机前方。姿态来自实际状态，不能用 reset 目标替代。状态没有精确对齐终帧时保留两侧状态并说明时间关系；杯子水平位置不稳定、模型身份不符或缺少图片时标为 UNKNOWN。

当前 agent 必须实际查看图片。自动化程序只能给出数值结果，不能替 agent 写视觉 PASS。两杯、无杯和中断也须保留支持场景成立的实际图片或状态；离线预渲染只能帮助准备场景。

图片不要求像素级相等，也不要求逐帧实例 mask、渲染状态配对或过程指标一致。过程 event log 用于调试；它不再是最终功能判据。安全 Stop、独立运行身份和进程所有权仍是运行条件。

## 保存开关

执行输入增加可选布尔字段 `save_all_rgb_frames`，按用户后续要求，省略时为 `false`，只保存检测帧。旧输入若需保存逐帧 RGB，必须显式设置 `true`。`event_log_enabled=false` 继续具有优先级，不创建 Head writer、图片 artifact 或新日志工作线程。

当 event log 开启而 `save_all_rgb_frames=false` 时，相机回调继续处理业务原始输入和故障检查，但不保存其逐帧 RGB。只有实际进入 `detector.detect` 的原始 RGB 才保存；空检测也保留，以便分析无杯和粗搜索。因过期、替换或未满足停止条件而没有进入检测的帧不保存。保留原始 source stamp、接收时间、payload digest，禁止用重渲染或后续帧替代。检测抛错时也尽量保留已进入检测的那帧。显式开启全帧保存时，避免重复写同一检测帧。

图片保存使用现有有界 writer，不能创建新队列或后台线程。关闭逐帧保存会去掉未检测帧的图片 artifact 入队和磁盘写入；业务原本需要的消息解析、校验和 hash 仍存在，不能宣称整个相机路径零消耗。

## 场景与串行运行

沿用已冻结的 40 个 case、10 类条件、各 4 个 seed 和已有 anchors；中断类各有两个独立 attempt，共 48 个正式 attempt。另做五个 pilot：单杯、两杯、无杯、相机中断、Stop 后重新获取，共七个 pilot attempt。历史盲搜不计入 pilot 或正式 40 点。

场景保留已实现的封闭 MJCF byte closure、真实 reset 和完整 pose readback。新增功能模式关闭可选逐帧 paired-truth native 发布和 Python collector；无需 V3 publication identity/raw RCL take。原 V1/V2 默认行为、代码和历史证据保留。场景变化仍须由真实状态与图片确认，不能以配置文件存在代替。

每个 attempt 使用独立 run/session/epoch/generation、私有目录和证据路径。一次只运行一套拥有的仿真栈，结束后采样真实 OS 退出码、Stop 确认、子进程身份及 ROS graph，再开始下一次。失败结果保留，调试可新建 attempt 并开启逐帧保存，但不替换正式失败结果。发现未确认的 Stop 或未退出的子进程时停止后续发起。

初始磁盘预算按新检测帧模式重新计算，包含七个 pilot、48 个正式 attempt、copy-install 和两轮普通包门禁 scratch；旧约 100 GB paired-truth 下限不再适用。预算及每轮实际消耗记在 campaign receipt。逐轮复核空闲空间，调试全帧运行另行预留。按用户后续授权，磁盘空间不足时可清理 `/data/work/so101-evidence` 下已核对的历史数据；优先清理已结束测试的临时 fixture，保留清单、测试报告和本轮验收证据。

## 范围

当前 GPT-6.1 Sol High 在现有 worktree 和分支执行，代码评审自行完成。设计按仓库要求由现有 Astra reviewer 只读审查。搜索结束即停止，不执行 pick-place，不操作硬件、不启动 dst、不创建第二执行者或新 worktree、不 push、不重启共享服务。证据清理限于上述用户授权的范围。

固定六项可见任务文字不变；其中旧“逐帧实例真值”文字由本设计的最终 pose/图片判据替代，详细变更记录在账本。

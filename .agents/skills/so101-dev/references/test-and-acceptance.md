# 修改、测试与验收

## 导航

- [修改前](#修改前)
- [构建与 package 测试](#构建与-package-测试)
- [运行时测试阶梯](#运行时测试阶梯)
- [按状态验收](#按状态验收)
- [视觉验收](#视觉验收)
- [最终报告模板](#最终报告模板)

## 修改前

1. 记录本地根仓、`moveit-demo` 子模块和 ai-station workspace 的 dirty files。
2. 将本轮根因绑定到一个拥有该行为的最小代码边界。
3. 写自动化回归测试并运行到预期失败。若缺陷只能 live 重现，先保存失败复现、退出码和前后状态断言，再补最接近边界的单测/launch contract。
4. 修改范围只覆盖根因。不要顺手格式化、重构或修复无关问题；不要运行 `ament_uncrustify --reformat`。

测试不是为了覆盖实现细节，而是证明机器人边界条件。例如：

- state success 后必须具有相应 attachment evidence；
- joint trajectory success 必须与目标 joint set 和反馈契约一致；
- detach 后 Gazebo 与 Planning Scene 必须收敛到各自正确状态；
- warning 的影响判断要由调用路径和参数 provenance 决定。

## 构建与 package 测试

在 ai-station 的 ROS-only zsh 中：

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo_cpp --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select so101_gazebo_demo_cpp \
  --event-handlers console_direct+
colcon test-result --verbose
```

若修改 CMake/install rules、launch/config 安装内容，或怀疑缓存污染，使用 `--cmake-clean-cache` 重新构建。不要用全 workspace build 掩盖 package 级失败。

验证运行产物：

```bash
ros2 pkg prefix so101_gazebo_demo_cpp
ros2 pkg executables so101_gazebo_demo_cpp
stat install/so101_gazebo_demo_cpp/lib/so101_gazebo_demo_cpp/pick_place_state_machine
```

定向测试先行，包级测试随后。精确测试名从当前 `CMakeLists.txt`、`colcon test-result --all` 或 build 目录发现，不从旧记录猜。

## 运行时测试阶梯

按风险从低到高：

1. 单元/contract test；
2. `run_mode:=dry_run` 的全状态与失败恢复；
3. `run_mode:=plan_only` 的规划证据；
4. headless Gazebo/MoveIt live test；
5. GUI 仿真 execute；
6. 真实机械臂，仅在用户明确授权和硬件安全门控后。

常用入口需先 `--show-args` 复核当前版本：

```bash
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py --show-args
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py \
  run_mode:=dry_run start_simulation:=false
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py \
  run_mode:=plan_only start_simulation:=true headless:=true \
  simulation_session_id:=<unique-id>
```

execute 调试时先用 `stop_after:=<STATE>` 将动作缩到首个失败边界。不要一开始反复运行完整 pick-place。

## 按状态验收

| 状态/边界 | 最小运行时证据 |
|---|---|
| MOVE_ABOVE_OBJECT / DESCEND / LIFT / PLACE / RETREAT | plan 有效；execute result 成功；目标 joints 完整；`/joint_states` 和 TCP 有符合方向的前后变化 |
| CLOSE/OPEN_GRIPPER | gripper action result；夹爪 joint feedback；视觉开合状态 |
| ATTACH_GAZEBO | attachment topic/state；Coke pose 随末端运动；必要时 contact evidence |
| ATTACH_MOVEIT | Coke 从 world collision 集合进入 attached 集合；attached link/touch links 正确 |
| DETACH_GAZEBO | 物理 detached；Coke 不再随末端；等待稳定后读取 pose |
| DETACH_MOVEIT / SYNC_WORLD_OBJECT | attached 集合移除；world object 以最终 Gazebo pose 恢复 |
| DONE | 上述受影响边界通过；退出码正确；最终 Gazebo/RViz 画面与状态查询一致 |

恢复路径还要验证：失败后只撤销已产生的副作用，最终状态可解释，错误路径返回非零退出码。

## 视觉验收

截图与 GUI 控制路由必须使用 `$gui-capture`，同时保留本文件的 SO-101 数据/视觉联合证据门。

1. 运行本轮 build 对应的 GUI stack。
2. 在加载 `~/gui-env.zsh` 和正确 ROS overlay 的 tmux shell 中运行 `ros2 run so101_teleop tile_ai_station_guis.py`，要求 `LAYOUT_OK`：RViz 左、Gazebo 右，各约占工作区 50%。
3. 从本轮 `mktemp -d` 证据目录定义 `capture_evidence_dir`，运行 `.agents/skills/gui-capture/scripts/capture-gui.sh --local --desktop --output-root "$capture_evidence_dir/captures"` 保存 baseline screenshot，并实际检查 manifest 声明的新鲜 `desktop.png` 已呈现左右分屏、无遮挡且两侧场景可辨认。
4. 使用 CUA 时按 `snapshot -> action -> fresh snapshot`；调整窗口内部视角后再次确认分屏没有被破坏。
5. 完成本轮动作后再次按 `$gui-capture` 路由生成新鲜截图。
6. 实际打开新的 desktop/RViz/Gazebo 图片，描述：机械臂姿态、夹爪开合、Coke 初末 pose、是否穿透/掉落、Planning Scene 显示是否一致。

截图必须与数据状态共同验收。至少保留一个数值证据，例如 Coke 6D pose 或关节/TF 前后差值，防止相机角度造成误判。

## 最终报告模板

```text
Root cause: CONFIRMED | NOT CONFIRMED
First bad boundary:
Evidence:
Change:
RED test:
GREEN/package tests:
Runtime command and exit code:
Gazebo proof:
MoveIt proof:
Controller/joint/TF proof:
Visual proof and screenshot path:
Preserved user changes:
Remaining risks / next exact command:
```

任何空白项都表示不能笼统宣布“完整修复”。

## Physical outcome acceptance addendum

Policy 仍含 `CALIBRATION_REQUIRED` 时不得宣称 live success。记录 runtime provenance、隔离的
`ROS_DOMAIN_ID`/`GZ_PARTITION`/overlay、cleanup ownership，以及独立 Gazebo pose/support contact、
MoveIt shadow/detachment/world sync、controller health 和 fresh GUI screenshot evidence。必须有
five consecutive valid runs；中间随机样本作为 bounded distributions 保留，不要求完全相同。
最终失败必须先保存 observed outcome，再开始独立 reset transaction。

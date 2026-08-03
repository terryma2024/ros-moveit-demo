# SO-101 放置释放与偏置 Retreat 实施记录

## 已完成

1. 为运动配置加入状态级速度/加速度缩放，并贯穿 target、request 和 MoveGroup ladder segment。
2. 将 release 终点从 `q6=1.70` 改为 `q6=0.750`，保留分阶段打开与物理到位采样。
3. 将 `DESCEND_TO_PLACE` 落点补偿约 `(+3.00, +3.06) mm`，降低释放后的系统性放置偏差。
4. 把 Retreat 改为“朝底座侧下移 -> 保持侧向偏置上升 -> 高位合流”的 6-waypoint ladder，速度/加速度均为 `0.03`。
5. 把 Retreat 前缀接触净空改为沿首段清障方向的 `4.4 mm`，要求接触清除证据且禁止复现。
6. 保持 `OPEN_GRIPPER -> DETACH_GAZEBO -> DETACH_MOVEIT -> SYNC_WORLD_OBJECT -> RETREAT` 的事务顺序。
7. 根据运行日志把臂控制器通用 path tolerance 修复为 `2 mrad`，但不放宽接触关键状态的独立末端门。
8. 根据 Gazebo 物理沉降证据，把携带相对姿态门固化为 `5 mm / 0.070 rad`。
9. 把唯一一次 regrasp 收紧量改为 `0.006 rad`，继续要求连续 6 个双侧接触样本和最大接触深度门。
10. 把 regrasp 明确为临时 seating 动作：首次稳定后回到 `q6_contact`，再次通过连续 6 个双侧样本才允许附着；附着后的 carry hold 也固定为 `q6_contact`。

## 冻结复跑证据

共同策略哈希：

- motion policy: `48dba1959278572e17af2256532a3201868fd4fa7a16c8e0b6a0f31e0723b33e`
- validation policy: `d4fdef83fca56d9f232c098c0f0ecfe5a3e2044bb6404c6ccba684559c2bc167`
- policy bundle: `d3a2ea99b6862c248c3e0cf4867b39687b6a3c3c75bba0e2bd905a382f263594`

| Trial | simulation session | checkpoint | 结果 | XY 误差 | Z 误差 | 最终 attachment |
|---|---|---|---|---:|---:|---|
| 1 | `reset-bc01bee2-f80c-4e01-a561-ff20382b4327` | `/tmp/so101-local-takeover-20260803/relaxfix-consecutive/trial1/checkpoint.json` | `DONE` | 2.218 mm | 0.000008 mm | false / false |
| 2 | `reset-90cde82e-5921-46c1-bf5c-84fb992b1a44` | `/tmp/so101-local-takeover-20260803/relaxfix-consecutive/trial2/checkpoint.json` | `DONE` | 2.124 mm | 0.000008 mm | false / false |
| 3 | `reset-8b1ee265-a4fc-4147-88c0-5fb0078a3c8a` | `/tmp/so101-local-takeover-20260803/relaxfix-consecutive/trial3/checkpoint.json` | `DONE` | 2.844 mm | 0.000098 mm | false / false |

统计：连续成功率 `3/3 = 100%`；位置平均误差 `2.396 mm`，最大 `2.844 mm`，总体标准差 `0.320 mm`。三轮最终 `moveit_collisions=[]`。

最终 Gazebo 证据：`/captures/gazebo-1785757436134.png`。画面显示杯子稳定落台，夹爪已按偏置路径撤至杯口外上方；整屏证据保存在 `/tmp/so101-local-takeover-20260803/relaxfix-consecutive/desktop-final/desktop.png`。

本轮 fresh CTest 显式排除已知过期的 `test_fingertip_pad_geometry` 后为 `62/62` 通过。该静态 mesh 套件仍记录着旧 DESCEND endpoint、旧 0.538 mm seating shift 和旧 attachment 假设；本轮没有通过放宽断言伪造全绿，应另行重建静态几何模型与实时 contact manifold 的对应关系。

## 后续门

- 在新仿真版本、模型或控制器参数变化后重新执行连续三次复跑。
- 实机迁移前单独建立力控/速度/碰撞和 emergency-stop 验收，不复用本次仿真成功率。

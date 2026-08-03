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

## 冻结复跑证据

共同策略哈希：

- motion policy: `48dba1959278572e17af2256532a3201868fd4fa7a16c8e0b6a0f31e0723b33e`
- validation policy: `f8ec294ec4591f4728880585b3c9275d04708e8fc19b8df79ee2e30b243d49df`
- policy bundle: `45c53a6cb0fe55987e00adb36d0035bedb390c7b9d85e36515bc22877c3f89e0`

| Trial | simulation session | checkpoint | 结果 | XY 误差 | Z 误差 | 最终 attachment |
|---|---|---|---|---:|---:|---|
| 1 | `reset-6f45e224-0e44-4924-869f-0ae7a71d5e41` | `/tmp/retreat-final-candidate-trial1.json` | `DONE` | 2.806 mm | 0.0000066 mm | false / false |
| 2 | `reset-d8b3e1bd-5991-4496-ad12-28763d45bd68` | `/tmp/retreat-final-candidate-trial2.json` | `DONE` | 2.048 mm | 0.0000083 mm | false / false |
| 3 | `reset-3dde1e33-5bf0-45cf-966d-3700d61e55ed` | `/tmp/retreat-final-candidate-trial3.json` | `DONE` | 2.742 mm | 0.0000066 mm | false / false |

统计：连续成功率 `3/3 = 100%`；XY 平均误差 `2.532 mm`，最大 `2.806 mm`，总体标准差 `0.343 mm`。

最终 Gazebo 证据：`/captures/gazebo-1785746221250.png`。画面显示杯子稳定落台，夹爪已按偏置路径撤至杯口外上方。

完整包测试共运行 63 个 CTest 项。状态机 dry-run 的两条旧 transition-count 断言已更新并单独复跑通过；`test_fingertip_pad_geometry.py` 仍有 8/15 个静态 mesh 几何断言使用旧 DESCEND endpoint、旧 0.538 mm seating shift 和旧 attachment 假设。它们与本次 3/3 实时双侧接触证据不一致，未通过放宽断言伪造全绿；应另行重建静态几何模型与实时 contact manifold 的对应关系。

## 后续门

- 在新仿真版本、模型或控制器参数变化后重新执行连续三次复跑。
- 实机迁移前单独建立力控/速度/碰撞和 emergency-stop 验收，不复用本次仿真成功率。

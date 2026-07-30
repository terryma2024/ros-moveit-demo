# SO-101 接近成功的 CLOSE 候选参数快照

- 保存日期：2026-07-30
- 状态：候选参数已保留；CLOSE 视觉效果良好，但 ATTACH/LIFT 尚未通过
- ai-station branch：`codex/direct-tpu-tongues`
- ai-station commit：`ff659cb`
- 复现证据：`/tmp/so101-debug-20260730-repro-m0p6-in022-34FWe1`

## 配置身份

临时配置：

- motion：`/tmp/so101-debug-20260730-mainline-9dvv2n/motion-pitch-minus0p6-inward0p22.yaml`
- validation：`/tmp/so101-debug-20260730-mainline-9dvv2n/validation-pitch-minus0p6-inward0p22.yaml`

候选文件 SHA-256：

```text
cb2192b3ba177f62ec7244ac1fc220529c603d64bde78703043e10f0d679672f  motion-pitch-minus0p6-inward0p22.yaml
97db315d08502992264d8c44ec54d1112c7537382baa02858026212f02117099  validation-pitch-minus0p6-inward0p22.yaml
```

候选以停止实验时 ai-station 的正式策略为基线。基线文件 SHA-256：

```text
5bdf7f1278da40fdbc744e544da7948ce23a66c498c6b8d13111626f698e5443  config/motion_policies/light_cup_wall_pick.yaml
45e517bf8dce1752048119878d965adb7c106994022b1ff7bff99423c942d2b3  config/validation_policies/light_cup_wall_pick.yaml
```

## 精确参数差异

相对上述基线，motion policy 只改变 DESCEND 末端关节目标，以及所有依赖该目标的 logical start：

```diff
- [-0.000272079188, 0.459351907806, 0.192119212168, 0.898387581703, -0.000279513780]
+ [-0.000272079188, 0.470459260051, 0.171207525141, 0.918657566090, -0.000279513780]
```

该替换共出现四处：

1. `DESCEND.waypoints` 最后一个 waypoint；
2. `LIFT.logical_start`；
3. `RECOVER_DESCEND_TO_PICK.waypoints` 最后一个 waypoint；
4. `RECOVER_RETREAT.logical_start`。

validation policy 只改变 DESCEND endpoint 的 world Y：

```diff
- endpoint_position: [0.020673889, -0.263338090, 0.205255723]
+ endpoint_position: [0.020673889, -0.263558090, 0.205255723]
```

该替换共出现两处：

1. `DESCEND.endpoint_position`；
2. `RECOVER_DESCEND_TO_PICK.endpoint_position`。

语义摘要：

- 抓取姿态 pitch 约为 `-0.6 deg`；
- TCP 相对对应基线向 world `-Y` 偏移 `0.22 mm`；
- q6 保持原校准值，`grasp_close_q6=-0.047409691482075`，没有使用已否决的 `q6 +1.6 mrad`。

## 2026-07-30 复现结果

### CLOSE

- 命令模式：`execute`；
- 停止状态：`CLOSE_GRIPPER`；
- 退出码：`0`；
- checkpoint 的杯子位置：`[0.020007314, -0.281135142, 0.166269094] m`；
- checkpoint 的杯子姿态 quaternion：`[-0.013515875, 0.000601938, 0.000737899, 0.999908205]`，顺序为 `qx, qy, qz, qw`；
- checkpoint 的实际 q6：`-0.046922691 rad`；
- 用户视觉判断：效果挺好，参数很接近成功；
- 截图：本机 `/tmp/so101-repro-close-gazebo.png`，远端 `/tmp/so101-debug-20260730-repro-m0p6-in022-34FWe1/close-gazebo.png`。

### ATTACH/LIFT

第一次从静置后的 CLOSE checkpoint 恢复时，因为杯子位姿继续漂移，被 `RESUME_GAZEBO_POSE_MISMATCH` 拒绝，没有动作。

随后重启干净 stack，在同一次连续运行中执行到 LIFT，结果在 `ATTACH_GAZEBO` 边界失败：

- 原始失败：`GRIPPER_CONTACT_PENETRATION_EXCEEDED`；
- 恢复后最终失败：`TASK_OBJECT_POSITION_DRIFT`；
- 杯子平移漂移：`0.00579702096528 m`；
- 杯子姿态漂移：`0.0268911949136 rad`；
- LIFT 未执行；
- 状态机打开夹爪后进入 `ERROR`；
- 退出码：`1`。

因此，该快照只代表“值得保留的 CLOSE 候选”，不能作为已通过的抓取策略或正式默认配置。

## 恢复使用约束

恢复时先核对基线文件哈希。若基线哈希不同，不应机械应用上述差异；应重新检查配置语义和 waypoint 依赖。

推荐的下一条唯一假设是：保留该 DESCEND/CLOSE 姿态，单独定位稳定窗口中是哪一侧、哪个 collision piece 触发 `GRIPPER_CONTACT_PENETRATION_EXCEEDED`，而不是继续同时调整 pitch、Y 和 q6。

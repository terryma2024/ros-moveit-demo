# SO-101 抓取硬门控失败 know-how 总结（2026-08-08）

适用范围：`codex/so101-gazebo-demo-py`，VERIFY_PHYSICAL_GRASP 边界，冻结 ceiling
`0.000800002 m`。证据来源：`docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`
中 PY-A0-BASELINE-GRASP-006、PY-A-X/Y/Z 系列、PY-C-Q6-PRELOAD 系列、
PY-B-XROT-NEG-00173-PLAN-001 与 CP-PHASE4-FEASIBILITY-AUDIT-001。

## 1. 失败事实（均为 VALID failure，证据目录保留在 /tmp/so101-py-*）

| 维度 | 已试范围 | 失败模式 |
|---|---|---|
| TCP X（world） | -0.0005, -0.001 m | moving pad 越顶 |
| TCP Y（world） | +0.000225..+0.0005 m | 越顶或 moving contact 丢失 |
| TCP Z（world） | +0.00025..+0.0005 m | 越顶；+0.0005 处 moving contact 丢失 |
| q6 preload | 0.0015..0.006 rad（0.006 为文档基线） | 0.0015 丢 contact；≥0.003 越顶 |
| orientation | world-X 负向 1° | plan-only 即 GOAL_STATE_INVALID，物理未执行 |

## 2. 不变量：失败模式与 target 值无关

- 所有 bilateral 运行：close 时 moving pad 深度约 0.00049–0.00119 m（7 次，均值
  0.000721，stdev 0.000318），preload 后升至 0.00085–0.00115。**变化 target 只微调
  均值，从不把分布压进 ceiling**。
- preload 的因果效应：+6 mrad 约使 moving 深度翻倍（0.000547 → 0.001152），而
  fixed pad 基本不变。即 q6 挤压的载荷几乎全部落在 moving pad 边缘上。
- moving contact 的存在窗口极窄：preload 0.0015 完全失去 contact，0.003 即越顶。
  窗口宽度 < 运行间方差。
- Z +0.0005 是 moving contact 有无的锐利边界；接触带对 Z 的敏感性远大于对
  深度的改善。

## 3. 判断逻辑：下一步策略方向如何从这些失败中读出

### 3.1 这已经不是 target 调参问题

同一失败模式（moving pad 峰值深度越顶）在所有已授权标量方向上不变，说明瓶颈在
结构/合同层，不在数值层。继续在 X/Y/Z/q6/orientation 上插值是结果挑选，不是工程。

### 3.2 三个候选根因层，按“上游优先、证据可区分”排序

1. **接触几何（系统性偏置，最上游）**：fixed 垫面上翘 +4.5°、moving +1.2°（URDF
   安装角 + 抓取姿态合成），杯壁接触集中在垫下缘，峰值深度约为名义干涉量
   （0.00004 m）的 10–25 倍。pad 垂直化是最直接的降深度手段，但：
   - orientation 候选在冻结的 pose-constraint 合同（0.0004 m 位置盒 + 0.005 rad
     姿态容差、5-DOF 臂）下不可规划；
   - 要解锁该方向，只能放宽 grasp 校正的规划合同（更大位置盒/姿态容差或改走
     joint-space 校正路径），或修改垫安装几何。两者都超出现授权。
2. **物理方差（统计可行性）**：门控要求“每个采样双垫 ≤ ceiling”，而固定配置下
   物理分布 spread 0.000707 m 是最佳余量 0.000314 m 的 2.25 倍。即使找到均值
   居中的 target，单次通过概率也远小于 1，五连成功在统计上不可达。降方差方向：
   contact-stop 确定性（controller 语义）、求解器参数、cup 微倾斜抑制——均为冻结层。
3. **门控/ceiling 语义（设计决策）**：0.000800002 m 是否相对当前 contact model
   （rigid_link_local_mesh + 生成碰撞网格 + Bullet Featherstone）校准正确，只能由
   用户裁决；agent 无权放宽。

### 3.3 不推荐的方向（已被证据否定）

- 继续细分 Z 或组合 X/Y/Z：bracket 已闭，深度不随 Z 改善到 ceiling 内。
- 更细 preload 二分：contact 存在窗口窄于方差，插值无稳健解。
- 换 orientation 轴/反号：H1/H2 已被几何证据否决；且任何非零姿态偏转在同一
  规划合同下同样不可规划。
- 臂级 ±X reseat：EXP-016/020 已证伪。
- 叠加 retry/随机重跑：违反无结果挑选规则，且五连验收会被方差击穿。

### 3.4 若获新授权，建议的判别顺序

1. 先回答“ceiling 相对当前 contact model 是否校准正确”（只读审计可补充：depth
   分布 vs 求解器 min_depth 0.0001 m 与网格分辨率）。
2. 若 ceiling 不动：优先解除 orientation 可规划性（规划合同修正案），因为 pad
   垂直化是唯一被证据支持的系统性降深度机制；用 plan-only 即可廉价筛选，不必
   先跑物理。
3. 同时评估方差降低（contact-stop 确定性），否则即使均值达标五连也不可达。
4. 仅在 1–3 都不可行时才考虑几何/材料修改，且必须重新校准全部指纹。

## 4. 方法论 know-how（本次有效、应保留的做法）

- 失败即停并冻结证据：physical-failure.json 总是先于任何 open/reset 写出。
- 每个候选先 plan-only：orientation 方向仅用一次 plan-only 就证伪，省掉三次物理
  stack。
- 先只读几何分析再选 orientation 轴/符号，避免猜测和双向试错。
- 单标量 + 预注册 + 确定性二分：每一步都可回放、可归因。
- fail-closed ceiling 与 0.10 s pose-pair freshness 在多次实现缺陷暴露时保护了结论
  有效性（INVALID 与 VALID failure 从未混淆）。

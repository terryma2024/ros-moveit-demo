# V5-T005 Grounding DINO Tiny + SAM 2.1 RGB-D experiment ledger

```yaml
task_id: so101-v5-t005-grounded-sam-rgbd
goal: 在 macOS MPS 与 ai-station CUDA 上使用 Grounding DINO Tiny 和 SAM 2.1 Hiera Tiny，从多物体 MuJoCo RGB-D 中选择唯一 plastic_cup，发布新鲜 /cup_pose，并完成仿真 pick&place
success_contract: 两个平台以同一 commit、模型包 SHA 和阈值通过四场景感知矩阵，随后各自 FULL_RESTART 连续 5 次 pick&place 成功
worktree: /Users/matianyi/.codex/worktrees/5b15/moveit-demo
branch: codex/v5-t004-yolo-seg-rgbd
base_commit: b55c869c919cd673bf84be8b125cc55a8e6eb98f
current_commit: b55c869c919cd673bf84be8b125cc55a8e6eb98f
evidence_root: /data/work/so101-evidence/v5-t005-grounded-sam-rgbd/20260901-b55c869
development_source_root: /tmp/so101-debug-v5-t005-grounded-sam-20260901
design: docs/superpowers/specs/2026-09-01-v5-t005-grounded-dino-sam2-rgbd-perception-design.md
confirmed_conclusions:
  - CONF-001 设计固定使用 IDEA-Research/grounding-dino-tiny 与 facebook/sam2.1-hiera-tiny
  - CONF-002 首版采用 Transformers 进程内推理，逐帧无状态，不启用 SAM 2.1 视频跟踪
  - CONF-003 GroundedSamDetector 复用 DetectorPort、TargetSelector、RgbdLocalizer 与 /cup_pose 链路
  - CONF-004 生产 detector 只读 RGB；MuJoCo object ID、truth pose 与颜色规则只用于验收
  - CONF-005 macOS 使用 MPS，ai-station 使用 CUDA；CPU fallback 默认关闭
open_hypotheses:
  - HYP-001 Grounding DINO Tiny 对受控提示词 plastic cup. 能在四个 MuJoCo 场景中满足候选数量与类别门槛
  - HYP-002 SAM 2.1 Hiera Tiny 的框提示 mask 在两个平台都能达到 truth IoU >= 0.80
  - HYP-003 两阶段 warmed request latency 在两个平台都能 <= 2000 ms
  - HYP-004 新 detector 接入后，两个平台可以分别完成 FULL_RESTART 连续 5/5 pick&place
latest_checkpoint: CP-001
next_experiment: 编写实现计划；未批准执行前不修改生产代码
```

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: 已批准架构、模型包、阈值起点、失败边界和双平台验收标准，等待实现计划
working_tree_status: 设计文档与本账本待提交；生产代码未修改
owned_processes: NONE
preserved_processes: 用户进程与既有 V5-T004 证据未触碰
retained_runs: []
archived_runs: []
deletion_candidates: []
next_command: 使用 superpowers:writing-plans 编写 V5-T005 实现计划
decision: DESIGN_APPROVED
```

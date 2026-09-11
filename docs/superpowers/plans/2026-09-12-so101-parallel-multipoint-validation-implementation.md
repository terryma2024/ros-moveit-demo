# SO-101 MoveIt 专家多点并行验证实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ai-station 上实现 MuJoCo 多 Worker 动态抢点验证；Worker 数量和单 Worker 最大领取量由启动参数指定，YOLO-Seg 优先、Grounded-SAM 受限回退，并用同一批次的不可变证据判断 20 个固定点是否全部首次通过。

**Architecture:** `ParallelBatchCoordinator` 是 queue、lease、容量和点位终态的唯一写入者；每个 Worker 拥有独立 ROS domain、MuJoCo/MoveIt/controller 进程树和证据目录；`PerceptionBroker` 只共享两套模型的 GPU 推理，不共享 ROS topic 或控制权。状态先写入 fsync 事件账本再发 ACK，Worker 结果先 seal 再提交，崩溃恢复按 coordinator epoch、worker generation 和 lease identity fail closed。

**Tech Stack:** Python 3、ROS 2 Jazzy、MuJoCo、MoveIt 2、ros2_control、Unix domain socket、JSON/JSONL、PyYAML、pytest、colcon、CUDA、YOLO-Seg、Grounded-SAM。

**Spec:** [SO-101 MoveIt 专家多点并行验证设计](../specs/2026-09-11-so101-parallel-multipoint-validation-design.md)

## Global Constraints

- 首版仅支持 MuJoCo；manifest 固定 `backend=mujoco`、`GZ_PARTITION=not_applicable`，不实现 Gazebo 并行适配。
- 不并行控制实体机械臂。本计划不授权真实硬件动作、push、force-push、证据删除或宽泛清理进程。
- 当前 20 点 catalog 来自 ai-station 的 `/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/manifest/candidate-points.yaml`，冻结 SHA256 `c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5`。实施时把同一字节内容纳入仓库；任何坐标、顺序或 catalog 哈希变化都必须停止并重新审查。小样本只通过重复的 `--point-id` 从 catalog 选择合法子集，另记 selection hash，不生成或修改另一份点位 YAML。
- YOLO-Seg 权重冻结 SHA256 `f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`；Grounded-SAM bundle manifest 冻结 SHA256 `0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775`。路径可以由 CLI 提供，哈希不能静默改变。
- 一个 Worker 同时只有一个有效 lease。`--max-points-per-worker K` 统计稳定 slot 的成功发放次数；进程重启只增加 `worker_generation`，不重置 K。
- 点位 `FAILED` 或 `INDETERMINATE` 后本轮不自动重试。`INVALID` attempt 只有在旧 lease fenced、旧进程和 controller goal 已确认停止、Worker 重新准入后才可重新排队。
- Worker 恢复成功后可以继续领取任意剩余点，不绑定固定分片。容量不足只设置 `full_coverage_no_longer_possible=true`；仍要执行所有当前可执行点。
- `POSE_ACCEPTED` 是 Worker 本地 admission latch。仅发布 `/cup_pose`、收到迟到推理或看到其他 Worker 的 topic 都不能打开 latch。
- Broker unhealthy 时暂停新 lease，不连续消耗 K。已有 `POSE_ACCEPTED` 的 Worker可完成动作；公共依赖在 deadline 内未恢复，批次以 `SHARED_DEPENDENCY_UNAVAILABLE` 收尾。
- 首版硬上限为 3 个 Worker、每 slot 最多 20 次 lease。默认 2 Worker。config 默认值为：heartbeat 1 s、失联 5 s、lease 300 s、lease/attempt/result ACK 5/5/10 s；`INITIALIZING`、`EXECUTING`、`FINALIZING` 硬期限分别为 180/240/120 s，批次总硬期限 5400 s；Worker recovery 120 s、Broker recovery 90 s；YOLO queue/inference 10/20 s、Grounded-SAM queue/inference 10/60 s；每模型总队列 3、每 Worker 每模型 queued+running 合计 1、IPC frame 上限 8 MiB。阶段和批次时间都取 monotonic 首次进入时刻，heartbeat、重连、续租和进程换代不能重置。初始门控沿用并哈希既有 reset、task geometry 和 dynamic policy，不复制或放宽几何/力阈值。
- 资源准入默认要求 `4 × N` 个可用逻辑 CPU、`6 + 4 × N` GiB 可用内存和 Broker 启动前 8 GiB 可用 GPU 显存；ROS domain 从 181–183 中原子分配。双 Worker 小样本必须记录峰值并保留至少 20% headroom；3 Worker 只有在上述静态门和实测 headroom 同时满足时才允许启动。MuJoCo 首版没有外部 simulation/bridge TCP 端口，资源 manifest 对这些字段写 `not_applicable`；teleop 禁用，不能虚构端口隔离证据。
- 当前顺序实现 `application/task_batch.py`、`runtime/task_batch_runtime.py` 和 `cli/mujoco_rgbd_batch.py` 保持兼容；并行入口使用新模块，不把首版并行语义偷偷塞进旧 CLI。
- 所有执行都在新 worktree `/data/work/ws_moveit/.worktrees/parallel-multipoint-v1`、分支 `codex/so101-parallel-multipoint-validation` 中完成。路径若已存在或分支被其他 worktree 占用，停止并报告，不删除或复用未知目录。
- 全任务只登记一个持久证据根：`/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1`。保留旧批次，不写入 `/data/work/so101-evidence/act-head-wrist-moveit-baseline/`。
- ai-station 上每次 pytest/colcon test 都在证据根下创建一个此前不存在的 scratch；设置 `TMPDIR`、`TMP`、`TEMP`，并用实际测试 Python 验证 `tempfile.gettempdir()`。scratch 读回后只标记为删除候选，不删除。
- 普通 package gate 只收集 `src/so101_demo_py/test/`，不运行 `benchmark_test`。README 若需修改只能写英文；本计划不要求修改 README。
- 只停止本任务 manifest 登记的 PID/PGID。禁止 `pkill`、按进程名宽泛清理、操作现有 `codex-19` 之外的 tmux 会话，或覆盖 canonical checkout 的 `.gitignore` 改动。
- 每个任务按 RED → 最小实现 → GREEN → diff 审查 → scoped commit 执行。每次 commit 只暂存该任务 Files 列出的路径；不自动 push。

---

## 已核实基线与文件职责

编写计划时，本机工作树 HEAD 为 `adacd7b4a04899795d9d4d9ef56d9762a0078f45`，另有设计文档和俯视图脚本/测试的用户改动。ai-station canonical checkout HEAD 为 `5bfc5dbe7a7a92448f6e89a9a262b82117dec0a5`，仅 `.gitignore` 有未提交改动；实施必须从该远端 checkout 的当前 HEAD 创建隔离 worktree，再把 handoff 中校验过的设计与计划快照复制进去，不能清理两边已有改动。

| 单元 | 文件 | 唯一职责 |
| --- | --- | --- |
| 冻结输入 | `config/mujoco/moveit_expert_validation_points_v1.yaml`, `config/mujoco/parallel_batch_v1.yaml` | 20 点与首版阈值、deadline、资源范围 |
| 闭合契约 | `parallel_batch/contracts.py` | ID、状态、lease、attempt、模型结果和汇总 schema |
| 持久事件 | `parallel_batch/journal.py` | 独占锁、epoch、带校验 event segment、fsync、重放 |
| 调度投影 | `parallel_batch/coordinator.py` | queue、K、lease、fencing、状态迁移、批次判定 |
| 结果封存 | `parallel_batch/artifacts.py` | working → sealed、manifest 验证、recovery receipt |
| 感知规则 | `parallel_batch/perception.py` | YOLO-first 状态机、失败矩阵、`PoseAdmissionLatch` |
| Broker | `parallel_batch/broker.py`, `cli/parallel_perception_broker.py`, `docker/parallel-perception/Dockerfile` | 有界队列、公平调度、模型预热、推理和 generation fencing |
| 资源分配 | `parallel_batch/resources.py` | ROS domain、端口、session、ROS_HOME、证据目录唯一性 |
| Worker 核心 | `parallel_batch/worker.py` | ready/initial gate、attempt、heartbeat、恢复和 quarantine |
| Linux 适配 | `runtime/parallel_worker_runtime.py` | 独立 headless MuJoCo/MoveIt/controller 生命周期和现有专家链复用 |
| IPC/进程 | `runtime/parallel_ipc.py`, `runtime/parallel_processes.py` | 0600 Unix socket、鉴权消息、协调器/Broker/Worker 进程归属 |
| 入口 | `cli/mujoco_parallel_batch.py`, `setup.py` | 参数校验、准入、自恢复、汇总退出码 |
| 审计 | `docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md` | checkpoint、实验、provenance、结果和证据索引 |

所有新 Python 包使用实际 import 路径 `so101_demo.parallel_batch.*`，源码路径为 `src/so101_demo_py/src/parallel_batch/`。纯领域模块不得导入 `rclpy`、MuJoCo、torch 或 detector 实现。

## 执行 shell 与统一测试函数

- [ ] 在 ai-station 直接运行，不得 SSH 到自身。先核对 `hostname`、canonical checkout、tmux、相关进程和 worktree 列表；确认没有正在运行的 MuJoCo/MoveIt 验证栈。
- [ ] 创建 evidence root、`handoff/`、`scratch/`、`reports/`；先写 `source-before.json`，记录 canonical HEAD/status、设计/计划/点位快照哈希和现有保留进程。
- [ ] 按 `superpowers:using-git-worktrees` 从 ai-station 当前 HEAD 创建指定 worktree/branch，把 handoff 中通过 Astra 审查的设计和计划快照复制到同一路径，再逐文件核对 SHA256。
- [ ] 在新 worktree 执行 `git submodule update --init --recursive -- third_party/mujoco_ros2_control`。用 `git ls-tree HEAD third_party/mujoco_ros2_control` 的 gitlink SHA 与 `git -C third_party/mujoco_ros2_control rev-parse HEAD` 比对，必须相等；保存 `git submodule status --recursive`。未初始化、dirty 或 SHA 不符时在 build 前停止，不能用 canonical 旧 install 补依赖。
- [ ] 只暂存两份已核对的 docs 快照，运行 `git diff --cached --check` 后提交 `git commit -m "docs: plan parallel point validation"`。这一步不得包含 canonical checkout 的 `.gitignore` 或本机俯视图脚本改动。
- [ ] 创建实验账本头部，登记唯一 evidence root、branch、base commit、dirty files、模型/点位哈希和下一实验。一个 agent 是账本唯一写入者。

```zsh
git submodule update --init --recursive -- third_party/mujoco_ros2_control
expected_submodule_sha=$(git ls-tree HEAD third_party/mujoco_ros2_control | awk '{print $3}')
observed_submodule_sha=$(git -C third_party/mujoco_ros2_control rev-parse HEAD)
test -n "$expected_submodule_sha" && test "$expected_submodule_sha" = "$observed_submodule_sha"
git submodule status --recursive > /data/work/so101-evidence/parallel-multipoint-validation/20260912-v1/reports/submodule-status.txt
test -z "$(git -C third_party/mujoco_ros2_control status --porcelain)"
```

在同一个 zsh 中定义以下环境。2026-09-12 只读核验发现 canonical `/data/work/ws_moveit/install/setup.zsh` 引用了已经不存在的旧 task8 overlay，因此本任务明确禁止 source 它。先只 source `/opt/ros/jazzy/setup.zsh`，在新 worktree 内 fresh build `--packages-up-to so101_demo_py`，之后只 source `/data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/setup.zsh`。这条发现写入 `source-before.json` 和账本，不能用旧 install 的命令成功冒充当前实现 provenance。

```zsh
cd /data/work/ws_moveit/.worktrees/parallel-multipoint-v1
source /opt/ros/jazzy/setup.zsh

PARALLEL_EVIDENCE=/data/work/so101-evidence/parallel-multipoint-validation/20260912-v1
PARALLEL_PYTHON=$(command -v python3)
export PARALLEL_EVIDENCE PARALLEL_PYTHON
export ROS_HOME="$PARALLEL_EVIDENCE/orchestrator-ros-home"
export ROS_LOG_DIR="$ROS_HOME/log"
mkdir -p "$ROS_LOG_DIR" "$PARALLEL_EVIDENCE/scratch" "$PARALLEL_EVIDENCE/reports"
"$PARALLEL_PYTHON" -m colcon --help >/dev/null

parallel_test() {
  local test_run test_name test_exit
  test_run=$(mktemp -d "$PARALLEL_EVIDENCE/scratch/pytest-XXXXXXXX") || return 1
  mkdir "$test_run/tmp" || return 1
  export TMPDIR="$test_run/tmp" TMP="$test_run/tmp" TEMP="$test_run/tmp"
  "$PARALLEL_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve() == Path(os.environ["TMPDIR"]).resolve()' || return 1
  printf '%s\n' "$test_run" >> "$PARALLEL_EVIDENCE/reports/scratch-deletion-candidates.txt"
  test_name=$(basename "$test_run")
  PYTHONNOUSERSITE=1 /usr/bin/time -p -o "$PARALLEL_EVIDENCE/reports/$test_name.time" "$PARALLEL_PYTHON" -m pytest -p no:cacheprovider "$@" >"$PARALLEL_EVIDENCE/reports/$test_name.log" 2>&1
  test_exit=$?
  printf '%s\n' "$test_exit" > "$PARALLEL_EVIDENCE/reports/$test_name.exit"
  sed -n '1,240p' "$PARALLEL_EVIDENCE/reports/$test_name.log"
  return "$test_exit"
}
```

变量名不得使用 zsh 的 `status` 或 `path`。测试不经过 pipeline，退出码在命令返回后立即保存；不能把环境导入失败当成 RED。Task 1 先创建空 `parallel_batch/__init__.py`，然后做一次 bootstrap `--symlink-install` 并 source worktree overlay。每个测试把待实现符号的 import 放在测试函数或 fixture 内，确保 pytest 已收集测试后才出现预期 RED；顶层 import/环境收集失败不计 RED。每次新增 console entry point 都先 rebuild/source，再运行入口。

---

### Task 1: 冻结 20 点、运行配置和闭合状态契约

**Files:**

- Create: `src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml`
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml`
- Create: `src/so101_demo_py/src/parallel_batch/__init__.py`
- Create: `src/so101_demo_py/src/parallel_batch/contracts.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_contracts.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:** Consumes the frozen point bytes and YAML. Produces `ParallelRuntimeConfig`, `BatchRequest`, `PointStatus`, `ValidationStatus`, `AttemptStatus`, `WorkerState`, `LeaseIdentity`, `AttemptIdentity`, `ModelOutcome`, `BatchSummary`, strict `load_parallel_runtime_config(path)`, and `validate_capacity(worker_count, max_points_per_worker, point_count)`.

- [ ] **Step 1: 写测试，锁定参数、状态和 20 点哈希。**

```python
import hashlib
from pathlib import Path

import pytest
import yaml

def test_capacity_and_frozen_points():
    from so101_demo.parallel_batch.contracts import ContractError, validate_capacity

    points = Path(__file__).resolve().parents[1] / "config/mujoco/moveit_expert_validation_points_v1.yaml"
    assert hashlib.sha256(points.read_bytes()).hexdigest() == "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
    ids = [item["id"] for item in yaml.safe_load(points.read_text())["points"]]
    assert [ids[index] for index in (0, 8, 17, 18, 19)] == [
        "task_start", "sample_05_near_center", "sample_14_far_right",
        "sample_15_far_center", "sample_16_far_right",
    ]
    with pytest.raises(ContractError, match="INSUFFICIENT_CAPACITY"):
        validate_capacity(worker_count=2, max_points_per_worker=9, point_count=20)
```

补测 bool/0/负数、重复点 ID、相对 evidence path、未知 YAML 字段、非有限 deadline、`worker_count=2,K=10` 和超额容量。

先只创建空 `parallel_batch/__init__.py`，再 bootstrap 当前 worktree；这一步只解决源码导入，不实现待测符号：

```zsh
"$PARALLEL_PYTHON" -m colcon build --packages-up-to so101_demo_py --symlink-install
source /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/setup.zsh
"$PARALLEL_PYTHON" -c 'from pathlib import Path; import so101_demo, so101_demo.parallel_batch as p; root=Path("/data/work/ws_moveit/.worktrees/parallel-multipoint-v1").resolve(); assert Path(p.__file__).resolve().is_relative_to(root); print(so101_demo.__file__, p.__file__)'
```

- [ ] **Step 2: 运行 RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_contracts.py -q
```

预期已收集的测试因 `contracts` 符号或冻结配置缺失而失败；pytest 必须完成非零收集。

- [ ] **Step 3: 实现严格 dataclass/StrEnum 契约。** 所有 JSON/YAML schema 拒绝未知字段、bool 冒充 int、NaN/Inf、空 ID 和路径穿越。`ParallelRuntimeConfig` 保存 `backend="mujoco"`、heartbeat/ACK/lease/broker deadline、queue cap、资源阈值和模型哈希；`BatchRequest` 保存 CLI 传入的 `worker_count` 和 `max_points_per_worker`。把权威 20 点文件按字节复制进 config，并由 `setup.py` 既有递归资源安装逻辑收录。`parallel_batch_v1.yaml` 必须使用下面的闭合值，调参需要新 config hash 和新实验：

```yaml
schema_version: 1
backend: mujoco
max_worker_count: 3
max_points_per_worker_upper_bound: 20
ros_domain_ids: [181, 182, 183]
heartbeat_interval_s: 1.0
heartbeat_timeout_s: 5.0
lease_duration_s: 300.0
lease_ack_timeout_s: 5.0
attempt_start_ack_timeout_s: 5.0
result_ack_timeout_s: 10.0
initializing_hard_timeout_s: 180.0
executing_hard_timeout_s: 240.0
finalizing_hard_timeout_s: 120.0
batch_hard_timeout_s: 5400.0
worker_recovery_timeout_s: 120.0
broker_recovery_timeout_s: 90.0
broker_max_frame_bytes: 8388608
broker_queue_capacity_per_model: 3
broker_inflight_per_worker_per_model: 1
yolo_queue_timeout_s: 10.0
yolo_inference_timeout_s: 20.0
grounded_sam_queue_timeout_s: 10.0
grounded_sam_inference_timeout_s: 60.0
yolo_model_id: plastic-cup-yolo11n-seg-v1
yolo_imgsz: 640
requested_device: cuda
allow_cpu_fallback: false
grounding_box_threshold: 0.35
grounding_text_threshold: 0.25
grounding_duplicate_iou: 0.85
grounding_max_candidates: 16
sam_mask_quality_threshold: 0.75
sam_min_mask_pixels: 64
sam_max_mask_area_ratio: 0.50
min_logical_cpu_per_worker: 4
available_ram_base_gib: 6
available_ram_per_worker_gib: 4
min_available_gpu_gib: 8
required_live_headroom_ratio: 0.20
```

`ValidationStatus` 只允许 `VALIDATION_PASSED`、`VALIDATION_FAILED`、`VALIDATION_INVALID`。dry-run 为每个 selection 保存 queue/lease/K/fencing 和 synthetic runtime trace；plan-only 还保存真实 worker-ready、reset、point-initial、RGB-D、模型链、POSE_ACCEPTED、完整 prefix plans、零 controller goal 与 cleanup。两种模式使用 `VALIDATION_STARTED`/`VALIDATION_COMMITTED`，目录固定为 `workers/{worker_id}/validations/{point_id}/{validation_id}/sealed/validation_result_manifest.json`，不写物理 `ATTEMPT_STARTED`、不改变 `PointStatus.UNRUN`。aggregate 设置 `validation_complete`、`validation_passed`，并硬编码 `qualification_applicable=false,qualification_passed=false`。只有 execute 使用物理 attempt/PASSED/FAILED/INDETERMINATE；补测即使 20 个 dry-run 或 plan-only validation 全部通过也不能生成 20/20 资格。

- [ ] **Step 4: 运行 GREEN，并验证安装资源哈希。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_contracts.py -q
"$PARALLEL_PYTHON" -m colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
python3 -c 'from ament_index_python.packages import get_package_share_directory; from pathlib import Path; import hashlib; p=Path(get_package_share_directory("so101_demo_py"))/"config/mujoco/moveit_expert_validation_points_v1.yaml"; assert hashlib.sha256(p.read_bytes()).hexdigest()=="c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"'
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml src/so101_demo_py/src/parallel_batch/__init__.py src/so101_demo_py/src/parallel_batch/contracts.py src/so101_demo_py/test/test_parallel_batch_contracts.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat: define parallel validation contracts"
```

### Task 2: 实现 fsync 事件账本、独占锁和 epoch 重放

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/journal.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_journal.py`

**Interfaces:** Consumes `batch_id`, evidence root, canonical JSON event. Produces `CoordinatorJournal.acquire()`, `append(event_type, idempotency_key, payload)`, `replay()`, `coordinator_epoch`, `JournalCorruption`; event frame is `8-byte big-endian payload length + 64 ASCII SHA256 + canonical JSON bytes + newline`。每个 event 还保存前一 event 的 frame SHA256，segment header 保存前一 segment 的终止 SHA256。

- [ ] **Step 1: 写断电窗口和幂等测试。**

```python
def test_replay_preserves_torn_tail_and_rotates_epoch(tmp_path):
    first = CoordinatorJournal.create(tmp_path, "batch-a")
    first.append("LEASE_GRANTED", "lease-1", {"slot": "worker-01", "k_debit": 1})
    segment = first.segment_path
    first.close()
    with segment.open("ab") as stream:
        stream.write(b"\x00\x00\x00")
        stream.flush(); os.fsync(stream.fileno())
    second = CoordinatorJournal.create(tmp_path, "batch-a")
    replay = second.replay()
    assert [event.type for event in replay.events] == ["LEASE_GRANTED"]
    assert replay.damaged_tail_path.is_file()
    assert second.coordinator_epoch == first.coordinator_epoch + 1
```

该例的三字节必须位于 EOF，且不足以组成完整 header，才能作为未提交 torn tail。另写两个 fail-closed 测试：完整 frame 的 checksum 错误抛 `JournalCorruption`；中段损坏或 segment chain 不连续抛 `JournalCorruption`。两者都禁止新 epoch、禁止新 lease，并进入受控停止，不能当作正常 rotation。补测第二协调器锁失败、重复 idempotency key 返回原 event、不重复写、投影文件不是恢复权威、目录 fsync 被调用。

- [ ] **Step 2: 运行 RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_journal.py -q
```

- [ ] **Step 3: 最小实现。** 用 `fcntl.flock(LOCK_EX|LOCK_NB)` 持有 `coordinator.lock`；epoch 由原子 JSON 写入并 fsync 父目录。`append` 在持锁状态下构造 canonical JSON，写完整 frame，flush+fsync 后才返回。重放只允许忽略 EOF 处可证明未完成的最后一个 header/payload，将原始字节复制到 `events/torn-tail-{epoch}.bin` 后开新 segment。完整 frame checksum 错误、非 EOF 损坏、event/segment chain 断裂都属于已提交数据不可验证：保留原文件、抛 `JournalCorruption`、不增加 epoch、不重建 projection、不授权任何 Worker。

- [ ] **Step 4: GREEN 与静态检查。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_journal.py -q
python3 -m compileall -q src/so101_demo_py/src/parallel_batch
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/journal.py src/so101_demo_py/test/test_parallel_batch_journal.py
git diff --cached --check
git commit -m "feat: add crash-safe parallel batch journal"
```

### Task 3: 实现动态 lease、K 记账和终态投影

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_coordinator.py`

**Interfaces:** Consumes `CoordinatorJournal`, frozen points and monotonic time. Produces `register_worker`, `grant_lease`, `ack_attempt_started`, `heartbeat`, `commit_result`, `expire_lease`, `record_recovery`, `mark_broker_health`, `snapshot`.

- [ ] **Step 1: 写状态机表驱动测试。**

```python
def test_failed_worker_recovers_and_steals_next_point(coordinator):
    lease = coordinator.grant_lease("worker-01", generation=1)
    coordinator.ack_attempt_started(lease, request_key="start-1")
    coordinator.commit_result(lease, sealed_result("FAILED"), request_key="result-1")
    coordinator.record_recovery("worker-01", generation=1, succeeded=True)
    next_lease = coordinator.grant_lease("worker-01", generation=1)
    assert next_lease.point_id != lease.point_id
    assert coordinator.snapshot().workers["worker-01"].lease_count == 2
```

补测：同点不双租；grant 在 journal fsync 前不返回；`LEASE_GRANTED` ACK 超时不得 reset，`ATTEMPT_STARTED` ACK 超时允许已完成的 reset/initial gate 保留证据但不得推理或动作；generation/epoch 过期请求拒绝；Worker 重启不重置 K；FAILED/INDETERMINATE 不重排；INVALID 完整 fencing 后重排；容量不足仍清空可执行队列；无在途/可恢复容量时才 `CAPACITY_EXHAUSTED`；Broker unhealthy 暂停新 lease 且不扣 K；最后点 PASSED 但 cleanup 未完成时 `qualification_passed=false`。另用 fake monotonic 证明 heartbeat 持续正常也不能越过 180/240/120 s 阶段 deadline 或 5400 s batch deadline；续租截止取 `min(now + 300 s, current_stage_deadline, batch_deadline)`，阶段进入时刻和 batch start 只写一次。批次 deadline 到达后不再续租或发新 lease，所有 Worker 停止新动作并 cancel/confirm；已开始但无法裁决的 execute point 进入 INDETERMINATE，未开始的 selection 在 cleanup 后为 UNRUN，batch terminal reason 为 `BATCH_DEADLINE_EXCEEDED`。

- [ ] **Step 2: 运行 RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_coordinator.py -q
```

- [ ] **Step 3: 实现纯状态机。** 所有 public transition 在一把 coordinator state lock 内完成，先 append event 再更新可重放投影/ACK。`aggregate_results.json` 通过临时文件、fsync、`os.replace` 和父目录 fsync 更新，但重启只信 journal。execute 模式的 `coverage_complete` 只接受 PASSED/FAILED；`execution_complete` 接受四种点终态；`qualification_passed` 还要求全 PASSED 和 `batch_cleanup_complete`。dry-run/plan-only 只写独立 `ValidationStatus` 和 `validation_complete/validation_passed`；它们的物理 point status 保持 UNRUN，aggregate 固定 `qualification_applicable=false,qualification_passed=false`。

- [ ] **Step 4: GREEN，并进行确定性重放。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_coordinator.py -q
parallel_test src/so101_demo_py/test/test_parallel_batch_journal.py src/so101_demo_py/test/test_parallel_batch_coordinator.py -q
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/coordinator.py src/so101_demo_py/test/test_parallel_batch_coordinator.py
git diff --cached --check
git commit -m "feat: schedule parallel point leases"
```

### Task 4: 封存 attempt、提交结果和追加恢复回执

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/artifacts.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_artifacts.py`
- Modify: `src/so101_demo_py/src/runtime/task_artifacts.py`

**Interfaces:** Consumes Worker/lease/attempt or validation identity and required artifacts. Produces `AttemptWorkspace`, `ValidationWorkspace`, `seal_attempt() -> SealedAttempt`, `seal_validation() -> SealedValidation`, corresponding verify methods, and `write_recovery_receipt()`; reuses `atomic_json` but never mutates sealed content or mixes physical and validation manifests.

- [ ] **Step 1: 写 seal 原子性与不可变测试。**

```python
def test_sealed_attempt_is_immutable_and_recovery_is_separate(tmp_path):
    workspace = AttemptWorkspace.create(tmp_path, identity("point-1", "attempt-1"))
    workspace.write_json("initial_state/reset.json", {"epoch": 7})
    workspace.write_json("attempt-result.json", {"status": "FAILED"})
    sealed = workspace.seal(required=("initial_state/reset.json", "attempt-result.json"))
    before = tree_digest(sealed.path)
    receipt = write_recovery_receipt(tmp_path, sealed.identity, succeeded=True)
    assert tree_digest(sealed.path) == before
    assert receipt.is_relative_to(tmp_path / "recoveries")
    with pytest.raises(ArtifactError, match="SEALED_IMMUTABLE"):
        sealed.write_json("late.json", {})
```

补测缺文件、hash 不匹配、symlink、路径穿越、rename 前崩溃保留 working、rename 后父目录 fsync、重复提交幂等、lease identity 不匹配。再测 `ValidationWorkspace` 只位于当前 Worker 根的 `validations/{point_id}/{validation_id}/` 并只能写 `validation_result_manifest.json`，physical attempt 只位于 `attempts/{point_id}/{attempt_id}/` 并只能写 `attempt_result_manifest.json`；两种 identity、目录和 coordinator commit event 不可互换。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_artifacts.py -q
```

- [ ] **Step 3: 实现。** manifest 记录每个文件相对路径、size、SHA256、producer PID/PGID、Worker slot/generation、coordinator epoch、lease/attempt/reset epoch/source stamp。逐文件和 working 目录 fsync 后 `os.replace(working,sealed)`，再 fsync attempt 父目录。若 sealed 已存在，只有 identity 和 tree hash 完全相同才返回原结果。

- [ ] **Step 4: GREEN。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_artifacts.py src/so101_demo_py/test/test_task_artifacts.py -q
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/artifacts.py src/so101_demo_py/src/runtime/task_artifacts.py src/so101_demo_py/test/test_parallel_batch_artifacts.py
git diff --cached --check
git commit -m "feat: seal parallel attempt evidence"
```

### Task 5: 固化 YOLO-first、回退矩阵和 pose admission

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/perception.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_perception.py`

**Interfaces:** Consumes model result plus complete request identity. Produces `PerceptionDecision.next_model`, terminal attempt classification, and `PoseAdmissionLatch.accept(request, localized_pose)`.

- [ ] **Step 1: 参数化完整失败矩阵。**

```python
@pytest.mark.parametrize(("yolo", "grounded", "attempt", "reason"), [
    ("POSE", None, "CONTINUE", None),
    ("NORMAL_REJECTION", "POSE", "CONTINUE", None),
    ("NORMAL_REJECTION", "NORMAL_REJECTION", "FAILED", "PERCEPTION_NO_POSE"),
    ("MODEL_ERROR", "NORMAL_REJECTION", "FAILED", "PERCEPTION_MODEL_ERROR"),
    ("NORMAL_REJECTION", "MODEL_ERROR", "FAILED", "PERCEPTION_MODEL_ERROR"),
    ("INFRA_ERROR", None, "INVALID", "PERCEPTION_INFRA_ERROR"),
    ("NORMAL_REJECTION", "QUEUE_TIMEOUT", "INVALID", "PERCEPTION_QUEUE_TIMEOUT"),
])
def test_yolo_first_matrix(yolo, grounded, attempt, reason):
    assert decide(yolo, grounded) == (attempt, reason)
```

再测 YOLO 成功后永不请求 Grounded-SAM；规划/执行失败不触发回退；request/lease/generation/reset epoch/source stamp/TF 任一不符拒绝；topic publish 不改变 latch；fenced/cancelled result 不 admission。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_perception.py -q
```

- [ ] **Step 3: 实现纯函数和单写 latch。** 模型结果枚举只允许 `POSE`、`NORMAL_REJECTION`、`MODEL_ERROR`、`INFRA_ERROR`、`QUEUE_TIMEOUT`、`INFERENCE_TIMEOUT`、`CANCELLED`。fallback 只由 YOLO 的 `NORMAL_REJECTION` 或 `MODEL_ERROR` 且 latch 未打开时触发；任何基础设施/timeout 直接 INVALID。只有 Worker 在本地核对完整 identity、新鲜 RGB-D、TF 和几何验收后写 `POSE_ACCEPTED`。

- [ ] **Step 4: GREEN。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_perception.py -q
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/perception.py src/so101_demo_py/test/test_parallel_batch_perception.py
git diff --cached --check
git commit -m "feat: enforce parallel perception fallback rules"
```

### Task 6: 实现 Broker 有界公平队列与 generation fencing

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/broker.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_broker.py`

**Interfaces:** Consumes `InferenceRequest` and injected detector callables. Produces `submit`, `cancel_generation`, `set_model_ready`, `next_ready_request`, `complete`; each Worker per model最多一个 in-flight，请求有独立 queue/inference deadline。

- [ ] **Step 1: 写公平性、背压和迟到结果测试。**

```python
def test_round_robin_prevents_one_worker_monopoly(broker):
    broker.submit(req("worker-01", "a")); broker.submit(req("worker-02", "c"))
    first = broker.next_ready_request()
    assert first.request_id == "a"
    broker.complete(first, normal_rejection())
    broker.submit(req("worker-01", "b"))
    second = broker.next_ready_request()
    assert second.request_id == "c"
    broker.complete(second, normal_rejection())
    assert broker.next_ready_request().request_id == "b"

def test_fenced_generation_cannot_complete(broker):
    request = req("worker-01", "a", generation=1)
    broker.submit(request); broker.next_ready_request()
    broker.cancel_generation("worker-01", 1)
    assert broker.complete(request, pose_result()).outcome == "CANCELLED"
```

这里的 in-flight 包含 queued 和 running；同一 Worker、同一模型已有其中任一状态时，第二次 submit 必须拒绝。补测总/每模型 queue cap、queue timeout 与 inference timeout 区分、Broker generation 重启取消旧请求、健康状态改变、同一请求幂等。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_broker.py -q
```

- [ ] **Step 3: 实现 ROS-free core。** 两个模型各自维护按 Worker 分组的 deque 和 round-robin 游标；队列满时 fail closed，不驱逐旧请求。monotonic deadline 在取队和完成时都检查。Broker restart 增加 generation，旧请求只产生审计结果，不返回 pose。

- [ ] **Step 4: GREEN。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_broker.py src/so101_demo_py/test/test_parallel_batch_perception.py -q
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/broker.py src/so101_demo_py/test/test_parallel_batch_broker.py
git diff --cached --check
git commit -m "feat: add fair bounded perception broker"
```

### Task 7: 接入真实 YOLO/Grounded-SAM 进程并只返回模型结果

**Files:**

- Create: `src/so101_demo_py/src/cli/parallel_perception_broker.py`
- Create: `src/so101_demo_py/src/runtime/parallel_perception_runtime.py`
- Create: `src/so101_demo_py/src/adapters/perception/errors.py`
- Create: `src/so101_demo_py/docker/parallel-perception/Dockerfile`
- Create: `scripts/parallel-perception-container.sh`
- Create: `src/so101_demo_py/test/test_parallel_perception_runtime.py`
- Create: `src/so101_demo_py/test/test_parallel_perception_container.py`
- Modify: `src/so101_demo_py/src/adapters/perception/yolo_seg.py`
- Modify: `src/so101_demo_py/src/adapters/perception/grounded_sam.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:** Consumes immutable RGB snapshot, `DetectionQuery`, model paths/hashes, socket endpoint. Produces normalized detection candidates/masks and model provenance; depth localization、TF、`/cup_pose` publish remain in Worker。Broker 固定运行在新建的 combined CUDA container，不依赖 host Python 同时具备两套模型依赖。

- [ ] **Step 1: 写 fake-detector integration 和异常分类测试。** 测试要求启动时通过 `detector_factory.build_detector` 各构造一次 YOLO 和 Grounded-SAM，预热成功后才写 ready receipt。每个请求带闭合 `execution_kind=attempt|validation`：execute 只能使用 `/inputs/{worker_id}/attempts/{point_id}/{attempt_id}/working/perception/input/rgb.npy` 并绑定已 ACK 的 `ATTEMPT_STARTED`；plan-only 只能使用 `/inputs/{worker_id}/validations/{point_id}/{validation_id}/working/perception/input/rgb.npy` 并绑定已 ACK 的 `VALIDATION_STARTED`。两种路径 resolve 后都必须仍位于只读 input root。逐次核对 RGB bytes SHA256、shape/source stamp；返回值必须可 canonical JSON 序列化，mask 使用无损 RLE 并能还原原尺寸。增加真实 validation 目录请求成功，以及 attempt kind + validation path、validation kind + attempt path、错误 ID/event identity 全部被拒绝的测试。

新增闭合异常类型：`DeterministicModelResultError` 只表示模型已完成计算、但 boxes/classes/confidence/mask 的输出 schema、有限值、尺寸或后处理契约不合法，对应 `MODEL_ERROR`；空候选是 `NORMAL_REJECTION`。`ModelRuntimeInfrastructureError` 包含模型 load/warmup、CUDA OOM、CUDA device/context/driver、内存分配、容器退出、socket 错误、deadline 和所有未分类 runtime exception，对应 `INFRA_ERROR` 并把 Broker 标记 unhealthy。补测 YOLO/Grounded-SAM OOM、YOLO `INFERENCE_FAILED`、未知 RuntimeError 均 INVALID；确定输出契约错误才进入 MODEL_ERROR；两种 `MODEL_ERROR + NORMAL_REJECTION` 排列仍为 FAILED/PERCEPTION_MODEL_ERROR。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_perception_runtime.py src/so101_demo_py/test/test_parallel_perception_container.py -q
```

- [ ] **Step 3: 实现 runtime/CLI 和 combined image。** 复用 `adapters/perception/detector_factory.py`，不复制模型加载代码。image 以当前 pinned ROS Jazzy base digest 构建，安装并验证 `torch==2.13.0+cu130`、`torchvision==0.28.0+cu130`、`ultralytics==8.4.115`、`transformers==4.56.2`、`scipy==1.17.1`、`huggingface-hub==0.34.4`、`safetensors==0.6.2`、`tokenizers==0.22.0`、`numpy==1.26.4`、`Pillow==12.3.0`、`PyYAML==6.0.2`，并安装当前 `so101_demo_py`。tag 固定为 `so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1`；build 后读取 Docker image ID 和 Dockerfile/lock/source hash，写入 Broker ready receipt 和每个 batch manifest。

Broker argv 固定参数包括 `--endpoint /runtime/perception.sock --input-root /inputs --ready-receipt /runtime/ready.json --yolo-weights /models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --yolo-model-id plastic-cup-yolo11n-seg-v1 --yolo-imgsz 640 --grounded-root /models/grounded --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --device cuda --no-cpu-fallback`，以及 Task 1 的七个 Grounded 阈值。wrapper 必须显式接收本次 CLI 已 resolve 的 `batch_root`；无论它是 `single-plan`、`live-small` 还是 `live-20`，只挂载 `batch_root/ipc:/runtime:rw` 和 `batch_root/workers:/inputs:ro`，不得退回任务级 `$PARALLEL_EVIDENCE/ipc`/`workers`。

container 用 `--gpus all --network none --ipc private --read-only --security-opt no-new-privileges --user "$(id -u):$(id -g)"`。wrapper 枚举 `/dev/nvidia*` 的实际 group ID，以重复 `--group-add` 传入并记录；没有设备或 group 无法读取时准入失败。`batch_root/ipc` 由 host 用户以 0700 创建，Broker 以同 UID:GID 创建 owner 相同的 0600 socket 和 ready receipt；`/tmp` 是同 UID/GID 的容器 tmpfs。两套模型目录只读挂载。socket/ready 路径不依赖 ROS graph。任何路径未知、软链接、越界、owner/mode 不符或 image ID 漂移都拒绝；不能靠放宽 0700/0600 权限绕过。

- [ ] **Step 4: GREEN、build 和完整模型 smoke。** 新 console entry point 先 rebuild/source；container test 用 `tmp_path/single-plan` 和 `tmp_path/live-small` 两个真实子目录验证 host `batch_root/ipc|workers` 到 container `/runtime|inputs` 的一一映射，同时验证 `--user`、所有 GPU `--group-add`、socket owner/mode、host 非 root client 连接和 ready receipt 读回。随后用上一轮 P01 的 `/data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/batches/formal-reset20-candidate-002/points/01-task_start/sensor-snapshot/rgb.png` 同时调用两模型的 `--smoke-input` 模式，无 ROS、无仿真、无动作；保存 image ID、ready/model provenance、两个 outcome 和 latency。

```zsh
parallel_test src/so101_demo_py/test/test_parallel_perception_runtime.py src/so101_demo_py/test/test_parallel_perception_container.py -q
"$PARALLEL_PYTHON" -m colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
scripts/parallel-perception-container.sh build --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
scripts/parallel-perception-container.sh smoke --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --input /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/batches/formal-reset20-candidate-002/points/01-task_start/sensor-snapshot/rgb.png --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --output "$PARALLEL_EVIDENCE/reports/broker-smoke.json"
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/cli/parallel_perception_broker.py src/so101_demo_py/src/runtime/parallel_perception_runtime.py src/so101_demo_py/src/adapters/perception/errors.py src/so101_demo_py/src/adapters/perception/yolo_seg.py src/so101_demo_py/src/adapters/perception/grounded_sam.py src/so101_demo_py/docker/parallel-perception/Dockerfile scripts/parallel-perception-container.sh src/so101_demo_py/test/test_parallel_perception_runtime.py src/so101_demo_py/test/test_parallel_perception_container.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat: serve shared parallel perception models"
```

### Task 8: 分配并验证 Worker 隔离资源

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/resources.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_resources.py`

**Interfaces:** Consumes batch config, evidence root and live resource/domain probes. Produces immutable `WorkerResources` with `ROS_DOMAIN_ID`, `simulation_port="not_applicable"`, `bridge_port="not_applicable"`, session ID, ROS_HOME/ROS_LOG_DIR/temp, socket namespace and Worker root.

- [ ] **Step 1: 写碰撞与资源阈值测试。** 两个 slot 的所有标识必须不同；现有 ROS domain/端口/目录冲突时 fail closed；`GZ_PARTITION` 永远是 `not_applicable`；Worker replacement 复用 slot 资源但 generation 增加；资源不足不得静默把 3 Worker 降为 2。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_resources.py -q
```

- [ ] **Step 3: 实现 allocator/probe。** domain/port 范围来自冻结 config。目录用 `mkdir(exist_ok=False)`，socket path 检查 Unix 长度限制，环境白名单构造而不是继承任意 `ROS_*`。记录 CPU、RAM、GPU free memory 和阈值；默认 2 Worker，3 Worker 必须显式参数且通过准入。

- [ ] **Step 4: GREEN 和 ai-station dry admission。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_resources.py -q
"$PARALLEL_PYTHON" -m so101_demo.parallel_batch.resources --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --worker-count 2 --evidence-root "$PARALLEL_EVIDENCE/resource-dry" --dry-run
```

dry-run 不创建 MuJoCo/MoveIt 进程；输出 resource manifest 和退出码。

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/resources.py src/so101_demo_py/test/test_parallel_batch_resources.py
git diff --cached --check
git commit -m "feat: allocate isolated parallel worker resources"
```

### Task 9: 实现 Worker 双门控、attempt 授权和恢复状态机

**Files:**

- Create: `src/so101_demo_py/src/parallel_batch/worker.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_worker.py`

**Interfaces:** Consumes coordinator/broker/runtime ports. Produces `ParallelWorker.run()`, independent watchdog heartbeat, `worker_ready_gate`, `point_initial_gate`, sealed result request and recovery receipt。

- [ ] **Step 1: 写 fake runtime 全状态测试。**

```python
def test_worker_waits_for_attempt_ack_before_perception_or_motion(fake):
    fake.coordinator.withhold_attempt_ack = True
    worker = ParallelWorker(fake.ports())
    worker.run_one()
    assert fake.runtime.calls == [
        "worker_ready_gate", "reset_point", "point_initial_gate"
    ]
    assert "request_model" not in fake.runtime.calls
    assert "submit_motion" not in fake.runtime.calls
```

这里有两层 execute 授权：`LEASE_GRANTED` 已持久化并 ACK 后，Worker 才能为该点执行 reset 和 `point_initial_gate`；`ATTEMPT_STARTED` 已持久化并 ACK 后，才允许请求模型或提交正式专家动作。plan-only 在相同 initial gate 后改用 `VALIDATION_STARTED` ACK，允许模型与规划但禁止 ActionClient goal；dry-run 不启动物理 runtime，只验证 lease/调度并走 validation event。另测 lease ACK 被扣留时 runtime 只有 `worker_ready_gate`，不得 reset。补测 heartbeat 在线程/进程阻塞规划时仍发送；ACK/lease 过期停止新动作并 cancel+confirm；ready gate 不验证下一点；point gate 在领取后验证 exact point、canonical joints、无 goal/attachment/contact/stale node、reset epoch/session 和新鲜 source frame；失败 seal 后才恢复；恢复成功继续抢点；恢复失败 quarantine；最后点 recovery failure 不改写点结果但阻止 cleanup。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_worker.py -q
```

- [ ] **Step 3: 实现状态机。** watchdog 与规划/GPU 调用分离；每个有副作用的方法前检查 lease token。execute 顺序固定为 `worker_ready_gate → LEASE_GRANTED ACK → reset_point → point_initial_gate → START_ATTEMPT request → ATTEMPT_STARTED ACK → model request → pose admission → expert action`。attempt ACK 前已经允许与该 lease 绑定的 reset/initial gate，但不允许推理或正式动作。plan-only 把后半段替换为 `START_VALIDATION → VALIDATION_STARTED ACK → model → pose admission → plans → VALIDATION_COMMITTED`；dry-run 只走 `START_VALIDATION → scheduler trace → VALIDATION_COMMITTED`。pose acceptance 后只走同一模型结果和专家链。异常先停新动作、确认 controller goal，再根据 run mode 和是否已授权/是否能证明未动作分类 physical INVALID/INDETERMINATE 或 validation INVALID；两套结果不可互转。

- [ ] **Step 4: GREEN。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_worker.py src/so101_demo_py/test/test_parallel_batch_coordinator.py -q
```

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/parallel_batch/worker.py src/so101_demo_py/test/test_parallel_batch_worker.py
git diff --cached --check
git commit -m "feat: run fenced parallel validation workers"
```

### Task 10: 接入独立 headless MuJoCo/MoveIt Worker runtime

**Files:**

- Create: `src/so101_demo_py/src/runtime/parallel_worker_runtime.py`
- Create: `src/so101_demo_py/test/test_parallel_worker_runtime.py`
- Modify: `src/so101_demo_py/src/runtime/task_stack.py`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/test/test_task_station_launch.py`
- Modify: `src/so101_demo_py/test/test_launch_composition.py`

**Interfaces:** Consumes `WorkerResources`, `run_mode`, existing reset/reachability/dynamic expert primitives and Broker detection result. Produces owned process manifest, `worker_ready_gate`, `reset_and_validate_point`, `localize_and_admit_pose`, `plan_expert`, `execute_expert`, `capture_terminal`, `recover`, `shutdown_owned`.

- [ ] **Step 1: 写 command-construction/ownership tests。** Linux `headless=true,sensor_rendering=true,include_teleop=false` 必须生成 task camera、controller 和 MoveIt actions；macOS 的 `headless=true` 仍拒绝；任何平台的 `headless=true,sensor_rendering=false` 或 `include_teleop=true` 都拒绝。两个 runtime 的 `session_id`、ROS domain、目录互不相同；只能停止 manifest 登记的 PGID。分别断言：dry-run runtime 不生成 ROS consumer argv；plan-only runtime 调用纯规划 adapter 且不带 `--execute`；execute runtime 的 consumer argv 精确包含 `--backend mujoco --mode execute --execute --expected-reset-epoch`。旧 macOS `default_task_station_config(headless=false)` 和顺序 CLI 测试保持不变。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_worker_runtime.py src/so101_demo_py/test/test_task_stack.py src/so101_demo_py/test/test_task_batch_runtime.py src/so101_demo_py/test/test_task_station_launch.py src/so101_demo_py/test/test_launch_composition.py -q
```

- [ ] **Step 3: 实现 Linux headless profile 和三种 run mode。** `build_task_station_launch_description` 把 `headless` choices 改为 true/false；`_configured_task_station_actions` 用 `platform.system()` 执行上述 Linux/macOS约束，并强制 headless 时 `sensor_rendering=true`、`include_teleop=false`。底层 `_mujoco_stack_actions` 已能把 `headless` 与 `sensor_rendering` 分开传入 URDF，继续复用，不创建第二套 launch。`task_stack.py` 提取通用 owned process-group primitive，保留 macOS 默认 wrapper。

每个 execute/plan-only Worker 启动一套 headless task station，等待 controllers/MoveIt/joint_states/planning scene，记录 PID/PGID/cmdline/start time。`run_mode=dry_run` 使用不启动 ROS/MuJoCo 的 `DryRunWorkerRuntime`；`plan_only` 完成 reset、真实 RGB-D/Broker localization 后，通过现有 `RosDynamicPlanner` 和 dynamic target resolver 对完整专家 motion prefix 逐段规划，但不创建 ActionClient goal；`execute` 才启动现有 dynamic consumer 并传 `--mode execute --execute`。不得把现有 `RosTaskBatchRuntime.start_consumer()` 改成多模式或破坏顺序 CLI。

detector 部分由 Broker 返回，Worker 执行 depth/TF/localization、发布 Worker-local `/cup_pose` 并写 `POSE_ACCEPTED`。headless 的关键视觉证据是 `sensor_rendering=true` 的固定 task camera：初始和终态各等待 source stamp 新于相应 reset/动作边界的 `/task_camera/color`，保存 `initial-rgb.png` 与 `terminal-rgb.png`；深度、TF 和物理状态另存数值证据。不得启动 teleop 或共享 GUI。

- [ ] **Step 4: GREEN 与 launch 参数读回。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_worker_runtime.py src/so101_demo_py/test/test_task_stack.py src/so101_demo_py/test/test_task_batch_runtime.py src/so101_demo_py/test/test_task_station_launch.py src/so101_demo_py/test/test_launch_composition.py -q
"$PARALLEL_PYTHON" -m colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
ros2 launch so101_demo_py so101_mujoco_task_station.launch.py --show-args
```

读回必须显示 headless true/false、sensor_rendering 只允许 true，且默认仍为 `headless=false,sensor_rendering=true`。单 Worker dry/plan-only 现场验收移到 Task 11，因为该任务才提供最终 CLI。

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/runtime/parallel_worker_runtime.py src/so101_demo_py/src/runtime/task_stack.py src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/test/test_parallel_worker_runtime.py src/so101_demo_py/test/test_task_station_launch.py src/so101_demo_py/test/test_launch_composition.py
git diff --cached --check
git commit -m "feat: isolate MuJoCo parallel worker stacks"
```

### Task 11: 实现鉴权 IPC、进程监督和用户 CLI

**Files:**

- Create: `src/so101_demo_py/src/runtime/parallel_ipc.py`
- Create: `src/so101_demo_py/src/runtime/parallel_processes.py`
- Create: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_cli.py`
- Create: `src/so101_demo_py/test/test_parallel_ipc.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:** Adds console script `so101_parallel_batch`. CLI accepts `--points`, repeatable `--point-id` selection, `--config`, `--batch-id`, `--worker-count`, `--max-points-per-worker`, `--evidence-root`, `--broker-image`, YOLO/Grounded model arguments and `--run-mode {dry_run,plan_only,execute}`. Omitted `--point-id` means the complete catalog；each supplied ID must occur exactly once in the frozen catalog，selection hash is the canonical ordered ID list hash。

- [ ] **Step 1: 写 CLI/IPC 失败测试。** 覆盖 `N*K<points`、重复 batch、相对 evidence root、点/模型 hash mismatch、未知 run mode、socket peer token 错误、超长/超大 frame、partial frame、coordinator ACK 丢失、子进程提前退出和 Ctrl-C cleanup。断言 `worker_count=2,K=10` 原样进入 batch manifest，不能静默固定分片。dry-run/plan-only 的所有 validation 成功且 cleanup 成功时退出 0，任一 validation/cleanup 失败时退出 1；execute 只有 `qualification_passed=true` 才退出 0。非 execute aggregate 必须是 `qualification_applicable=false,qualification_passed=false`，physical point status 均为 UNRUN。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_cli.py src/so101_demo_py/test/test_parallel_ipc.py -q
```

- [ ] **Step 3: 实现。** Unix sockets 位于 `evidence_root/ipc/`，目录 0700、socket 0600；每个 Worker 用 coordinator 生成的 256-bit token，消息含 schema version/epoch/generation/lease/request/idempotency key。长度前缀有限制，canonical JSON 拒绝多余字段。supervisor 只管理自身启动并登记的 Broker/Worker PGID；SIGINT/SIGTERM 时先停止新 lease、cancel/confirm goal、请求 Worker recovery，再按单个 PGID 受控退出。

- [ ] **Step 4: GREEN、help、重复启动保护和单 Worker现场门。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_cli.py src/so101_demo_py/test/test_parallel_ipc.py -q
"$PARALLEL_PYTHON" -m colcon build --packages-select so101_demo_py --symlink-install
source install/setup.zsh
ros2 run so101_demo_py so101_parallel_batch --help
ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id single-dry-20260912-v1 --worker-count 1 --max-points-per-worker 1 --evidence-root "$PARALLEL_EVIDENCE/single-dry" --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode dry_run
ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id single-plan-20260912-v1 --worker-count 1 --max-points-per-worker 1 --evidence-root "$PARALLEL_EVIDENCE/single-plan" --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode plan_only
```

dry-run 必须不启动 ROS/MuJoCo/Broker；plan-only 必须启动一套 headless stack 和 Broker、产生真实 reset/initial/POSE_ACCEPTED/完整 prefix planning/cleanup receipts，但 controller goal 数为零。两者都核对 `validation_passed=true`、`qualification_applicable=false`、`qualification_passed=false`、physical UNRUN 和 owned process 清零。任何 CALIBRATION_REQUIRED、stale install 或模型环境错误先修复，不算有效业务失败。

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/src/runtime/parallel_ipc.py src/so101_demo_py/src/runtime/parallel_processes.py src/so101_demo_py/src/cli/mujoco_parallel_batch.py src/so101_demo_py/test/test_parallel_batch_cli.py src/so101_demo_py/test/test_parallel_ipc.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat: expose parallel validation coordinator"
```

### Task 12: 对提交窗口、lease 和公共依赖做故障注入

**Files:**

- Create: `src/so101_demo_py/test/test_parallel_batch_crash_recovery.py`
- Create: `src/so101_demo_py/test/test_parallel_batch_fault_injection.py`
- Create: `scripts/inject_so101_parallel_fault.py`
- Create: `src/so101_demo_py/test/test_inject_so101_parallel_fault.py`
- Modify: `src/so101_demo_py/src/parallel_batch/coordinator.py`
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/broker.py`

**Interfaces:** Injects deterministic crash/fault hooks around journal/seal/ACK boundaries; no production CLI flag may weaken safety gates.

- [ ] **Step 1: 写参数化 crash matrix。** 每个边界至少覆盖 before/after：`LEASE_GRANTED` fsync、K debit ACK、`ATTEMPT_STARTED` fsync/ACK、working fsync、atomic seal、`RESULT_COMMITTED` fsync/ACK、`LEASE_EXPIRED`、recovery receipt。重启后断言不重复扣 K、不双租、不覆盖首次结果。

```python
def test_expired_then_late_seal_then_restart_is_never_accepted(harness):
    lease = harness.start_attempt()
    harness.expire_and_fsync(lease)
    harness.late_seal(lease, status="PASSED")
    recovered = harness.restart_coordinator()
    assert recovered.point(lease.point_id).status == "INDETERMINATE"
    assert recovered.audit_contains("LATE_RESULT_REJECTED")
```

另测只有可信账本证明 `ATTEMPT_STARTED` 从未授权时才 INVALID/requeue；无法证明时 INDETERMINATE；Broker crash 暂停新 lease，恢复后继续；deadline 未恢复则 `SHARED_DEPENDENCY_UNAVAILABLE`；Worker crash 后旧 generation 结果永不 admission。`inject_so101_parallel_fault.py` 只接受本任务 batch root、`worker-01|worker-02|worker-03|broker` 和 `TERM`；它从 supervisor manifest 读取 PID/PGID/start time/batch ID，逐项比对 `/proc` 后才向该 PGID 发信号，归属不一致即拒绝。测试 monkeypatch `os.killpg`，不得真的杀进程。

- [ ] **Step 2: RED。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_crash_recovery.py src/so101_demo_py/test/test_parallel_batch_fault_injection.py src/so101_demo_py/test/test_inject_so101_parallel_fault.py -q
```

- [ ] **Step 3: 只补齐被测试暴露的恢复逻辑。** 故障 hook 通过依赖注入提供，不暴露为 execute 模式参数。持久事件优先级固定：历史 `RESULT_COMMITTED`/`LEASE_EXPIRED`/点终态不可被目录扫描改写；未知事实按更保守的 INDETERMINATE 裁决。

- [ ] **Step 4: GREEN 与重复运行。**

```zsh
parallel_test src/so101_demo_py/test/test_parallel_batch_crash_recovery.py src/so101_demo_py/test/test_parallel_batch_fault_injection.py src/so101_demo_py/test/test_inject_so101_parallel_fault.py -q
parallel_test src/so101_demo_py/test/test_parallel_batch_crash_recovery.py src/so101_demo_py/test/test_parallel_batch_fault_injection.py src/so101_demo_py/test/test_inject_so101_parallel_fault.py -q
```

两次结果都必须稳定通过，且第二次使用新的 scratch。

- [ ] **Step 5: 提交。**

```zsh
git add src/so101_demo_py/test/test_parallel_batch_crash_recovery.py src/so101_demo_py/test/test_parallel_batch_fault_injection.py scripts/inject_so101_parallel_fault.py src/so101_demo_py/test/test_inject_so101_parallel_fault.py src/so101_demo_py/src/parallel_batch/coordinator.py src/so101_demo_py/src/parallel_batch/worker.py src/so101_demo_py/src/parallel_batch/broker.py
git diff --cached --check
git commit -m "test: harden parallel batch crash recovery"
```

### Task 13: 建立实验账本并完成 package gate

**Files:**

- Create: `docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md`

本任务不修改源码。package gate 失败时回到对应实现任务补 RED/GREEN 和 scoped fix commit，再重新建立 package-gate 实验。

**Interfaces:** The ledger is the single human-readable index for evidence and decisions; it does not replace sealed artifacts or coordinator events.

- [ ] **Step 1: 填写账本，不保留模板占位。** 记录 worktree、branch、base/current commit、唯一 evidence root、模型/点位/config/source/install hashes、保留进程、已确认结论、下一实验。为 package gate 建立 `EXP-001`，状态先 PLANNED，命令启动后 RUNNING，读回后落 VALID/INVALID。

- [ ] **Step 2: 在全新 scratch 跑完整普通 gate。**

```zsh
parallel_package_gate() {
  local package_run test_exit result_exit
  package_run=$(mktemp -d "$PARALLEL_EVIDENCE/scratch/package-gate-XXXXXXXX") || return 1
  mkdir "$package_run/tmp" || return 1
  export TMPDIR="$package_run/tmp" TMP="$package_run/tmp" TEMP="$package_run/tmp"
  "$PARALLEL_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve() == Path(os.environ["TMPDIR"]).resolve()' || return 1
  "$PARALLEL_PYTHON" -c 'import colcon_core,pytest,sys; print(sys.executable, colcon_core.__file__, pytest.__file__)' > "$package_run/python-provenance.txt" || return 1
  printf '%s\n' "$package_run" >> "$PARALLEL_EVIDENCE/reports/scratch-deletion-candidates.txt" || return 1
  "$PARALLEL_PYTHON" -m colcon build --packages-select so101_demo_py --symlink-install > "$package_run/build.log" 2>&1 || return 1
  source /data/work/ws_moveit/.worktrees/parallel-multipoint-v1/install/setup.zsh || return 1
  /usr/bin/time -p -o "$package_run/test.time" "$PARALLEL_PYTHON" -m colcon test --packages-select so101_demo_py --pytest-args test > "$package_run/test.log" 2>&1
  test_exit=$?
  "$PARALLEL_PYTHON" -m colcon test-result --verbose > "$package_run/test-result.log" 2>&1
  result_exit=$?
  printf '%s\n' "$test_exit" > "$package_run/test.exit"
  printf '%s\n' "$result_exit" > "$package_run/test-result.exit"
  sed -n '1,240p' "$package_run/test.log"
  sed -n '1,240p' "$package_run/test-result.log"
  (( test_exit == 0 && result_exit == 0 ))
}
parallel_package_gate
```

`$PARALLEL_PYTHON -m colcon` 保证 colcon 和 tempfile 校验使用同一个解释器；package 的 pytest 命令和实际收集数还要从 `build/so101_demo_py` 的测试日志/JUnit 读回。必须记录 elapsed、exit code 和 test-result errors/failures；准备步骤任一失败都在 test 前返回。不得运行 `benchmark_test`。

- [ ] **Step 3: 校验 provenance 并重建最终 Broker image。** 从 sourced worktree overlay 读取 console script/module/config 的绝对路径与 SHA256，确认没有 source canonical 旧 install。运行 `git diff --check`、`python3 -m compileall` 和点位/模型哈希复核。由于 Task 12 可能修改 Broker，使用同一 tag 重建 combined image，再执行 Task 7 的双模型 smoke；把最终 image ID 写入 source manifest。Task 14 和 15 必须使用这个相同 image ID，不能只比较可变 tag。

```zsh
scripts/parallel-perception-container.sh build --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
docker image inspect --format '{{.Id}}' so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 > "$PARALLEL_EVIDENCE/reports/final-broker-image-id.txt"
scripts/parallel-perception-container.sh smoke --image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --input /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/reset-world-20/8a87dc3e-9836-4feb-8f3c-3286b1efcaff/batches/formal-reset20-candidate-002/points/01-task_start/sensor-snapshot/rgb.png --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --output "$PARALLEL_EVIDENCE/reports/final-broker-smoke.json"
```

- [ ] **Step 4: 更新账本并提交。**

```zsh
git add docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md
git diff --cached --check
git commit -m "docs: register parallel validation evidence"
```

若 package gate 修复了源码，先按对应任务文件边界另做 scoped fix commit，再更新账本；不能把大量修复藏进 docs commit。

### Task 14: 两 Worker 小样本 live 验证动态抢点和隔离

**Files:**

- Modify: `docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md`
- Runtime evidence only: `$PARALLEL_EVIDENCE/live-small/`

**Interfaces:** Executes installed `so101_parallel_batch`; no source behavior changes during counted batch.

- [ ] **Step 1: 先写 `EXP-002` PLANNED。** 使用完整 catalog，并通过 `--point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right` 选择 P01、P02、P09、P18；不生成另一份 YAML。`worker_count=2,max_points_per_worker=2`，lifecycle 为 `ISOLATED_STACK`。冻结 executable source tree/install/config/policy/scene/model/container/catalog hash 和四项 canonical selection hash、资源阈值、成功/失败/无效判据。

- [ ] **Step 2: 运行 execute。** 使用下面的唯一 batch ID，两个 Worker 各自 headless；命令输出和退出码写入 `live-small-command.log/.exit`。

```zsh
ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --point-id task_start --point-id cup_test_forward_5cm --point-id sample_05_near_center --point-id sample_14_far_right --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-small-20260912-v1 --worker-count 2 --max-points-per-worker 2 --evidence-root "$PARALLEL_EVIDENCE/live-small" --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute > "$PARALLEL_EVIDENCE/reports/live-small-command.log" 2>&1
small_exit=$?
printf '%s\n' "$small_exit" > "$PARALLEL_EVIDENCE/reports/live-small-command.exit"
sed -n '1,240p' "$PARALLEL_EVIDENCE/reports/live-small-command.log"
```

启动后读取 resource manifest，验证两个 ROS domain、session、PID tree、ROS_HOME、socket 和 attempt 目录互不相同。

- [ ] **Step 3: 验证动态抢点。** 不要求固定 2+2 分片；只要求每个 slot 不超过 K、任一点只有一个有效 lease、空闲 Worker 能领取全局队列下一点。若自然出现有效点失败，验证该 Worker seal+recovery 后可继续；不要为了制造失败放宽或改坏安全配置。

- [ ] **Step 4: 做一次受控 fault run `EXP-003`。** 在 dry-run 或 plan-only 模式，仅对 supervisor manifest 登记的单个 Worker PGID 发送 SIGTERM，验证 generation fencing、旧 request 取消、其他 Worker 继续及无双租；不得在持杯 execute 阶段杀进程。再以同样的 ownership 边界停止 Broker，验证暂停新 lease 而非消耗 K。故障注入不通过 execute CLI 暴露测试开关。

- [ ] **Step 5: 物理和视觉读回。** 对 execute 的每个有效点核对 reset/canonical joints、fresh RGB-D、POSE_ACCEPTED、MoveIt trajectory/controller、杯子最终 pose、table support、无 fingertip contact、无 attached object、retreat 和新鲜离屏帧。用 `$gui-capture` 的图像检查原则逐图查看，不以文件存在代替目视。

- [ ] **Step 6: 收尾和判定。** 所有 owned PID/PGID 已停止，controller goal 为零，Worker recovery receipts 完整，batch cleanup true。更新 ledger 为 VALID 或 INVALID，列出 retained/archived/deletion candidates；不删除。

- [ ] **Step 7: 仅提交账本。**

```zsh
git add docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md
git diff --cached --check
git commit -m "test: validate two-worker point scheduling"
```

小样本未通过时停止 20 点正式批次。修复必须回到对应 Task 的 RED/GREEN 和新 commit，再重新跑一个全新小样本 batch，旧结果保留为审计证据。

### Task 15: 完整运行 20 点并形成资格结论

**Files:**

- Modify: `docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md`
- Runtime evidence only: `$PARALLEL_EVIDENCE/live-20/`

**Interfaces:** Final acceptance consumes one immutable 20-point batch; produces aggregate summary and per-point sealed evidence, not a merged set of retries.

- [ ] **Step 1: 准入。** 只有 Task 13 package gate 和 Task 14 双 Worker live 都 VALID 才建立 `EXP-004`。重新读回无活动旧 stack、GPU/CPU/RAM、executable source tree/install/config/policy/scene/model/container/catalog hashes。允许相对 Task 14 改变的只有 selection（从四点变为完整 catalog）、N/K、batch ID、evidence 子目录和 docs-only ledger commit；这些差异逐项写入 EXP-004。`src/`、`scripts/`、相关 third-party gitlink、install、模型、container、policy、scene 或 catalog 任一变化，都必须先回到新的双 Worker 小样本，不能直接进入 20 点。

- [ ] **Step 2: 冻结启动参数。** 默认 `--worker-count 2 --max-points-per-worker 10`。只有已有双 Worker 资源实测明确支持 3 Worker，才可另建新实验使用 3；不能在同一 batch 动态改变 N/K。使用完整冻结 20 点 manifest 和新 batch ID。

- [ ] **Step 3: 执行一次完整批次。** 运行过程中不改源码、install、配置、阈值、模型或点位。Worker 失败恢复后继续抢剩余点；点位 FAILED/INDETERMINATE 不在本轮重试。监控只读 aggregate、heartbeat、GPU 和进程归属，不向运行中的 Worker 注入第二套命令。命令输出和退出码写入 `live-20-command.log/.exit`：

```zsh
ros2 run so101_demo_py so101_parallel_batch --points src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --config src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --batch-id parallel-20-20260912-v1 --worker-count 2 --max-points-per-worker 10 --evidence-root "$PARALLEL_EVIDENCE/live-20" --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute > "$PARALLEL_EVIDENCE/reports/live-20-command.log" 2>&1
live20_exit=$?
printf '%s\n' "$live20_exit" > "$PARALLEL_EVIDENCE/reports/live-20-command.exit"
sed -n '1,240p' "$PARALLEL_EVIDENCE/reports/live-20-command.log"
```

- [ ] **Step 4: 逐点审计。** 对 P01–P20 每点验证：唯一 lease/attempt、有效初始门、YOLO-first 路径（或允许的 Grounded 回退链）、POSE_ACCEPTED identity、规划与 controller 反馈、物理抓放/最终位置、空 attachment、stable support、retreat、sealed manifest 全文件 hash 和新鲜视觉帧。抽查不足以声明 20/20。

- [ ] **Step 5: 汇总门。** 只有以下条件同时满足才写“20 个点都回归通过”：20 个点均 `PASSED`；`coverage_complete=true`；`execution_complete=true`；`batch_cleanup_complete=true`；`qualification_passed=true`；没有未确认 goal、活动 owned process、重复点、缺文件/hash mismatch；同一批 source/install/config/policy/scene/model/point hashes。

- [ ] **Step 6: 若不通过，保持真实分母。** FAILED、INDETERMINATE、UNRUN、INVALID attempts、capacity/broker/cleanup 状态逐项报告。需要修复时先结束本 batch，追加新实验和新 batch ID；修复后必须重新运行全部 20 点，不能只补失败点凑 20/20。

- [ ] **Step 7: 更新账本并提交最终证据索引。**

```zsh
git add docs/experiments/so101-parallel-multipoint-validation-experiment-ledger.md
git diff --cached --check
git commit -m "test: record parallel 20-point qualification"
```

最终不 push。向用户报告 branch/commit、package gate、small/live-20 batch IDs、20 点状态、模型使用统计、Worker 分配/K、qualification 字段、证据根、retained/archived/deletion candidates 和仍存风险。

---

## 计划完成前自检

- [ ] 设计文档第 3–13 节的每项状态、持久化、fencing、感知、容量、恢复和验收规则都映射到至少一个实现任务及一个测试。
- [ ] 全文没有未决占位符或“测试上述逻辑”一类不可执行步骤。
- [ ] `PointStatus`、`AttemptStatus`、`WorkerState`、model outcome 和 batch flags 在契约、事件、IPC、sealed manifest、aggregate、CLI 退出码中名称一致。
- [ ] `LEASE_GRANTED`、`ATTEMPT_STARTED`、`RESULT_COMMITTED` 都遵循先 fsync 后 ACK；late seal、unknown start、coordinator restart 有明确测试。
- [ ] lease 续期不会越过当前阶段或 5400 s 批次硬期限；heartbeat 正常但阶段卡死的测试仍会 fail closed。
- [ ] YOLO 成功后没有 Grounded-SAM；正常拒绝、MODEL_ERROR、INFRA_ERROR 和 timeout 的矩阵没有互相覆盖。
- [ ] Broker 只挂载当前 resolved batch root，并以 host UID:GID 和 GPU supplementary groups 运行；0700 目录和 0600 socket 可由非 root Worker 连接。
- [ ] 初始状态证据分为 `worker_ready_gate` 和领取后的 `point_initial_gate`；最后一点 recovery failure 不改写点结果。
- [ ] dry-run/plan-only 只产生 validation 结果，physical point 保持 UNRUN，任何数量的 validation success 都不能令 `qualification_passed=true`。
- [ ] 所有 ai-station pytest/colcon test 使用唯一 NVMe scratch，并记录为删除候选；没有自动删除证据。
- [ ] 旧顺序 CLI 和用户已有 dirty files 有回归测试或显式保留；没有 push、实机动作、宽泛进程清理或 benchmark suite。

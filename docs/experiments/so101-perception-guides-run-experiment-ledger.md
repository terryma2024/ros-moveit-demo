# SO-101 perception guides end-to-end run experiment ledger

```yaml
task_id: so101-perception-guides-run-20260921
goal: 在当前 main checkout 上，按 docs/guides 的两篇导读各完成一次真实的 MuJoCo 感知 + 动态抓放端到端运行（YOLO-Seg 与 Grounded SAM），权重来自用户 Hugging Face 仓库
success_contract: 两篇导读各一次 run_mode=execute 的端到端运行，退出码 0，感知发布唯一 plastic_cup 的 /cup_pose 且证据目录完整，随后 MoveIt/controller/MuJoCo 物理抓放通过，并有本轮新鲜截图
worktree: /home/matianyi/Projects/ros-moveit-demo
branch: main
base_commit: e73543144aa6647031a53138d996fe9620fbb14b
current_commit: e73543144aa6647031a53138d996fe9620fbb14b
evidence_root: /data/work/so101-evidence/perception-guides-run/20260921-e7354314
development_source_root: /tmp/so101-debug-so101-perception-guides-run
deployment_artifacts:
  yolo_weights: /data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_sam_repo: /data/work/models/so101-perception/grounded-sam-cup-pickplace
  grounded_sam_bundle: /data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle
  grounded_sam_manifest_sha256: b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05
  grounded_sam_revision: 52b8334358e5ff11f94f10f7c14b1697ef44d964
  grounded_sam_venv: /data/work/venvs/so101-grounded-sam
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  dependency_underlay: /home/matianyi/Projects/ws_mujoco_ros2_control_fork/install
confirmed_conclusions:
  - CONF-001 Hugging Face 仓库 zjumty/so101-yolo11n-seg-plastic-cup 的 best.pt 下载后 SHA256=f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781，与导读 19 节固定值逐字一致，来自 2026-09-21 下载与 sha256sum 回读
  - CONF-002 Hugging Face 仓库 zjumty/so101-grounded-sam-cup-pickplace 的当前 main SHA 等于导读 17 节固定 revision 52b8334358e5ff11f94f10f7c14b1697ef44d964；`sha256sum -c SHA256SUMS` 对全部已下载文件返回 OK，只有被刻意排除的 datasets tarball 报 missing
  - CONF-003 EXP-002 导读 18 节的 `verify_model_bundle()` 读回 root、manifest SHA b55bb601…ed05、detector_dir 与 segmenter_dir 全部成功
  - CONF-004 EXP-002 宿主机 ROS entrypoint 注入 venv site-packages 后同时导入 rclpy(/opt/ros/jazzy)、torch 2.13.0+cu130、transformers 4.56.2、mujoco 3.12.0，`torch.cuda.is_available()` 为 True，RTX 5060 Ti 真实张量运算通过
  - CONF-005 EXP-004/005 三次 FULL_RESTART grounded_sam 一体化运行均为 RUN_EXIT=0、status=DONE、transition_count=19、final table_contact=true
  - CONF-006 EXP-004 感知输出唯一候选：class_id=cup、DINO confidence 0.8317、SAM predicted IoU 0.9887、mask 4671 px、warmed inference 278.1 ms，world center (0.0201, -0.2805, 0.1650)
  - CONF-007 EXP-004 状态轨迹包含 DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT，release_marker_sequence=5817，最终 MoveIt attached_object_ids 为空
  - CONF-008 EXP-005 用 `xwd -id <MuJoCo window>` 直读窗口像素可在 GNOME 锁屏状态下拿到真实 Viewer 画面；gui-capture 的屏幕/桌面模式在锁屏时只返回锁屏画面
  - CONF-009 EXP-001 推理镜像 `so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115` 首次构建在最后一步失败：setup.py 把 `../../scripts/run_so101_adaptive_batch.zsh` 放进 data_files，而 `yolo-inference`、`yolo-training`、`grounding-dino-training` 三个 Dockerfile 只 COPY 了 `src/so101_demo_py`，wheel 构建报 `can't copy '../../scripts/run_so101_adaptive_batch.zsh'`
  - CONF-010 EXP-001 三个 Dockerfile 补 `COPY scripts/run_so101_adaptive_batch.zsh /scripts/run_so101_adaptive_batch.zsh` 并放开同名 dockerignore 后，镜像重建退出码 0；容器内 rclpy/torch 2.13.0+cu130/torchvision 0.28.0+cu130/ultralytics 8.4.115/open3d 0.19.0 全部导入成功，`torch.cuda.is_available()` 为 True，RTX 5060 Ti 上 512x512 CUDA matmul 有限值通过
  - CONF-011 EXP-003 YOLO-Seg 一体化运行 RUN_EXIT=0、status=DONE、transition_count=19；感知唯一候选 plastic_cup，confidence 0.9687、mask 4260 px、容器内 CUDA 推理 47.83 ms、world center (0.02011, -0.28047, 0.16500)
  - CONF-012 EXP-006 同一命令第二次 FULL_RESTART 复现完全相同的感知数值（0.9687、4260 px、48.44 ms），并成功经 `camera_preset --backend mujoco table_corner_sw` 读回 `matched=true`
  - CONF-013 EXP-007 `tools/so101_pytest_gate.py` 的普通 gate 在本机需要 perception venv 提供 torch，且需要仓库根可导入 `tools`；裸 `colcon test` 会在收集期因 `No module named 'torch'` 失败，这是本机既有的解释器分工门，不是本轮修改引入
disproven_routes:
  - DISPROVED-001 在 GNOME 会话锁定时用 `$gui-capture --window-id/--desktop` 代替 Viewer 视觉证据：SHOT 只得到锁屏像素，SHA 完全相同
  - DISPROVED-002 用 CPU smoke 代替推理镜像的 CUDA 预检
open_hypotheses: []
latest_checkpoint: CP-003
next_experiment: NONE
```

## Checkpoints

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-007
current_hypothesis: 两篇导读都已各完成一次真实 execute 运行；剩余工作只是包级 gate 与提交
working_tree_status: 修改 6 个 Dockerfile/dockerignore，新增 1 个回归测试与 1 个账本
owned_processes: NONE
preserved_processes: 用户 GNOME 会话（当前锁定）、dst tmux session 未触碰
confirmed_conclusions:
  - CONF-001 至 CONF-013 见头部
disproven_routes:
  - DISPROVED-001 锁屏下的 gui-capture 桌面/窗口模式不能作为 Viewer 视觉证据
  - DISPROVED-002 CPU smoke 不能代替推理镜像的 CUDA 预检
open_risks:
  - yolo-training 与 grounding-dino-training 镜像只做了静态契约测试，本轮没有重建
  - 裸 colcon test 在本机收集期仍缺 torch，包级 gate 需要显式解释器分工
evidence_disposition:
  retained:
    - /data/work/so101-evidence/perception-guides-run/20260921-e7354314
  archived: []
  deletion_candidates:
    - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/scratch（pytest scratch，读回后仅列为候选）
next_command: python3 tools/so101_pytest_gate.py --evidence-root /data/work/so101-evidence/perception-guides-run/20260921-e7354314 --run-id package-gate --expected-source-commit <commit>
```

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-005
current_hypothesis: grounded_sam 导读已在当前 main 上稳定通过；剩下 YOLO-Seg 导读需要等推理镜像构建完成
working_tree_status: clean；仅新增本账本
owned_processes: docker build（bash-3）；无残留 ROS 进程
preserved_processes: 用户 GNOME 会话（当前锁定）、dst tmux session 未触碰
confirmed_conclusions:
  - CONF-001 至 CONF-008 见头部
disproven_routes:
  - DISPROVED-001 锁屏下的 gui-capture 桌面/窗口模式不能作为 Viewer 视觉证据
open_risks:
  - 推理镜像构建依赖 daocloud 与 download-r2.pytorch.org，前者曾 EOF 重试、后者曾 120 秒读超时后重下
  - GNOME 会话处于锁定状态，最终视觉证据改用 `xwd -id` 直读窗口
evidence_disposition:
  retained:
    - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/grounded-sam
  archived: []
  deletion_candidates: []
next_command: docker run --rm --gpus all --network host --entrypoint /ros_entrypoint.sh <image> python -c 'import torch; ...'
```

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: 只要补齐两篇导读的运行前置（CUDA 推理镜像、grounded-sam venv、HF 权重），当前 main 就能各完成一次端到端 execute
working_tree_status: clean；本账本为新增文件
owned_processes: 后台 docker build 与 venv 安装各一个
preserved_processes: 用户 GNOME 会话、dst tmux session 与既有 install overlay 未触碰
confirmed_conclusions:
  - CONF-001 best.pt 下载 SHA256 与导读固定值一致
  - CONF-002 grounded-sam bundle revision 与导读固定值一致
disproven_routes: []
open_risks:
  - docker build 依赖 daocloud 镜像加速，base layer 拉取曾出现 EOF 重试
  - 主机 GPU 为 RTX 5060 Ti 16GB，与旧账本记录的 RTX 5080 不同；sm_120 需要 CUDA 13 wheel 才能运行
evidence_disposition:
  retained: []
  archived: []
  deletion_candidates: []
next_command: 等待镜像构建与 venv 安装完成后，执行 EXP-001 的镜像 GPU 预检
```

## Experiments

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: 用仓库脚本构建的固定 YOLO 推理镜像可在 RTX 5060 Ti 上完成 CUDA 预检
prediction: nvidia-smi、torch.cuda.is_available() 与一次真实 CUDA 张量运算全部通过
single_variable: NONE（首次搭建）
lifecycle: FULL_RESTART
preconditions:
  - 无既有 ros2_control_node、move_group、MuJoCo 进程
  - docker daemon 可用且无同名镜像
success_criteria:
  - 镜像 so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115 构建退出码 0
  - 容器内 import rclpy, torch, ultralytics, open3d 通过且版本与 lock 一致
  - 容器内 torch.cuda.is_available() 为 True 且真实张量运算结果正确
failure_criteria:
  - 构建或 GPU 预检非零退出
invalid_criteria:
  - 使用 CPU smoke 代替 CUDA 预检
provenance:
  source_commit: e73543144aa6647031a53138d996fe9620fbb14b（构建时；修复后为本地提交 6 个 Dockerfile/dockerignore）
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: docker image so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115 (5998505c1deb)
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: scripts/yolo-seg-inference-container.sh build
    exit_code: 1
  - command: scripts/yolo-seg-inference-container.sh build   # 补 COPY scripts 之后
    exit_code: 0
  - command: docker run --rm --gpus all --entrypoint /ros_entrypoint.sh <image> python -c 'import rclpy, torch, torchvision, ultralytics, open3d; ...'
    exit_code: 0
observed:
  - OBSERVED 首次构建在最后一步失败：`error: can't copy '../../scripts/run_so101_adaptive_batch.zsh': doesn't exist or not a regular file`
  - OBSERVED 补 `COPY scripts/run_so101_adaptive_batch.zsh /scripts/run_so101_adaptive_batch.zsh` 后镜像构建退出码 0，镜像 3.93GB
  - OBSERVED 容器内 rclpy=/opt/ros/jazzy/lib/python3.12/site-packages/rclpy，torch 2.13.0+cu130，cuda_available=True，device=NVIDIA GeForce RTX 5060 Ti，torchvision 0.28.0+cu130，ultralytics 8.4.115，open3d 0.19.0，CUDA matmul 有限值通过
inferred:
  - INFERRED 同一缺陷同样存在于 yolo-training 与 grounding-dino-training（同一 setup.py data_files），已一并修复但未重建镜像
conclusion: 推理镜像在本机 GPU 上构建并通过 CUDA 预检；构建失败根因是构建上下文缺少 setup.py 需要的仓库级脚本
evidence:
  - /tmp/so101-debug-so101-perception-guides-run/docker-build.log
  - /tmp/so101-debug-so101-perception-guides-run/docker-build-2.log
decision: KEEP
next_experiment: EXP-003
```

```yaml
experiment_id: EXP-002
status: VALID
prior_experiment: NONE
hypothesis: 按导读 20 节在 /data/work/venvs/so101-grounded-sam 安装 requirements.lock 后，宿主机 ROS entrypoint 能同时导入 rclpy、torch、transformers 并使用 CUDA
prediction: python -c 'import rclpy, torch, transformers' 全部成功，torch.cuda.is_available() 为 True
single_variable: NONE（首次搭建）
lifecycle: FULL_RESTART
preconditions:
  - /data/work/venvs/so101-grounded-sam 尚不存在
success_criteria:
  - venv 创建与 pip install 退出码 0
  - torch 2.13.0、transformers 4.56.2 与 lock 一致
  - 注入 site-packages 后 rclpy 仍来自 /opt/ros/jazzy
failure_criteria:
  - 依赖安装失败或 CUDA 不可用
invalid_criteria:
  - 只验证 venv python 而跳过 ROS entrypoint 组合验证
provenance:
  source_commit: e73543144aa6647031a53138d996fe9620fbb14b
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: /usr/bin/python3.12 -m venv /data/work/venvs/so101-grounded-sam && pip install -r src/so101_demo_py/config/perception/requirements.lock
    exit_code: 0
  - command: /data/work/venvs/so101-grounded-sam/bin/python -c 'import torch; torch.cuda.is_available(); torch.randn(512,512,device="cuda") @ ...'
    exit_code: 0
  - command: PYTHONPATH=<venv site-packages> python3 -c 'import rclpy, torch, transformers, numpy, mujoco'
    exit_code: 0
observed:
  - OBSERVED venv 安装 EXIT=0，torch 2.13.0+cu130、transformers 4.56.2、mujoco 3.12.0、numpy 2.5.3
  - OBSERVED cuda_available=True，device=NVIDIA GeForce RTX 5060 Ti，512x512 CUDA matmul 有限值通过
  - OBSERVED 组合导入时 rclpy 来自 /opt/ros/jazzy，torch/transformers 来自 venv
inferred: []
conclusion: 导读 20 节的 Linux CUDA 本地部署路径在本机可复现
evidence:
  - /tmp/so101-debug-so101-perception-guides-run/venv-install.log
decision: KEEP
next_experiment: EXP-004
```

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-001
hypothesis: 当前 main 的 yolo_seg 一体化解读可完成一次完整 execute 抓放
prediction: 感知发布唯一 plastic_cup 的 /cup_pose，动态执行完成 DONE 并退出码 0，证据目录含 selected-mask.png 与 result.json
single_variable: NONE（导读 19 节命令原样执行）
lifecycle: FULL_RESTART
preconditions:
  - EXP-001 通过
  - best.pt SHA256 已核验
success_criteria:
  - ros2 run so101_demo_py so101_mujoco_perception_pick_place 退出码 0
  - perception result.json 记录 published_cup_pose=true 且 frame 为 world
  - workflow 终态 DONE，含抓取、微抬升、放置、脱离与桌面支撑
failure_criteria:
  - 感知或执行任一门禁失败
invalid_criteria:
  - 复用其他 run 的 evidence 目录
provenance:
  source_commit: e73543144aa6647031a53138d996fe9620fbb14b
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py + docker 镜像 5998505c1deb
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: ros2 run so101_demo_py so101_mujoco_perception_pick_place run_mode:=execute execute:=true headless:=false sensor_rendering:=true session_id:=yolo-tutorial-run-001 evidence_file:=<root>/yolo-seg/run-001.json mujoco_scene:=<prefix>/assets/mujoco/v5_multi_object_scene.xml mujoco_initial_keyframe:=task_start perception_backend:=yolo_seg perception_weights:=<best.pt> perception_weights_sha256:=f281d2…0781 perception_runtime:=auto perception_device:=auto perception_allow_cpu_fallback:=false
    exit_code: 0
observed:
  - OBSERVED 容器内 `status=READY request_id=yolo-tutorial-run-001 runtime_device=cuda`，随后 POSE_ACCEPTED source_stamp_ns=2503999999
  - OBSERVED result.json：status=OK、candidate_count=1、matching_candidate_count=1、published_cup_pose=true、inference_latency_ms=47.83、cold_start 2579.51、model_id=plastic-cup-yolo11n-seg-v1
  - OBSERVED detections.json：plastic_cup confidence 0.9687、mask 4260 px、bbox 153.86,187.42,218.33,271.89，640x480
  - OBSERVED dynamic manifest：status=DONE、transition_count=19、release seq 5602、attached_object_ids=[]
  - OBSERVED final_samples：杯 world (-0.07897, -0.24732, 0.16493)、table_contact=true
  - OBSERVED prediction-overlay.png 上 green mask 只覆盖杯子并标注 `plastic_cup 0.97`，没有覆盖旁边的橙色瓶子
inferred:
  - INFERRED 杯从 (0.02011,-0.28047) 移到 (-0.07897,-0.24732)，位移约 0.103 m，落在策略放置点
conclusion: 导读 19 节的一体化 yolo_seg 命令在当前 main 上完整通过
evidence:
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/yolo-seg/run-001.d
  - /tmp/so101-debug-so101-perception-guides-run/yolo-seg-run-001.log
decision: KEEP
next_experiment: EXP-005
```

```yaml
experiment_id: EXP-004
status: VALID
prior_experiment: EXP-002
hypothesis: 当前 main 的 grounded_sam 一体化解读可完成一次完整 execute 抓放
prediction: Grounding DINO + SAM 2.1 唯一选出 plastic_cup，/cup_pose 驱动动态执行到 DONE，退出码 0
single_variable: NONE（导读 22 节命令原样执行）
lifecycle: FULL_RESTART
preconditions:
  - EXP-002 通过
  - threshold-lock.json 数值与启动参数一致
success_criteria:
  - ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py 退出码 0
  - 证据目录含 model-provenance.json、selected-mask.png、result.json
  - workflow 终态 DONE 且物理抓放证据齐全
failure_criteria:
  - DINO/SAM/选择/深度/TF/执行任一门禁失败
invalid_criteria:
  - 复用其他 run 的 evidence 目录
provenance:
  source_commit: e73543144aa6647031a53138d996fe9620fbb14b
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py run_mode:=execute execute:=true headless:=false sensor_rendering:=true session_id:=grounded-sam-tutorial-run-001 evidence_file:=<root>/grounded-sam/run-001.json mujoco_scene:=<prefix>/assets/mujoco/scene.xml mujoco_initial_keyframe:=task_start perception_backend:=grounded_sam perception_model_root:=<bundle> perception_model_manifest_sha256:=b55bb6…ed05 perception_device:=cuda perception_allow_cpu_fallback:=false grounding_box_threshold:=0.50 grounding_text_threshold:=0.50 grounding_duplicate_iou:=0.85 grounding_max_candidates:=16 sam_mask_quality_threshold:=0.50 sam_min_mask_pixels:=64 sam_max_mask_area_ratio:=0.50
    exit_code: 0
observed:
  - OBSERVED runtime_device=cuda，READY 后 POSE_ACCEPTED source_stamp_ns=4701999999
  - OBSERVED result.json：status=OK、candidate_count=1、matching_candidate_count=1、published_cup_pose=true、inference_latency_ms=278.13、cold_start 4742.29
  - OBSERVED detections.json：cup confidence 0.8317、segmentation_quality 0.9887、mask 4671 px、bbox 153.2,186.9,219.2,271.0
  - OBSERVED dynamic manifest：status=DONE、transition_count=19、release_marker_sequence=5817、attached_object_ids=[]
  - OBSERVED 状态轨迹含 DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE
  - OBSERVED final_samples：杯 world (-0.07902, -0.24729, 0.16493)、线速度≈0、table_contact=true、左右指接触 0
inferred:
  - INFERRED 杯从 (0.0201,-0.2805) 移到 (-0.0789,-0.2473)，位移约 0.103 m，符合策略放置点
conclusion: 导读 22 节的一体化 grounded_sam 命令在当前 main 上完整通过
evidence:
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/grounded-sam/run-001.d
  - /tmp/so101-debug-so101-perception-guides-run/grounded-sam-run-001.log
decision: KEEP
next_experiment: EXP-005
```

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: 同一命令重复执行仍能通过，且可用 `xwd -id` 在锁屏会话中取得 MuJoCo Viewer 的新鲜画面
prediction: 第二次、第三次 FULL_RESTART 仍为 DONE/退出码 0，Viewer 截图显示抓取、搬运与放置阶段
single_variable: 新增 `xwd -id` 窗口级截图（不改任何运行参数）
lifecycle: FULL_RESTART
preconditions:
  - EXP-004 通过
  - 无残留 ROS 进程
success_criteria:
  - run-002 与 run-003 均 RUN_EXIT=0、status=DONE、transition_count=19
  - Viewer 截图能看到机械臂、杯子、桌面与放置区，并能分辨抓取与搬运阶段
failure_criteria:
  - 任一 run 非零退出或截图只有锁屏像素
invalid_criteria:
  - 截图来自其他 run 或复用旧窗口 id
provenance:
  source_commit: e73543144aa6647031a53138d996fe9620fbb14b
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: RUN_ID=run-002 ./run-grounded-sam.zsh
    exit_code: 0
  - command: RUN_ID=run-003 ./run-grounded-sam.zsh
    exit_code: 0
  - command: ./capture-window.zsh <evidence>/run-003-viewer 100 2.5
    exit_code: 0
observed:
  - OBSERVED run-002 与 run-003 都是 status=DONE、transition_count=19、RUN_EXIT=0
  - OBSERVED run-003 final_samples 杯 world (-0.07894, -0.24732, 0.16493)、table_contact=true
  - OBSERVED run-002 用 gui-capture 窗口模式只得到锁屏像素，shot-001 与 shot-005 SHA256 相同
  - OBSERVED run-003 用 `xwd -id 39845895` 取得 16 张真实 Viewer 画面，窗口 id 与 title "MuJoCo : so101_task_scene" 来自当轮 inventory
  - OBSERVED viewer-001 起始态、viewer-008 夹爪夹住杯、viewer-012 杯子离开起始圈被搬运、viewer-016 带杯下降
inferred:
  - INFERRED GNOME 锁屏只影响屏幕抓取，不影响 X11 窗口级像素读取
conclusion: grounded_sam 导读连续三次 FULL_RESTART 通过，且拿到真实 Viewer 视觉证据
evidence:
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/grounded-sam/run-002.d
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/grounded-sam/run-003.d
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/grounded-sam/run-003-viewer
decision: KEEP
next_experiment: EXP-003
```

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-003
hypothesis: 重复 YOLO-Seg 导读并先用包自带 preset 调整 Viewer 取景，可复现同一感知结果并得到可辨认的可见画面
prediction: 第二次 FULL_RESTART 仍 RUN_EXIT=0/status=DONE，感知数值与 run-001 一致，preset 服务读回 matched=true
single_variable: 运行前调用 `camera_preset --backend mujoco table_corner_sw`（不改任务参数、不改模型、不改阈值）
lifecycle: FULL_RESTART
preconditions:
  - EXP-003 通过
  - 无残留 ROS 进程与容器
success_criteria:
  - run-002 为 RUN_EXIT=0、status=DONE、transition_count=19
  - 候选数、class、confidence 与 mask 像素数与 run-001 一致
  - preset 回执 success=true 且 evidence.matched=true
failure_criteria:
  - 任一 run 非零退出或 preset 读回不一致
invalid_criteria:
  - 复用 run-001 的窗口 id 或证据目录
provenance:
  source_commit: e73543144aa6647031a53138d996fe9620fbb14b
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py + docker 镜像 5998505c1deb
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: RUN_ID=run-002 ./run-yolo-seg-preset.zsh
    exit_code: 0
observed:
  - OBSERVED preset 回执 `{"backend": "mujoco", "evidence": {"matched": true}, "failure_code": null, "phase": "READ_BACK", "preset": "table_corner_sw", "success": true}`，PRESET_EXIT=0
  - OBSERVED run-002 status=DONE、transition_count=19、RUN_EXIT=0
  - OBSERVED 感知复现：candidate 1、plastic_cup 0.9687、mask 4260 px、推理 48.44 ms、published_cup_pose=true
  - OBSERVED final_samples 杯 world (-0.07901, -0.24729, 0.16493)、table_contact=true
  - OBSERVED 63 张 viewer 截图；viewer-001 与 viewer-062 的仿真步数与接触数不同，说明画面来自运行中的仿真而不是静态窗口
inferred:
  - INFERRED v5 多物体场景的 Viewer 默认距离较远，preset 只改操作员视角，不影响 task_camera 或物理
conclusion: YOLO-Seg 导读连续两次通过，且第二次带可读的 Viewer 取景证据
evidence:
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/yolo-seg/run-002.d
  - /data/work/so101-evidence/perception-guides-run/20260921-e7354314/yolo-seg/run-002-viewer
  - /tmp/so101-debug-so101-perception-guides-run/yolo-seg-run-002-preset.log
decision: KEEP
next_experiment: EXP-007
```

```yaml
experiment_id: EXP-007
status: PLANNED
prior_experiment: EXP-006
hypothesis: 补齐构建上下文后，包级普通 gate 对本轮修改没有新增失败
prediction: 普通 gate 全绿；此前裸 colcon test 的 torch/tools 收集失败被解释为解释器分工门
single_variable: 本轮新增 test_image_build_context.py 与 6 个 Dockerfile/dockerignore 改动
lifecycle: FULL_RESTART
preconditions:
  - 修改已提交，工作树干净
success_criteria:
  - tools/so101_pytest_gate.py 退出码 0，无失败、无错误
failure_criteria:
  - 出现与本轮修改相关的失败
invalid_criteria:
  - 用 CPU/venv 之外的 interpreter 冒充 ROS gate
provenance:
  source_commit: PENDING（本轮修改提交后填写）
  install_overlay: /home/matianyi/Projects/ros-moveit-demo/install
  runtime_executable: /home/matianyi/Projects/ros-moveit-demo/install/so101_demo_py
  ros_domain_id: 231
  gz_partition: so101-guides-20260921
commands:
  - command: PENDING
    exit_code: PENDING
observed: []
inferred: []
conclusion: PENDING
evidence: []
decision: PENDING
next_experiment: NONE
```

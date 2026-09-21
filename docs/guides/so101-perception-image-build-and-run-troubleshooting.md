# SO-101 感知镜像构建与导读运行排障记录

**范围：** 在 ai-station 上按 [`so101-yolo-seg-rgbd-perception-pick-place-source-guide.md`](so101-yolo-seg-rgbd-perception-pick-place-source-guide.md) 和 [`so101-grounded-sam-rgbd-perception-pick-place-source-guide.md`](so101-grounded-sam-rgbd-perception-pick-place-source-guide.md) 各跑通一次完整抓放时踩到的坑

**对象：** 已经读过那两篇导读，准备在 Linux CUDA 机器上照着跑一遍的开发者

**结论：** 感知和抓放代码没有改。唯一需要动源码的地方在 Docker 构建上下文，其余都是环境、工具链和验证方法的问题。

```yaml
验证基线:
  host: ai-station
  gpu: RTX 5060 Ti 16GB / 驱动 595.91.07
  commit: 7c1a2f50（修复）+ a9851007（账本）
  yolo: 2/2 FULL_RESTART 成功，cuda，47.8–48.4 ms
  grounded_sam: 4/4 FULL_RESTART 成功，cuda，272–278 ms
  package_gate: tools/so101_pytest_gate.py PASS，3544/3544，70.7 s
```

## 1. 先看清楚：这次真正改了什么

三个会 `pip install /opt/so101_demo_py` 的 Dockerfile 各补了一行：

```dockerfile
COPY scripts/run_so101_adaptive_batch.zsh /scripts/run_so101_adaptive_batch.zsh
```

外加对应的 `Dockerfile.dockerignore` 放行，和一个从 `setup.py` 反推镜像内必需路径的回归测试。`object_pose.py`、`yolo_seg.py`、`grounded_sam*.py`、`launch_composition.py`、权重、阈值、场景 XML 全部没动。

下面按实际发生的顺序记问题。第 3 节是核心，其他都是外围。

## 2. 网络与依赖

### 2.1 Hugging Face 直连超时

不挂代理时 `hf models info zjumty/...` 60 秒无响应。按用户给的开关：

```bash
source "$HOME/.xray-proxy.env"
```

之后 `hf auth whoami` 直接返回 `zjumty`，两个仓库都能读。

顺带一提，`download.pytorch.org` 反过来是直连比走代理快（HEAD 1.8 s vs 4.1 s），所以别见到“外网”就无脑挂代理，测一下。

### 2.2 `hf download --include` 被静默忽略

`hf` 1.32.0 下这条命令只下到了两个文件（`README.md` 和 `SHA256SUMS`），权重压根没下：

```bash
hf download zjumty/so101-yolo11n-seg-plastic-cup \
  --include "best.pt" "SHA256SUMS" "README.md" \
  --local-dir <dir>
# UserWarning: Ignoring `--include` since filenames have been explicitly set.
```

两个可用写法，按需要挑：

```bash
# 明确要哪几个文件：位置参数
hf download zjumty/so101-yolo11n-seg-plastic-cup best.pt --local-dir <dir>

# 明确不要哪些：排除大目录
hf download zjumty/so101-grounded-sam-cup-pickplace \
  --repo-type model \
  --revision 52b8334358e5ff11f94f10f7c14b1697ef44d964 \
  --exclude "datasets/*" \
  --local-dir <dir>
```

下完必须回读，别信“Downloaded”：

```bash
sha256sum best.pt          # 应为 f281d252…0781
sha256sum bundle/manifest.json   # 应为 b55bb601…ed05
cd <dir> && sha256sum -c SHA256SUMS
```

`SHA256SUMS` 里会有一条 datasets tarball 报 `No such file or directory`，那是 `--exclude` 的预期结果，不是缺文件。

### 2.3 Docker 基础镜像与 PyTorch wheel 的抖动

第一次构建时 `docker.m.daocloud.io` 拉 blob 报过一次 `EOF`，pip 从 `download-r2.pytorch.org` 拉 `torch-2.13.0+cu130` 报过一次 `ReadTimeoutError(... read timeout=120.0)`。两次都自动重试成功了，不需要人工干预。

要注意的是 pip 重试是**从头重下**，不是断点续传。526 MB 的 wheel 掉一次就得多等几分钟。BuildKit 的层缓存能救回来：同一条 `RUN` 只要指令没变，重跑构建会直接命中缓存，所以拿到报错先原样重跑一次，别急着改参数。

普通 Python 包走清华源：

```bash
pip config list    # /etc/pip.conf: index-url = https://pypi.tuna.tsinghua.edu.cn/simple
```

Dockerfile 里 `PIP_INDEX_URL` 默认就是 tuna，`PYTORCH_INDEX_URL` 指向官方 `cu130` 索引（tuna 的 `pytorch-wheels` 镜像也有 `+cu130` wheel，速度一般，可作为兜底）。

## 3. 核心问题：镜像构建在最后一步失败

### 现象

镜像的前面所有层都成功，卡在装包那一步：

```
#11 [stage-0 8/9] RUN python -m pip install --no-cache-dir --no-deps /opt/so101_demo_py ...
#11 0.861   Building wheel for so101_demo_py (setup.py): finished with status 'error'
#11 0.890       error: can't copy '../../scripts/run_so101_adaptive_batch.zsh': doesn't exist or not a regular file
#11 ERROR: process "/bin/sh -c python -m pip install ..." did not complete successfully: exit code: 1
```

### 根因

`setup.py` 的 `data_files` 里有一条相对路径：

```python
data_files=[
    ...
    (
        f"lib/{package_name}",
        ["../../scripts/run_so101_adaptive_batch.zsh"],
    ),
]
```

这个路径是相对**包目录**算的。镜像里包在 `/opt/so101_demo_py`，`../../` 一路退到文件系统根，于是 setuptools 去找 `/scripts/run_so101_adaptive_batch.zsh`。而 Dockerfile 只 `COPY src/so101_demo_py /opt/so101_demo_py`，仓库根的 `scripts/` 从来没进过构建上下文。

`parallel-perception/Dockerfile` 里已经有对应的 `COPY scripts /scripts`，另外三个没有。引入 `../../scripts/...` 的那个提交只覆盖了当时会构建到的那个镜像。

### 解法

在 `COPY src/so101_demo_py` 之后补一行，目标路径要和 `setup.py` 解析出来的完全一致：

```dockerfile
COPY src/so101_demo_py /opt/so101_demo_py
# setup.py packages ../../scripts/run_so101_adaptive_batch.zsh, which resolves to
# /scripts/... relative to /opt/so101_demo_py. Without it the wheel build aborts
# while copying data files, so the file must exist inside the image too.
COPY scripts/run_so101_adaptive_batch.zsh /scripts/run_so101_adaptive_batch.zsh
```

三个 Dockerfile 的 `.dockerignore` 都以 `**` / `*` 开头忽略全部，所以还得显式放行，否则文件仍然进不了上下文：

```gitignore
!scripts/
!scripts/run_so101_adaptive_batch.zsh
```

### 怎么确认修好了

别只看到 `Successfully installed so101_demo_py` 就收工。镜像最后一层本来就带自检，重建后它会真的执行：

```bash
docker run --rm --gpus all \
  --entrypoint /ros_entrypoint.sh \
  so101-yolo11n-seg-inference:ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115 \
  python -c 'import rclpy, torch, torchvision, ultralytics, open3d; from vision_msgs.msg import Detection2DArray; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))'
```

期望 `2.13.0+cu130 True NVIDIA GeForce RTX 5060 Ti`。CPU smoke 不算数，`torch.cuda.is_available()` 才是这条路径的验收线。

### 让它在测试里挡住

新增 `src/so101_demo_py/test/test_image_build_context.py`，思路是从 `setup.py` 自己反推，而不是把 `/scripts/...` 写死在测试里：

1. 用 `ast` 解析 `setup.py`，收集所有以 `../` 开头的字符串常量；
2. 找到 Dockerfile 里复制包的那条 `COPY`，把它的目标目录和这些相对路径拼起来，得到镜像内必需路径；
3. 检查每条 `COPY` 是否能提供该路径，并且源文件没被对应的 `Dockerfile.dockerignore` 排除。

这样以后 `setup.py` 再加一条往外跑的 `data_files`，测试会先红，不用等一次完整镜像构建。

一个坑：一开始想用正则从 `setup.py` 里抠字符串，结果被文件里的三引号 docstring 带偏，配对错位，`found` 是空集。换成 `ast` 就干净了。

## 4. 截图：会话锁着的时候怎么办

### 现象

用 `$gui-capture` 抓 MuJoCo 窗口，拿到的两张图 SHA256 完全一样，画面是 GNOME 锁屏：

```
LockedHint=yes
gdbus ... org.gnome.ScreenSaver.GetActive  ->  (true,)
```

`--window-id` 和 `--desktop` 都只返回锁屏像素，因为屏幕抓取走的是合成后的画面。

### 解法

`xwd -id` 直接向 X server 要那个窗口自己的像素，锁屏盖在上面也不影响：

```bash
source ~/gui-env.zsh           # DISPLAY=:1 / XAUTHORITY / XDG_RUNTIME_DIR
xwd -id "$WID" -out shot.xwd   # WID 来自当轮 --list-windows 的 MuJoCo 窗口
```

窗口 id 必须每轮重新取。本次是 `owner=MuJoCo/MuJoCo`、`title="MuJoCo : so101_task_scene"`，抓到 3840x2091。

### XWD 解析的两个坑

本机没有 ImageMagick 也没有 ffmpeg，得自己转 PNG。写转换器时踩到：

- 文件头字段是**大端**，但 `byte_order` 字段写的是 `0`（LSBFirst）。别用这个字段去推断文件头本身的字节序，用 `version == 7` 判断更稳。
- `header_size` 字段是 `109`，不是期望的 `100`。像素数据的真正起点是 `header_size + ncolors * 12`（本次 `109 + 256*12 = 3181`，和文件总大小对得上）。按 `100 + ncolors*12` 硬算会整体错位。

32bpp、`red_mask=0xff0000` 且 LSBFirst 时，内存里字节顺序是 B、G、R、X。核心逻辑就这么点：

```python
import struct
import numpy as np
from PIL import Image

def xwd_to_png(src: str, dst: str) -> None:
    raw = open(src, "rb").read()
    fields = ("header_size version pixmap_format pixmap_depth pixmap_width "
              "pixmap_height xoffset byte_order bitmap_unit bitmap_bit_order "
              "bitmap_pad bits_per_pixel bytes_per_line visual_class red_mask "
              "green_mask blue_mask bits_per_rgb colormap_entries ncolors "
              "window_width window_height window_x window_y window_bdrwidth").split()
    for endian in ("<", ">"):
        values = dict(zip(fields, struct.unpack(endian + "25I", raw[:100])))
        if values["version"] == 7:
            break
    width, height = values["pixmap_width"], values["pixmap_height"]
    step = values["bits_per_pixel"] // 8
    offset = values["header_size"] + values["ncolors"] * 12
    rows = np.frombuffer(raw, dtype=np.uint8,
                         count=values["bytes_per_line"] * height,
                         offset=offset
                         ).reshape(height, values["bytes_per_line"])
    rows = rows[:, : width * step].reshape(height, width, step)
    if values["byte_order"] == 0 and step == 4:      # LSBFirst -> B,G,R,X
        blue, green, red = rows[:, :, 0], rows[:, :, 1], rows[:, :, 2]
    elif step == 4:                                   # MSBFirst -> X,R,G,B
        red, green, blue = rows[:, :, 1], rows[:, :, 2], rows[:, :, 3]
    else:                                             # 24bpp
        blue, green, red = rows[:, :, 0], rows[:, :, 1], rows[:, :, 2]
    Image.fromarray(np.dstack([red, green, blue]).astype(np.uint8)).save(dst)
```

抓图节奏也有讲究。MuJoCo Viewer 在 workflow 走到 `DONE` 后立刻随 launch 一起关掉，所以最后一张成功截图落在 `RETREAT` 前后。本次 `grounded_sam` 每 0.3 s 一轮拿到 77 张，覆盖了起始、夹取、搬运、带杯下降和放置后回退；`yolo_seg` 的 63 张同理。

想看清楚一点可以调包自带的相机 preset，跑起来之后单独发一条命令：

```bash
ros2 run so101_demo_py camera_preset --backend mujoco table_corner_sw
# {"backend": "mujoco", "evidence": {"matched": true}, "success": true}
```

`matched: true` 是服务读回，不是“命令发出去了”。preset 只改操作员视角，不影响 `task_camera` 和物理，所以不算改实验变量。

顺带记一条证伪：锁屏状态下 `$gui-capture` 的窗口/桌面模式不能当 Viewer 视觉证据用。别拿它凑数。

## 5. 测试门禁

### 5.1 裸 `colcon test` 在本机收不了

```
E   ModuleNotFoundError: No module named 'torch'
    test/test_grounding_dino_domain_retention.py:6: in <module>  import torch
```

`test_grounding_dino_domain_retention.py` 在模块顶层 `import torch`，而 ROS 解释器里没有 torch。按导读第 15 节的做法把 perception venv 的 site-packages 加到 `PYTHONPATH` 后，下一个报错换成：

```
E   ModuleNotFoundError: No module named 'tools'
    test/test_pytest_full_gate_runner.py:6: from tools.so101_pytest_gate import ...
```

这个要仓库根可导入。两个都是本机解释器分工问题，不是代码回归。

### 5.2 正确的入口是仓库自带 gate

`tools/so101_pytest_gate.py` 才是这个仓库的普通 gate：按文件分片、固定若干必须串行的模块、校验收集集合与 commit provenance。

```bash
source /opt/ros/jazzy/setup.zsh
source <mujoco_ros2_control 的 underlay>/setup.zsh
source <repo>/install/setup.zsh
export PYTHONNOUSERSITE=1
export PYTHONPATH=<perception venv>/lib/python3.12/site-packages:$PWD${PYTHONPATH:+:$PYTHONPATH}

python3 tools/so101_pytest_gate.py \
  --workers 8 \
  --evidence-root <evidence-root> \
  --run-id g2-7c1a2f50 \
  --process-id-chars 4 \
  --expected-source-commit "$(git rev-parse HEAD)" \
  --python /usr/bin/python3
```

本次结果：`result=PASS`，8 个 shard 全部 `rc=0`，`collection.actual_count == expected_count == 3544`，70.7 s，`cleanup.owned_processes_remaining=[]`。

### 5.3 证据根路径太长会被拒

第一次跑直接退出：

```
SO101_PYTEST_GATE_ERROR: AF_UNIX process scratch path exceeds the 107-byte payload limit:
123 bytes for <evidence-root>/scratch/package-gate-7c1a2f50/000000000000/ipc-response/s
```

这是 Unix domain socket 的路径长度上限，不是配置错误。两个旋钮一起用就够了：

- `--run-id` 起短一点（21 字符 → 11 字符）
- `--process-id-chars 4`（默认 12，专门为长证据根准备的）

算下来 `103` 字节，通过。

### 5.4 证据根权限会让一个测试失败

```
so101_demo.runtime.unix_address.UnixAddressError: ANCESTOR_WRITABLE:
<evidence-root> uid=1000 mode=0775 is writable without a root-owned sticky bit
FAILED src/so101_demo_py/test/test_unix_address_strategy.py::test_a_symlinked_base_refuses_to_be_created_through
```

`unix_address` 会检查 socket 路径上的每一级祖先：可写但不是 root 所有的 sticky 目录，一律拒绝，因为别人能把目录换掉。默认 umask 是 `0002` 时 `mkdir` 出来就是 `0775`，正好踩中。

```bash
chmod 0755 <evidence-root>/<task-family> <evidence-root>/<task-family>/<run-id>
```

改的是自己证据树的权限，`unix_address` 的实现一行没动。

## 6. 一条可复现的运行序列

把上面所有结论收成一份能直接照着敲的清单。`<...>` 全部替换成绝对路径。

```bash
# 0. 代理（只在直连失败时）
source "$HOME/.xray-proxy.env"

# 1. 权重
hf download zjumty/so101-yolo11n-seg-plastic-cup best.pt --local-dir <models>/yolo11n-seg
hf download zjumty/so101-grounded-sam-cup-pickplace --repo-type model \
  --revision 52b8334358e5ff11f94f10f7c14b1697ef44d964 \
  --exclude "datasets/*" --local-dir <models>/grounded-sam

# 2. 两个运行时（互不干扰）
scripts/yolo-seg-inference-container.sh build          # Linux CUDA 走容器
/usr/bin/python3.12 -m venv <venv>/so101-grounded-sam  # grounded_sam 走宿主机
<venv>/so101-grounded-sam/bin/python -m pip install \
  -r src/so101_demo_py/config/perception/requirements.lock

# 3. overlay
source /opt/ros/jazzy/setup.zsh
source <mujoco_ros2_control underlay>/setup.zsh
source <repo>/install/setup.zsh

# 4. grounded_sam（宿主机 CUDA，必须注入 venv site-packages）
export PYTHONPATH=<venv>/so101-grounded-sam/lib/python3.12/site-packages${PYTHONPATH:+:$PYTHONPATH}
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
source ~/gui-env.zsh     # 需要可见 Viewer 时

ros2 launch so101_demo_py so101_mujoco_perception_pick_place.launch.py \
  run_mode:=execute execute:=true headless:=false sensor_rendering:=true \
  session_id:=grounded-sam-tutorial-001 \
  evidence_file:=<evidence>/grounded-sam/run-001.json \
  mujoco_scene:="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py/assets/mujoco/scene.xml" \
  mujoco_initial_keyframe:=task_start \
  perception_backend:=grounded_sam \
  perception_model_root:=<models>/grounded-sam/bundle \
  perception_model_manifest_sha256:=b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05 \
  perception_device:=cuda perception_allow_cpu_fallback:=false \
  grounding_box_threshold:=0.50 grounding_text_threshold:=0.50 \
  grounding_duplicate_iou:=0.85 grounding_max_candidates:=16 \
  sam_mask_quality_threshold:=0.50 sam_min_mask_pixels:=64 sam_max_mask_area_ratio:=0.50
```

YOLO 那条把 `perception_backend` 换成 `yolo_seg`，权重参数换成 `perception_weights` 加 `perception_weights_sha256`，场景换成 `v5_multi_object_scene.xml`，`perception_runtime:=auto` 在 Linux 会自动选 docker 并把设备收敛成 `cuda`。

几个容易白跑一趟的细节：

- `run_mode:=execute` 和 `execute:=true` 必须同时给，只给一个直接报错；
- grounded_sam 的阈值参数和 YOLO 的权重参数不能混着传，参数门禁在节点起来之前就拒绝；
- `--show-args` 对 `so101_mujoco_perception_pick_place` 无效（它自己解析 argv，会报 `malformed launch argument`），要查参数名就翻 `launch_composition.py` 里的 `DeclareLaunchArgument`；
- `sensor_rendering:=true` 不能省。无头跑也要给，否则 Viewer 不显示的同时相机也可能不出 RGB-D。

## 7. 怎么判断“真的跑通了”

`DONE`、`SUCCESS`、退出码 0 是三层不同的东西，任何一层都不能替代另外两层。

感知层的证据在 `<evidence>.d/<session-id>/perception/`：

```text
source-rgb.png          # 相机原图
prediction-overlay.png  # 框 + 类别 + 置信度 + mask
candidate-mask-000.png  # 逐个候选的实例 mask
selected-mask.png       # 被选中的那个
selected-cloud.ply      # 反投影点云
detections.json         # confidence 与 segmentation_quality 分开记
model-provenance.json   # backend / pipeline_id / manifest SHA
result.json             # candidate_count / matching_candidate_count / published_cup_pose
```

打开 overlay 看一眼是最省事的判断：mask 有没有只贴住杯子、有没有粘到旁边的瓶子。本次 YOLO 是 `plastic_cup 0.97`、4260 px；Grounded SAM 是 `cup 0.83 sim=0.989`、4671 px。

物理层的证据在 `<evidence>.d/<session-id>/dynamic/dynamic-execute-manifest.json`。本次五次运行都满足：

```text
status=DONE  transition_count=19  failure=None
state_trace: ... CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT -> VERIFY_PHYSICAL_GRASP
             -> ATTACH_MOVEIT -> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE
             -> DETACH_MOVEIT -> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE
             -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> RETREAT -> DONE
planning_scene_readback.attached_object_ids = []
final_samples[0]: cup_position_world_m ≈ (-0.079, -0.247, 0.165)
                  table_contact=true   线速度 ≈ 0
```

`DETACH_MOVEIT` 在 `OPEN_GRIPPER` 之前、`final_samples` 里 `table_contact=true` 且速度归零，这两条合起来才说明杯子是放在桌上，不是被抓着悬空。

收尾再生成一份清单，别只留一句“跑过了”：

```bash
cd <evidence-root>
find . -type f -not -path "./scratch/*" -not -name "*.err" -not -name "SHA256SUMS" \
  | sort | xargs sha256sum > SHA256SUMS
sha256sum -c SHA256SUMS | grep -c ": OK"
```

`find` 要先排除 `SHA256SUMS` 自己。重定向会先创建空文件，`find` 会把空文件也算进去，结果是校验时永远有一条 `FAILED`。

## 8. 还没验证的边界

- `yolo-training` 和 `grounding-dino-training` 两个镜像的缺文件缺陷按同样方式修了，静态契约测试覆盖，但**没有重建镜像验证**。下次要跑训练镜像时先跑一次构建。
- 结论覆盖 MuJoCo 仿真，不代表真实 SO-101 硬件。真实机械臂动作需要单独的急停、限速和净空门控。
- 本次两个 HF 仓库都是当前 `main` / 固定 revision 的快照。仓库后续更新后，上面写死的 SHA256 和 manifest digest 需要重新核对。

# SO-101 MuJoCo Viewer Camera Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将官方 `mujoco_ros2_control 0.0.3` 定制代码迁入独立 Gitee fork，并为 `so101_mujoco_demo_py` 提供可回读的 ROS 2 viewer camera service、CLI 和桌面四角俯视 preset。

**Architecture:** `moveit-demo` 通过 `third_party/mujoco_ros2_control` submodule 固定 Gitee fork commit；fork 通用地拥有 viewer camera message、set/get service 和 `mjvCamera` 并发边界，项目包拥有严格 YAML、ROS client、CLI 和 SO-101 场景 preset。定制安装脚本把 fork 构建到独立 overlay，旧 patch overlay 保留回滚，最终用 headless contract、正常物理状态和四张 CUA 截图共同验收。

**Tech Stack:** Ubuntu 24.04、ROS 2 Jazzy、C++17、`rclcpp`、rosidl、MuJoCo 3.x、`mujoco_vendor 0.0.8`、`mujoco_ros2_control 0.0.3`、Python 3.12、`rclpy`、PyYAML、pytest、GTest、colcon、zsh、Git submodule。

## Global Constraints

- 设计权威文件是 `docs/superpowers/specs/2026-08-11-so101-mujoco-viewer-camera-presets-design.md`，实现不得扩大其范围。
- 执行者直接运行在 ai-station 时不得再次 SSH 到 ai-station；目标项目 worktree 是 `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2`。
- fork 远端固定为 `git@gitee.com:zjumty/mujoco_ros2_control.git`；官方基线固定为 `https://github.com/ros-controls/mujoco_ros2_control` tag `0.0.3`、commit `35ba8174b62d9560093614f981a3d4b978a96036`。
- submodule 路径固定为 `third_party/mujoco_ros2_control`；fork 发布 tag 固定从 `so101-0.0.3-r1` 开始。
- 新 overlay 固定为 `/data/work/ws_mujoco_ros2_control_fork/install`；不得覆盖或删除 `/data/work/ws_mujoco_ros2_control_003`。
- source 顺序固定为 `/opt/ros/jazzy/setup.zsh`、fork overlay、project overlay；不得向 `/opt/ros/jazzy` 写文件。
- 所有行为修改必须经历定向 RED、最小 GREEN、包级回归和独立提交；不得运行 `ament_uncrustify --reformat`。
- fork commit 必须先推送到 Gitee，主项目随后才可提交指向该 commit 的 gitlink 和 dependency lock。
- camera callback 只允许修改 `mjvCamera` 和 `sim_->camera`，并且必须持有 `sim_mutex_`；不得调用 pause/reset/step，不得写 `mjModel`、`mjData`、`qpos`、`qvel` 或 controller state。
- 第一版只支持 `FREE` 和 `FIXED`，不实现 tracking camera、Teleop Web UI、RGB-D、ROS image topic 或自动改写 YAML。
- 不修改 `src/so101_gazebo_demo_py/**`，不修改或提交 ai-station 现有 Task13 未跟踪文件。
- GUI 验收使用 `codex-cua` 的 `snapshot -> action -> fresh snapshot`，不使用为 Gazebo demo 准备的截图脚本。
- 长程运行实验使用唯一账本 `docs/experiments/so101-mujoco-viewer-camera-experiment-ledger.md` 和唯一证据根 `/tmp/so101-debug-mujoco-viewer-camera/`；只有一个写入者。
- 禁止 force-push、`git reset --hard`、`git clean` 和宽泛进程清理；只停止本任务明确拥有的 PID/session。
- 除非命令块显式切换目录，所有项目命令都从 `/data/work/ws_moveit/.worktrees/so101-mujoco-ros2` 运行；使用 package-relative pytest 路径的命令块必须先进入 `src/so101_mujoco_demo_py`。

---

## Planned File Structure

### Gitee fork

- `mujoco_ros2_control_msgs/msg/ViewerCamera.msg`：通用 free/fixed viewer camera state。
- `mujoco_ros2_control_msgs/srv/SetViewerCamera.srv`：原子 set request 与 applied state response。
- `mujoco_ros2_control_msgs/srv/GetViewerCamera.srv`：读取实际 viewer camera。
- `mujoco_ros2_control_msgs/CMakeLists.txt`：生成新增 msg/srv。
- `mujoco_ros2_control/include/mujoco_ros2_control/viewer_camera.hpp`：纯校验、规范化、apply/read helper API。
- `mujoco_ros2_control/src/viewer_camera.cpp`：不接触 ROS executor 的 camera state 实现。
- `mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp`：service callback 与 service owner 声明。
- `mujoco_ros2_control/src/mujoco_system_interface.cpp`：service 注册、headless 拒绝和 mutex 临界区。
- `mujoco_ros2_control/tests/test_viewer_camera.cpp`：helper 原子性、free/fixed、非法输入测试。
- `mujoco_ros2_control/tests/test_headless_init.cpp`：callback、headless、physics-state 不变回归。
- `mujoco_ros2_control/tests/CMakeLists.txt`、`mujoco_ros2_control/CMakeLists.txt`：编译新增 source 和 tests。

### `moveit-demo`

- `.gitmodules`、`third_party/mujoco_ros2_control`：fork pin。
- `scripts/install-mujoco-ros2-control.zsh`：submodule 校验、隔离 build/test/install、prefix 验证。
- `src/so101_mujoco_demo_py/config/dependency-lock.yaml`：schema 3 fork provenance。
- `src/so101_mujoco_demo_py/config/camera_views.yaml`：现场标定后的四角 preset。
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/camera_presets.py`：纯 Python strict YAML 和四角不变量。
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/viewer_camera_client.py`：typed ROS 2 gateway。
- `src/so101_mujoco_demo_py/so101_mujoco_demo_py/camera_preset_cli.py`：`--list`、apply、`--current`、YAML 输出。
- `src/so101_mujoco_demo_py/setup.py`、`package.xml`：console entry point 和运行依赖。
- `src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py`：fork、接口和 installed hash read-back。
- `src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py`、`check_migration_isolation.sh`：新 overlay/source 顺序。
- `src/so101_mujoco_demo_py/test/test_fork_dependency.py`：submodule、installer、lock、无破坏操作 contract。
- `src/so101_mujoco_demo_py/test/test_camera_presets.py`：schema 和四角不变量。
- `src/so101_mujoco_demo_py/test/test_camera_preset_cli.py`：CLI 与 gateway failure contract。
- `src/so101_mujoco_demo_py/test/test_viewer_camera_live_contract.py`：opt-in headless service contract。
- `docs/guides/so101-mujoco-ros2-integration-guide.md`：fork 安装、source、camera CLI 和回滚说明。
- `docs/experiments/so101-mujoco-viewer-camera-experiment-ledger.md`：GUI 标定和最终验收账本。

---

### Task 1: Seed the Gitee Fork with the Existing Reset Contract

**Files:**
- Modify in fork: `mujoco_ros2_control/src/mujoco_system_interface.cpp`
- Modify in fork: `mujoco_ros2_control/tests/test_headless_init.cpp`
- Modify in fork: `mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp`
- Consume from project: `src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch`

**Interfaces:**
- Consumes: official commit `35ba8174b62d9560093614f981a3d4b978a96036` and the exact approved reset patch.
- Produces: Gitee fork `main` containing normal committed reset/pause/snapshot hooks; `origin/main` is safe for submodule use.

- [ ] **Step 1: Freeze the two repositories and refuse a non-empty fork**

Run on ai-station:

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
git status --short
git rev-parse HEAD
git ls-remote git@gitee.com:zjumty/mujoco_ros2_control.git
```

Expected: project status contains only the three already-known Task13 untracked files, and `git ls-remote` prints no refs. If the fork contains refs, stop and review them; do not overwrite the repository.

- [ ] **Step 2: Create a temporary upstream checkout with explicit remotes**

```zsh
fork_bootstrap_dir=$(mktemp -d /tmp/mujoco-ros2-control-fork-bootstrap.XXXXXX)
git clone https://github.com/ros-controls/mujoco_ros2_control "$fork_bootstrap_dir"
git -C "$fork_bootstrap_dir" checkout -b main 35ba8174b62d9560093614f981a3d4b978a96036
git -C "$fork_bootstrap_dir" remote rename origin upstream
git -C "$fork_bootstrap_dir" remote add origin git@gitee.com:zjumty/mujoco_ros2_control.git
git -C "$fork_bootstrap_dir" tag --points-at HEAD
```

Expected: tag output contains exactly the official `0.0.3` tag among any aliases pointing at the same commit; `origin` is Gitee and `upstream` is GitHub.

- [ ] **Step 3: Replay the approved reset patch and prove it is the only source delta**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
git -C "$fork_bootstrap_dir" apply --unidiff-zero --check \
  src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch
git -C "$fork_bootstrap_dir" apply --unidiff-zero \
  src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch
git -C "$fork_bootstrap_dir" status --short
git -C "$fork_bootstrap_dir" diff --check
```

Expected: only the three files listed in this task are modified and `diff --check` is clean.

- [ ] **Step 4: Build and run the fork baseline tests**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log build \
  --base-paths "$fork_bootstrap_dir" \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --cmake-clean-cache \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log test \
  --base-paths "$fork_bootstrap_dir" \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control \
  --event-handlers console_direct+
colcon test-result --test-result-base /data/work/ws_mujoco_ros2_control_fork/build --verbose
```

Expected: build exits 0 and all three package suites report no failures.

- [ ] **Step 5: Commit and publish the reset baseline before any project pin**

```zsh
git -C "$fork_bootstrap_dir" add \
  mujoco_ros2_control/src/mujoco_system_interface.cpp \
  mujoco_ros2_control/tests/test_headless_init.cpp \
  mujoco_ros2_control_plugins/include/mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp
git -C "$fork_bootstrap_dir" diff --cached --check
git -C "$fork_bootstrap_dir" commit -m "feat: add reset pause snapshot hooks"
git -C "$fork_bootstrap_dir" push origin main
git -C "$fork_bootstrap_dir" push origin refs/tags/0.0.3
git ls-remote git@gitee.com:zjumty/mujoco_ros2_control.git refs/heads/main refs/tags/0.0.3
```

Expected: Gitee returns the fork commit for `main` and the official commit for tag `0.0.3`; no force-push is used.

---

### Task 2: Add the Fork as a Project Submodule

**Files:**
- Create/Modify: `.gitmodules`
- Create gitlink: `third_party/mujoco_ros2_control`

**Interfaces:**
- Consumes: published fork `origin/main` from Task 1.
- Produces: project-local fork source at `third_party/mujoco_ros2_control`; later fork tasks edit this checkout directly.

- [ ] **Step 1: Add the submodule and verify remotes**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
git submodule add git@gitee.com:zjumty/mujoco_ros2_control.git third_party/mujoco_ros2_control
git -C third_party/mujoco_ros2_control remote add upstream \
  https://github.com/ros-controls/mujoco_ros2_control.git
git -C third_party/mujoco_ros2_control checkout main
git -C third_party/mujoco_ros2_control remote -v
git submodule status
```

Expected: the gitlink points to the published reset-hook commit, `origin` is Gitee, and `upstream` is GitHub. If `upstream` already exists, verify its URL instead of adding it again.

- [ ] **Step 2: Write and run the project contract for the submodule identity**

Create the initial `src/so101_mujoco_demo_py/test/test_fork_dependency.py` assertions:

```python
from pathlib import Path
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SUBMODULE = PROJECT_ROOT / "third_party/mujoco_ros2_control"


def test_fork_submodule_has_approved_origin_and_official_base() -> None:
    origin = subprocess.run(
        ["git", "-C", str(SUBMODULE), "remote", "get-url", "origin"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert origin == "git@gitee.com:zjumty/mujoco_ros2_control.git"
    ancestry = subprocess.run(
        [
            "git",
            "-C",
            str(SUBMODULE),
            "merge-base",
            "--is-ancestor",
            "35ba8174b62d9560093614f981a3d4b978a96036",
            "HEAD",
        ],
        check=False,
    )
    assert ancestry.returncode == 0
```

Run:

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py
python3 -m pytest test/test_fork_dependency.py -q
```

Expected: the contract passes for the just-added submodule. If it fails, correct `.gitmodules`, checkout or remote identity rather than weakening the assertions; this is a setup/provenance task, so do not manufacture an artificial RED.

- [ ] **Step 3: Run the contract GREEN and commit only the gitlink boundary**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
python3 -m pytest src/so101_mujoco_demo_py/test/test_fork_dependency.py -q
git add -- .gitmodules third_party/mujoco_ros2_control \
  src/so101_mujoco_demo_py/test/test_fork_dependency.py
git diff --cached --check
git commit -m "build(so101_mujoco): add maintained control fork"
```

Expected: the main project commit contains only `.gitmodules`, the gitlink and the focused identity test. Do not push the main project yet; camera fork commits must be published first.

---

### Task 3: Add Typed Viewer Camera State Logic in the Fork

**Files:**
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/msg/ViewerCamera.msg`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/SetViewerCamera.srv`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/srv/GetViewerCamera.srv`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_msgs/CMakeLists.txt`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/viewer_camera.hpp`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/viewer_camera.cpp`
- Create: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_viewer_camera.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/CMakeLists.txt`

**Interfaces:**
- Consumes: MuJoCo `mjModel`, `mjvCamera`, viewer selector convention `0=free`, `1=tracking`, `2+camera_id=fixed`.
- Produces: `ViewerCameraResult validate_and_apply_viewer_camera(const ViewerCamera &, const mjModel *, mjvCamera &, int &)` and `ViewerCameraResult read_viewer_camera(const mjModel *, const mjvCamera &, int)`; Task 4 callbacks use only these helpers.

- [ ] **Step 1: Write the RED helper tests**

Define this API in the test before the header exists:

```cpp
namespace mujoco_ros2_control
{
struct ViewerCameraResult
{
  bool success;
  std::string message;
  mujoco_ros2_control_msgs::msg::ViewerCamera camera;
};

double normalize_viewer_azimuth(double degrees);

ViewerCameraResult validate_and_apply_viewer_camera(
  const mujoco_ros2_control_msgs::msg::ViewerCamera & request,
  const mjModel * model,
  mjvCamera & camera,
  int & camera_selector);

ViewerCameraResult read_viewer_camera(
  const mjModel * model,
  const mjvCamera & camera,
  int camera_selector);
}  // namespace mujoco_ros2_control
```

Tests must assert:

```cpp
EXPECT_DOUBLE_EQ(normalize_viewer_azimuth(225.0), -135.0);
EXPECT_DOUBLE_EQ(normalize_viewer_azimuth(-225.0), 135.0);

// A valid FREE request sets mjCAMERA_FREE, selector 0, clears fixed/track ids,
// copies lookat/distance/elevation/orthographic and returns normalized azimuth.

// NaN lookat, Inf azimuth, distance <= 0, elevation <= -90 or >= 90,
// a non-empty fixed_camera_name in FREE mode, and unknown mode all fail.
// Every failure leaves byte-for-byte camera fields and selector unchanged.

// A valid FIXED request resolves a named MJCF camera, sets mjCAMERA_FIXED,
// fixedcamid and selector=id+2. An unknown name fails without mutation.

// read_viewer_camera returns FREE or FIXED state; tracking/user camera returns
// success=false rather than being misreported as a supported mode.
```

Run:

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
source /opt/ros/jazzy/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log build \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control
```

Expected RED: configure or compile fails because the new interfaces/helper do not exist.

- [ ] **Step 2: Add the exact rosidl definitions**

`ViewerCamera.msg`:

```text
uint8 FREE=0
uint8 FIXED=1

uint8 mode
float64[3] lookat
float64 distance
float64 azimuth_deg
float64 elevation_deg
bool orthographic
string fixed_camera_name
```

`SetViewerCamera.srv`:

```text
ViewerCamera camera
---
bool success
string message
ViewerCamera applied_camera
```

`GetViewerCamera.srv`:

```text
---
bool success
string message
ViewerCamera camera
```

Add all three paths to `mujoco_ros2_control_msgs/CMakeLists.txt` and ensure `rosidl_generate_interfaces` generates the message before services consume it.

- [ ] **Step 3: Implement atomic validation and state conversion**

Implement helpers in `viewer_camera.cpp` with these rules:

```cpp
const auto original_camera = camera;
const int original_selector = camera_selector;
mjvCamera candidate = camera;
int candidate_selector = camera_selector;

// Validate every mode-specific field and resolve names into candidate only.
// Assign camera=candidate and camera_selector=candidate_selector only after
// all validation succeeds. Failure returns without touching the originals.
```

Normalize azimuth into `[-180.0, 180.0)`. FREE sets `type=mjCAMERA_FREE`, `fixedcamid=-1`, `trackbodyid=-1`, selector `0`. FIXED resolves with `mj_name2id(model, mjOBJ_CAMERA, name.c_str())`, sets `type=mjCAMERA_FIXED`, `fixedcamid=id`, `trackbodyid=-1`, selector `id+2`.

- [ ] **Step 4: Build and run the focused GREEN suite**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log build \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --cmake-clean-cache \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log test \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --packages-select mujoco_ros2_control \
  --ctest-args -R test_viewer_camera \
  --event-handlers console_direct+
colcon test-result --test-result-base /data/work/ws_mujoco_ros2_control_fork/build --verbose
ros2 interface show mujoco_ros2_control_msgs/msg/ViewerCamera
ros2 interface show mujoco_ros2_control_msgs/srv/SetViewerCamera
ros2 interface show mujoco_ros2_control_msgs/srv/GetViewerCamera
```

Expected: helper tests pass and all three interfaces match this plan exactly.

- [ ] **Step 5: Commit and push the fork data-plane change**

```zsh
git -C third_party/mujoco_ros2_control add \
  mujoco_ros2_control_msgs/msg/ViewerCamera.msg \
  mujoco_ros2_control_msgs/srv/SetViewerCamera.srv \
  mujoco_ros2_control_msgs/srv/GetViewerCamera.srv \
  mujoco_ros2_control_msgs/CMakeLists.txt \
  mujoco_ros2_control/include/mujoco_ros2_control/viewer_camera.hpp \
  mujoco_ros2_control/src/viewer_camera.cpp \
  mujoco_ros2_control/tests/test_viewer_camera.cpp \
  mujoco_ros2_control/CMakeLists.txt \
  mujoco_ros2_control/tests/CMakeLists.txt
git -C third_party/mujoco_ros2_control diff --cached --check
git -C third_party/mujoco_ros2_control commit -m "feat: add viewer camera state model"
git -C third_party/mujoco_ros2_control push origin main
```

Expected: Gitee `main` contains the helper commit before the project gitlink is advanced.

---

### Task 4: Expose Viewer Camera Services from `MujocoSystemInterface`

**Files:**
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_system_interface.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_headless_init.cpp`

**Interfaces:**
- Consumes: helper functions and message/service definitions from Task 3.
- Produces: `~/set_viewer_camera` and `~/get_viewer_camera`, resolving to `/mujoco_ros2_control_node/set_viewer_camera` and `/mujoco_ros2_control_node/get_viewer_camera`.

- [ ] **Step 1: Write RED callback tests beside the existing reset tests**

Extend the headless test MJCF with a fixed camera:

```xml
<camera name="fixed_test" pos="1 -1 1" xyaxes="1 1 0 -0.5 0.5 1"/>
```

Add tests that directly invoke the private callbacks using the file's existing private-test access pattern:

```cpp
TEST_F(HeadlessInitTest, ViewerCameraServicesRejectHeadlessWithoutMutation)
{
  // Initialize with headless=true, copy cam_ and sim_->camera, call set/get,
  // expect success=false, message="viewer unavailable", and no mutation.
}

TEST_F(HeadlessInitTest, ViewerCameraSetGetPreservePhysicsState)
{
  // After initialization set headless_=false only for callback unit coverage.
  // Copy qpos/qvel/ctrl/xfrc, apply a FREE request, then GET.
  // Assert applied/read-back camera values agree and all physics arrays match.
}

TEST_F(HeadlessInitTest, ViewerCameraInvalidRequestIsAtomic)
{
  // Apply one valid FREE state, submit an invalid distance, and assert camera,
  // selector and physics arrays remain unchanged.
}
```

Run the focused test and require RED because callbacks/members do not exist:

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log test \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --packages-select mujoco_ros2_control \
  --ctest-args -R test_headless_init \
  --event-handlers console_direct+
```

- [ ] **Step 2: Add service ownership and registration**

Add header includes, callbacks and members:

```cpp
void set_viewer_camera_callback(
  const std::shared_ptr<mujoco_ros2_control_msgs::srv::SetViewerCamera::Request> request,
  std::shared_ptr<mujoco_ros2_control_msgs::srv::SetViewerCamera::Response> response);

void get_viewer_camera_callback(
  const std::shared_ptr<mujoco_ros2_control_msgs::srv::GetViewerCamera::Request> request,
  std::shared_ptr<mujoco_ros2_control_msgs::srv::GetViewerCamera::Response> response);

rclcpp::CallbackGroup::SharedPtr viewer_camera_cb_group_;
rclcpp::Service<mujoco_ros2_control_msgs::srv::SetViewerCamera>::SharedPtr set_viewer_camera_service_;
rclcpp::Service<mujoco_ros2_control_msgs::srv::GetViewerCamera>::SharedPtr get_viewer_camera_service_;
```

Register both services with `~/set_viewer_camera` and `~/get_viewer_camera` using one mutually-exclusive callback group and the same service QoS as reset/pause/step.

- [ ] **Step 3: Implement the exact callback boundary**

Both callbacks must follow this order:

```cpp
if (headless_ || sim_ == nullptr || sim_mutex_ == nullptr || mj_model_ == nullptr)
{
  response->success = false;
  response->message = "viewer unavailable";
  return;
}

const std::unique_lock<std::recursive_mutex> lock(*sim_mutex_);
// SET: validate_and_apply_viewer_camera(request->camera, mj_model_, cam_, sim_->camera)
// GET: read_viewer_camera(mj_model_, cam_, sim_->camera)
```

Map the helper result to response fields. Do not call `update_sim_display`, pause, reset, step, plugin hooks or any function that writes `mj_data_`.

- [ ] **Step 4: Run focused and full fork GREEN tests**

```zsh
source /opt/ros/jazzy/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log build \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon --log-base /data/work/ws_mujoco_ros2_control_fork/log test \
  --base-paths third_party/mujoco_ros2_control \
  --build-base /data/work/ws_mujoco_ros2_control_fork/build \
  --install-base /data/work/ws_mujoco_ros2_control_fork/install \
  --merge-install \
  --packages-select mujoco_ros2_control_msgs mujoco_ros2_control_plugins mujoco_ros2_control \
  --event-handlers console_direct+
colcon test-result --test-result-base /data/work/ws_mujoco_ros2_control_fork/build --verbose
```

Expected: new camera tests and all reset/pause/snapshot upstream/fork tests pass.

- [ ] **Step 5: Commit, tag and publish the first qualified fork release**

```zsh
git -C third_party/mujoco_ros2_control add \
  mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp \
  mujoco_ros2_control/src/mujoco_system_interface.cpp \
  mujoco_ros2_control/tests/test_headless_init.cpp
git -C third_party/mujoco_ros2_control diff --cached --check
git -C third_party/mujoco_ros2_control commit -m "feat: expose viewer camera services"
git -C third_party/mujoco_ros2_control tag -a so101-0.0.3-r1 \
  -m "SO-101 reset and viewer camera qualified fork"
git -C third_party/mujoco_ros2_control push origin main
git -C third_party/mujoco_ros2_control push origin so101-0.0.3-r1
git ls-remote git@gitee.com:zjumty/mujoco_ros2_control.git \
  refs/heads/main refs/tags/so101-0.0.3-r1 refs/tags/so101-0.0.3-r1^{}
```

Expected: annotated tag dereferences to the just-tested callback commit. Record that exact commit for Task 5.

---

### Task 5: Replace Patch Replay with the Fork Installer and Lock

**Files:**
- Create: `scripts/install-mujoco-ros2-control.zsh`
- Modify: `src/so101_mujoco_demo_py/config/dependency-lock.yaml`
- Modify: `src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py`
- Modify: `src/so101_mujoco_demo_py/scripts/check_reset_qualified_runtime.py`
- Modify: `src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh`
- Modify: `src/so101_mujoco_demo_py/test/test_dependency_contract.py`
- Modify: `src/so101_mujoco_demo_py/test/test_fork_dependency.py`
- Modify: `src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py`
- Delete: `src/so101_mujoco_demo_py/scripts/build_reset_qualified_overlay.sh`
- Delete: `src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch`
- Delete: `src/so101_mujoco_demo_py/test/test_reset_qualified_dependency.py`

**Interfaces:**
- Consumes: published `so101-0.0.3-r1` commit and gitlink from Tasks 2–4.
- Produces: schema-3 fork lock, replayable installer, fork overlay and runtime provenance report.

- [ ] **Step 1: Rewrite dependency tests to RED against the old patch provider**

The new lock contract must assert:

```python
assert lock["schema_version"] == 3
assert lock["provider"] == "gitee_fork_submodule"
assert lock["release"] == "0.0.3"
assert lock["fork"]["url"] == "git@gitee.com:zjumty/mujoco_ros2_control.git"
assert lock["fork"]["tag"] == "so101-0.0.3-r1"
assert lock["fork"]["commit"] == subprocess.run(
    ["git", "-C", str(SUBMODULE), "rev-parse", "HEAD"],
    check=True,
    text=True,
    capture_output=True,
).stdout.strip()
assert lock["upstream"]["commit"] == "35ba8174b62d9560093614f981a3d4b978a96036"
assert lock["submodule_path"] == "third_party/mujoco_ros2_control"
assert lock["prefix"] == "/data/work/ws_mujoco_ros2_control_fork/install"
assert "patch" not in lock
```

Also assert the installer contains no `git reset`, `git clean`, `/opt/ros/jazzy` install base or old `_003` install base. Run:

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py
python3 -m pytest \
  test/test_dependency_contract.py \
  test/test_fork_dependency.py \
  test/test_repository_isolation_contract.py -q
```

Expected RED: old schema/provider/patch paths violate the new contract.

- [ ] **Step 2: Implement the zsh installer with fail-closed source checks**

The script must use focused functions with these responsibilities:

```zsh
resolve_project_root()       # script directory parent; no cwd assumption
initialize_submodule()       # only when --init-submodule is explicit
verify_source_identity()     # origin, clean status, HEAD, tag, base ancestry
build_and_test_overlay()     # explicit base/build/install/log/package list
verify_installed_overlay()   # ros2 pkg prefix, interfaces, required files
```

Use `/data/work/ws_mujoco_ros2_control_fork/{build,install,log}` and the project submodule as `--base-paths`. Source `setup.zsh`, never `setup.bash`. Unknown arguments return exit 2. Missing/uninitialized/dirty/wrong-commit submodule fails before colcon is called.

- [ ] **Step 3: Write schema 3 and update all runtime checkers**

Record the exact Task 4 tag commit, source order and package prefixes. Add these interface keys to the runtime probe:

```python
"mujoco_ros2_control_msgs/msg/ViewerCamera"
"mujoco_ros2_control_msgs/srv/SetViewerCamera"
"mujoco_ros2_control_msgs/srv/GetViewerCamera"
```

Retain `ResetWorld`, `SetPause` and `StepSimulation`. Replace patch/file-diff checks with gitlink HEAD, origin URL, official base ancestry, release tag and clean status checks.

- [ ] **Step 4: Run installer RED/GREEN contract tests without touching source**

```zsh
zsh -n scripts/install-mujoco-ros2-control.zsh
python3 -m pytest \
  src/so101_mujoco_demo_py/test/test_dependency_contract.py \
  src/so101_mujoco_demo_py/test/test_fork_dependency.py \
  src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py -q
```

Expected: all static contracts pass. Tests must include a fake `colcon` and temporary Git repository proving dirty/wrong commit fails before build and clean/correct source reaches the fake build command.

- [ ] **Step 5: Build the real overlay, capture hashes and verify provenance**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
zsh scripts/install-mujoco-ros2-control.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
ros2 pkg prefix mujoco_ros2_control
ros2 pkg prefix mujoco_ros2_control_msgs
ros2 pkg prefix mujoco_ros2_control_plugins
ros2 pkg prefix mujoco_vendor
python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
```

Expected prefixes: three fork packages use `/data/work/ws_mujoco_ros2_control_fork/install`; `mujoco_vendor` uses `/opt/ros/jazzy`. Insert the actual SHA-256 values emitted by the probe into `required_files`, rerun the probe, and require `validation_errors=[]`.

- [ ] **Step 6: Remove patch replay artifacts only after the fork gate is GREEN**

Delete the old patch, build script and patch-replay test. Run:

```zsh
rg -n 'patched_source|build_reset_qualified_overlay|mujoco_ros2_control-0.0.3-reset-hook' \
  src/so101_mujoco_demo_py scripts
```

Expected: no runtime/build/test reference remains. Historical design and experiment documents may retain provenance statements about earlier runs.

- [ ] **Step 7: Commit the main-project dependency migration**

```zsh
git add -- .gitmodules third_party/mujoco_ros2_control scripts \
  src/so101_mujoco_demo_py/config/dependency-lock.yaml \
  src/so101_mujoco_demo_py/scripts \
  src/so101_mujoco_demo_py/test/test_dependency_contract.py \
  src/so101_mujoco_demo_py/test/test_fork_dependency.py \
  src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py \
  src/so101_mujoco_demo_py/test/test_reset_qualified_dependency.py \
  src/so101_mujoco_demo_py/patches/mujoco_ros2_control-0.0.3-reset-hook.patch
git diff --cached --check
git commit -m "build(so101_mujoco): consume qualified control fork"
```

Expected: deletion paths are staged, gitlink equals the already-pushed `so101-0.0.3-r1` commit, and no Task13 file is staged.

---

### Task 6: Implement Strict Project Camera Preset Parsing

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/camera_presets.py`
- Create: `src/so101_mujoco_demo_py/test/test_camera_presets.py`
- Modify: `src/so101_mujoco_demo_py/package.xml`

**Interfaces:**
- Consumes: YAML mappings supplied by tests now and installed `camera_views.yaml` in Task 9.
- Produces: immutable `FreeCameraPreset`, `FixedCameraPreset`, `CameraPreset`, `load_camera_presets`, `normalize_azimuth`, `circular_azimuth_distance`, `preset_to_yaml_fields`.

- [ ] **Step 1: Write RED strict-schema tests**

Use these exact public shapes:

```python
@dataclass(frozen=True)
class FreeCameraPreset:
    name: str
    lookat: tuple[float, float, float]
    distance: float
    azimuth_deg: float
    elevation_deg: float
    orthographic: bool


@dataclass(frozen=True)
class FixedCameraPreset:
    name: str
    fixed_camera_name: str


CameraPreset = FreeCameraPreset | FixedCameraPreset
```

The module exports these exact call signatures:

- `load_camera_presets(config_file: Path) -> dict[str, CameraPreset]`
- `normalize_azimuth(degrees: float) -> float`
- `circular_azimuth_distance(left: float, right: float) -> float`
- `preset_to_yaml_fields(preset: CameraPreset) -> dict[str, object]`

Tests must cover valid free/fixed records and reject duplicate YAML keys, unknown root/preset fields, unknown mode, missing fields, non-finite values, bool-as-number, nonpositive distance, elevation outside the open interval `(-90, 90)`, free records with fixed fields and fixed records with free fields.

Run:

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py
python3 -m pytest test/test_camera_presets.py -q
```

Expected RED: module import fails.

- [ ] **Step 2: Implement the duplicate-safe YAML loader and dataclasses**

Subclass `yaml.SafeLoader` with a mapping constructor that raises `CameraPresetConfigError` on a repeated key before constructing the dictionary. Validate `schema_version == 1`, root keys exactly `{schema_version, presets}`, non-empty string names, and mode-specific key sets.

Normalize azimuth into `[-180.0, 180.0)` only when producing the immutable record. Preserve the three-element lookat order as floats.

- [ ] **Step 3: Run GREEN tests and Ruff**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py
python3 -m pytest test/test_camera_presets.py -q
zsh scripts/check_ruff.sh
```

Expected: parser tests and both Ruff check/format gates pass.

- [ ] **Step 4: Commit the pure configuration boundary**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/camera_presets.py \
  src/so101_mujoco_demo_py/test/test_camera_presets.py \
  src/so101_mujoco_demo_py/package.xml
git diff --cached --check
git commit -m "feat(so101_mujoco): parse viewer camera presets"
```

Expected: no ROS client or uncalibrated production YAML is included in this commit.

---

### Task 7: Add the ROS Gateway and CLI

**Files:**
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/viewer_camera_client.py`
- Create: `src/so101_mujoco_demo_py/so101_mujoco_demo_py/camera_preset_cli.py`
- Create: `src/so101_mujoco_demo_py/test/test_camera_preset_cli.py`
- Modify: `src/so101_mujoco_demo_py/setup.py`
- Modify: `src/so101_mujoco_demo_py/package.xml`

**Interfaces:**
- Consumes: Task 6 `CameraPreset` and fork `SetViewerCamera`/`GetViewerCamera`.
- Produces: immutable `FreeViewerCameraState`/`FixedViewerCameraState`, `ViewerCameraState`, `viewer_camera_state_to_yaml_fields`, `ViewerCameraGateway` protocol, `RosViewerCameraGateway`, `run(argv, gateway_factory, config_file) -> int`, console executable `camera_preset`.

- [ ] **Step 1: Write RED CLI tests using a fake gateway**

Define the test seam:

```python
@dataclass(frozen=True)
class FreeViewerCameraState:
    lookat: tuple[float, float, float]
    distance: float
    azimuth_deg: float
    elevation_deg: float
    orthographic: bool


@dataclass(frozen=True)
class FixedViewerCameraState:
    fixed_camera_name: str


ViewerCameraState = FreeViewerCameraState | FixedViewerCameraState
```

The client/CLI modules export these exact call signatures:

- `viewer_camera_state_to_yaml_fields(state: ViewerCameraState) -> dict[str, object]`
- `ViewerCameraGateway.set_camera(preset: CameraPreset) -> ViewerCameraState`
- `ViewerCameraGateway.get_camera() -> ViewerCameraState`
- `ViewerCameraGateway.close() -> None`
- `run(argv: Sequence[str] | None = None, *, gateway_factory: Callable[[], ViewerCameraGateway] = RosViewerCameraGateway, config_file: Path | None = None) -> int`

Tests must assert:

- `--list` prints names in YAML order and creates no ROS gateway;
- applying `table_corner_nw` passes the typed preset once and prints applied state;
- `--current` prints readable fields;
- `--current --format yaml` prints a copyable free/fixed mapping without writing a file;
- unknown preset/config errors exit 2;
- service unavailable/timeout/rejected response exit nonzero and preserve the server message;
- gateway `close()` is called on every path after construction.

Run:

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py
python3 -m pytest test/test_camera_preset_cli.py -q
```

Expected RED: gateway and CLI modules do not exist.

- [ ] **Step 2: Implement typed request/response conversion**

`RosViewerCameraGateway` creates clients for:

```text
/mujoco_ros2_control_node/set_viewer_camera
/mujoco_ros2_control_node/get_viewer_camera
```

Use one 3.0-second service discovery deadline and one 3.0-second response deadline. FREE fills every free field and clears `fixed_camera_name`; FIXED fills only mode/name. A response with `success=false` raises `ViewerCameraServiceError(message)`. Always destroy the node and call `rclpy.shutdown()` only if this gateway initialized rclpy.

Convert every successful ROS response into `FreeViewerCameraState` or `FixedViewerCameraState`; `viewer_camera_state_to_yaml_fields` emits the same mode-specific key set used by Task 6 config parsing.

- [ ] **Step 3: Implement CLI path resolution and output**

Default config is resolved through the installed package share with `ament_index_python.packages.get_package_share_directory("so101_mujoco_demo_py") / "config/camera_views.yaml"`. A test-provided `config_file` bypasses ament lookup.

`--current` must not load `camera_views.yaml`; it only queries the get service. `--list` and preset apply load and validate YAML before constructing a ROS gateway.

Register:

```python
"camera_preset = so101_mujoco_demo_py.camera_preset_cli:main"
```

Do not add Web routes or import Teleop modules.

- [ ] **Step 4: Run focused GREEN and package Python gates**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/src/so101_mujoco_demo_py
python3 -m pytest \
  test/test_camera_presets.py \
  test/test_camera_preset_cli.py \
  test/test_pick_place_cli.py -q
zsh scripts/check_ruff.sh
```

Expected: all focused tests and Ruff gates pass.

- [ ] **Step 5: Commit the CLI boundary**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
git add -- \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/viewer_camera_client.py \
  src/so101_mujoco_demo_py/so101_mujoco_demo_py/camera_preset_cli.py \
  src/so101_mujoco_demo_py/test/test_camera_preset_cli.py \
  src/so101_mujoco_demo_py/setup.py \
  src/so101_mujoco_demo_py/package.xml
git diff --cached --check
git commit -m "feat(so101_mujoco): add viewer camera CLI"
```

---

### Task 8: Prove the Installed Services in Headless Mode

**Files:**
- Create: `src/so101_mujoco_demo_py/test/test_viewer_camera_live_contract.py`
- Modify: `src/so101_mujoco_demo_py/test/test_mujoco_launch.py`
- Modify: `src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py`

**Interfaces:**
- Consumes: fork overlay from Task 5 and project CLI from Task 7.
- Produces: opt-in live proof that interfaces/services come from the fork and headless rejects camera operations explicitly.

- [ ] **Step 1: Write an opt-in RED live contract**

Gate the test with `SO101_MUJOCO_LIVE_TEST=1`. It must launch `so101_mujoco.launch.py headless:=true`, wait for both camera services, call GET and SET, and assert both responses are:

```python
assert response.success is False
assert response.message == "viewer unavailable"
```

Also assert reset/pause/step services remain present. The test must fail if any service type resolves from `/opt/ros/jazzy` instead of the fork overlay.

- [ ] **Step 2: Build the project against the fork overlay and observe RED**

```zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
colcon build --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --symlink-install --cmake-clean-cache
source install/setup.zsh
SO101_MUJOCO_LIVE_TEST=1 python3 -m pytest \
  src/so101_mujoco_demo_py/test/test_viewer_camera_live_contract.py -q
```

If this test is already GREEN because Tasks 3–5 fully supplied the behavior, record it as pre-existing integration coverage and do not manufacture a failure. Any real failure must be fixed at its owning launch, install or fork boundary.

- [ ] **Step 3: Make only the owning launch/runtime contract changes**

Do not special-case headless in Python. Fix launch dependencies, installed config or fork service registration at the owning layer until the exact test passes.

- [ ] **Step 4: Run GREEN, package tests and provenance checks**

```zsh
SO101_MUJOCO_LIVE_TEST=1 python3 -m pytest \
  src/so101_mujoco_demo_py/test/test_viewer_camera_live_contract.py -q
PYTHONNOUSERSITE=1 colcon test \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --event-handlers console_direct+
colcon test-result --verbose
python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
```

Expected: live contract, both project packages and provenance validation pass.

- [ ] **Step 5: Commit the headless integration proof**

```zsh
git add -- \
  src/so101_mujoco_demo_py/test/test_viewer_camera_live_contract.py \
  src/so101_mujoco_demo_py/test/test_mujoco_launch.py \
  src/so101_mujoco_demo_py/test/test_repository_isolation_contract.py
git diff --cached --check
git commit -m "test(so101_mujoco): prove viewer camera services"
```

---

### Task 9: Calibrate and Commit the Four Table-Corner Presets

**Files:**
- Create: `src/so101_mujoco_demo_py/config/camera_views.yaml`
- Modify: `src/so101_mujoco_demo_py/test/test_camera_presets.py`
- Create: `docs/experiments/so101-mujoco-viewer-camera-experiment-ledger.md`

**Interfaces:**
- Consumes: live GUI set/get services and CLI.
- Produces: four measured, symmetric project presets and CUA visual evidence references.

- [ ] **Step 1: Create the experiment ledger before starting a GUI stack**

Create the ledger with:

```yaml
task_id: so101-mujoco-viewer-camera
goal: provide four reproducible table-corner debug views without changing physics
success_contract: all four presets round-trip through set/get, preserve physics lifecycle, and show the full robot base cup and main table in fresh CUA screenshots
worktree: /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
branch: codex/so101-mujoco-ros2
evidence_root: /tmp/so101-debug-mujoco-viewer-camera/
```

Fill `base_commit` and `current_commit` from the actual `git rev-parse HEAD`. Record the three preserved Task13 files, existing tmux sessions/processes, fork commit/tag, install overlay, runtime executable, and a new unused integer `ROS_DOMAIN_ID`. Pre-register the calibration as `PLANNED` with `lifecycle: FULL_RESTART` before launching.

- [ ] **Step 2: Start one owned GUI stack with the fork overlay**

Inspect `codex-cua` first; do not send input if it is busy. Use tmux session `so101-mujoco-camera` only if it does not exist. Inside the tmux command, source:

```zsh
source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
source /data/work/ws_moveit/.worktrees/so101-mujoco-ros2/install/setup.zsh
```

Launch `so101_mujoco_demo_py so101_mujoco.launch.py` with `headless:=false`, the pre-registered ROS domain and a unique `simulation_session_id`. Save stdout/stderr under `/tmp/so101-debug-mujoco-viewer-camera/`; do not write logs into the repository.

- [ ] **Step 3: Use CUA to align the reference view and read its real state**

Follow `snapshot -> action -> fresh snapshot`. Adjust the free camera until the composition matches the approved reference: complete arm/gripper/base/cup and main table, approximately 20-degree downward view, no important clipping.

Then run:

```zsh
ros2 run so101_mujoco_demo_py camera_preset --current --format yaml
```

Record the exact returned `lookat`, `distance`, `azimuth_deg`, `elevation_deg` and `orthographic` in the ledger. Do not infer distance or lookat from pixels.

- [ ] **Step 4: Write the RED four-corner invariant test**

The production-config test must assert:

```python
required = [
    "table_corner_nw",
    "table_corner_ne",
    "table_corner_se",
    "table_corner_sw",
]
assert list(presets) == required
assert all(isinstance(presets[name], FreeCameraPreset) for name in required)
assert len({presets[name].lookat for name in required}) == 1
assert len({presets[name].distance for name in required}) == 1
assert len({presets[name].elevation_deg for name in required}) == 1
assert len({presets[name].orthographic for name in required}) == 1
for left, right in zip(required, required[1:] + required[:1], strict=True):
    assert circular_azimuth_distance(
        presets[left].azimuth_deg,
        presets[right].azimuth_deg,
    ) == 90.0
```

Run it before the production YAML exists and require RED.

- [ ] **Step 5: Create production YAML from the measured reference**

Use the exact measured free-camera values for `table_corner_nw`. Generate the other three records by keeping all fields identical and adding successive 90-degree azimuth rotations normalized into `[-180, 180)`. Do not round `lookat` or `distance` more aggressively than the get-service output.

- [ ] **Step 6: Build, apply and visually inspect all four views**

```zsh
colcon build --packages-select so101_mujoco_demo_py --symlink-install
source install/setup.zsh
ros2 run so101_mujoco_demo_py camera_preset --list
ros2 run so101_mujoco_demo_py camera_preset table_corner_nw
ros2 run so101_mujoco_demo_py camera_preset table_corner_ne
ros2 run so101_mujoco_demo_py camera_preset table_corner_se
ros2 run so101_mujoco_demo_py camera_preset table_corner_sw
```

After each apply, call `--current`, compare the read-back numerically, and use CUA to obtain a fresh screenshot. Record four absolute screenshot/evidence paths and visible contents in the ledger. Each must show the full robot, gripper, base, cup and main table without key geometry clipping.

- [ ] **Step 7: Run GREEN tests and commit calibrated values**

```zsh
python3 -m pytest \
  src/so101_mujoco_demo_py/test/test_camera_presets.py \
  src/so101_mujoco_demo_py/test/test_camera_preset_cli.py -q
zsh src/so101_mujoco_demo_py/scripts/check_ruff.sh
git add -- \
  src/so101_mujoco_demo_py/config/camera_views.yaml \
  src/so101_mujoco_demo_py/test/test_camera_presets.py \
  docs/experiments/so101-mujoco-viewer-camera-experiment-ledger.md
git diff --cached --check
git commit -m "feat(so101_mujoco): add four-corner camera presets"
```

Expected: config contains measured values, not design examples; ledger experiment is `VALID` or explicitly `INVALID` with a new planned retry.

---

### Task 10: Qualify Physics Invariance and Update the Execution Guide

**Files:**
- Modify: `docs/experiments/so101-mujoco-viewer-camera-experiment-ledger.md`
- Modify: `docs/guides/so101-mujoco-ros2-integration-guide.md`

**Interfaces:**
- Consumes: all fork/project commits and the calibrated four views.
- Produces: final provenance, physics-invariance evidence, user execution guide and clean handoff.

- [ ] **Step 1: Pre-register the final no-pause qualification**

Create a new ledger experiment referencing Task 9. Freeze the fork/main commits, overlay prefixes, ROS domain, GUI session and normal-running initial state. Success requires unchanged `reset_epoch`, strictly increasing `simulation_step`, unchanged controller lifecycle, no joint discontinuity aligned to camera calls, four successful set/get round trips and four accepted CUA screenshots.

- [ ] **Step 2: Capture time-bounded numeric evidence around camera switching**

Before the first switch, save:

- one `SimulationEvidence` sample containing `reset_epoch` and `simulation_step`;
- `ros2 control list_controllers`;
- a timestamped `/joint_states` stream covering a no-switch baseline window.

During the same normally running lifecycle, apply all four presets while recording `/joint_states`. After the last switch, capture another evidence sample and controller list. Compare maximum adjacent joint delta in each switch window with the no-switch baseline; a camera call must not introduce a new discontinuity. Do not demand exactly zero joint motion from a running physics simulation.

- [ ] **Step 3: Prove callback and runtime boundaries together**

Record in the ledger:

- fork unit test proving no qpos/qvel/ctrl/xfrc writes;
- source location of the `sim_mutex_` critical section;
- unchanged `reset_epoch`;
- increasing `simulation_step`;
- controller states before/after;
- joint-delta comparison;
- set/get responses and screenshot paths.

A screenshot alone and a service success alone are both insufficient.

- [ ] **Step 4: Rewrite the integration guide for the fork workflow**

Update the guide to include:

- Gitee fork URL, official base and release tag policy;
- `git submodule update --init third_party/mujoco_ros2_control`;
- `zsh scripts/install-mujoco-ros2-control.zsh`;
- exact source order and package-prefix checks;
- removal of patch replay as the current workflow;
- old `_003` overlay as rollback only;
- `camera_preset --list`, apply and `--current --format yaml` examples;
- four-corner calibration/visual acceptance;
- distinction between viewer debug camera and RGB-D sensor camera;
- Teleop Web UI explicitly deferred.

Historical sections may describe the old patch route only when clearly labeled as superseded.

- [ ] **Step 5: Run every final automated gate from a fresh shell**

```zsh
source /opt/ros/jazzy/setup.zsh
source /data/work/ws_mujoco_ros2_control_fork/install/setup.zsh
cd /data/work/ws_moveit/.worktrees/so101-mujoco-ros2
source install/setup.zsh
zsh scripts/install-mujoco-ros2-control.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select so101_mujoco_support so101_mujoco_demo_py \
  --event-handlers console_direct+
colcon test-result --verbose
zsh src/so101_mujoco_demo_py/scripts/check_ruff.sh
python3 src/so101_mujoco_demo_py/scripts/check_mujoco_runtime.py \
  --lock src/so101_mujoco_demo_py/config/dependency-lock.yaml
zsh src/so101_mujoco_demo_py/scripts/check_migration_isolation.sh
git diff --check
git -C third_party/mujoco_ros2_control status --short
git status --short
```

Expected: fork and project suites pass; provenance and isolation pass; fork is clean; main status contains only intentional guide/ledger changes plus the three preserved Task13 untracked files.

- [ ] **Step 6: Commit the final guide and qualification checkpoint**

```zsh
git add -- \
  docs/guides/so101-mujoco-ros2-integration-guide.md \
  docs/experiments/so101-mujoco-viewer-camera-experiment-ledger.md
git diff --cached --check
git commit -m "docs(so101_mujoco): qualify fork camera workflow"
```

If the final isolation gate exposes an implementation defect, stop and add a focused RED/GREEN correction to the task that owns it; do not fold an unplanned code fix into this documentation commit. Never stage the Task13 files.

- [ ] **Step 7: Push in dependency order and verify remote read-back**

```zsh
git -C third_party/mujoco_ros2_control status --short
git -C third_party/mujoco_ros2_control push origin main
git push origin codex/so101-mujoco-ros2
git ls-remote git@gitee.com:zjumty/mujoco_ros2_control.git refs/heads/main refs/tags/so101-0.0.3-r1^{}
git ls-remote origin refs/heads/codex/so101-mujoco-ros2
```

Expected: fork remote contains every pinned commit before the main-project branch; remote branch SHA equals local HEAD. Do not merge or push a default branch.

---

## Completion Gate

The implementation is complete only when all of the following are true:

- Gitee fork preserves the official 0.0.3 ancestry and publishes immutable `so101-0.0.3-r1`.
- project gitlink and schema-3 lock pin that published commit.
- installer rebuilds/tests the fork from the project submodule and proves package/interface provenance.
- old patch replay is removed from the active build path while the old overlay remains available for rollback.
- FREE/FIXED helper and service tests pass, including invalid-request atomicity and physics-array invariance.
- headless services are discoverable and return `viewer unavailable`.
- four measured table-corner presets round-trip through CLI/get service with 90-degree azimuth spacing.
- normal physics continues without reset epoch change, step discontinuity, controller lifecycle change or camera-aligned joint jump.
- four fresh CUA screenshots visibly contain the complete robot, gripper, base, cup and main table.
- integration guide and experiment ledger contain exact commits, prefixes, commands, exit codes and evidence paths.
- `src/so101_gazebo_demo_py/**`, Teleop Web UI, RGB-D and the three Task13 files remain untouched.

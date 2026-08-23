# `mujoco_ros2_control` 跨平台 Patch Series 设计

> Superseded on 2026-08-14 by `so101-0.0.3-r7`. This document records the validated migration input; active builds consume the clean fork and do not replay this series.

## 目标

仓库固定 `third_party/mujoco_ros2_control` 在提交
`738e304551b4ea6db020b466086a13db71b65607`，以同一组、同一顺序的 patch 构建 Linux 和
macOS。安装器不得按操作系统选择是否应用 patch；平台差异只能由应用 patch 后的 CMake
和 C++ 条件分支表达。

完成后应满足：

- submodule 保持干净，不直接保存本地适配改动；
- Linux 与 macOS 对相同固定提交重放相同 patch 字节；
- macOS 保留已验证的 MuJoCo viewer、headless、dylib 和测试运行能力；
- Linux 保留现有 tinyxml2 linker 行为和无 AppKit/Cocoa 依赖的构建；
- patch 可正向应用、反向移除，并在反向移除后恢复零 diff；
- 两个平台都完成 fork 的构建、包测试、安装前缀和接口校验。

## 非目标

- 不改变 SO-101 策略、MJCF、MoveIt、reset 生命周期或资格判据。
- 不更新 fork tag、gitlink 或依赖锁中的 fork commit。
- 不把适配代码直接提交到 `mujoco_ros2_control` fork。
- 不要求 Linux 启用 macOS viewer 实现，也不要求 macOS 采用 Linux ELF linker 参数。

## 当前状态

主仓已经跟踪 10 个 `scripts/patches/mujoco-ros2-control-macos-*.patch`。安装器只在
`uname -s == Darwin` 时重放它们，Linux 使用未打 patch 的源码。

`third_party/mujoco_ros2_control` 当前有 3 个修改文件，其完整 diff 已由
`patches/mujoco_ros2_control/macos-format-uint64.patch` 保存。该 patch 与现有正式 patch
系列重复，并且未被安装器使用。迁移必须先证明其每个 hunk 已进入新的权威 series，再恢复
submodule；不得直接丢弃未覆盖差异。

## Patch 组织

权威目录调整为：

```text
scripts/patches/mujoco_ros2_control/
├── series
├── 0001-portable-heartbeat-format.patch
├── 0002-platform-build-and-rpath.patch
├── 0003-headless-rendering-control.patch
├── 0004-apple-main-thread-ui.patch
├── 0005-apple-framework-linkage.patch
├── 0006-apple-test-logging-runtime.patch
├── 0007-apple-test-rmw-runtime.patch
├── 0008-platform-cxx17-requirements.patch
├── 0009-apple-conversion-warnings.patch
├── 0010-apple-test-backward-runtime.patch
└── 0011-guard-apple-test-runtime-dependencies.patch
```

实施时保留原 10 个已验证 patch 的相对顺序，并追加第 11 个 guard patch，将 Apple 测试
依赖和 `APPEND_LIBRARY_DIRS` 收紧到 `APPLE` 分支。所有文件必须遵守以下规则：

- `series` 是唯一顺序来源，每行一个相对 patch 文件名；
- 文件名使用数字前缀，应用顺序不依赖 glob 或文件系统排序；
- patch 只以固定 fork commit 为基线，不以已修改 submodule 为基线；
- 不保留内容重复的第二套 patch；
- `.gitattributes` 增加 `scripts/patches/mujoco_ros2_control/*.patch -whitespace`，避免嵌套
  目录中的补丁正文被 Git 改写；
- 安装器拒绝空行以外的未知条目、绝对路径和包含 `..` 的路径。

## 平台边界

同一 series 在两个平台都完整应用。应用后的源码按下列边界编译：

| 修改 | Linux | macOS |
| --- | --- | --- |
| `PRIu64` heartbeat 格式 | 编译并使用 | 编译并使用 |
| C++17 target feature | 编译并使用 | 编译并使用 |
| `disable_rendering` / headless 公共参数 | 编译并使用 | 编译并使用 |
| ELF tinyxml2 linker 选项 | `if(NOT APPLE)` 保持原行为 | 不生成 |
| Mach-O install rpath 与可执行路径 | 不生成 | `if(APPLE)` / `#ifdef __APPLE__` |
| Objective-C++、Cocoa、CoreVideo | 不启用 | `if(APPLE)` |
| viewer 主线程调度 | 保持现有 Linux executor/render thread | `#ifdef __APPLE__` 使用 AppKit 主线程 |
| CTest dylib 补充路径 | 不增加无用依赖 | `if(APPLE)` 添加必要 runtime library dirs |

Apple 专用 include、symbol、framework、编译语言和测试依赖不得出现在 Linux 的有效构建
分支中。Linux 原有代码不得通过“Linux 不应用 patch”获得保护，而应由上述条件分支明确
保护。

## 安装器行为

`scripts/install-mujoco-ros2-control.zsh` 在所有平台执行同一流程：

1. 校验 dependency lock、gitlink、fork URL、tag 和固定 commit；
2. 要求原始 submodule 零 diff；
3. 创建或复用独立 build source；
4. 按 `series` 逆序移除已应用 patch，使 build source 回到固定 commit；
5. 要求恢复后的 build source 零 diff；
6. 按 `series` 正序执行 `git apply --check` 和 `git apply`；
7. 在当前平台构建、测试并校验安装产物。

该流程保持幂等：连续执行安装器不会累积 patch，也不会修改 submodule。任一 patch 不能应用、
反向恢复后仍有差异、或 series 出现未登记文件时都必须 fail closed。

## 迁移当前脏改动

迁移按以下证据顺序进行：

1. 保存当前 submodule commit、状态和 diff SHA-256；
2. 将固定 commit 复制到独立临时目录；
3. 在临时目录应用新 series；
4. 比较当前 3 个脏文件，确认其语义均已由新 series 覆盖；
5. 特别将 heartbeat 的 `%llu` 临时写法收敛为跨平台 `PRIu64`；
6. 删除重复的 `patches/mujoco_ros2_control/macos-format-uint64.patch`；
7. 仅在覆盖证明通过后恢复 submodule 到固定 commit。

第 4 步不是要求新 series 与临时 patch 字节完全相同；允许用 `PRIu64` 替换 `%llu`，但必须
证明 CMake、linker 和 heartbeat 行为没有遗漏，并以双平台编译测试作为最终裁决。

## 自动化测试

主仓 contract tests 增加：

- `series` 文件存在、条目唯一、文件均被 Git 跟踪且无未登记 patch；
- 所有 patch 能在固定 fork commit 上依次 `git apply --check`；
- 应用完整 series 后可逆序移除并恢复零 diff；
- 安装器不存在 Darwin-only apply gate；
- 安装器从 `series` 读取顺序，而不是硬编码数组或 glob；
- Apple 专用 CMake/C++ 代码具有明确条件分支；
- heartbeat 使用 `PRIu64`，不使用平台相关的 `%lu` 或 `%llu` 假设。

测试先以旧安装器产生预期失败，再实现最小修改并转为通过。

## 双平台验收

### macOS

- contract tests 通过；
- 从干净固定 commit 重放完整 series；
- fork 三个包完成 clean-cache build；
- fork 包测试全部通过；
- `mujoco_vendor`、三个 fork 包和 `so101_demo_py` 的 prefix 符合锁定 overlay；
- 现有 headless 启动与接口查询 smoke 通过。

### Linux / ai-station

- 使用与本地主仓相同 commit、相同 `series` 和相同 fork commit；
- 从干净固定 commit 重放完整 series；
- fork 三个包完成 clean-cache build 和包测试；
- 验证 Linux 未链接 Cocoa/CoreVideo，仍保留预期 ELF/tinyxml2 linker 行为；
- 校验安装前缀、服务接口 SHA-256 和 required files；
- 运行 headless smoke，确认控制节点启动和 reset/pause/step 接口可发现。

只有两端都通过，才能声明“同一 patch series 跨平台兼容”。macOS 的既有 5 连胜可作为行为
回归背景，但本次构建组织变更不重新计入资格批次，也不创建新的资格结论。

## 失败处理与回退

- Linux 编译失败时，优先把 Apple 专用依赖收紧到条件分支，不恢复“Linux 跳过 patch”。
- patch 无法重放时停止并报告首个失败 hunk，不修改 submodule 或 install overlay。
- build/test 失败时保留独立 build source 和日志；不覆盖上一版已验证 install。
- 回退通过主仓 commit 完成；submodule commit 始终不变，因此不需要改写 fork 历史。

## 完成边界

最终主仓只保留一套权威 patch series、一个读取 series 的跨平台安装器、对应 contract tests
和简洁使用文档。submodule 必须为 clean，Linux/macOS 验收结果分别报告，不以单平台成功
推断另一平台兼容。

# `mujoco_ros2_control` Fork r7 权威迁移设计

## 目标

将当前由 `moveit-demo` 构建时重放的 11 个跨平台 patch 正式提交到
`git@gitee.com:zjumty/mujoco_ros2_control.git`，发布为 `so101-0.0.3-r7`，并让
`moveit-demo` 直接锁定和构建这个 clean fork commit。完成后，fork Git 历史是唯一实现
权威，主仓不再对 fork source 二次打 patch。

## 当前基线

- fork `main`、tag `so101-0.0.3-r6`、submodule gitlink 和 dependency lock 均指向
  `738e304551b4ea6db020b466086a13db71b65607`；
- 11-patch series 位于 `codex/mujoco-portable-patch-series`，可在 r6 上正向应用、逆序
  移除，并已产生相同的 macOS/Linux patched-tree SHA-256；
- 原 `moveit-demo/main` worktree 中的 dirty submodule 和其他用户改动不属于本迁移，不得
  reset、stash、清理或夹带；
- 本迁移继续遵守用户要求，不创建或更新 experiment ledger。

## 权威迁移

### Fork 历史

从最新且仍为 r6 的 fork `main` 创建隔离分支。按现有 `series` 顺序使用 11 个 patch 生成
11 个普通 Git commit，不 squash、不修改 patch 语义。提交顺序保持：

1. portable heartbeat format；
2. platform build and rpath；
3. headless rendering control；
4. Apple main-thread UI；
5. Apple framework linkage；
6. Apple test logging runtime；
7. Apple test RMW runtime；
8. platform C++17 requirements；
9. Apple conversion warnings；
10. Apple test backward runtime；
11. guard Apple test runtime dependencies。

应用后要求 fork worktree clean，且 `r6..candidate` 的组合 diff 与已经跨平台验证的 patched
tree 字节一致。候选 commit 在发布前通过 macOS 和 Linux 验证；验证失败时不得更新远端
`main` 或创建 r7 tag。

### 发布顺序

只有全部候选验证通过后才执行：

1. 重新读取 Gitee `main`，要求仍为 r6；
2. 以普通 fast-forward push 将候选 commit 推到 fork `main`，禁止 force-push；
3. 在候选 commit 创建 annotated tag `so101-0.0.3-r7` 并推送；
4. 用 `git ls-remote` 和 Gitee API 回读 `main` 与 tag peeled commit，要求都等于候选 commit。

如果 `main` 在发布前漂移，停止并重新比较，不自动 rebase 或覆盖远端。如果 `main` push
成功但 tag push 失败，保留 main，不回写历史；修复 tag 冲突后再发布 tag。

## `moveit-demo` 同步

fork 发布并回读成功后，在当前隔离 feature worktree 中：

- 将 `third_party/mujoco_ros2_control` gitlink 更新到 r7 commit；
- 将 dependency lock 的 fork tag、fork commit 和相关 provenance 更新到 r7；
- 删除活动的 `scripts/patches/mujoco_ros2_control/series` 与 11 个 patch；Git 历史仍可重建
  这些 patch，但它们不再是构建权威；
- 删除安装器的 patch loader、反向移除和正向应用逻辑；build source 必须是 clean r7；
- 将 installer contract 从“两个平台应用同一 series”改为“两个平台构建同一 clean r7
  commit，且安装器不包含 patch apply 路径”；
- 更新指南和设计文档，明确 r7 fork 是唯一权威，避免继续指导维护者添加主仓 patch。

原 `moveit-demo/main` worktree 中现存的 3-file dirty submodule diff 不在实施阶段直接清理。
只有 feature branch 经用户选择 merge 后，才能在主 worktree 对已被 r7 吸收的精确 diff 做
无损核验和清理；其他用户改动继续保留。

## 验证门

### 自动 contract

先写 RED contract，至少证明：

- dependency lock 和 gitlink 必须解析到相同 r7 commit；
- submodule HEAD 必须包含 r6 且 worktree clean；
- installer 不得引用 `series`、`git apply` 或 Darwin-only patch gate；
- 主仓不得保留活动 patch 文件；
- fork candidate 的组合 diff 与旧 11-patch 结果一致。

实现后运行 contract、安装脚本语法检查、`git diff --check` 和 submodule clean gate。

### macOS

在新的候选 workspace 中直接从 clean fork candidate 构建三个 package，运行全部 package
测试，检查 package prefix、接口、Mach-O/rpath/framework，并运行有界 headless
reset/pause/step smoke。不得覆盖已验证 overlay。

### Linux / ai-station

通过 bundle 把同一 fork candidate 传到新的 `/data/work` 隔离目录；不得修改
`/data/work/ws_moveit` 或现有 tmux/ROS stack。直接从 clean candidate 构建三个 package，
运行全部测试，检查 ELF、`ldd`、tinyxml2 link option、无 Apple framework，并运行有界
headless reset/pause/step smoke。只清理本轮拥有的进程组。

### 发布后

从 Gitee r7 tag 新建无本地对象借用的 fresh clone，在 macOS 至少重跑 installer build、
tests 和 provenance；ai-station 至少从 Gitee tag 回读 commit 并重跑 installer/package
verification。两端 `ros2 pkg prefix` 必须指向本轮候选 install，不能落回 r6 overlay。

## 证据与完成条件

普通日志统一保存在 `/tmp/so101-debug-mujoco-fork-r7/`；远端使用同名临时根，并在完成前
复制关键日志回本机根目录。不得删除候选 checkout、bundle、build 或日志，除非用户另行
授权。

只有以下事实同时成立才算完成：

- Gitee `main` 与 `so101-0.0.3-r7` 都回读为同一候选 commit；
- fork r7 worktree clean，11 个主题 commit 可审计；
- macOS 与 Linux 直接从 clean r7 构建、测试和 headless smoke 通过；
- `moveit-demo` gitlink、lock、installer、contract 和指南都改为 r7 单一权威；
- feature worktree clean，原 main worktree 的用户改动未被覆盖；
- retained、archived 和 deletion candidates 已分别报告。

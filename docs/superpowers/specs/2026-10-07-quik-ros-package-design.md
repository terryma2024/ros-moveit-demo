# QuIK ROS 2 package 拆分方案

状态：用户已用 "ok" 确认完整设计和实施计划；批准记录和原始文档哈希保存在本任务证据根的 `quik-ros-package-01/approval.json`。

建议在当前仓库增加一个 `src/so101_quik/` package，版本 `0.1.0`，供 `so101_demo_py` 依赖。采用 `ament_cmake` 构建 C++ 库，使用 `ament_cmake_python` 安装 Python 加载接口。当前冻结的加权 QuIK 源码直接迁入这个包，SO-101 的 URDF 转换和运动验收留在 demo。

## 已核实的基线

当前任务隔离 worktree 的 HEAD 为 `38e333507127a8073061811a7b08a02e41cbe7d1`，开始本轮时 clean。原唯一证据根继续使用；本目录只是它的一个子目录。已有主 checkout、其他 worktree、Mac 和 ai-station 的已有进程均未修改。

Mac 固定 ROS Python 的实际安装产物与该 HEAD 的数值源码一致，两个内核的 SHA256 与 EXP-049 的普通包测试相同。20 点完整 horizon 输出和 64 个固定求解请求已各运行两次，两种后端各自的输出完全一致。native 为 20/20，QuIK 为 18/20，P18/P19 仍失败。2003 个向量对应的 QuIK FK 矩阵也已保存。这是行为基线，不是 latency 测量。

`baseline-verification.json`、`baseline-mac/manifest.json` 保存判据和产物哈希。当前 colcon 识别 8 个项目包，没有独立的 QuIK 包。默认 ROS domain 的本次 node-list 查询为空；已有 PID 的存在与保留情况以 `host-before.json` 为准。

## 两种打包方式

| 方式 | 交付内容 | 代价 |
| --- | --- | --- |
| 推荐：`ament_cmake` 加 Python 加载接口 | ROS 2 包、可链接的 C++ target、Python 接口；Python 和 C++ 共用数值源码 | 需要补 CMake 导出、Python 包安装和独立 wheel 构建 |
| `ament_python` 加现有 C++ 扩展 | 独立 ROS 2 包和 Python 接口，沿用现有 setuptools 编译 | 改动较少，但不提供独立的 C++ CMake target |

用户已确认同时支持 C++ 和 Python 的推荐方式。

## 包边界和接口

`so101_quik` 拥有第三方 QuIK 源码、加权头文件、许可、QuIK/Eigen 构建锁、C ABI、C++ library 和 Python loader。它不依赖 `so101_demo_py`，也不读取 demo 的 URDF 或配置。

C++ 客户端使用 `find_package(so101_quik REQUIRED)` 和 `so101_quik::core`。安装 upstream 头文件与项目的 `so101_quik/c_api.h`；后者公开当前 `quik_create`、`quik_destroy`、`quik_fk`、`quik_solve` 的签名、row-major 布局、固定 5 关节缓冲区大小和 context 生命周期。当前项目提供的 C ABI 仍是 5 关节 profile。其余机器人自由度不属于本次新增验证范围。

Python 接口为 `so101_quik.load_native_library() -> tuple[ctypes.CDLL, pathlib.Path]`，完成确定路径加载和 C ABI 类型声明，仅使用 Python 标准库。库编译为不含 `Python.h` 的 C++ shared library。CMake target 安装到正常 `lib/` 路径；同一次编译的库副本作为 Python package data 安装，loader 使用包内相对路径。两个安装副本必须字节一致，安装证明记录二者哈希。普通 wheel 使用同一个 CMake core target 的 standalone 模式构建。

demo 的 `QuikPoseIk` 调用这个公共 loader，继续管理串行 context、weakref 释放、URDF 到 DH 的转换、角度归一化、canonical FK 和误差门。现有 `create_pose_ik`、`solve`、`forward`、`joint_limits`、CLI 和 `SO101_IK_BACKEND` 的使用方式保留，默认仍为 `native`。缺包、缺库、初始化失败或求解失败都返回明确的后端错误；选择 QuIK 后仍不自动改用 native。

`so101_demo_py/package.xml` 显式依赖 `so101_quik`，Python distribution 也声明 `so101-quik==0.1.0`。demo 的 setup 不再编译 QuIK，也不再持有其 vendor 源码；项目自建 `_ik_numeric` 仍在 demo。新包成为声明的安装依赖，运行时 backend 选择继续由原开关控制。

ROS 2 混合包的构建和安装依据官方 [ament_cmake 文档](https://github.com/ros2/ros2_documentation/blob/jazzy/source/How-To-Guides/Ament-CMake-Documentation.rst) 和 [ament_cmake_python 文档](https://github.com/ros2/ros2_documentation/blob/jazzy/source/How-To-Guides/Ament-CMake-Python-Documentation.rst)。

## 冻结的计算和依赖

QuIK upstream commit 为 `a9ebd1f21dfd3c9f0869140dfb0a4ae5a538cccc`，姿态权重 `0.08`，Eigen `3.4.0`。第三方每个文件的 SHA256 随 lock 迁移，文件内容不变。迭代参数、seed 策略、位置 `0.002 m` / 姿态 `0.10 rad` 误差门、关节 `0.002 rad` 余量和 planner/cache 算法均保持当前值。保留 `-O3 -DNDEBUG -fno-fast-math -ffp-contract=off -std=c++17` 构建约束，两个构建入口使用同一套检查。

NumPy 约束继续由 demo 当前 `config/ik/requirements.lock` 管理：Linux `1.26.4`、macOS `2.4.6`。loader 不新增 NumPy 运行依赖。原 uv、CPython、setuptools、wheel、PyYAML 和 typing_extensions 约束保持；新增构建工具在 bootstrap lock 中固定为 `cmake==3.31.6`，并记录实际安装版本和产物哈希。该新 pin 必须经过两平台实际安装验证。

正式 setup 为 Eigen 增加私有 CMake package 配置，生成 `Eigen3_DIR` 构建环境。ROS 和 standalone 构建都要求精确的 Eigen 3.4.0，并在编译时校验；错误版本显式失败。已有共享 ROS、全局 Python 和 Homebrew Eigen 不变。

## 实施顺序

1. 保存本次确认，再补独立包的行为回归测试。让测试实际尝试安装后加载、创建 context、FK 和求解，证明当前缺少独立 package 时失败；收集或 underlay 失败不计为 RED。
2. 创建 `src/so101_quik/package.xml`、`CMakeLists.txt`、`cmake/`、`include/so101_quik/c_api.h`、`src/quik_c_api.cpp`、`so101_quik/`、standalone wheel 的 `setup.py` 和 `test/`。迁入当前 `third_party/quik/` 与 `quik.lock.json`。C++ 数值函数从现有 wrapper 提取，只移除 CPython module 尾部并补接口声明，不重写求解器。先单独构建和安装新包，在没有 demo Python 路径的进程中通过 FK、求解和 context 测试。
3. 修改 demo 的 `package.xml`、`setup.py` 和 `quik_ik.py` 的加载边界，更新 `test_pose_ik_backends.py`。测试新安装路径、缺包/缺库、CLI 开关、明确失败、并发 context 和默认 native 行为。SO-101 的数值适配算法继续使用原代码。
4. 修改正式 `setup-so101-quik.sh`、`so101_quik_setup.py`、bootstrap lock 和对应 setup 测试：私有安装 CMake/Eigen，先构建安装 QuIK wheel，再构建安装 demo wheel；manifest 覆盖两个包和实际库。重复执行、错误 SHA、错误版本、缺库和 prefix 隔离继续验证。更新 repo 内英文 guide 和实验账本。
5. 在两平台使用新 source/build/install 目录构建 ROS overlay。限定 discovery 为这两个包并加载已验证的完整 underlay，执行 `colcon build --base-paths src/so101_quik src/so101_demo_py --packages-up-to so101_demo_py`，实际确认先构建 QuIK，demo 通过安装前缀导入它。另用安装后的 CMake target 构建 C++ consumer，执行真实 FK/求解，证明导出接口可用。
6. Mac 用固定 ROS Python 分别运行 demo 的完整普通 `test/` 和新包的完整 Python 测试，worker 数为 `min(8, logical CPUs)`，保留各自 JUnit、实际 worker 和新 scratch 证明；新包的 C++ 测试进入 CTest。Ubuntu 24.04 bare container 和 Mac 新空 prefix 跑正式 setup 的首次/重复验证。ai-station 做实际安装产物的数值和单 P 核 latency 对比。完成 inline self review，按持续有效的授权 commit/push 当前 Gitee 分支并回读精确 SHA。

上述文件及验收范围是本次已批准计划。执行细目见 `docs/superpowers/plans/2026-10-07-quik-ros-package.md`。

## 数值和 latency 验收

每种后端分别与同平台拆包前的结果比较。比较全部 20 点的 receipts、selected_steps、失败位置和完整错误；64 个固定请求的返回值、浮点 hex、FK 和错误消息也要求完全一致。2003 个 QuIK FK 矩阵对拆包前后逐项核对。计算字段有任何变化就停止发布，先定位编译、模型或 adapter 边界；不通过放宽误差门接受变化。

ai-station 重新在本轮 Linux runtime 下建立拆包前基线，不能拿 Mac 浮点结果当 Linux 参照。仍用 CPU14，排空并保留空闲 SMT15，隔离同一个物理 P 核。固定解释器、NumPy、编译器和单线程环境。每个后端的 before/after 按 3 AB/3 BA 的配对顺序，各 6 个新进程，每进程 20 点 warmup 后各测 3 次；所有完整输出在计时外校验。两个后端共 24 个进程。计时仍覆盖整个 `prepare_horizon`，不包括初始化和结果审计。保存 CPU 迁移、SMT 活动、温度、频率和恢复证明。

数值行为完全一致且无新增失败点是硬门。latency 验收以各后端自己的共同成功点为样本，拆包后 pooled median 和 p95 均不得高于拆包前的 `1.05x`。失败退出单列，不用于宣称速度优势；不新增跨进程通信。有效测量超门记为失败，禁止挑选样本或重新调算法。隔离或 provenance 污染的运行保留为 INVALID，只允许修正污染后补一个完整批次。

## 证据和保留

唯一注册根仍为 `/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`。远端仅使用 task-owned `/data/tmp/` 执行暂存目录；所有原始日志、输出、JUnit、构建与安装证明完整传回该根并核验路径、大小、SHA256 和 symlink 文本。不得另注册 Linux 证据根。需要 fsync-heavy 临时 fixture 时使用新的 NVMe scratch 并验证实际 Python 的 `tempfile.gettempdir()`；遵从本次唯一根的用户约束，临时执行 scratch 不作第二个保留根。

所有旧证据和本轮有效/无效运行保留，archived 为 NONE。本轮尚未产生构建缓存或测试 scratch；之后的私有 build/install/cache、执行暂存和 scratch 只列删除候选，未经授权不删除。图形、物理抓取和控制器 live 验收为 N/A，本次改动为 headless library/package 边界。

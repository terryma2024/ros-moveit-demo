# SO-101 Python 测试的 macOS 与 Linux 兼容指南

这份指南整理 `so101_demo_py` 普通 Python 测试从 macOS 跑到 Linux 时遇到的实际问题。目标
不是让两台机器产生完全相同的测试数量，而是让同一套非 ML 测试在各自支持的能力范围内
零失败，并且让每个 skip 都有明确的平台理由。

适用范围：

- `src/so101_demo_py/test/` 下的单元测试、contract test 和轻量集成测试；
- macOS Apple Silicon 固定 ROS 2 Jazzy 环境；
- ai-station Linux 环境；
- `pytest-xdist -n 8` 并行运行。

不包含 `benchmark_test/`。Torch、SAM、GroundingDINO 等需要完整模型依赖的测试标记为
`explicit_ml`，由单独的门禁执行。

## 1. 先判断测试有没有真正开始

收集失败和断言失败不是一类问题。下面几种情况发生在 pytest 执行 testcase 之前，应先修复
runner 环境，不能记作代码 RED：

- ROS overlay 顺序错误，导入了旧版 message 或 service；
- macOS 缺少 `@rpath/*.dylib`，或者 SIP 边界丢掉了 `DYLD_LIBRARY_PATH`；
- pytest 使用了系统 Python，而 ROS package 安装在项目固定 venv；
- 可选 ML 模块在文件顶层 import，导致没有 ML 依赖的主机无法完成 collection。

预检至少记录这些信息：

```zsh
"$TEST_PYTHON" -c 'import sys,tempfile; print(sys.executable); print(tempfile.gettempdir())'
"$TEST_PYTHON" -c 'import rclpy,so101_demo; print(rclpy.__file__); print(so101_demo.__file__)'
ros2 pkg prefix so101_demo_py
```

只有 testcase 已被收集并进入 setup/call/teardown 后出现的失败，才算测试 RED。这个区分很
实用：一次 macOS 运行曾因旧工作区 overlay 缺少 `FreeJointState` 在 collection 阶段退出；按
固定顺序重新加载 overlay 并重建项目包后，整包测试正常通过，代码无需为旧消息定义做兼容。

## 2. 临时目录由运行环境决定，测试只消费它

不要在测试中写死 `/tmp`、用户 home 或某台机器的工作区路径，也不要通过
`Path(TMPDIR).parent` 猜测可写目录。macOS 的固定测试环境使用 `/opt/data/tmp`；ai-station
必须使用登记在 durable evidence root 下、此前不存在的 NVMe scratch。两者的物理路径不同，
接口相同：`TMPDIR`、`TMP` 和 `TEMP` 指向本轮唯一目录。

普通 fixture 优先使用 pytest 的 `tmp_path`：

```python
def test_writes_receipt(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}\n", encoding="utf-8")
    assert receipt.is_file()
```

如果产品契约要求 runtime root 的叶子是固定 batch ID，就在当前临时根下增加唯一父目录，
不要复用全局短名：

```python
key = hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]
runtime_root = (
    Path(os.environ["TMPDIR"])
    / f"rt-{os.getpid():x}-{key}"
    / "a001"
)
```

这样既保留了 `a001` 的产品约束，也避免八个 xdist worker 同时创建 `<scratch>/a001`。

测试启动前必须用实际测试 Python 回读路径：

```zsh
resolved_temp=$("$TEST_PYTHON" -c \
  'import pathlib,tempfile; print(pathlib.Path(tempfile.gettempdir()).resolve())')
[[ "$resolved_temp" == "${TMPDIR:A}" ]] || exit 1
```

`--basetemp` 每次都换新目录。旧目录可能留下 socket、lock、权限或半写入文件，复用后得到的
结果没有诊断价值。

## 3. Unix socket 需要同时考虑路径长度和目录权限

Darwin 与 Linux 的 `sockaddr_un.sun_path` 容量不同；pytest 自带的长临时路径在 macOS 上很
容易超限。不要为了让测试通过而削弱产品对 owner、mode 或 sticky bit 的检查。

处理原则如下：

- 通用 IPC 测试使用测试提供的唯一临时根；
- 只有验证 Darwin 私有目录传输时，才在 `/private/tmp` 下创建短且唯一的目录；
- 长度按 `os.fsencode(path)` 后的字节数判断，不按 Python 字符数判断；
- macOS 专属 AF_UNIX 契约可以 module-level skip，通用编码、帧上限和 schema 测试仍应在
  Linux 运行；
- fixture teardown 只清理自己创建并验证过身份的目录。

`--dist loadscope` 只影响调度，不是跨 worker 锁。固定 socket 名、固定 ROS domain、固定 lock
文件仍会冲突，必须在 fixture 或资源分配层解决。

## 4. 平台能力放进适配层，不散落在 testcase 里

Linux 可从 `/proc` 读取 start time、cmdline 和进程组；macOS 没有 procfs，需要通过 `psutil`
读取同一组逻辑事实。调用方应依赖统一返回值，而不是在每个测试里分别实现两套扫描逻辑。

进程身份至少包含：

- PID；
- PGID/session；
- 启动时间；
- 启动时记录的 argv。

其中 PID、PGID 和启动时间用于防止 PID reuse。进程退出期间 cmdline 可能先变空，因此它不适合
继续作为唯一身份依据。

zombie 的定义也必须一致。macOS 的 `psutil` 路径已经把 `STATUS_ZOMBIE` 当作不再运行；Linux
如果仍把 `/proc/<pid>` 中的 zombie 计为进程组成员，外部清理器会等待一个自己无权 reap 的
子进程。正确做法是让身份读取和进程组扫描都排除 `Z` 状态，同时由原 owner 对自己的
`Popen` 子进程执行有界回收。对应实现与回归测试见：

- [`parallel_processes.py`](../../src/so101_demo_py/src/runtime/parallel_processes.py)
- [`test_parallel_processes.py`](../../src/so101_demo_py/test/test_parallel_processes.py)

平台分支本身也要测试。适合注入 `platform` 参数的代码，直接参数化 `darwin` 和 `linux`；读取
`sys.platform` 的旧边界可以用 `monkeypatch`。只有真实依赖 MPS、Darwin dylib 或 Linux procfs
的测试才 skip：

```python
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="MPS broker bootstrap is macOS-only",
)
```

不要用整文件 skip 掩盖其中可移植的纯逻辑测试。拆分文件通常更清楚：通用 contract 两边都
跑，平台适配测试只在对应系统运行。

## 5. 可选 ML 依赖不能破坏普通测试收集

普通 package gate 在 [`setup.cfg`](../../src/so101_demo_py/setup.cfg) 中默认使用
`-m "not explicit_ml"`。标记之外还要注意 import 时机：pytest 为了判断 marker 仍需导入测试
模块，所以文件顶层的 `import torch` 会让没有 Torch 的 Linux 主机在过滤前失败。

推荐写法是：

```python
@pytest.mark.explicit_ml
def test_tensor_contract():
    import torch

    tensor = torch.zeros((1, 3, 16, 16))
    assert tensor.shape == (1, 3, 16, 16)
```

不要在整个测试模块上使用 module-level `pytest.importorskip("torch")` 代替 marker。ROS 的
launch-testing collector 与这种写法组合时，可能只得到一个 module skip，最后以“没有测试”
的 exit 5 结束。仓库中的 collection contract 会分别检查默认门禁和 `-m explicit_ml` 的
nodeid 集合，新增 ML 测试时需要同步更新它。

## 6. 并行测试要消除共享状态，不靠延时碰运气

单文件通过、整包 `-n 8` 失败，通常意味着 fixture 或子进程生命周期存在共享状态。优先检查：

- 是否使用固定目录、socket、端口、ROS domain 或 batch ID；
- 子进程是否在断言前完成 exec，退出后是否由 owner reap；
- daemon thread 是否与清理器同时 poll 同一个 `Popen`；
- 环境变量或模块级对象是否被 testcase 修改后没有恢复；
- 测试是否从同一个长 scratch 派生出超过平台上限的 socket 路径。

修复应落在资源所有权或适配边界。任意增加 `sleep()` 只会改变复现概率。确实需要等待异步
状态时，使用短周期、单调时钟和明确 deadline，并在超时时输出正在等待的身份或状态。

对于不能并行的真实共享资源，维护精确 nodeid 清单并串行运行；其余测试继续并行。并行组与
串行组的合集必须等于原 gate 的 collection，不能用拆组漏掉测试。

## 7. 两个平台的推荐门禁

### macOS

macOS 先执行统一准备入口。它负责构建固定 overlay、生成 dylib farm 并运行 doctor：

```zsh
scripts/so101-macos.zsh prepare
scripts/so101-macos.zsh doctor --json
```

随后在干净 zsh 中按固定顺序加载环境：

```zsh
source /opt/ros2_jazzy/install/setup.zsh
source /opt/ros2_jazzy/extra_ws/install/setup.zsh
source /opt/data/so101/runtime/fork/current/setup.zsh
source /opt/data/so101/workspace/install/setup.zsh
export DYLD_LIBRARY_PATH=/opt/ros2_jazzy/dylib_farm/current
export TMPDIR=/opt/data/tmp TMP=/opt/data/tmp TEMP=/opt/data/tmp

/opt/ros2_jazzy/.venv/bin/python -m pytest -q -n 8 --dist loadscope \
  --basetemp=/opt/data/tmp/pytest-<unique-run-id> \
  --junitxml="$TASK_EVIDENCE/so101-demo-py-macos.xml" \
  src/so101_demo_py/test
```

不要 source 工作区根部可能已经过期的 `install/setup.zsh`。先用 `ros2 pkg prefix` 和模块
`__file__` 确认新构建的项目 overlay 在最前面。

### ai-station Linux

Linux 的 scratch 必须位于任务 durable evidence root 的 `/data` NVMe 下：

```zsh
scratch="$TASK_ROOT/scratch/pytest-n8-<unique-run-id>"
test ! -e "$scratch" || exit 1
mkdir -p -m 700 "$scratch/tmp"
export TMPDIR="$scratch/tmp" TMP="$scratch/tmp" TEMP="$scratch/tmp"

"$TEST_PYTHON" -c \
  'import pathlib,tempfile; print(pathlib.Path(tempfile.gettempdir()).resolve())'

"$TEST_PYTHON" -m pytest -q -n 8 --dist loadscope \
  --basetemp="$scratch/tmp/pytest-base" \
  --junitxml="$TASK_ROOT/results/so101-demo-py-linux.xml" \
  src/so101_demo_py/test
```

运行前验证精确 Python、ROS underlay、依赖 overlay、候选 install 和 submodule commit。测试完成
后保存 log、JUnit、退出码、elapsed、collection 数量和 scratch 路径。scratch 只标记为删除
候选；没有用户授权时不要删除。

## 8. 怎样解释双平台结果

macOS 和 Linux 的 pass/skip 数量可以不同。MPS、Darwin dylib、私有 `/tmp` 语义只在 macOS
测试；procfs 测试只在 Linux 运行。验收关注下面四点：

1. 普通非 ML 范围在两边都完成 collection；
2. 所有可运行 testcase 通过，failed/error 都是 0；
3. skip 数量和 reason 可审计，没有用 skip 藏通用逻辑失败；
4. 两边都使用八个 worker、唯一临时目录和正确的候选产物。

本次兼容修复的最终结果是：macOS `3654 passed, 10 skipped`，Linux
`3529 passed, 135 skipped`。详细失败演进、环境和证据路径记录在
[`so101-macos-runtime-contract-experiment-ledger.md`](../experiments/so101-macos-runtime-contract-experiment-ledger.md#run-006--linux-eight-worker-parity-gate)。

## 9. 提交前检查

- 测试没有用户目录、旧 workspace、`/tmp` 父目录或 Linux 可执行文件绝对路径；
- 通用行为两边都测，平台专属能力才 skip；
- `explicit_ml` 模块可以在没有 Torch 的环境完成 collection；
- Unix socket 路径按编码后的字节长度检查；
- 子进程身份、防 PID reuse、zombie 与 reap 语义在两套适配器中一致；
- `-n 8` 使用唯一 fixture root，没有固定共享资源；
- 运行前记录 interpreter、module origin、package prefix、commit 和 submodule；
- 完整 log、JUnit、退出码、elapsed 和 scratch 分类已经落到登记的 evidence root。

如果同一个失败连续出现，先缩成能区分“环境、平台适配、并行共享状态、产品逻辑”的最小
复现。等根因明确后再改测试或实现，别一上来批量加 skip。

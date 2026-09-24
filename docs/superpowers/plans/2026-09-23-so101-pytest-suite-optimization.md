# SO-101 Python 测试套件优化方案

**目标：** 让 `so101_demo_py` 和 `so101_teleop` 的普通测试稳定进入门禁，删去确实重复或自证的断言，并保留 retry、进程归属和 launch 行为的有效回归覆盖。

**依据：** 2026-09-23 对两包 `test/` 的静态审查；仓库根目录 `AGENTS.md`；`so101-dev` 的测试与证据规则。审查覆盖 200 个 `so101_demo_py` 测试文件、94 个 `so101_teleop` 测试文件；没有运行 pytest，因此文件数和函数数不是已收集 case 数。

**实施边界：** 本方案只调整测试、测试 fixture 和测试注册。历史实录属于审计证据，不直接改写、搬入源码或删除。`benchmark_test/` 继续独立运行；`explicit_ml` 继续显式选择。现有 `src/so101_teleop/web/` 未提交改动属于用户工作，不纳入本方案。

## 取舍与顺序

先补门禁漏收，再处理固定 `/tmp` 依赖，最后精简弱测试。只删重复断言可能让报告数字好看，却不能解决 CTest 漏跑和跳过的问题。每步单独提交，失败时能定位到一次具体变更。

### 任务 1：让 CTest 注册与普通测试目录一致

**文件：** `src/so101_teleop/CMakeLists.txt`；新增 `src/so101_teleop/test/test_ctest_registration.py`。

1. 在 CMake 中补录四个文件：`test_expert_validation_retry_endpoint_refusal.py`、`test_expert_validation_retry_owner_reconcile.py`、`test_macos_live_window_runner.py`、`test_package_import_isolation.py`。`test_support.py` 没有测试函数，继续作为辅助文件。
2. 写注册契约测试：扫描 `test/**/test_*.py`，排除没有 `test_` 函数的辅助文件，与 CMake 的 `so101_add_pytest_test(... test/...py)` 路径集合比较。对内存字符串或 `tmp_path` 副本删去一条注册，验证检查器会失败；测试不改写工作树中的 CMake。测试还应检查注册名唯一。
3. 定向运行新契约测试；配置包并用 `ctest -N` 核对四个名字实际出现。`ctest -N` 只证明注册，不代替执行。

**完成判据：** 无遗漏或重复注册；直接 pytest 的普通测试文件集合与 CTest 注册集合一致。若四个文件的历史 fixture 仍不可用，CTest 的跳过数必须如实记录，不能把“已注册”写成“已验证”。

### 任务 2：把关键 retry 回归从历史 `/tmp` 产物中解耦

**文件：** `src/so101_teleop/test/teleop/test_expert_validation_retry_endpoint_refusal.py`、`test_expert_validation_retry_owner_reconcile.py`；需要复用时新增 `src/so101_teleop/test/teleop/retry_fixture.py`。参考现有 `test_expert_validation_campaign_layout_projection.py` 的 `_write_campaign_batch`、`_service`，以及 `test_expert_validation_store.py` 的 owner/retry 构造方式。

1. 在 `tmp_path` 中生成最小的 first-pass、失败 point、cleanup receipt、owner row 和 lease。用 task-local 配置及文件建立完整 production environment，经 `create_production_service` 装配真实 store、supervisor 和 lease service；只在最终 `_spawn` 边界拦截外部进程。参考的 `_service` 使用 `SimpleNamespace` 和预填 campaign 缓存，仅适用于 projection 测试，不能直接复用为这两个跨层测试的 service fixture。fixture 返回服务、store、campaign ID、batch ID、point ID，不读取固定主机路径。
2. 先用不存在的历史根运行两个文件，记录预期跳过；改用新 fixture 后，同样条件下关键正反例必须执行。正例应到达 spawn 边界并验证持久状态；反例分别覆盖真实存活 owner、无法确认的身份、请求形状错误，以及缺少 cleanup receipt 时的指定拒绝码。
3. 对照现有 `test_expert_validation_store.py`：store 层已覆盖的分支留在 store 测试；这两个文件只保留 API/production service 跨层断言。历史实录回放如仍有独有价值，另设显式运行的 replay 入口和环境变量，并在缺少实录时清楚报告“未运行”；它不能是普通门禁中唯一能验证该行为的测试。
4. `test_expert_validation_campaign_layout_projection.py` 中依赖历史批次的 case 逐个比对其已有合成 batch 测试，先列出“旧断言 → 新测试”的映射及迁移前后的收集清单。`FULL_RESTART_RETRY` 的 binding vocabulary、cleanup readback 和错误输入必须逐项核对。独有断言先补确定性合成测试并跑通，再将实录 case 移出普通门禁，保留独立的显式只读 replay 入口；不要放入 perception benchmark 套件。

**完成判据：** 无历史产物的干净环境中，retry 的 API、owner reconcile 与 campaign projection 关键行为仍有确定性测试；普通门禁不因固定 `/tmp` 缺失而跳过这些关键断言。历史证据不被修改或删除。

### 任务 3：精简 `demo_py` launch 测试中的重复与弱断言

**文件：** `src/so101_demo_py/test/test_launch_composition.py`。

1. 删除第 91 和 106 行两个完全相同的 `inspect.getsource(_configured_actions)` 测试，改为一个行为测试：分别构造 Gazebo 的 `pick_place=False/True` launch actions，检查无 workflow 时没有 workflow、scene/readiness gate 与对应 shutdown handler，有 workflow 时各出现一次。
2. 第 85 行的测试目前只比较 `DeclareLaunchArgument` 名称。把名称改为实际断言范围，或扩展为比较 action graph；不再让测试名暗示验证了未检查的执行链。
3. 保留对用户可见 launch 参数及故障传播的独立断言。源码字符串检查仅用于难以通过公开 action graph 表达的静态约束；优先检查对象关系和事件绑定，不以 `OnProcessExit(` 出现次数代替事件顺序。

**完成判据：** 两种 launch 形态的 workflow 有无及门控关系有行为断言；重复测试体为零；删除源码行或移动注释不会单独改变测试结果。

### 任务 4：删除自证断言，核对跳过项

**文件：** `src/so101_teleop/test/teleop/test_macos_live_window_runner.py`；必要时修改同目录其他相关测试。

1. 删除第 133 行对测试自身构造字典的 JSON 往返断言。若要验证 manifest 形状，从 runner 实际输出或专门的生成函数读取，并断言 `cases` 只有选定 case、`stability` 指向同一 case。
2. 收集两包普通测试的 skip 清单，逐条标记为平台限制、显式外部资源或需要转成确定性 fixture。不要仅因缺少裸 `assert` 就删测试；NumPy 断言、异常断言和辅助函数断言仍有效。
3. 复核 `so101_demo_py/setup.cfg` 的 `testpaths=test` 与 `explicit_ml` 标记，保持基准和 ML 显式测试的现有分区。

**完成判据：** 没有自证断言；每个跳过项有可解释的边界；普通门禁不依赖不可持久保证的历史 `/tmp` 目录。

## 执行与验收

- 原计划按 `AGENTS.md` 交给 `tmux` 中的 `dst` 执行。2026-09-24 用户暂停 `dst` 并要求 Codex 接手，后续实施由 Codex 完成；交接时先核对运行中的测试和已写入的文件。
- 实施前记录当前 commit、dirty files、主机、精确 Python 与 ROS overlay；只在隔离 worktree 修改本方案文件，保留用户已有 web 改动。SO-101 任务登记一个 evidence root。
- 每个改动先运行能显示缺陷的定向测试，再运行修改后的定向测试。增加 CTest 注册后，用 `--cmake-clean-cache` 重建、重新 source 并核验 package prefix/overlay；必须实际执行新注册用例。`ctest -N` 只用于核对清单，且先查看实际 CTest 命令与解释器。
- 在 `ai-station` 上跑 pytest/colcon 前，在该任务的 `/data/work/so101-evidence/<task-family>/<run-id>/scratch/<test-run-id>/tmp` 新建 scratch，设置 `TMPDIR`、`TMP`、`TEMP`。对直接 pytest 和每个实际 CTest 子进程解释器分别保存带 executable/origin 的 `tempfile.gettempdir()` 证明，并确认 xdist worker 的临时目录仍在该 scratch 内。保存 elapsed、退出码、JUnit、skip 数与 scratch 路径；不删除证据。
- 两包分别运行完整普通 `test/` 范围，xdist worker 为 `min(8, os.cpu_count() or 1)`。两个包都要执行 package gate 和 `colcon test-result --verbose`；核对 CTest 命令，避免多个 CTest case 各开 8 worker 造成超订阅。`benchmark_test/` 仅在改到其实现、配置、适配器、报告或测试时另跑，本方案默认不涉及。
- 完成后对比“注册文件数、实际收集数、skip 数、耗时、失败数”与实施前基线。目标是消除已确认的 4 文件漏注册及关键 retry 的历史产物跳过，不设未经测量的提速百分比。报告 retained、archived 和可删除候选证据，未经授权不删除。

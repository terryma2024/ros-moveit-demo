# SO-101 Teleop sealed archive viewer implementation plan

> **For agentic workers:** 确认后使用 `superpowers:executing-plans`，由当前 Codex 自己逐任务实现并 inline self review；不使用 `dst`，不委派子 agent。步骤使用 checkbox 跟踪。用户本次明确要求覆盖 AGENTS.md 的默认 dst 执行方式。

**Goal:** 在统一 Teleop 网页中查看封存包、统计、全部场景及 episode 双相机和信号，并能分页查看文件及按需校验完整性，全程保持封存内容只读。

**Architecture:** 在统一 FastAPI factory 中挂载独立的 `/api/archives` router，文件读取和有界内存缓存由 `archive_viewer` 包负责，不依赖控制域。前端增加 `/archives` 页面，以服务器签发的 id 获取数据；root、package、scene 选择保存在 URL query。校验任务只在服务器内存中保存状态。

**Tech Stack:** Python 3.12、FastAPI、Pydantic v2、标准库文件读取和线程；现有 React 18.3、Vite 5、Tailwind 3、shadcn、Bun、Vitest、inline SVG。

**Spec:** [需求](../specs/2026-10-17-so101-teleop-sealed-archive-viewer-requirements.md)、[设计](../specs/2026-10-17-so101-teleop-sealed-archive-viewer-design.md)。两份文件从受保护 worktree 逐字节复制，来源及 SHA256 见证据根 `spec-provenance.json`；不修改原稿。

**Status:** 待用户确认。当前只有计划、原始规格副本及任务账本；尚未安装依赖、运行测试、启动服务或写实现代码。

## Global Constraints

- 仅在 `/home/matianyi/Projects/ros-moveit-demo/.worktrees/teleop-archive-viewer` 开发；分支 `codex/teleop-archive-viewer`，基线 `007cb1e3c1830f9348052fa2cc4f39e4bd0396a7`，创建前 fetch 并与远端回读一致。
- 不修改、构建或安装到 `so101-act-data-0917a` worktree，不动其分支和 main，不改共享子模块元数据，不使用 gh。只允许 `git push origin codex/teleop-archive-viewer`，不 force-push。
- 保护注册表中所有 root、所有含 `SEALED.json` 的目录及 seal manifest：不写、不创建、不改名、不删除、不 chmod。只对自建 fixture 设置只读权限。禁止从封存源码 import、执行封存脚本或打开其中 SQLite，防止 pycache、journal、锁文件等隐性写入。
- 客户端请求只包含服务器签发的 root/package/scene/file id 及受限的行号、分页和过滤值，不能提交文件路径。响应可展示相对文件名，但不能把它用作请求路径。
- 包内路径逐一校验 realpath；拒绝通向包外的符号链接。manifest 是包外读取的唯一特例：只接受同一父目录中精确的 `<包名>.seal-manifest.jsonl`，校验其 realpath 未逃逸及 SHA256；不跟随文档给出的任意 manifest 地址。
- 无 `--archive-root` 时所有 `/api/archives/*`（包括 config、未知子路由和 verify 操作）返回 HTTP 404、`code=ARCHIVES_DISABLED`；不采用设计早段的 config 200/enabled=false。保留完整 OpenAPI 路由声明，方便离线导出。
- 不依赖 ROS 或 Docker。沿用 bind policy；不新增认证机制、不申请控制 lease、不触发机器人操作。无新图表库、无磁盘缩略图和缓存。
- 单元测试只构造 synthetic fixture，不打开真实 `/data/work` 数据。fixture 的物理 TMPDIR 位于任务 NVMe scratch，是运行环境规则；禁止读取真实业务 evidence，二者不要混淆。
- 普通门禁为完整 `src/so101_teleop/test/` pytest（xdist 8 workers，本机 32 logical CPUs）、前端完整 Vitest 和类型检查。维护 CTest 注册并执行包门禁；不跑任何 benchmark，不运行 `ament_uncrustify --reformat`。
- 每个实现任务先写测试，保留 RED → GREEN 命令和输出，再 inline review、单独 commit。collection/import/环境失败不是有效 RED；必须进入 testcase 并在目标行为断言处失败。
- 每个新 shell 先记录 Bun 路径和版本；所有 web install/scripts/CLI 使用 Bun。长命令先核对确切 executable；zsh 不赋值 `status`；管道先开 `set -o pipefail` 并保存真实退出码。
- 唯一证据根：`/data/work/so101-evidence/teleop-archive-viewer/20261017T062429Z-007cb1e3`。日志、venv、build/install、截图、JUnit、临时验收脚本和 scratch 均在其下。账本为 `docs/experiments/so101-teleop-sealed-archive-viewer-experiment-ledger.md`。

## 代码和数据核对结果

下面的引用已在基线核对；实现前再次通过符号名定位，不沿用可能过时的行号。

| 位置或字段 | 现场事实及计划决定 |
| --- | --- |
| `unified/app.py:create_unified_app`，约 1020 行 | 独立 factory，现无 archive 参数；新增 `archive_roots: tuple[Path, ...] = ()`。router 在 `_mount_static` 前注册。 |
| `unified/app.py:API_NAMESPACES` / `_mount_static` | 当前无 `api` namespace。补入 `api`，防止未知 archive API 被 SPA 回退成 HTML；显式增加 `/archives` 页面。 |
| `unified/main.py:build_parser/build_app` | CLI 实际位于这里，不在安装脚本；新增 repeatable `--archive-root`，严格验证绝对、存在的目录。本版只提供 CLI，避免环境变量分隔约定和隐式开启。 |
| `web/src/state/runtime-provider.tsx:pageFromPath/usePageRouting` | 使用 pathname 和 History API，无 `?page=` 编码。采用 `/archives?root=…&pkg=…&scene=…`；既有页面保留原 URL 和 runtime 生命周期。 |
| `web/src/components/unified/app-shell.tsx` | Page 类型有三项，但导航只显示 Teleop、Expert Validation；新增 Archives 导航，Tasks 继续现有兼容入口。 |
| `openapi_export.py` / web `package.json` | 实际导出为 `python -m so101_teleop.openapi_export --unified OUTPUT`，类型为 `bun run generate:api:unified`。compat Teleop schema 目前会纳入所有非 validation 路由，应显式排除 `/api/archives`，保留既有兼容路由范围。过滤视图仍共享全部 components；如果现有快照校验要求同步，则用各自已有 exporter/generate script 更新兼容文档和类型，不手工裁剪 components。 |
| `CMakeLists.txt` / `test/test_ctest_registration.py` | 包是 ament_cmake，每个普通 test module 都须注册；没有 setup.py。新增测试逐模块登记，不只跑新测试目录。 |
| 封存注册表 | 已只读确认 7 项；supporting roots 中有 symlink，不能因 symlink 存在就遗漏包或跟随其目标。 |
| 场景清单 | 集合包内 `inputs/frozen/inputs-manifest.json` 的 `scene_manifest.path` 为 `scene_manifest/scenes.json`，相对 manifest 所在目录；列表字段是 `scenarios`，位置字段 `cup_position_world_m`。无需读取独立 inputs 包。 |
| collection / campaign | 现场 collection schema=3；campaign-result schema=2，最终场景有 `recording_attempts[]`，每个录制项内含 processing `attempts[]`。schema 2 collection 兼容单轮回退，不虚构历史。 |
| retry | `retry.rounds_run=1`、`retry.recovered=5`；round 2 为 SKIPPED，不计入已运行轮数。`recording_attempts` 中的重录和 processing 重试必须分开计数。 |
| committed | `frm-000` 在 `committed_episodes[]`，但 `episode/seal.json.committed=false`。表格及统计以 collection index 为准，详情原样展示 seal.committed，命名分别为 `collection_committed` 和 `seal.committed`。 |
| records | `observation.head_png` 是 `frames/000000-head.png`，不是裸文件名；相对 episode 解析后须落在 `episode/frames`。action 长度为 6，现场 state 长度为 8，不写死为 6。 |
| seal manifest | 行含 `path/bytes/sha256`，相对包根；现场不包含 `SEALED.json` 自身。验收另存 seal、manifest 和完整目录快照，不能仅靠清单校验声称没有新增文件。 |
| identity | `campaign-index.json` 主要是 wave 场景安排；commit/image 可读包内 `host/teacher-provenance.json` 和 frozen inputs。`host/resources.jsonl` 含 monotonic_ns，不当成 wall-clock 起止时间。配置、qualification SHA 或 wall-clock 没有可靠包内来源时标记 unavailable，绝不跨包补读或以 sealed_at 冒充运行结束。 |
| 环境 | 系统 `/usr/bin/python3` 缺 xdist/FastAPI/httpx/uvicorn；技能默认 venv 路径不存在。确认后创建任务私有 venv。现有 Claude gate build 正在运行；不接管或停止。新 worktree 的 MuJoCo 子模块未初始化，本任务不需要它。 |

## Review Focus

1. 迁移包的旧绝对路径、相似前缀目录、manifest 逃逸和符号链接替换：只允许记录根前缀的精确路径重定位，实际打开仍验证边界（任务 1、3）。
2. final processing outcome、集合提交和 seal.committed 不一致，FAULT 没有 episode：保留来源语义，场景行和详情仍可访问（任务 2、3）。
3. 截断 JSONL、超长 UTF-8 单行、非行边界 offset 和最后一页：有界读取、明确错误或继续游标，不整文件装载（任务 3）。
4. 快速切换包/场景、浏览器后退、末帧及图片失败：旧响应不能覆盖新选择，播放和曲线共用当前行（任务 5、6）。
5. 并发 verify、取消后立即重启、LRU 淘汰在用包和关闭服务器：同一时刻只允许一个工作线程校验；状态和缓存内存有界（任务 2、4）。

## 设计第 6 节风险与处理

| 原风险项 | 处理方式与证据 |
| --- | --- |
| collection 到 scene list / inputs 的链接 | 优先包内 frozen manifest，校验相对链接及 SHA。未绑定时回退 campaign/result/index 的 scene id 并给元数据缺失提示；不跨包读取。任务 2 测无清单、路径逃逸、schema 2 和 FAULT。 |
| 索引中的绝对路径及迁移 | 以 `SEALED.json.root` 为旧根，使用 Path 前缀语义提取相对路径，再映射到当前包；禁止任意字符串替换。旧根之外的绝对地址拒绝；任务 1、3 测整体移动和 sibling-prefix 攻击。 |
| 约 140k 行 manifest 内存开销 | 包缓存最多 2 个、records 缓存最多 2 个 episode；只缓存解析所需字段，不缓存 audit/PNG。refresh 替换目录快照；活跃读取/verify 持有自己的引用。任务 2、4 测 LRU、refresh 和在用快照。 |
| PNG 服务 | 只通过已校验、manifest-listed 的帧路径返回 FileResponse，`image/png`、`Cache-Control: private, max-age=3600`；无转码、无磁盘缩略图。任务 3 测 row/camera、逃逸和 missing frame。 |
| bind policy | 继续 `validate_bind_address`（loopback 或 Tailscale `100.64.0.0/10`），同一 app/端口，archive 路由不接控制域。任务 1 测不安全 bind、无 ROS/Docker 导入；手工验收使用独立 loopback 空闲端口。 |

补充风险：发现包后不下钻并不保证整个 registry 扫描快，未封存的 build 树可能很大。scandir 无逐文件 stat 地检查目录、跳过 symlink，注册项可先解析和去重，完整刷新仍搜索未注册包；任务 1 测遍历剪枝，任务 6 后实测发现耗时和包页冷/热耗时，超标不能宣称验收完成。只读读取可能改变文件系统 atime，验收核对内容、文件集合和 mtime，不把 atime 当成应用写入。

## 共用接口和验证命令

所有 DTO 定义于新增 `archive_viewer/models.py`，采用 `ConfigDict(extra='forbid')`；数据缺失用 null 和结构化 warnings 表达。错误类位于 `errors.py`：unknown id 404，包外路径 409 `ARCHIVE_PATH_OUTSIDE_PACKAGE`，文档错误 422 `ARCHIVE_DOCUMENT_INVALID`（仅返回相对 document 名和说明），禁用 404 `ARCHIVES_DISABLED`。JSON 大于 2 MiB 返回 413 `ARCHIVE_FILE_TOO_LARGE`，不尝试解析。

- `ArchiveConfig(roots: tuple[Path, ...])`、`ArchiveStore(config)` 是唯一配置和缓存所有者；router 由 `archive_router(store) -> APIRouter` 创建，禁用检查在路径参数校验前发生。
- `store.config_view() -> ArchiveConfigView`：`enabled, roots[{root_id,label}]`；启用时 enabled=true。
- `store.packages(root_id: str, refresh: bool=False) -> PackageList`：`packages[]` 含 `package_id,name,kind,sealed_at,reason,files,bytes,manifest_sha256,registered`，另有 warnings。
- `store.package(package_id: str) -> PackageSnapshot`；snapshot 提供 `view() -> PackageView`、`episodes(query: EpisodeQuery) -> EpisodePage` 和 `episode(scene_id: str) -> EpisodeSnapshot`。snapshot 不接受客户端路径。
- `PackageView` 含 seal、identity（各值及来源/缺失原因）、statistics、warnings；statistics 含 planned/committed、non_committed_by_outcome、committed_by_split、retry_rounds_run/recovered/recovered_by_round、duration_rows/seconds 的 total/median、episode_bytes 的 total/median。duration=record_count/10，episode_bytes 为该 processing_output 子树的 manifest bytes 总和，不混用 phase1.recording_bytes。
- `EpisodeQuery` 支持 split/outcome/q/sort/offset/limit；默认 scene_id 升序、offset=0、limit=100，limit 1..200、q 最长 128。sort 为表格字段白名单，前缀 `-` 降序，null 始终置尾，scene_id 作稳定次序。每一显示列均有相应可排序字段。
- `EpisodeRow` 含 scene_id/split/collection_committed/outcome/reason、recording_attempt_count/final_recording_round、record_count/duration_s/bytes、teacher_result/qc_status。FAULT 仍有一行；不存在的数值为 null。
- `EpisodeSnapshot.detail() -> EpisodeDetail`：scene(seed/cup)、collection_committed、seal、processed_result、qc_summary、attempts、files、frame_count、warnings。attempts 含 kind(recording/processing)、round/wave/shard/proc_attempt/outcome/reason；files 含 file_id/name/bytes/sha256，可列出对应 processing_output 的 seal、QC、processed result、records 和 audit。
- `EpisodeSnapshot.series() -> EpisodeSeries`：`points[{row,t,action,state}]`、`stride`，最多 2000 点且包含首尾；另有轻量 `row_times_s[]` 供每一帧精确显示 sim_time_s。state 维度按数据保留。
- `EpisodeSnapshot.frame(row: int, camera: Literal['head','wrist']) -> Path`：只返回已通过权限边界和 manifest 身份校验的路径。`EpisodeSnapshot.file(file_id: str, offset: int=0, limit: int=100) -> FileView`：JSON parsed content 或 JSONL `lines,next_offset,eof`，limit 1..500，offset 非负且在行边界，单页至多 2 MiB；超长单行返回 413 `ARCHIVE_LINE_TOO_LARGE`。
- `VerificationManager.start(snapshot) / status(package_id) / cancel(package_id) -> VerifyProgress`：`state=idle|running|cancelling|cancelled|complete|failed`，total/checked/mismatch_count/missing_count、有限 issues（最多 100 条）、truncated。其他包 status 不泄露当前包内容；第二个 start 返回 409 `ARCHIVE_VERIFY_BUSY`，cancel 幂等。关闭时 cancel 并 join 本任务线程。

路由严格采用设计第 3 节的 11 个 method/path 操作（config、packages、package、episodes、detail、series、frames、files、verify POST/GET/DELETE），客户端封装使用对应生成类型。只传 root_id 等 id；刷新为 `refresh=true`，verify POST/DELETE 不写文件。列表过滤值、行数和 offset 有界校验；必要时用 router dependency/middleware 实现禁用状态，使未知路径或无效参数也不会提前变成 HTML/422。

确认后先核验可用工具及负载，再建私有 venv（不改系统或采集 venv），安装现有包测试所需依赖；按 `python-dependency-install.md` 使用单命令 TUNA 配置。记录依赖版本和完整安装日志。`TEST_PYTHON` 固定为 `$TASK_ROOT/venv/bin/python`，所有测试、导出和启动均先 `test -x`。新环境须核验 Pydantic v2、FastAPI、httpx、pytest、xdist 和项目实际依赖；缺少依赖记环境门，不能当 RED。

以下为计划中的命令模板，**现在不执行**。`pygate` 是确认后写入证据根并回读的临时 shell helper，不是产品代码。每次调用建立此前不存在的 scratch，设置三项临时目录变量，保存 tempfile proof、elapsed、退出码和 stdout；调用时传 `red-任务号` 或 `green-任务号` 等唯一标签。

```zsh
export TASK_ROOT=/data/work/so101-evidence/teleop-archive-viewer/20261017T062429Z-007cb1e3
export WORKTREE=/home/matianyi/Projects/ros-moveit-demo/.worktrees/teleop-archive-viewer
export TEST_PYTHON="$TASK_ROOT/venv/bin/python"
command -v bun
bun --version
test -x "$TEST_PYTHON" || exit 1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$WORKTREE/src/so101_teleop:$WORKTREE/src/so101_demo_py/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$WORKTREE"

pygate() (
  set -o pipefail
  local gate_label="$1"
  shift
  local gate_dir=$(mktemp -d "$TASK_ROOT/scratch/${gate_label}.XXXXXXXX") || exit 1
  mkdir "$gate_dir/tmp" || exit 1
  export TMPDIR="$gate_dir/tmp" TMP="$gate_dir/tmp" TEMP="$gate_dir/tmp"
  "$TEST_PYTHON" -c 'import os,pathlib,sys,tempfile,pytest,xdist; a=pathlib.Path(tempfile.gettempdir()).resolve(); b=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,pytest.__version__,pytest.__file__,xdist.__version__,xdist.__file__,a); assert a==b' > "$gate_dir/tempfile-proof.log" 2>&1 || exit 1
  local gate_start=$SECONDS
  "$TEST_PYTHON" -m pytest "$@" --junitxml="$gate_dir/junit.xml" > "$gate_dir/output.log" 2>&1
  local gate_rc=$?
  print -r -- "exit_code=$gate_rc elapsed_s=$((SECONDS-gate_start)) scratch=$gate_dir" > "$gate_dir/result.txt"
  cat "$gate_dir/result.txt"
  return "$gate_rc"
)
```

RED 命令预期非零且 testcase 到达目标断言，GREEN 必须 0。每次回读 output/JUnit，不能只看 helper 最后一行。新增 archive fixture 测试还检查每个 worker 的 tmp_path 确实落在本次 TMPDIR 内。源码测试使用项目路径；安装验收清除源码 PYTHONPATH，防止误用源文件。

## Task 1: 配置、发现和只读路径边界

任务中的缩写路径约定：`archive_viewer/` 指 `src/so101_teleop/so101_teleop/archive_viewer/`，`unified/` 指同级 `so101_teleop/unified/`，`test/`、`web/`、`CMakeLists.txt` 均相对 `src/so101_teleop/`。裸模块名继承本任务列出的 archive_viewer 目录。

**Files:** 新增 `src/so101_teleop/so101_teleop/archive_viewer/{__init__,config,models,errors,paths,scan,api}.py`；修改 `unified/{app,main}.py` 和 `src/so101_teleop/CMakeLists.txt`。新增 `test/archive_viewer/conftest.py`、`test_archive_scan.py`、`test_archive_paths.py`、`test_archive_config.py`（均在 `src/so101_teleop/test/archive_viewer/`）。

**Interfaces:** 实现 ArchiveConfig、ArchiveStore 的 config/packages 部分及 `archive_router`；路径辅助 `resolve_package_path(package_root: Path, recorded_root: Path, value: str, *, base: Path | None = None) -> Path`。在 scan 中签发 root/package id；后续任务只从 store 取包。

- [ ] 先建 synthetic builder（collection、supporting、未封存、嵌套 seal、symlink dir、可选注册表），所有文件通过 tmp_path 创建；先写 API 测试并运行到行为失败：配置 root 后列表应 200、正确发现两个包且 registered 值正确；初始不存在的 API 返回 404 是此测试有效 RED。
- [ ] 写配置/路径测试：无配置所有 archive 操作 404 ARCHIVES_DISABLED；相对或不存在 root 启动拒绝；未知 id 404；unsafe bind 拒绝；无 ROS/Docker import。路径测试覆盖包整体迁移、旧根相似前缀、`..`、外部 manifest/SEALED symlink、目录链接循环；scanner 到 SEALED.json 即停止，即使标记损坏也不下钻，并用 warning 指出损坏文档。
- [ ] 实现最小配置与发现；os.scandir 不跟随目录链接，查到 seal 后不遍历包树。registered 只是已登记标志，不代替读取 seal kind；重复配置 root 去重。refresh 原子替换 root 快照，id 基于 resolved root/path 稳定签发。
- [ ] 验收：`pygate red-1 src/so101_teleop/test/archive_viewer/test_archive_scan.py`；实现后 `pygate green-1 src/so101_teleop/test/archive_viewer/test_archive_scan.py src/so101_teleop/test/archive_viewer/test_archive_paths.py src/so101_teleop/test/archive_viewer/test_archive_config.py src/so101_teleop/test/test_ctest_registration.py`。注册每个新 module，核对主 app 的未知 API 返回 JSON 而非 HTML。
- [ ] inline review 后提交：`feat(teleop): discover sealed archives behind explicit roots`。

## Task 2: 包统计、全场景列表和 attempts 来源

**Files:** 新增 `archive_viewer/{manifest,package}.py`；修改 `models.py`、`api.py`、`scan.py`、`CMakeLists.txt`；新增 `test/archive_viewer/test_archive_package.py`、扩展 builder。

**Interfaces:** 完成 PackageSnapshot、PackageView、EpisodeQuery/EpisodePage；manifest 索引以相对路径查 bytes/sha，文件 id 与包及相对路径绑定；PackageSnapshot 最多 2 项 LRU。通过 collection_evidence 构建 scene→processing_output 的服务器内部映射。

- [ ] 先写 RED：合成 4 个正式场景，2 committed（train=1、validation=1、offline_test=0），另有 FAULT=1、MISSING=1；其中一个 committed 经 INVALID→VALID 重录救回，round 1 RUN、round 2 SKIPPED，断言 retry_rounds_run=1、recovered=1。两段 episode 为 5/7 rows，duration total=1.2 s、median=0.6 s，bytes 与 manifest 和相等；seal.committed=false 不改变 collection committed=2。
- [ ] 加入 schema 2 单轮、缺 scene manifest、损坏必要文档 422、可选 identity 缺失、final INVALID、processing 重试不冒充重录；一行一个正式 scene，不因两个 attempts 重复计数。覆盖所有列排序、null 置尾、过滤/search/paging 和 LRU/refresh；文件缺失不悄悄抹掉 scene。
- [ ] 实现包投影：scene 清单优先 frozen `scenarios`，缺失时对 campaign/index 的 scene id 取并集；以 final scene 和 index membership 展示 outcome/committed。从 recording_attempts 关联所有 processing attempts，并保留 round、wave、worker_id。必要文档 malformed 与可选文档 absent 分开处理。
- [ ] 读取 manifest 一次，校验其 SHA，并建立每个 processing_output 的文件分组；统计不打开 records、PNG 或 audit。identity 从已核对的包内来源选值，展示 source_commit 与 image git_commit 的区别，不把不同 commit 混为一个。
- [ ] 验收：`pygate red-2 src/so101_teleop/test/archive_viewer/test_archive_package.py`；`pygate green-2 src/so101_teleop/test/archive_viewer src/so101_teleop/test/test_ctest_registration.py`。预期全部通过，目录外 open 探针为 0。
- [ ] inline review 后提交：`feat(teleop): project sealed collection statistics and scene history`。

## Task 3: Episode 详情、双相机、信号及有界文件读取

**Files:** 新增 `archive_viewer/{episode,files}.py`；修改 `package.py`、`models.py`、`api.py`、`CMakeLists.txt`；新增 `test/archive_viewer/test_archive_episode.py`、`test_archive_files.py`。

**Interfaces:** 实现 EpisodeSnapshot 的 detail/series/frame/file，路由按共用接口声明。records 缓存最多 2 项，只留 t/action/state/frame 名；文件表覆盖 processing_output 下 metadata 与 episode 文件。

- [ ] 先写 RED：fixture detail 返回 seal/QC/processed summary、完整 recording/processing timeline、manifest file ids；series action=6、state=8、不含 audit；row=4 的 head/wrist 返回各自 fixture PNG，slider 所需 row_times 与 sim_time_s 相同。
- [ ] 覆盖 5001 rows 下采样≤2000且保留首尾、空 records、不同 state 维度、非法 row/camera、frame 丢失；越界 processing_output/frame/QC 路径、manifest 中未登记帧、符号链接切换和未知 file id 拒绝。FAULT detail 无 frames，仍显示原因和 attempts。
- [ ] 文件测试固定 JSON 2 MiB 上限及超限 413；JSONL UTF-8、多页无重复/遗漏、EOF、最后无换行、行边界错误 offset、负 offset、越限 limit、超过页大小的单行 413；探针禁止 `read()` 无上限和整份 audit read_text。
- [ ] 实现 line-by-line records 提取、固定 stride 首尾保留；帧相对 episode 解析后检查 `episode/frames` 边界及 manifest。每次打开前重验路径，不盲信扫描时结果；按原始 PNG 返回 FileResponse。JSONL 使用 byte offset 和有界 readline，无磁盘索引。
- [ ] 验收：`pygate red-3 src/so101_teleop/test/archive_viewer/test_archive_episode.py src/so101_teleop/test/archive_viewer/test_archive_files.py`；`pygate green-3 src/so101_teleop/test/archive_viewer src/so101_teleop/test/test_ctest_registration.py`。
- [ ] inline review 后提交：`feat(teleop): serve sealed episode frames signals and paged files`。

## Task 4: 后台校验、取消和全部端点只读证明

**Files:** 新增 `archive_viewer/verify.py`；修改 `api.py`、`models.py`、`unified/app.py`、`CMakeLists.txt`；新增 `test/archive_viewer/test_archive_verify.py`、`test_archive_readonly.py`。

**Interfaces:** 实现 VerificationManager 和 3 个 verify 操作；独立生命周期只管理自己的线程，不与控制域耦合。

- [ ] 先写 RED：干净 fixture 最终 complete、checked=manifest 项数、无 mismatch/missing；另一个可写 fixture 副本改一个 byte 和移走一个文件，准确报告 mismatch/missing。并发 start 返回 busy，取消后状态最终 cancelled，再次 start 只能在旧线程退出后成功。
- [ ] 用可注入 hash 进度同步点控制取消测试，不靠 sleep 碰运气；覆盖大文件分块取消、在用包被 LRU 淘汰、refresh、校验中读取 frame、超过 100 issues 截断、异常结束和 app shutdown 线程回收。symlink 项只检查 link 自身信息，不读取目标内容；包外目标明确列为 refused issue，绝不跟随。真实 supporting 包仍可列出 metadata。
- [ ] 只读证明：创建全功能 fixture，先快照全部相对路径/类型/size/mtime_ns/hash（包、兄弟 manifest、注册表），再仅对 fixture chmod a-w；记录 chmod 后基线。以非 root 身份遍历所有成功/失败 GET 和 POST/DELETE verify（含 refresh、分页第二页、两相机首尾行和取消），最后确认列表、mtime、bytes、hash 完全相同。增加写模式/rename/unlink/mkdir/chmod 探针，拒绝读取器尝试修改 fixture；fixture teardown 不删除证据。
- [ ] 实现单工作线程、分块只读 hash、cancel event、内存 progress 和有限 issues。启动校验先校验 manifest 自身 SHA；不因不一致继续信任清单。SEALED.json 自身不在 manifest 时单独保持 seal 元数据身份，不伪造清单条目。
- [ ] 验收：`pygate red-4 src/so101_teleop/test/archive_viewer/test_archive_verify.py src/so101_teleop/test/archive_viewer/test_archive_readonly.py`；`pygate green-4 src/so101_teleop/test/archive_viewer src/so101_teleop/test/unified/test_unified_lifecycle.py src/so101_teleop/test/test_ctest_registration.py`。
- [ ] inline review 后提交：`feat(teleop): verify sealed archives without mutating evidence`。

## Task 5: OpenAPI、类型化客户端、包列表及场景页面

**Files:** 下列路径相对 `src/so101_teleop/`：修改 `so101_teleop/openapi_export.py`、`so101_teleop/unified_openapi.json`、`test/api/test_openapi_export.py`、`CMakeLists.txt`；修改 `web/src/api/unified-schema.d.ts`、`web/src/state/runtime-provider.{tsx,test.tsx}`、`web/src/components/unified/app-shell.{tsx,test.tsx}`、`web/src/main.tsx`。新增 `web/src/api/archives-client.{ts,test.ts}`、`web/src/components/archives/archive-browser.{tsx,test.tsx}`、`package-view.{tsx,test.tsx}`、`archive-routing.{ts,test.ts}`。如需同步过滤视图，则同时生成 `so101_teleop/{openapi,expert_validation_openapi}.json` 和 `web/src/api/{schema,expert-validation-schema}.d.ts`。

**Interfaces:** `ArchivesApiClient` 以生成 schema 推导 DTO，提供 config/packages/package/episodes/detail/series/frameUrl/file/startVerify/verify/cancelVerify；支持 AbortSignal。`ArchiveBrowser` 负责 config、root/package/scene URL 状态及页面选择；`PackageView` 消费 package id 展示完整统计、过滤表格和 verify progress。

- [ ] 先写 RED：OpenAPI 包含全部 archive 操作及 DTO，未配置时也可导出；兼容 Teleop schema 不出现 `/api/archives`。前端测试断言 Archives 导航、`/archives` 路由及 query 深链接/后退、现有 runtime 不重建；初始代码没有新导航或 pathname 映射，应在 UI 断言失败。
- [ ] client 测所有请求只发送 id/受限参数，正确编码 id，结构化失败抛出 code、不把 404 payload 当数据；未启用显示可理解的禁用状态。测试 root 切换清除 pkg/scene、非法 id 错误、refresh、supporting metadata 无 episode 入口、完整 scene 行、每列排序和双过滤/search。
- [ ] 实现列表和包页，含时长/大小总计与中位数、identity/缺失说明、retry、Teacher/QC、截短原因及完整可读原因。verify 支持 start/poll/cancel，离开页停止轮询；只在用户动作启动校验，切换选择时 abort 并忽略旧响应。使用现有 UI 组件和主题变量，不新增依赖。
- [ ] 按既有流程导出，再生成类型，禁止手改生成文件：

```zsh
"$TEST_PYTHON" -m so101_teleop.openapi_export --unified src/so101_teleop/so101_teleop/unified_openapi.json
cd "$WORKTREE/src/so101_teleop/web"
command -v bun
bun --version
bun run generate:api:unified
```

- [ ] 验收：`pygate red-5 src/so101_teleop/test/api/test_openapi_export.py`、`pygate green-5 src/so101_teleop/test/api/test_openapi_export.py src/so101_teleop/test/test_ctest_registration.py`；在 web 执行 `bun run test -- src/api/archives-client.test.ts src/components/archives/archive-browser.test.tsx src/components/archives/package-view.test.tsx src/components/archives/archive-routing.test.ts src/state/runtime-provider.test.tsx src/components/unified/app-shell.test.tsx`，记录 RED 与 GREEN；`bun x --no-install tsc -b` 必须 0。
- [ ] inline review 后提交：`feat(teleop-web): browse sealed packages and scene statistics`。

## Task 6: Episode 页面、同步播放器和 SVG 曲线

**Files:** 新增 `web/src/components/archives/episode-detail.{tsx,test.tsx}`、`frame-player.{tsx,test.tsx}`、`signal-chart.{tsx,test.tsx}`、`file-viewer.{tsx,test.tsx}`；修改 archive-browser/package-view 连接详情与返回路径；必要主题样式放现有 CSS 或组件 Tailwind，不修改设计系统依赖。

**Interfaces:** `EpisodeDetail` 使用 detail/series 响应；`FramePlayer` 消费 packageId/sceneId/frameCount/row/onRowChange/rowTimes；`SignalChart` 消费 points/group/currentRow，在内部按时间映射 cursor；`FileViewer` 只消费 file id 及文件元数据。EpisodeDetail 持有唯一 currentRow，两个相机和两组曲线全部派生自此。

- [ ] 先写 RED：选择 scene 后显示 seal/processed/QC/timeline；slider 到 row 4，同时改变 head/wrist URL、row/sim_time 文本和 action/state 两组 cursor。fake timers 检查每 100 ms 推进行、末行暂停、播放/暂停、切换 scene 重置和卸载清理；按钮和 slider 可键盘操作。
- [ ] 测 >2000 rows 下采样后的 cursor 仍对应当前原始行时间、空数据和 FAULT 无播放、单张图片失败提示、快速切换旧响应不覆盖新页面；JSON dialog 格式化、JSONL next page 使用服务器 next_offset、末页禁用下一页、413 可读说明。
- [ ] 实现双图懒加载、仅预取后续 2 行（每相机）并限制在 frameCount 内；不一次加载全 episode。SVG 使用现有主题色，action 6 条线、state 按实际维数，具图例和时间轴。详情 URL 刷新/分享恢复同一 scene，前进/后退正确；signal 无需新图表库。
- [ ] 验收：web 执行 `bun run test -- src/components/archives/episode-detail.test.tsx src/components/archives/frame-player.test.tsx src/components/archives/signal-chart.test.tsx src/components/archives/file-viewer.test.tsx`（先 RED 后 GREEN）；随后完整 `bun run test`、`bun x --no-install tsc -b`、`bun run build`，必须全部 0，保存日志和耗时。
- [ ] inline review 后提交：`feat(teleop-web): inspect sealed episodes with synchronized playback`。

## 最终门禁、安装和真实手工验收

这是任务 1–6 完成后的验证阶段，不先改产品行为。失败则返回拥有该边界的任务补充 RED → GREEN，并另行提交修复；不能把安装失败算 RED。最后单独提交更新后的任务账本和验收记录，不混入未经测试的实现。

### 完整普通测试和安装来源

- [ ] 先核对并发负载、CPU、内存；实际机器仍为 32 logical CPUs 时固定 workers=8。先跑无修改基线测试并留结果；基线门应在任务 1 实现前完成，后续全量门在任务 6 后完成。不因他方采集负载改成串行冒充通过。
- [ ] `pygate full-teleop src/so101_teleop/test -n 8`；保存完整收集范围、worker 证据、退出码、JUnit 和每项 skip。IPC 测试按现有隔离约定在任务根使用短私有 socket 目录，记录路径并确认 Linux sun_path 上限；绝不共享采集 socket/state/ROS 环境。若资源不足，记录未完成门禁，等待合适条件。
- [ ] web 的完整 Vitest、类型检查、build 已通过；再次运行 exporter 到证据根临时文件，与 tracked unified_openapi.json byte compare，重新生成类型后 `git diff` 应无漂移。OpenAPI 测试验证兼容视图和 refs 完整。
- [ ] 新安装由**新 worktree 源码**构建，build/install/log 都在任务根：先检查 `/opt/ros/jazzy` ament underlay 及 Python/Bun/CMake；`so101_teleop` 的 build 仅需 ament_cmake/ament_cmake_python。不复用采集 gate install，不初始化不需要的第三方子模块，不把缺 underlay 误判源码失败。

```zsh
source /opt/ros/jazzy/setup.zsh
export SO101_TELEOP_BUN=$(command -v bun)
test -x "$SO101_TELEOP_BUN" || exit 1
colcon --log-base "$TASK_ROOT/colcon-log" build \
  --base-paths "$WORKTREE/src/so101_teleop" \
  --build-base "$TASK_ROOT/build" --install-base "$TASK_ROOT/install" \
  --packages-select so101_teleop \
  --cmake-args -DBUILD_TESTING=ON -DPython3_EXECUTABLE="$TEST_PYTHON"
source "$TASK_ROOT/install/setup.zsh"
```

- [ ] 包门禁：从新 `CTestTestfile.cmake` 核对实际 interpreter/argv；每个真实 interpreter 先生成本次 tempfile proof。为该次 `colcon test` 建全新 NVMe scratch 并设置 TMPDIR/TMP/TEMP；`PYTEST_ADDOPTS='-n 8'`，`CTEST_PARALLEL_LEVEL=1`，colcon sequential，避免每个 CTest 同时各开 8 workers。命令为 `colcon --log-base "$TASK_ROOT/colcon-test-log" test --build-base "$TASK_ROOT/build" --install-base "$TASK_ROOT/install" --packages-select so101_teleop --executor sequential --event-handlers console_direct+`，再 `colcon test-result --test-result-base "$TASK_ROOT/build/so101_teleop" --verbose`。确认 ament 子进程收到 xdist 参数；否则先修验证环境，不缩小测试范围。保存 CTest 的 JUnit、退出码、elapsed、skip 和完整登记集合。
- [ ] 证明安装来源：清除源码 PYTHONPATH，从工作树外目录读取 installed `so101_teleop.unified.main.__file__`、archive 模块路径、安装脚本和 web bundle SHA；均归属任务 install。使用该安装入口 `--check` 后才能启动服务。

### 真包验收前后的只读保护

- [ ] 重新只读获取注册表，冻结本次 7 项的 root/manifest/manifest SHA。检查任务 state/install/capture/scratch 不在任何封存树或 manifest 上；设置 `PYTHONDONTWRITEBYTECODE=1`、缓存/state/TMPDIR 全部指向本任务根。
- [ ] 验收脚本仅放证据根，不作为单元测试或普通 gate 收集。所有输出均写证据根；不运行封存目录中的脚本，不 chmod、不执行任何修复封存权限的操作。
- [ ] 浏览前：对 EXP-620 清单逐条流式 SHA256/size 核对并保存明细；单独 hash `SEALED.json`、兄弟 manifest 和注册表。对 7 个封存根用不跟随 symlink 的只读遍历保存完整路径/类型/size/mtime_ns/link-target 快照，覆盖清单未收录的 seal 和目录；浏览后再次采集比较，不能只检查原有文件。
- [ ] hash 低优先级顺序读取，使用单 verify worker，避免并行扫 55 GB 影响采集。只校验 EXP-620 内容；其他 supporting 包只比较完整目录元数据，不跟随其指向包外的链接。

### 独立安装服务和浏览器

- [ ] 从新 shell 核对 `ss -ltnp`、tmux、进程和服务环境。使用空闲 `127.0.0.1:8014`（占用则选择并记录另一空闲 loopback 端口），不得占用现有服务或杀端口持有者。统一服务的 bind validation 保持生效。
- [ ] 独立 tmux session `so101-archive-viewer-20261017` 承载服务；只使用本任务 evidence/state/socket/install，不继承 ACT GPU/instance/ROS worker 配置，不启动仿真或控制 bridge。普通 compose 中未配置的 domain 可以 unavailable，不影响 archive。启动前重读 compose 和 `--help`，验证确切安装入口，环境变量使用本任务 `SO101_UNIFIED_EVIDENCE_ROOT` 和唯一 socket/runtime id。

```zsh
"$TEST_PYTHON" "$TASK_ROOT/install/so101_teleop/lib/so101_teleop/so101_unified_web_server.py" \
  --host 127.0.0.1 --port 8014 \
  --archive-root /data/work/so101-evidence/act-data/20260924-fbc25063-resume
```

- [ ] 用项目 `$gui-capture` 当前平台流程取得 baseline 和动作后的新截图并实际查看；必要的浏览器自动化只连本任务服务。不能拿旧会话截图或纯 API 返回代替可见验收；若 GUI 能力不可用，明确标记该项未完成。
- [ ] `/archives` 列出当前 7 个根，supporting 包只显示 seal metadata；刷新不进入任何已发现封存包。保存发现耗时，目标数秒（以 ≤5 s 记录），包页 warm <3 s、cold <10 s；没有通过不能省略报告。
- [ ] EXP-620 `act-w8f-20261017T021838Z` 显示 planned=70、committed=69、train=49/validation=10/offline_test=10，未提交 FAULT=1（frm-007），round 1 recovered=5，rounds_run=1。测试 split/outcome/search/sort，FAULT 详情和 supporting metadata；对照真实文档，而非前端硬编码常量。
- [ ] 打开 frm-000 可分享 URL 并刷新恢复；显示 frame_count=905、action 6维、state 实际8维，双相机并排播放，可暂停、拖动到首/中/尾行（0、452、904）。逐行可访问 905 行两相机，保存加载失败数；观察 row/sim_time 和两个 SVG cursor 同步。打开 seal/QC/processed JSON 及 audit 第一页/下一页，确认没有下载整份 audit。
- [ ] 页面触发 verify，保存 progress、取消再启动的行为和最终通过结果；浏览结束后再用独立只读脚本按封存 manifest 逐字节 hash EXP-620，与浏览前结果一致，并核对 7 根目录无新文件/mtime 变化、seal/manifest/registry bytes 不变。manifest 自身 SHA 应保持 `82e06969c9a94ff69ac936237248fc4e117da8aafdf4b8e99f5d11b2fbb4bbfd`。
- [ ] 只停止本任务明确持有的服务/线程/browser 进程，保留已有采集和 gate；再次记录 process/port ownership。归档验收结论和截图路径到任务账本，记录耗时及任何缺失 identity 字段。

## 提交、推送和完成报告

- [ ] 每个任务提交前 `git diff --check`、inline self review，并将测试 run id、scratch、命令、退出码和 checkpoint 写入账本。提交清单按任务 1–6 的边界；初始计划/spec/ledger 单独 docs 提交，最终验证记录再单独 docs 提交。
- [ ] 最终核验 `git diff 007cb1e3c...HEAD` 只包含本功能及必要文档；受保护 worktree 未写入。不自动 merge，不修改任何全局模型配置。
- [ ] push 前 fetch/回读目标 ref，检查 LFS status，不设置 `GIT_LFS_SKIP_PUSH=1`。仅执行 `git push origin codex/teleop-archive-viewer`；回读远端 SHA 与本地一致。
- [ ] 报告提交列表、完整 pytest/Vitest/类型/CTest 命令及结果、7 根和 EXP-620 逐项手工验收、性能、无变化 hash 证据、安装来源、保留的既有进程和未完成事项。
- [ ] retained：本任务证据根、测试日志/JUnit、截图、独立安装和校验报告。archived：当前无，后续若有则列出。删除候选：所有已回读 scratch run（包括失败 run）的绝对路径；不删除，不清理任何封存证据。

## 计划自审

- R1/N2/N5 → 任务 1；R2 → 任务 2、5；R3 → 任务 3、6；R4 → 任务 4、5；N1/N6 → 任务 4；N3 → 任务 2、3、最终性能实测；N4 → 任务 1 和安装验收。
- 共用 DTO、函数名称与各任务消费者一致；3 种 committed/outcome/QC 来源明确；真实数据只用于独立手工验收。
- 五项设计风险均有处理和验证位置；无需额外设计选择。用户确认前停在本计划，不进行任务 1 的环境准备、测试或实现。

# SO-101 ACT 容器化采集 campaign 执行计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本仓库的实施执行者必须是 ai-station 上 tmux 内的 DeepSeek Harness TUI（`dst`）；先取得用户对本计划的明确执行批准。不得在当前文档编写会话中实施。

**Goal:** 将 ACT 仿真采集迁移为 campaign 级共享 head-YOLO/教师 YOLO 服务和一 shard 一容器，取得独立 exact-W8 资格，并交付可审计的正式采集数据。

**Architecture:** Host owner 持有统一准入、GPU/resource lease、调度、独立 verifier 和 commit。两个推理容器使用同一服务镜像、各自配置和队列，跨 wave 存活；每 wave 创建 shard 容器，容器内顺序执行 Teacher、原始 bag 收尾、离线 episode 和独立 QC。Host 崩溃即结束旧 campaign；只清理已确认拥有的 generation，不接管共享服务，不自动重跑已提交结果。

**Tech Stack:** Python、ROS 2 Jazzy、MuJoCo、MoveIt/JTC、Docker、CUDA YOLO、Unix stream IPC、rosbag2 MCAP、pytest/xdist。

**Spec:** [已审容器化 campaign 设计](../specs/2026-09-30-so101-act-containerized-campaign-design.md)，以及[设计 Astra 审查记录](../specs/2026-10-11-so101-act-containerized-campaign-astra-review.md)。

状态：已按 2026-10-12 用户批准的简化方案更新设计与计划：保留可配置证据 ROOT，按同一绝对路径挂载；RGB 直接走 socket；Host 崩溃结束 campaign；资源只记日志并设置磁盘停派点；只构建推理、shard 两类镜像。本次由 Sol 在当前会话自检，未获实施授权。原 Astra / High PASS 只对应历史冻结稿，见[历史审查及最新处置](2026-10-11-so101-act-containerized-campaign-implementation-astra-review.md)。日期：2026-10-12。

## 全局约束

- 基线为 `origin/codex/so101-act-data-0917a` 的 `6baf54e6313daca287fa86e7cc248c4c2f1b1dc3`，来自 2026-10-11 的两个 remote 读回；本次仅修订文档，未刷新远端。以下路径按该提交解析，不按本地 `main` 的旧代码猜测。执行开始重新核对远端 HEAD；若发生重构漂移，先更新精确文件映射并审查，不能套用旧补丁。
- 业务名称使用抓放校准、抓放 live、Head Search、并行采集资格；不新增阶段编号式模块/CLI。每类业务只有一个当前 schema/接口，writer、reader、调用方和测试一起迁移；旧格式拒绝，旧证据不改写。历史文件名可保留。
- MuJoCo-only，CUDA/no CPU fallback；不运行真实 SO-101。不恢复 CommandBroker，不改变 Teacher 的 MoveIt/JTC 执行和停止合同。
- ACT 容器采集路径 YOLO-only；不移除 macOS 双 Worker/通用并行验证的既有 Broker、Grounded/SAM 与 MPS 能力。它们是另一业务的当前接口，不是本业务的兼容版本；ACT 正式路径不能选择旧 Broker。模型不新增独立 QUALIFIED 门禁；阈值推算不是本计划的一部分。
- 每 campaign 启动一次共享 head-YOLO 和一次教师 YOLO Broker；每 wave 一 shard 一容器。服务只接收闭合推理/query 消息，不感知 wave、lease、token 或 campaign resource binding。
- 资源绑定仅在统一启动入口校验。容器内核对自身 provenance/GPU/EGL/局部消息，不在各内部组件重做 campaign 资源授权。
- head 每 shard 至多一个未决请求；服务 `max_inflight_requests=8` 包含接收中的有界帧、queued/running/responses_pending。完整等待从 RGB 序列化前起算，计入本 campaign 已批准 policy 的 `perception_job_timeout_s`。`default_document()` 的 1.0 s 只是候选，不能直接当批准值；保留 `perception_max_age_s <= perception_job_timeout_s <= stop_confirmation_timeout_s`。
- 推理输入为 Unix socket 帧内的 C-contiguous `uint8 H×W×3` RGB8 字节，不写 staging 文件，不为传输生成图像 hash。measurement/Recorder 仍按现有合同保存原始图像与 hash，21 项测量来源不变。证据 ROOT 可配置；需要的证据与输入目录按同一绝对路径挂载，不批量改造现有 artifact schema。
- 推理进程数为正整数配置，只能下一 campaign 调整；不按 `1/2/4` 硬编码，不做逐档容量资格或预测预算。CPU/GPU/RAM/RTF/吞吐只观测；磁盘见底停止新派发，OOM、设备错误、服务退出及采集损坏按既有故障合同处理。需要人工决定时不自动缩容、降 Worker、改画质/采样率/阈值。
- Teacher 结果、ACT 数据 VALID/INVALID、基础设施故障分开。录制/QC 不成为 Teacher 运动门禁；bag→离线 10 Hz→独立 QC→seal→Host verify/commit 保持因果关系。
- W1/W2 使用同一完整八场景功能清单；W2 后直接 YOLO 教师的独立 40 场景 exact-W8、两个 20 项 wave。不测试 W4/W6。每 Worker 每 wave 至少两个真实 terminal lease；资格中零基础设施失败、重试和 crash-resume。
- 按后续审查所载用户决定，W8 的指标硬门槛仅为 Recorder 丢失、10 Hz 间隔、QC 合格率和 Teacher 物理成功率，沿用既有 QC/成功率规则。CPU/GPU/RAM、磁盘 I/O、RTF、队列长度和吞吐只记录，不设通过线或资源预算。拓扑、身份、原始证据、零infra/重试及cleanup仍必须成立；磁盘见底、实际采集缺失或服务故障停止派发，不自动降档。
- 正式采集可保留单 shard 故障的部分证据；不把资格的零故障断言套到正式恢复。业务 FAILED 不在同一 campaign 重排或重试。失败 case 不撤销整 wave。
- 受控 source/config/policy 改动后旧校准/bundle/live 对新身份失效，从新 run subroot 重做。21 项测量和十成员 identity 不扩充 Docker 参数。模型运营配置单独记录，不能通过 runtime hash 隐含变成模型资格门禁。
- 不 push，不删除或移动证据，不覆盖已有 dirty work。实现完成只做限定文件本地 commit；发布须另获授权。训练算法及 `act_train` 执行不在本计划内。

## 执行位置、证据和审查

你直接运行在 ai-station；不要自我 `ssh ai-station`。恢复时先读仓库 `AGENTS.md`、`so101-dev`、最新账本、tmux fresh pane、进程/容器、Git HEAD/dirty 和现存 install。已有 owner 仍活跃时不启动第二套执行者或 ROS/MuJoCo stack。本文不规定旧用户目录；执行者必须在现场确认的 `codex/so101-act-data-0917a` worktree 内工作，记录其绝对路径，不能清理其他 worktree。

唯一 `evidence_root` 是 campaign 配置的绝对路径，也必须与启动入口 `--registered-evidence-root`/payload 的值一致；运行前登记到该机器的任务账本并核对真实文件系统与目录归属。不同机器可以选不同 ROOT，但一个 campaign 开始后不改。当前 ai-station 任务仍沿用已登记的 `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`，在其下创建全新且不存在的 `container-campaign-<UTC时间>-<随机ID>/` run subroot。资格、正式和故障注入各用独立子目录，不移动旧批次。ROOT 只决定新运行路径，不自动改写旧证据的绝对引用；旧证据跨机复核须保留原路径的只读映射或另获批准迁移。ledger 缺失或归属不明则停下。现行账本 `docs/experiments/so101-act-data-experiment-ledger.md` 由执行者追加 checkpoint，记录 ROOT、分支/commit、run subroot、受控身份、RED/GREEN、退出码、耗时、owned/preserved processes。

每个业务步骤定向 RED/GREEN 后提交限定路径、本地 commit 并请求独立审查。执行中的审查由 ai-station tmux 中的 Codex `gpt-6.1-sol` / High 完成；无可用环境就停下等待协调者，审查通过后才继续。本次 Sol 文档修订只做会话内自检，不重新派发 Astra；历史 Astra 结果不适用于新稿。每个 review packet 含准确 SHA/diff、测试 evidence、spec 覆盖和下一边界。不得把等待审查、工具 poll 中断或仍运行的测试当成资源失败。

普通全量 package gate 仅在“代码与镜像集成冻结”和最终修复边界运行；此前只跑定向测试。任何受控源码变化都先重建/source、更新 freeze，并使依赖它的旧运行证据失效。纯配置运营参数调整也不得在同一 campaign 中发生。

### 测试命令约定

执行者先用 `command -v`、`test -x`、`sys.executable`、模块 origin、ROS overlay/package prefix 核对测试环境，把精确解释器设置为 `ACT_TEST_PYTHON`。每次定向、xdist、colcon 测试都新建 scratch；不能复用上一轮 TMP。下面是实际执行模板，`ACT_EVIDENCE_ROOT` 指向上面的登记 root，`ACT_RUN_ROOT` 指向新 run subroot，均须在 ledger 写明后设置。

```zsh
test -d "$ACT_EVIDENCE_ROOT" && test -d "$ACT_RUN_ROOT" && test -x "$ACT_TEST_PYTHON" || exit 1
mkdir -p "$ACT_RUN_ROOT/scratch"
ACT_TEST_RUN=$(mktemp -d "$ACT_RUN_ROOT/scratch/pytest.XXXXXXXX") || exit 1
mkdir "$ACT_TEST_RUN/tmp" || exit 1
export TMPDIR="$ACT_TEST_RUN/tmp" TMP="$ACT_TEST_RUN/tmp" TEMP="$ACT_TEST_RUN/tmp"
"$ACT_TEST_PYTHON" -c 'import os,pathlib,sys,tempfile; a=pathlib.Path(tempfile.gettempdir()).resolve(); b=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,a); assert a == b' || exit 1
set -o pipefail
SECONDS=0
"$ACT_TEST_PYTHON" -m pytest src/so101_demo_py/test/runtime/inference/test_contract.py -q \
  --junitxml="$ACT_TEST_RUN/junit.xml" 2>&1 | tee "$ACT_TEST_RUN/pytest.log"
ACT_TEST_RC=$?
print -r -- "exit_code=$ACT_TEST_RC elapsed_s=$SECONDS scratch=$ACT_TEST_RUN"
test "$ACT_TEST_RC" -eq 0
```

定向步骤替换 pytest 后的精确文件/测试名，不替换 scratch 证明。记录日志和 JUnit；scratch 反读后仅列为删除候选。colcon 使用的每个实际 Python 也须有 origin/tempfile proof，xdist worker 的目录须落在该 scratch。

## 文件结构与依赖

`D` 是 `src/so101_demo_py`，`T` 是 `src/so101_teleop`；下表是完整路径前缀，不是需创建的新 package。现有 Python 模块安装为 `so101_demo`，新代码沿用 `D/src/` 布局。新增文件标为“新”，不得当成现有 CLI。

| 业务步骤 | 文件范围及产物 | 依赖 |
| --- | --- | --- |
| 推理合同与配置身份 | 新 `D/src/runtime/inference/{contract,codec,config}.py`、`__init__.py`；新 `D/config/act/{campaign-runtime-schema.json,inference-contract-schema.json}`；改 `adapters/perception/{yolo_seg,detector_factory}.py` 的配置注入；核对 `parallel_batch/frozen_models.py`、`runtime/parallel_perception_runtime.py` 的常量，不删除其他业务使用；复用 `runtime/parallel_ipc/frames.py` 的 JSON 校验规则，不沿用其 JSON-only envelope | 已审设计及后续用户决定 |
| 共享 YOLO 服务 | 新 `D/src/runtime/inference/{service,executor,client}.py`、新 `D/src/cli/campaign_inference.py`；改 `setup.py`、旧 Broker 当前调用方 | 推理合同 |
| Worker 感知接入 | 改 `D/src/adapters/act/{detector,head_inference_owner}.py`、`runtime/parallel_ros_ports/{perception,observations}.py`；新 `parallel_batch/act_perception.py`；逐项处理本节跨业务调用方清单 | 共享服务 |
| 镜像与 shard 启动 | 新 `D/docker/campaign-{inference,shard}/Dockerfile`；新 `D/src/runtime/container_campaign/{__init__,launch,provenance,paths}.py`；新 `D/src/cli/campaign_shard.py`；改 Worker lifecycle、setup | Worker 接入 |
| Host 生命周期与数据提交 | 新 `D/src/runtime/container_campaign/{owner,service_owner,recovery,resource_log}.py`；改 `act/parallel_collection.py`、`act/parallel_collection_recovery.py`、`cli/mujoco_batch/{composition,broker_lifecycle,worker_lifecycle}.py`、`runtime/parallel_worker_parts/collection.py`、真实 collection CLI/composition | 镜像与 shard |
| 并行资格及正式准入 | 新 `D/src/act/parallel_qualification_report.py`；两个不同业务文件为 `D/config/act/parallel-qualification-schema.json`（最终报告）和 `parallel-qualification-contract-schema.json`（预运行合同）；改旧gate writer/verifier、CLI/spec builder、`T/so101_teleop/unified/{admission,contracts}.py` | 生命周期与证据 |
| 校准/Head Search/live 的生产接线 | 新 `D/src/runtime/container_campaign/{measurement_port,case_port}.py`；改 `act/calibration_production_composition.py`、`act/pick_place_calibration_*`、`cli/act_measure_pick_place_calibration.py`、`cli/act_run_pick_place_validation.py`、Head Search 实际 provider/CLI、`T/so101_teleop/unified/{pick_place_case_owner,act_stack_probes}.py` | 镜像、生命周期与 ROOT/同路径挂载 |
| 集成冻结与容器校准/live 运行 | 前述 provider/入口均已定向 GREEN 后冻结代码/镜像；登记新运行产物，不在运行时补接线 | 全部代码完成 |
| 功能验证、独立 W8、正式采集交付 | `act_collect_parallel`、新 `act_build_parallel_qualification_report`/`act_verify_parallel_qualification`；新 `D/test/runtime/container_campaign/test_end_to_end.py` 和运行证据 | 集成冻结 |

这是一份串行迁移计划。共享服务、容器生命周期和 admission 相互约束，不能各自按旧消息上线；每个 commit 可独立测试，但正式运行只使用最终同一 freeze 的镜像和调用方。

## 推理合同与配置身份

文件：上表第一行；测试新 `D/test/runtime/inference/{test_contract,test_codec,test_config_identity}.py`，并更新 `D/test/runtime/test_parallel_ipc.py`。新测试目录镜像源码，现有测试路径沿用基线。

接口均为本计划新增，参数与结果如下；字典闭合字段取设计 §3.4，不另发第二套格式。代码块的 `...` 仅用于展示函数签名，不是交付空函数的实施步骤；每个签名的实现规则、异常及测试在本节紧接列出。

```python
def validate_inference_request(document: dict) -> dict: ...
def validate_inference_response(document: dict) -> dict: ...
def validate_service_query(document: dict) -> dict: ...
def encode_inference_frame(document: dict, payload: bytes, *, max_frame_bytes: int) -> bytes: ...
def decode_inference_frame(frame: bytes, *, max_frame_bytes: int) -> tuple[dict, bytes]: ...
def pack_rgb(rgb: numpy.ndarray, *, stamp_ns: int, frame_id: str) -> tuple[dict, bytes]: ...
def unpack_rgb(image: dict, payload: bytes, *, limits: dict) -> numpy.ndarray: ...
def load_campaign_config(path: Path) -> dict: ...
def calibration_runtime_hash(controlled_runtime_path: Path) -> str: ...
```

campaign config 唯一 `schema_version=1/kind=ACT_CONTAINER_CAMPAIGN`，外层只含 `schema_version,kind,evidence_root,controlled_runtime,head_service,teacher_service,shard_image,gpu_uuid,qualification_contract`。`evidence_root` 为已登记绝对 ROOT；本配置新增文件引用使用 `path,sha256`，path 指向真实绝对输入路径。现有 artifact 的绝对/相对字段各保留原合同，不作统一格式迁移。镜像引用含 `digest,package_source_sha256,install_sha256`；head_service 与 teacher_service 的 image 必须是同一推理镜像，shard_image 是第二类镜像。每个服务闭合块包含 `image,model,instances,torch_threads,torch_interop_threads,max_inflight_requests,max_frame_bytes,max_image_height,max_image_width,queue_timeout_s,inference_timeout_s`；model 含 `model_id,weights,classes,score_threshold`。帧上限同时限制请求及响应，shape/字节数必须满足设计 §3.3。首份教师配置从基线源码常量迁出，不声称已有教师配置文件：`frozen_models.py` 的权重 SHA256=`f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781`，`parallel_perception_runtime.YOLO_ID=plastic-cup-yolo11n-seg-v1`，`YoloSegDetector._predict()` 的 `conf=0.25`。权重路径从现场实际文件核对，不能凭默认路径生成配置；迁出本身是一次受控源码变更，之后仅改教师运营配置不再改 source hash。

`runtime_config_sha256` 十成员 identity 继续指向一份实际文件的完整 hash：该文件只承载受控执行、采样、head 策略/绑定和 IPC 规则，不用忽略字段后的 hash 冒充文件 hash。教师权重/类别/分数阈值、教师线程配置和两服务实例数属于运营配置；head的模型、分数门槛、Torch线程/interop线程及torch/ultralytics版本必须从当前Head Search绑定派生并逐项相等，不能跟着教师配置变更。`IMAGE_TAG/PINS`迁为两类镜像的 build manifest 及 digest，不作为源码内教师运行选择器；依赖或image执行代码变化仍是受控变化。完整 campaign config 另存 hash 作同 campaign 与故障清理溯源；ROOT 是路径配置，不增入十成员 identity，不能作为跨campaign模型QUALIFIED条件。

上述head绑定规则用于已有绑定后的测量、live和采集；首轮尚无绑定时，只有下述受限measurement kind从批准measurement plan/candidate policy派生head配置，不能以该例外运行正式搜索或抓放。`qualification_contract`键始终存在，仅W8资格为预运行contract引用；测量/live/W1/W2为null，正式资格证据由独立`qualification_receipt`传入，不塞进此键。结构校验不等于加载所有角色：measurement只核对/加载head实际运行配置和权重，不因未使用Teacher的ready/权重文件缺失阻断首轮测量。

- [ ] 为`YoloSegDetector`增加显式`score_threshold`构造参数，经`DetectorFactoryOptions`注入`_predict(conf=...)`，验证finite且在[0,1]。ACT服务必须显式传值；head传绑定值。共享类的其他业务保留其当前0.25默认行为，不改其效果；ACT不读取`frozen_models/YOLO_ID`作为硬拒绝条件。新服务的model ID、weights hash、class map均来自冻结配置，实际权重反读hash一致才ready。
- [ ] 新`D/test/runtime/inference/test_model_configuration.py`覆盖首份常量迁出、教师0.25与另一合法阈值确实进入predict、换合法权重/model ID无需改源码、head与教师不串配置。head模型/版本/线程不等于绑定时报`HEAD_SEARCH_RUNTIME_VERSION_DRIFT/HEAD_SEARCH_THREAD_DRIFT`；这些证明移到head服务子进程，不因Worker不再加载Torch而删掉。macOS及其他detector调用方默认行为的定向回归必须保留。

- [ ] 写以下 RED：旧 `broker_call` 字段、额外 lease/token、错误版本、重复 JSON key、NaN、非法 RLE、缺 mask、跨类别和过大帧被拒绝；RGB 通道/像素原样往返，非 C-contiguous、非 uint8、非法 shape/byte_length、截断帧、额外 payload、非法 header length 和超限 body 均拒绝。收到 length prefix 后先检查总帧上限，不能先分配声明大小再拒绝。

```python
import pytest
from so101_demo.runtime.inference.contract import validate_inference_request

def test_authority_fields_are_not_an_inference_contract():
    with pytest.raises(ValueError, match="INFERENCE_REQUEST_INVALID"):
        validate_inference_request({"schema_version": 1, "kind": "broker_call",
                                    "request_id": "r", "lease": {}, "payload": {}})
```

- [ ] 跑三个新测试文件确认 RED 是实际断言/新模块未实现，而不是缺 ROS underlay 或错误解释器。
- [ ] 实现闭合校验及唯一 binary envelope：`[u32be body_length][u32be header_length][UTF-8 JSON header][payload]`，body_length 含 header_length 的 4 字节、JSON 和 payload。请求 payload 是 RGB8，响应和 ready/health query 的 payload 为空；640×480×3 恰为 921600 字节。复用 canonical JSON 的重复键/有限值检查，不直接复用旧 JSON-only `encode_frame`。header/shape/长度先校验，RGB 不压缩、不 pickle、不写 `.npy` 文件、不做传输 SHA；局部原始证据仍照现有合同落盘。
- [ ] 写身份回归：迁移完成后改Teacher score/weights/model ID/实例数时`source_sha256`、controlled runtime hash和image digest不变、campaign hash变化；改R6/head绑定/采样时受控身份必变。十成员identity、21核心字段不变，旧ACT格式直接拒绝。
- [ ] 定向GREEN；ACT新调用方不得使用`_BROKER_COMPATIBILITY_FIELDS`或`Snapshot.start_event_id/start_event_type/start_identity`，这些旧合同仅在另一业务保留。复用 JSON 校验规则，不复用 compatibility envelope；不删除Coordinator控制面。review通过后只commit限定路径。

### 可配置 ROOT 与同路径挂载

这一节替代跨 Host/容器的 artifact 路径迁移。基线校准 sample、bundle_root、offline result 等文件包含绝对路径；把所需目录按同一绝对路径挂进容器后，Host 与容器 reader 可直接读同一文件，无需转换约 25 个 writer/schema/reader，也不因容器化升级这些业务的 SCHEMA_VERSION。

新增 `runtime/container_campaign/paths.py` 只处理启动路径与挂载清单，不提供新的通用 artifact resolver：

```python
def validate_registered_evidence_root(config_root: str, payload_root: str,
                                      *, registration) -> Path: ...
def make_campaign_paths(root: Path, run_id: str) -> dict: ...
def build_role_mounts(role: str, *, owned_root: Path, approved_inputs: tuple,
                      socket_roots: dict, config_paths: tuple) -> tuple: ...
```

- [ ] 新 `D/test/runtime/container_campaign/test_paths.py`：两台机器分别使用不同绝对 ROOT，新 run 的 Host/shard 得到相同绝对路径；ROOT 与登记/payload 不一致、相对 ROOT、未知归属、重用已有 run 拒绝。验证 ROOT 不进入十成员模型 identity，但完整 campaign config hash 记录它。
- [ ] Host 从 ROOT 派生 run/wave/shard/measurement/live 私有目录。shard 仅挂自己的证据目录 `<absolute>:<same-absolute>:rw`；校准样本、bundle、资格原件等只挂确需的已批准文件/目录，源与目标同路径且只读。不可挂整个 ROOT 供 shard 写，也不能让它看见其他 shard 或改 Host journal。服务不挂 shard 证据目录。
- [ ] 启动入口反读真实路径、归属、输入 hash 和逐角色挂载清单；现有业务 reader 的范围/hash/QC 验证保留，不在内部重新做 campaign resource authority。已存在的相对引用仍用原业务基准，绝对引用不改写。image 内 source/install 与短 socket 可用固定 `/act/source`、`/act/install`、`/act/ipc`，不要求证据只出现 `/act/...`。
- [ ] 使用真实校准/bundle/offline/QC/seal writer 与 reader 做同路径挂载回归：Host 与容器读取同一 bytes/hash，绝对引用和原有相对引用均保持原合同。错 shard、只读输入被写、漏挂依赖目录、变 hash、假 memo 拒绝；不新增双视角格式、不字符串替换 receipt、不让 Host QC 因 memo 命中省掉原始验证。
- [ ] ROOT 改变只用于下一次新运行。旧证据跨机器读取时，先核对其原绝对引用并建立必要的只读同路径映射；本计划不授权旧 ROOT 移动、自动 rewrite 或 reader 兼容升级。缺映射就报告具体文件，不放宽 reader。定向 GREEN 与审查后再接镜像步骤。

## 共享 YOLO 服务

文件：第二行；新增 `D/test/runtime/inference/{test_service,test_client}.py`。`campaign_inference` 为新 console script，接受 `--config <已批准只读配置路径> --socket /act/ipc/inference.sock`；head/Teacher 角色从冻结配置选择，不能由请求换模型。两个角色共用同一镜像与 wire contract，各有自己的容器、实例池、队列和权重/阈值。

```python
class InferenceService:
    def __init__(self, *, config: dict, executor_factory, monotonic_ns, generation: str): ...
    def submit(self, request: dict, payload: bytes, connection) -> None: ...
    def query(self, request: dict) -> dict: ...
    def close(self) -> dict: ...

class InferenceClient:
    def __init__(self, *, socket_path: Path, service_generation: str, max_frame_bytes: int): ...
    def infer(self, request: dict, payload: bytes) -> dict: ...
    def query(self, kind: str, request_id: str) -> dict: ...
```

- [ ] RED 覆盖两角色同一合同、实例数 3 可加载、无 `1/2/4` 拦截、CUDA 不可用 fail closed、一实例同时只执行一请求、子进程退出不自动重启/缩容。服务不读取 wave/lease/context，不 import Coordinator/admission。
- [ ] 接收缓冲、queued、running、responses_pending 共同有界；先预留接收槽再读取大 payload，不用无界接收队列绕过 `max_inflight_requests`。慢客户端占槽、队列满、部分帧断连、pending reply 背压均有定向测试；控制 ready/health 帧也受大小和连接上限约束。
- [ ] 仅在请求处于接收/排队/执行/待回复时保存 request ID，拒绝同时重复请求。client 保证 campaign 内唯一 ID 且不自动重试；完成并释放后不保存全历史 seen-ID，不承诺跨断连的 exactly-once 或持久幂等。局部 attempt/结果不会因晚响应重新生效。
- [ ] fake executor 以显式 Event 控制完成：过期 queued 不执行；running 超时可回复一次但仍占运行槽，真实计算完成后才释放。断连不等于 CUDA 已取消，迟到响应只审计不提交；响应连同 RLE 超过帧上限时返回明确失败，不能截 mask。
- [ ] 实现父进程连接/队列与 `multiprocessing.get_context("spawn")` 执行器。父进程不创建 CUDA context；子进程设置 Torch threads、校验权重/UUID/绑定版本后加载一模型。所有配置实例 alive 且 `loaded_instances==configured_instances` 才 ready。
- [ ] 实现八种 outcome 与唯一 `service_ready/service_health` 查询。health 只报告当前状态，不增加 service_state、累计接纳计数或 drain/takeover 证明；Host 崩溃直接结束 campaign。定向 GREEN 保存真实 Unix socket binary codec 测试；无 CUDA 环境只给静态/模拟证据，真实 GPU ready 留给镜像集成。限定 commit 和 checkpoint review。

## Worker 的 head 与教师感知接入

文件：第三行；新 `D/src/adapters/act/head_ipc_detector.py`、`D/src/parallel_batch/act_perception.py`、`D/test/adapters/act/test_head_ipc_detector.py`、`D/test/parallel_batch/test_act_teacher_perception.py`。接口保持`HeadRgbDetector.detect/reset`的本地业务形状；新增backend如下。

```python
class HeadIpcDetector:
    def __init__(self, *, client: InferenceClient, context_probe,
                 policy, monotonic_ns): ...
    def detect(self, frame, query): ...  # 返回 core.detection 的当前 DetectionBatch
```

`context_probe()` 返回当前 session/attempt/reset/lease/worker generation/sequence 的闭合局部映射。它不传给服务；Worker 以 request ID 保存不可变关联，响应到达后与当前映射、源帧身份、局部原始证据关联和 service generation 一起核对。`frame/query` 使用现有 `DetectionFrame/DetectionQuery`，RLE 解码为原 mask，再交 `HeadRgbDetector`；shared 服务不生成 track ID。head 一次 detect 只允许一个未决请求，deadline=`min(RGB 序列化前 monotonic 起点+批准推理预算, search_deadline)`，检测完成后仍做现有停稳新帧/freshness/连续锁定检查。

`HeadIpcDetector`使用冻结的`query_class_id`↔本地字符串类别映射：`plastic_cup`查询只接受受控class map中的`plastic_cup/cup`，恢复到当前`DetectionCandidate`的字符串类别，不把整数模型class ID直接交给`HeadRgbDetector`。query/响应类别不一致、未知类别或class map hash不符拒绝，不能靠改名接纳非杯目标。新增class映射正负例及mask不变测试。

### 迁移范围与另一业务的保留接口

| 文件 | 本计划处理 |
| --- | --- |
| `runtime/parallel_ros_ports/perception.py` | ACT composition使用新`ActTeacherPerceptionPolicy`及新InferenceClient，不构造`grounded_model_id=GROUNDED_ID`；通用验证composition仍用原policy。两个构造路径按业务入口选择，ACT没有可切回旧Broker的开关。 |
| `parallel_batch/act_perception.py`（新） / `parallel_batch/perception.py` | 新类只请求YOLO，复用现有PoseAdmissionLatch/R6与提交逻辑；原类和模块级`decide()`保留另一业务的Grounded回退。不同业务类，不是同业务多版本或alias。 |
| `cli/mujoco_batch/{request,outcome,provenance,rpc_proxies}.py` | ACT请求改走新闭合wire，映射outcome和来源；Coordinator lease/start bookkeeping仍只在本地。通用验证现有transport不改语义，按真实entry tests核对隔离。 |
| `parallel_batch/contracts/identity.py`、`runtime/parallel_ipc/broker_transport.py` | 保留macOS/通用验证现行类型和transport；ACT只借本地Worker关联类型，不调用旧broker_call或兼容Snapshot。新InferenceClient不复用旧BrokerTransport的接收分支。 |
| `parallel_batch/broker.py`、`runtime/parallel_perception_runtime.py`、`cli/parallel_perception_broker.py`、`docker/parallel-perception/` | 保留给另一业务；ACT启动与Worker不再使用它们，不删Grounded构造要求，不把旧镜像当新角色image。常量初值只供一次迁出/build来源记录。 |
| `runtime/macos_two_worker_broker_port.py`及对应macOS composition | 保持现行BrokerTransport/Snapshot、MPS且无CPU fallback；普通定向回归证明没有被ACT迁移破坏，不以Mac测试冒充CUDA W8。 |

RED/GREEN须扫描ACT实际production imports/启动argv，证明没有进入旧Broker/model构造；另一业务的当前contract tests仍通过。删除旧compatibility字段的要求限于ACT调用方与新服务，不能全仓删除仍在使用的字段。

### Wire outcome、内部 outcome 与 attempt 终态

`act_perception.py`新增`map_inference_outcome(response: dict) -> ModelOutcome`，保留wire reason作本地诊断；`ActTeacherPerceptionPolicy`取消回退，但沿用现有infra/timeout→INVALID、模型拒绝/确定性错误→FAILED归类。公共`ModelOutcome.QUALIFIED`不改名，以免破坏macOS/通用验证；它在此只是可读候选的中间值，不是模型资格或运动许可。

| wire / 本地结果 | 内部ModelOutcome | ACT Teacher attempt的下一步/终态 |
| --- | --- | --- |
| DETECTED | QUALIFIED | 仅候选可读，进入本地RGB-D/TF/R6及PoseAdmissionLatch；只有latch接受后CONTINUE，不直接SUCCEEDED |
| NOT_DETECTED | NORMAL_REJECTION | YOLO-only用尽，Teacher FAILED；不请求Grounded |
| INPUT_INVALID | INFRA_ERROR，保留INPUT_INVALID原因 | attempt INVALID，记infra；不伪装物理失败 |
| QUEUE_FULL | INFRA_ERROR，保留QUEUE_FULL原因 | attempt INVALID，记infra；不隐式重试/回退 |
| QUEUE_TIMEOUT | QUEUE_TIMEOUT | attempt INVALID，沿用当前infra归类 |
| INFERENCE_TIMEOUT | INFERENCE_TIMEOUT | attempt INVALID，沿用当前infra归类；迟到响应不能恢复attempt |
| MODEL_ERROR | MODEL_ERROR | 确定性结果错误，Teacher FAILED；不回退 |
| INFRA_ERROR | INFRA_ERROR | attempt INVALID，记infra |
| 本地R6/pose准入拒绝 | NORMAL_REJECTION | Teacher FAILED；若latch.requires_adjudication则沿用INFRA_ERROR/INVALID，不能抹掉停止安全停点 |

本地旧generation/取消仍按既有CANCELLED处理，不新增wire outcome。head端只把失败交给Head Search自己的搜索/时序状态，不直接改Teacher终态。数据QC仍独立决定VALID/INVALID；有有效录制的Teacher业务FAILED可以是data VALID，但不自动进入成功训练集合。W8全部40 scene保持分母，任何infra INVALID触发资格的零infra失败，不能排除后重算成功率。

- [ ] 参数化测试逐一喂八种wire及本地R6/adjudication拒绝，断言内部值、reason、attempt终态、无Grounded调用和分母计数。DETECTED但R6拒绝不得CONTINUE，latch接受也不得伪造Teacher物理SUCCEEDED；晚响应/取消保持现有停止语义。

- [ ] RED：同一 RGB 像素从服务返回 raw batch 后，本地去重/碎片/track 行为与冻结基线相同；模型 factory 在 Worker 未调用，track 不在服务。显式构造旧 attempt/reset/wave、迟到和重复响应，均不进入锁定或 Teacher。
- [ ] fake clock 给 RGB 序列化/发送增加 40 ms，queue/inference/decode 分别增加时间，证明完整时长包含所有部分。原始像素与 source stamp 不变，不把发送时刻写成图像采样时刻；deadline 后 raw batch 合法也拒绝，默认 candidate policy 不可冒充批准值。
- [ ] 实现 IPC backend，`HeadInferenceOwner` 保留本地异步调度、fault/retirement/stop 监督，只把模型拥有权移出；reset 清本地 track/mapping，不在服务发 reset-wave 操作。禁止 Worker 端 import/load YOLO 模型。
- [ ] ACT入口改用`ActTeacherPerceptionPolicy`；canonical candidates完整mask、RGB-D/TF skew、R6和z-clip保留。上述映射进入真实Worker results，不能只测纯函数。
- [ ] GREEN：head timing/stop/safety、`test_act_teacher_perception.py`、ACT入口无回退，以及另一业务现有fallback/macOS定向回归。benchmark与其他模型业务不纳入删除范围。审查后限定commit。

## 两类镜像与同路径挂载

文件：第四行；新增 `D/test/runtime/container_campaign/{test_launch,test_provenance}.py`、`D/test/cli/test_campaign_shard.py`。只构建 `campaign-inference` 与 `campaign-shard` 两类镜像，来自同一 source/install freeze；head 与 Teacher 共用推理 digest，分别启动独立容器。权重和配置只读外挂。`campaign_shard` 为新 console script，接受 `--spec <已批准只读 spec 路径>`。

```python
def build_container_argv(*, role: str, image: dict, gpu_uuid: str,
                         host_paths: dict, container_name: str, uid: int, gid: int) -> list[str]: ...
def read_container_provenance(container_id: str, *, docker_runner) -> dict: ...
```

- [ ] RED：argv 不含 `--privileged`、Docker socket、`--network host`、`--gpus all` 或外部源码 override。三个运行角色只映射 admission 选中的 UUID；head/Teacher image 不同、未知 role/GPU/mount 拒绝。shard spec 使用 Host 派生的真实绝对证据路径，不作容器路径翻译。
- [ ] 实现 source/install/dependency/submodule manifest 与 Git 元数据入镜像；bootstrap `/act/source`、`/act/install`，启动反读实际解释器/module origin/package prefix、digest 和源码/安装 hash。不能只凭 LABEL 或 commit 字符串证明 provenance。共用推理镜像的 Torch/ultralytics 等依赖必须满足 head 绑定，不因合并镜像放宽版本。
- [ ] 挂载使用上一节唯一清单：shard 私有证据目录同绝对路径 rw，批准输入同路径 ro；head/Teacher 服务仅挂各自配置、权重、日志/临时目录和 socket，不挂 RGB staging 或 shard 证据。shard 连接两个短 socket `/act/ipc/head`、`/act/ipc/teacher`，服务各用 `/act/ipc:rw` 发布自己的 socket。日志/临时目录由 Host 登记，不用镜像层存证。
- [ ] 固定 non-root uid/gid、只读 rootfs；以执行用户 UID 做真实权限测试，证明 shard 可写自己的证据、可读批准输入、不能写输入/Host journal或读其他 shard；服务不能读任何未挂载证据。RGB 只从 socket 到模型，不复制到共享文件目录。
- [ ] shard 私有 network namespace、唯一 ROS Domain/namespace、MuJoCo session；Host→Worker 控制经 bind-mounted Unix socket，ROS/DDS confined，不用 Host ROS graph 跨容器通信。child registry 记录 container ID/启动身份/角色/generation，不把 Host `Popen.pid` 当内层 ROS ownership。
- [ ] 完成下述 PID/heartbeat/stop 合同与真实 namespace 测试才视为生命周期接通；禁止 `--pid=host`。GREEN 后在 ai-station 构建两类镜像，保存 digest/source/install/依赖 pin；无动作 ready 检查覆盖 GPU UUID/CUDA、EGL、MuJoCo 场景、controller、七关节反馈、双 RGB 新鲜度、socket/挂载和无未知 goal。Recorder 按 case 检查，不变成 Teacher ready 门禁。失败保留日志，不起宿主替代 stack；review 后 commit。

### 私有 PID namespace 的存活与停止证明

改 `T/so101_teleop/unified/{bridge,ros_child,pick_place_case_owner,act_stack_probes}.py` 的ready/watchdog/stop消费者，新 `D/src/runtime/container_campaign/process_identity.py` 和 `T/test/unified/test_container_child_ownership.py`。只迁移ACT容器路径，保留其他宿主业务的实际合同，不给正式ACT留第二入口。

Host持有`ContainerOwnerKey(container_id, docker_started_at, image_digest, launch_generation)`；容器内ready/stop证据持有`ProcessOwnerKey(pid, pgid, started_ticks, argv_sha256, environment_sha256)`。两个不同类型不得相互替代。Host经Docker inspect读回固定container ID/启动身份，并把内层receipt绑定到launch generation、独占控制socket及内层process key；内层进程身份只能在该容器namespace内核对。跨namespace不比较数字PID，也不以Docker CLI进程退出证明容器退出。

容器内watchdog不读取`SO101_CHILD_WEB_PID`或`os.kill(HostPID,0)`。Host经原控制socket发送闭合heartbeat `kind=owner_heartbeat,generation,sequence,sent_monotonic_ns`；shard用自身接收单调时间及冻结owner失联预算监督，拒绝旧generation/回退sequence，断连或到期只停止接纳并按现有controller撤销/stop合同收敛。预算取现行已批准owner/dead-man配置，不猜默认值；这不是推理服务消息或resource authority。Host死亡时内层stop receipt持久化在私有证据根供旧 campaign 终止/清理反读，不供 Host 接管。

ready包含内层process key，不再等于Host Popen.pid；stop receipt须证明同一generation/goal/controller已停止、内层ROS子进程已退出/graph清空。Host再检查整个container及其进程退出，才释放该launch的socket/Domain与GPU使用。容器被强制杀掉只能记infra并由Host证明进程确实退出，不能伪造controller成功停止。全campaign GPU lease仍由统一finish处理。RED/GREEN覆盖PID不同及数字碰撞、旧heartbeat、Host死亡、CLI退出但container存活、controller未停、旧stop receipt与新launch冲突；任一不确定保留fence，不进入下一wave。

## Host campaign、wave 与数据提交

文件：第五行，并改 `D/src/adapters/act/parallel_collection_results.py`、`act/result_store.py`、`runtime/act_fixed_collection_composition.py`、`cli/act_collect_parallel.py`、`T/so101_teleop/unified/{compose,ports,admission,contracts,bridge}.py` 的实际接线和child登记；新 `D/test/runtime/container_campaign/{test_owner,test_recovery}.py`、更新 `D/test/act/test_act_parallel_collection_recovery.py`。

```python
class ContainerCampaignOwner:
    def __init__(self, *, admitted_context, config: dict, root: Path,
                 launcher, coordinator, verifier, monotonic_ns): ...
    def run(self, manifest: dict) -> dict: ...
    def stop_dispatch(self, reason: str) -> None: ...
    def close(self) -> dict: ...

class GenerationCleanup:
    def __init__(self, *, generation: str, stop_controller, retire_children, clock): ...
    def run(self) -> dict: ...
```

- [ ] 先迁移唯一生产调用链。基线CLI取不存在的`act_collection_context`、字典spec及`start(spec, request)`不符合实际接口，必须删除，而不是让fake service兼容它。`compose_services()`只调用一次；其中`act_workload`和已验证的source/proposal/resource配置产生启动输入，尚未取得admitted context。新增纯`prepare_collection_operation(arguments, *, services) -> OperationSpec`替换原builder的context循环依赖；使用真实`OperationSpec(command_id,domain,kind,payload,runtime_id,execution_generation,deadline_ns)`，domain取VALIDATION，epoch/runtime/owner取composition，generation/deadline取统一服务持久分配与已批准租约规则。容器 campaign 不支持 Host 崩溃后的 resume；现有 resume 入口对该 campaign kind 明确拒绝，不影响另一业务的既有恢复接口。
- [ ] CLI执行顺序为解析/受限输入反读→上述builder→`act_workload.start(spec, allow_existing=False)`→得到`AdmittedCampaignContext`→用同一composition的launcher/coordinator/verifier创建`ContainerCampaignOwner`→`owner.run(manifest)`→`owner.close()`→仅完整cleanup证明成立时`act_workload.finish(context, cleanup_confirmed=True)`。`start()`只表示准入，不能将其返回值打印为采集完成；close异常/未知controller保持fence/GPU lease并报告block。通过进程级`finally`收尾，不在异常分支无条件传True；新容器 campaign 只准入全新 run，不以 allow_existing=True 跳过旧 owner/cleanup fence；崩溃清理不调用 workload.start 恢复工作。
- [ ] 闭合两个registry职责：启动entry一次性冻结并保留`worker_count`个逻辑Worker slot（独占Domain/namespace/controller），context绑定其不可变hash；两共享服务和每wave/每case实际容器实例进入另一个持久launch registry，以role/slot/wave/launch generation/container key关联。新MuJoCo session/socket在实例receipt中唯一，不能冒充旧`ActChildLaunch`。同步迁移admission的`children`/context字段、`reserve_many`、bridge和`finish`：固定slot数不等于累计实例数；finish同时核对原slot hash与全部owned实例终止证明，再原子释放。只在上一实例停止已证后复用预留slot，不每wave重新做resource binding，也不修改context hash掩盖资源重用。故障清理反读这两份 registry，未知实例停下，不接管旧实例。
- [ ] `test_act_parallel_collection_integration.py`从真实CLI `main()`进入生产composition、OperationSpec builder、SQLite admission、owner、finish，不注入`service_factory/context_factory`、fake start或fake owner；允许替代Docker/NVML/ROS外部I/O边界。覆盖 W1/W2 功能、W8 资格、formal 与容器 resume 拒绝：至少两wave的launch/run/finish真实代码均运行，错误输入在任何spawn前拒绝，cleanup失败不释放，重复finish幂等，第二wave/新session不破坏slot hash。真正容器/真实GPU的同链验收留至运行gate，不将这些替代测试称为runtime PASS。
- [ ] RED：两个 20 项 wave 只启动两共享服务各一次，shard 每 wave 各新建；所有 shard ready 前没有 lease。真实并行入口不是 `FixedActCollectionCampaign.run()` 的串行 `for scene` 伪并发；barrier 测试证明八 shard 的执行窗口重叠。
- [ ] 实现 Host 先原子无覆盖写 index/冻结 wave，再按设计状态图运行。基线 batch composition 的 Broker start/finally-retire 改为 campaign owner 拥有；batch/wave 只借用已验证端点，不拥有服务关闭权。现有模块名称不加后缀，不保留可进入正式路径的第二套兼容实现。
- [ ] W8资格采用确定性slot预留：每波20项按manifest顺序，将前16项的相邻两项分别预留给w00至w07；slot只能先顺序消费自己两项。余下4项在对应Worker完成两个terminal后，才从共享有序队列按lease发放顺序拉取。索引同时冻结assignment，20项每项只派一次；不得把慢Worker的预留项抢给快Worker。实现`reserve_qualification_scenes(scene_ids: tuple, worker_ids: tuple) -> dict`，新`D/test/act/test_qualification_dispatch_reservations.py`用八个受控Event模拟极快/极慢Worker，证明每Worker均有两terminal、surplus恰好4、无重复；若预留Worker退出本次资格失败，不改分配补资格。正式采集不套用该两项预留规则。
- [ ] 每 shard 顺序处理一 case：一次 reset→Teacher+record-only→Teacher 退出且停止已证→bag 关闭→offline/QC→seal→Host verify/commit→下一 case。处理 timeout 读取冻结 `min(1200 s, lease 剩余-60 s)`；少于当前 `MIN_PROCESSING_S=60 s` 不启动处理，数据 INVALID，Teacher 结果不变。finalizing/lease deadline 均来自真实租约，不用整 wave 预算代替。
- [ ] 沿用当前 seal 的文件表及 artifact 引用，容器与 Host 看到同一绝对 shard 根；Host 在登记范围内独立反读完整 hash/QC，再写 result commit/wave journal。不改校准/bundle/offline/QC 文档的既有路径格式。没有 seal+commit 的文件、迟到 seal、资格/surplus 均不得被训练目录扫描捡入。缺片/Recorder 失败与 QC INVALID 必须显示 Teacher 独立结果未被覆盖。
- [ ] 故障注入以 private sandbox 执行：单 case 未检出/失败，其他 case 继续；数据丢消息/10 Hz gap/QC 失败不能撤销 Teacher。共享服务失效或实例退出结束 campaign；磁盘见底、实际数据缺失或服务故障先停新 lease，在途 Teacher 只按自身完成/停止合同收尾，等待人工。CPU/GPU/RAM/RTF/吞吐观测值本身不触发停派或资格失败；OOM、设备错误等真实故障另行记录，不伪装成观测限额。
- [ ] 正式 shard crash：已开始 case 记 infra，未开始 lease 回收，已 commit 不重做；剩余 shard 可收尾当前 wave，下一 wave 前恢复八 ready。W8 qualification 任意 shard/Host crash 判资格失败，不 resume 或拼接。
- [ ] cleanup 为 `generation-scoped/single-flight`：同一 generation 只有一次收敛执行，其他调用等待同一结果；证明 controller 停止、容器退出及 owned Domain/socket/GPU 释放后才发下一波。旧 generation 结果不能清新资源；未知 owner/goal 停下，禁止 broad pkill。
- [ ] Host 崩溃测试：shard heartbeat 到期按既有停止合同收敛；旧 campaign 终止，保留 index/journal/commit/partial。协调者只反读旧 launch registry、controller/内层 stop receipt 与 Docker 实际退出，按 generation 清理自己拥有的服务和 shard。未知进程或停止未证保持 fence，报告人工停点；不查询零在途、不接管服务、不恢复旧 ID。获准新开 campaign 后也必须先有旧资源终止证明，再用新 run/ID/服务。已 commit 不自动重采；新 manifest 如何补未完成项另行批准。
- [ ] 定向 GREEN，review 精确 dirty/测试/failure receipts，commit 本步骤。wave 结果分母始终来自冻结清单，业务 FAILED 不重新安排。

### 资源日志与磁盘停派

新增 `runtime/container_campaign/resource_log.py`，复用已有观测接口记录实际可用值；不新增统一 14-metric registry、闭合 raw schema、reducer、全窗口 coverage 或 service drain 事件。观测日志不是资格 authority，不扩充 21 项测量。

```python
def read_disk_free_bytes(evidence_root: Path) -> int: ...
def check_disk_dispatch_guard(free_bytes: int, *, approved_floor_bytes: int) -> bool: ...
def append_resource_log(path: Path, *, monotonic_ns: int, observed: dict,
                        missing: dict) -> None: ...
```

- [ ] Host 按已有观测周期写低频日志：CPU/GPU/RAM、真实文件系统空闲空间、已导出的 RTF/Recorder 队列/处理耗时/吞吐，有什么记什么，并记录来源、单位与缺测原因。不为取得齐全字段新增 profiler/生产者；不把 null/0 当实测值。GPU 信息读取选中的 UUID，时间间隔用单调时钟。
- [ ] 每次发新 lease 前检查 ROOT 所在真实文件系统的磁盘空间，并复用已批准空间下限。若无既有下限，只以无可用块或 ENOSPC 为停点，不引入示例 50 GiB 或资源预算。检查失败/无法证明可写空间也停止新派发并报告读取错误，不能当作零或无穷大。已有周期检查可以提前停派。
- [ ] 磁盘触发保存实测空间、时间、规则/错误和 generation 日志，调用 owner.stop_dispatch；在途 Teacher 按自身完成/停止合同收尾，保留 partial，不删除旧证据腾空间。CPU/GPU/RAM/RTF/吞吐极端或缺测本身不触发资格失败/停派；实际 OOM、设备错误、服务退出、Recorder 丢失由既有故障合同处理。
- [ ] 四项硬门槛直接消费已有原始 bag、逐帧时间戳、独立 QC 与 Teacher 物理结果/commit receipts，沿用已批准 Recorder lossless、10 Hz 连续性、QC 合格率、物理成功率规则。不得用资源日志、内存 PASS、平均 gap 或丢弃 FAILED/INVALID 分母代替；不另写通用 metric reducer。
- [ ] 新 `D/test/runtime/container_campaign/test_resource_log.py`：不同 ROOT 的 statvfs、空间见底/ENOSPC/读取失败停止新 lease、不改 Teacher 终态；NVML 缺测和高利用率只记日志；现有质量测试证明原始缺源/单帧 gap/丢失/QC 仍拒绝资格。定向 GREEN 和 checkpoint review 先于集成冻结。

## 独立八 Worker 报告与正式启动准入

文件：第六行；新 `D/src/cli/act_build_parallel_qualification_report.py`、`act_verify_parallel_qualification.py`，新 `D/config/act/{parallel-qualification-contract-schema,parallel-qualification-schema}.json`、`D/test/act/test_parallel_qualification_report.py`，改 `D/test/act/test_act_eight_worker_qualification.py`、`D/test/cli/test_act_parallel_collection_integration.py`、`T/test/unified/test_act_campaign_admission.py`、`setup.py`。

```python
def build_parallel_qualification_report(contract_path: Path, campaign_root: Path,
                                        output: Path, *, registered_root: Path) -> Path: ...
def verify_eight_worker_qualification(qualified_path: Path, payload: dict) -> bool: ...
```

report 唯一外层字段：`schema_version=1,kind=ACT_PARALLEL_COLLECTION_QUALIFICATION,status=QUALIFIED,qualification_run_id,worker_count=8,controlled_identity,contract,campaign_index,waves,quality,resource_logs`。新报告的 artifact ref 为 `path,sha256`，运行证据的绝对路径必须位于登记 ROOT 的对应资格 run，规则输入按批准配置反读，waves 恰好两 ref；不改已有 index/seal/receipt 的引用格式。controlled_identity 含 `source_sha256,runtime_config_sha256,collection_config_sha256,contact_policy_fingerprint,image_source_install,gpu_uuid`，从冻结实物读回；image_source_install 记录两类镜像，并验证 head/Teacher 共用 digest。quality 只含 `recorder_lossless,frame_continuity,qc_valid_rate,teacher_physical_success_rate`，每项给出既有规则引用、原始证据引用及独立结果。resource_logs 是可用日志引用数组，允许为空；独立 verifier 读取资源日志失败/缺测只报告，不单独否决资格，也不能用日志替代质量来源，不生成资源 reducer/coverage/通过线。报告本身及权威质量证据的 hash 仍须成立。

预运行合同与最终报告是两个不同业务文件，不是同业务两个版本。预运行唯一 `schema_version=1/kind=ACT_PARALLEL_COLLECTION_GATE`，闭合字段为 `schema_version,kind,qualification_run_id,worker_count,scene_manifest,functional_manifest,formal_split_manifest,controlled_identity,quality_rules`。quality_rules 恰为上述四项，分别引用现有 QC/业务规则及 hash，规则的具体字段/阈值沿用实际业务合同，不增加泛化 source/unit/window/reducer/purpose 字段表。generator 用现有 verifier 从完整原始证据与全部 40 场景分母重算；单次 gap 不可被平均值/p99 掩盖，业务 FAILED/INVALID 不排除。规则或原始质量来源缺失只定位该缺项，不能补猜阈值。磁盘停派与资源日志不塞进质量合同，也不申请 CPU/GPU/RTF 预算；合格才无覆盖写 QUALIFIED。

- [ ] 明确替换`act/parallel_collection.py`的旧`create_qualification_contract()`与`require_collection_mode()`、`QUALIFICATION_KINDS`以及spec builder的旧调用；不再生成SINGLE_WORKER/TWO_WORKER/EIGHT_WORKER或只有scenes=40的gate。W8只使用上述gate，W1/W2使用另一业务唯一`schema_version=1/kind=ACT_COLLECTION_FUNCTIONAL_RUN`，闭合字段为`schema_version,kind,run_id,worker_count,scene_manifest,controlled_identity`，worker_count只能1或2、manifest固定同八scene；功能报告不能被formal当W8资格。两类mode在纯builder和真实admission共同测试，未知kind拒绝，无alias/版本dispatcher。

- [ ] RED 直接沿用现有八 Worker 测试的 14 项 live fixture，改断言为必须拒绝。新增真实磁盘 index、40 refs、两波 journal、每 Worker lease 与 commit/receipt fixture；fixture 用当前 writer 构造，不能 mock verifier 返回 True。

```python
import pytest
from so101_demo.act.parallel_qualification_verifier import verify_eight_worker_qualification

def test_self_declared_qualification_is_not_evidence(tmp_path):
    report = tmp_path / "qualified.json"
    report.write_text('{"status":"QUALIFIED","worker_count":8}')
    with pytest.raises(ValueError, match="EIGHT_WORKER_QUALIFICATION"):
        verify_eight_worker_qualification(report, {})
```

- [ ] 实现独立磁盘重算：40 scene 精确/不重叠、两20项 wave、八 worker 每波≥2 terminal、零infra/retry/resume、唯一场景结果和用途、source/image/config、GPU/EGL、cleanup、原始质量/QC。缺原始证据、跨 run、删一波、少一个 Worker lease、伪造聚合状态或篡改 receipt 都拒绝；不再调用抓放 9+5 validator 充当 W8。
- [ ] 不把新字段直接加进被多个业务继承的`_ACT_PAYLOAD_KEYS`。先拆出闭合公共键，再分别定义collection、pick-place validation和diagnostic payload集合，逐kind选择；collection新增`registered_evidence_root,campaign_config_path,campaign_config_sha256,qualification_receipt_sha256`，validation新增前三项而保留preparation receipt，资格receipt置原有null、不得要求W8。`act_diagnostic_episode`保持自己原有scope/inputs合同，不继承新容器/W8要求。所有builder/CLI、context序列化、admission分支与测试同迁；业务各一当前接口，没有宽松extra字段。`qualification_contract`是预运行gate，`qualification_receipt`是已运行W8报告，不复用参数。
- [ ] CLI 现有必选参数保留；新增 `--campaign-config`、`--registered-evidence-root`、正式专用 `--qualification-receipt`。资格模式 `qualification_receipt_path=None`，先无覆盖持久化 gate contract；正式模式必须引用 QUALIFIED 报告且真实 admission 重算证据。错误根、版本、status/字段、hash 直接拒绝，不试旧格式。
- [ ] 两 run 位于同登记 root 不同 subroot，正式只读引用资格原件；启动入口逐段 no-follow/限制真实路径并重算整链，activation receipt 仍限本次 run。不能复制资格改变 run 身份或放宽 `_read_json()` 供全部 receipt 跨根读取。
- [ ] 新正式 campaign 真实 `UnifiedWorkloadService.start()` 正例；实际 gate producer+report writer+admission+verifier 联通，不 mock 安全边界。负例：旧14项、PASSED、受控身份不同、篡改、路径逃逸、资格run被改名、源或原件消失。Teacher模型参数/实例数下一campaign变化的正例，必须证明不会经runtime hash间接撤销资格；同 campaign 改参数仍拒绝，Host 崩溃后 resume 明确拒绝。
- [ ] 定向 GREEN 和双 package contract 回归；review 后限定 commit。可重新命名误导性旧函数/参数，但不新增 alias 或版本 dispatcher。

## 校准、Head Search 与 live 的生产容器接线

此节是代码实施步骤，必须在镜像集成冻结之前完成；后面的校准/live阶段只运行已实现的入口。改 `D/src/act/calibration_production_composition.py`、`pick_place_calibration_measurement_client.py`、`pick_place_calibration_admission.py`、`head_search_binding.py`、`D/src/cli/{act_measure_pick_place_calibration,act_run_pick_place_validation}.py`；改 `adapters/act/head_execution_{provider,composition,owner_bridge}.py`、`cli/head_search/{run,scene_measurements,closed_loop,stop_timing,restarts,smoke_readback}.py` 的实际生产调用方，以及 `T/so101_teleop/unified/{pick_place_case_owner,act_stack_probes}.py`。新增端口和测试如下。

```python
class ContainerMeasurementPort:
    def __init__(self, *, admitted_measurement, shard_control, artifact_roots): ...
    def launch(self, anchor: str) -> dict: ...
    def readback(self, anchor: str) -> dict: ...
    def frame(self, anchor: str) -> dict: ...
    def camera_info(self, anchor: str) -> dict: ...
    def tf(self, anchor: str) -> dict: ...
    def neck_feedback(self, anchor: str) -> dict: ...
    def run_search(self, anchor: str, request: dict) -> dict: ...
    def probe(self, anchor: str, command: dict) -> dict: ...
    def command(self, anchor: str, command: dict) -> dict: ...
    def close(self, anchor: str) -> bool: ...
    def cleanup(self, anchor: str, generation: str) -> dict: ...

class ContainerCasePort:
    def __init__(self, *, admitted_context, campaign_owner): ...
    async def run_full_restart(self, case: dict, journal_path: Path) -> dict: ...

class ContainerServiceOwner:
    def __init__(self, *, admitted_context, config: dict, roles: tuple,
                 launcher, root: Path): ...
    def start(self) -> dict: ...
    def close(self) -> dict: ...
```

measurement port使用Host→shard的受限控制socket，不使用stateless推理socket作运动通道。它委托容器内同一真实MuJoCo/ROS stack读取相机、TF、反馈、contact与执行已准入命令；不在Host另开`MjModel`或用几何projection充当RGB detector。frame引用包含真实RGB文件/stamp/hash，由`HeadIpcDetector`调用共享head服务；Host可读原始测量但不加载模型。原始21字段仍由既有driver/formulas及phase-camera规则计算，缺一源拒绝，不加Docker数值代替测量。

- [ ] RED：真实`act_measure_pick_place_calibration.main()`和Head Search实际安装provider从入口到新port，无test-only driver/io_client/detector factory替代；可替换Docker/外部ROS I/O，但不能替换composition、准入、IPC client和formula。断言Host不调用本地`MujocoMeasurementClient`构造器或`build_detector`，真实Unix IPC server返回的像素结果被实际业务consumer消费，21字段原始refs可反读。
- [ ] `build_real_providers()`明确构造`ContainerMeasurementPort`与`HeadIpcDetector`，去掉本采集路径上的本地模型factory和Host独立MuJoCo client；`head_execution_provider.provide()`及上述Head Search子命令同迁，不能让开发入口隐式回到宿主模型。生产host/shard只保留角色分工，不增加后缀版本/旧入口alias。
- [ ] 将`act_run_pick_place_validation._case_owner_factory()`的宿主`make_pick_place_act_stack/ActCampaignChildOwner`链替换成`ContainerCasePort`，保留真实`PickPlaceCaseOwner`的FULL_RESTART/journal/停止判据，但迁出其每case的全局`workload_service.start/finish`。新增`start_case(admitted_context, case)`/`finish_case(attempt_id)`只管理本case的shard、controller和局部journal；既有`start(spec)`/`finish(...)`作为独立抓放业务入口委托外层owner，不可在已准入campaign内重复调用。phase/full case共用这一局部边界，不能沿用仅接受`pick_place_validation_full`的检查挡住九个phase。每case新shard/内部ROS/controller和session，完整stop/exit/cleanup证明后才下一case；共享模型不随case重启。
- [ ] 新 `D/test/runtime/container_campaign/{test_calibration_ports,test_first_measurement,test_live_case_provider,test_service_owner}.py`和`T/test/unified/test_container_pick_place_case_owner.py`：CLI默认provider、无注入的生产composition、真实准入与port贯通；旧identity/假READY、非法release/recorder、第二measurement flight、旧session、stop未证、Host模型加载均拒绝。断言14个case仅一次全局start/finish、服务只启动一次、case间GPU lease/fence仍有效、失败cleanup不finish、不重复shutdown，九phase及五full均走实际case端口。9+5的manifest/journal代码不能mock为已通过；真正动作与GPU验收在冻结后的run gate才执行。

### 测量/live 阶段的服务生命周期

`ContainerServiceOwner`是Host上的同一个服务生命周期实现，供采集、测量和live外层owner调用，不持有调度或运动策略。它消费已经准入的context、已反读的campaign配置和按业务kind确定的service roles，登记launch、等待全部指定实例ready并返回端点；推理容器不取得authority，也不感知这些业务kind。start部分失败必须退役已登记子容器；close按generation single-flight收敛。共享服务不得由port、case或wave的finally关闭。

| 业务入口与准入kind | 配置与服务 | 非 wave 证据目录及退役 |
| --- | --- | --- |
| Head Search受限测量及完整抓放校准测量：新`act_calibration_measurement_start` | Host测量owner先调用统一workload入口取得受限context，再启动仅head服务；同一份campaign配置记录Teacher配置但不加载、不做Teacher ready校验。head候选配置由批准measurement plan/candidate policy提供；取得有效绑定后的完整测量则严格从绑定派生。均不得拿Teacher配置代替head批准。 | Host 在 ROOT 下冻结 `run/measurement/w00/g{generation}` 私有证据目录；每次measurement flight有独立campaign/run subroot及服务generation。先关闭受限shard并证明controller停止，再关闭head服务；全部终止证明成立才全局finish。 |
| `act_run_pick_place_validation`的9+5 campaign：`pick_place_validation_full` | 外层live owner一次准入：新READY、bundle/activation、Head Search绑定、worker_count=1及冻结9+5 manifest；不要求W8采集资格。启动head和Teacher各一次，14个case借用同一context/端点。 | 每 case 在 ROOT 下派生 `run/live/case-{case_id}/w00/g{generation}` 私有证据目录；case_id来自冻结manifest并校验路径字符。每case退役shard，最后一个case或campaign终止后退役两服务，再全局finish。 |
| 独立单phase抓放验证：`pick_place_validation_phase` | 独立外层owner按原phase准入条件启动所需两服务，只有一个case；不能将它的结果登记为9+5 live资格。 | 与 live case 相同目录规则；case/shard及服务全部退役后全局finish。 |

上述目录仅由 Host 从已登记 ROOT 和冻结标识派生，再按同一绝对路径挂入对应 shard。采集目录为 `run/{wave}/wNN/g{generation}`；共享推理服务不挂这些目录，不核对路径前缀，不感知 measurement/wave/case。RGB 经 socket 发送，原始 frame 文件/hash 留给已有测量与录制 evidence reader。

- [ ] 新受限measurement kind在`OperationSpec` builder、kind路由和admission中成套落地，不借`act_collection_start`或伪造READY。其闭合payload由原measurement contract所需source/十identity/manifest/candidate policy/安全区间、统一运行身份与`registered_evidence_root,campaign_config_path,campaign_config_sha256`构成；逐字段列入schema及测试，未知键拒绝。不要求`calibration_report`、activation或W8 receipt；只允许既有measurement plan批准的动作，CALIBRATION_REQUIRED只对该kind有效。统一入口一次校验资源/measurement单flight/cleanup fence，内部不重复campaign资源授权；第二flight在任何spawn之前拒绝。若真实安全区间或动作许可缺失，等待人工，不靠新增kind扩大许可。
- [ ] validation builder/payload/context接受外层9+5 manifest及上述三个容器配置键，不继承collection新增的W8 receipt要求；phase与full的局部case参数由冻结manifest派生而非重新准入。`act_diagnostic_episode`维持独立原payload和owner，不自动容器化。新增生产调用链测试逐kind验证闭合payload、服务roles、启动顺序及finish：CLI→OperationSpec→真实admission→service owner→port→停止证明→finish；外部Docker/ROS可替代，但不mock准入或context。测量和live均在共享服务ready之前不得launch动作，在未证退役时不得释放全局lease。

### 首轮测量顺序与准入

首轮不能调用需要尚未存在的`calibration_report`的`_admitted_controller_config()`。只为`role=calibration`保留现行`CalibrationMeasurementAdmission(status=CALIBRATION_REQUIRED)`的单flight边界，不放宽正式`validate_head_search_binding()`。受限路径消费新source/十identity、冻结measurement plan、候选policy、controller/service generation与从真实geometry/模型joint limits核对的safe interval；资源只在入口绑定，准入receipt随port记录。

1. 在新run下，先通过现有Head Search测量生产者取得geometry、camera、feedback/stop、operating point等原始文档。无有效生产Head Search绑定时，只能执行批准measurement plan里的`neck_target/arm_probe/stop/retire`，以真实反馈确认停止；controller adapter按受限测量plan执行，不构造需要READY报告的正式Head SearchController。收集像素走共享head IPC，不允许release/Recorder/抓放Teacher；缺安全区间、测量policy或批准测量预算即停下。
2. Head Search各原始producer经新port运行既有aggregate/bundle→必要的现行promotion审批→实际effective-value readback/Head Search资格；所有来源在新受控身份下。promotion缺当前审批就等待人工，不伪造approval receipt，不把bundle的SUCCEEDED等同QUALIFIED。不恢复已删除`measure-feedback-bootstrap`入口；若使用现有`run --execution-inputs`开发范围，其结果不能直接充当正式资格。
3. 已批准且本轮反读成立的Head Search binding才可供完整抓放测量中的真实搜索controller使用；`build_production_measurement_driver()`的measurement分支显式消费该绑定，而不是要求先有抓放READY。21项原始测量→既有独立aggregator→新身份的`PICK_PLACE_CALIBRATION_READY`→验证bundle/activation→9+5抓放live。正式抓放controller仍要求完整新READY/activation，measurement receipt不能替代它。

代码实施审查须提交可运行的依赖链测试：从没有本轮READY的输入开始，受限测量可产真实源文档，aggregate/promotion/readback后完整测量可运行，正式入口在READY之前始终拒绝。若现有Head Search reader需要抓放READY导致循环，在该受限measurement分支以明确的Head Search绑定参数消除循环，不伪造抓放报告、不保留同时接受两报告形状的生产reader；各业务只有自己的当前合同。此步骤不能增加动作类型或安全范围，任何超出既有measurement许可的需求回到用户决策。

## 代码与镜像集成冻结

依赖：前述步骤均有 review PASS。文件：`setup.py`/install rules，相关新增 schema，`docs/experiments/so101-act-data-experiment-ledger.md` 的新 checkpoint；交付时创建或更新 [采集训练 guide（计划交付文件）](../../guides/so101-act-data-collection-training-guide.md)，中文使用 humanizer-zh。该guide仅在协调者本地main存在，不在本计划代码基线分支内；执行者不得因链接不存在而等待。若协调者提供可追溯正文，先核对其当前合同再导入；否则在`docs/guides/`创建当前容器链路guide，依据本设计、已实现接口及真实证据编写，不复制旧阶段名/多版本接口。不改 Teacher 算法或 release 顺序以“顺便修复”。

- [ ] 全量扫描 ACTIVE 源码/CLI/schema 只有当前名字和格式。逐项确认CLI→OperationSpec→admission→owner→finish、两个 registry、PID/heartbeat/stop、ROOT/同路径挂载、binary RGB codec、轻量日志/磁盘 guard、measurement/head/live实际provider均已定向GREEN；不能留下“冻结后接入”的代码项。所有新路径已被安装，module origin 与镜像 manifest 相符；保留历史 ledger/spec 引用。
- [ ] 在已验证 ROS underlay 上用 `colcon build --packages-up-to so101_demo_py so101_teleop` 构建完整依赖闭包，构建/log/install base 全部在登记 run subroot 下；source 新 `install/setup.zsh`，核对每包 prefix。缺 underlay/override 或 setup 文件不能算源码 RED。C++ 未改不跑无关全 workspace gate。
- [ ] 第一次完整普通 package/xdist gate：每包独立 fresh NVMe scratch，workers=`min(8, os.cpu_count() or 1)`，记录 CPU/worker/range/exit/JUnit/skips 和实际子进程 argv。`so101_demo_py` 仅 `test/`，`so101_teleop` 仅自身 `test/`，不收集 benchmark，不并发两个整包造成超订阅。

```zsh
ACT_CPUS=$("$ACT_TEST_PYTHON" -c 'import os; print(os.cpu_count() or 1)') || exit 1
ACT_XDIST=$(( ACT_CPUS > 8 ? 8 : ACT_CPUS ))
colcon test --packages-select so101_demo_py --pytest-args test -n "$ACT_XDIST" \
  --event-handlers console_direct+
colcon test-result --verbose
```

`so101_teleop` 同样逐包执行，但先核对 package 声明和真实 argv 是否接受 xdist；若 ament/CTest 不转发则采用兼容的完整 xdist 调用并完成必要的 package 注册 gate，不宣称串行或缩小范围等价。所有 run 记录命令 exit code，`colcon test-result` 不替代真实 pytest 子进程证据。

- [ ] 两类 image 从最终同一 commit/source/install freeze 重建，digest 变化更新冻结清单；真实 CUDA 多实例 ready 和非 root固定权限/EGL 检查再做一次。模型 explicit ML 实例 smoke 如涉及 Torch集成另行精确执行，不默认跑 SAM benchmark。资源不足停下，不降低 xdist 或推理实例数取得 PASS。
- [ ] 审查完整集成 diff、全量 gate、镜像身份和运行清单，冻结实现 SHA。此后开始校准；若发现受控代码错误，回该冻结边界重新构建并创建新校准run，旧 evidence保留。

## 新容器链路的校准与抓放 live

文件：前一生产接线步骤已实现的业务入口与新证据；不能重写源码中的candidate defaults当批准参数。此阶段不新增port/provider代码。

- [ ] 以新 run subroot发布冻结context、十成员identity和measurement contract，先按上一节的受限测量→Head Search aggregate/promotion/反读→完整21项→抓放READY顺序运行。完整容器provenance与校准/Head Search原始样本通过来源证据关联，不扩充十identity，不伪造READY/activation。需要新promotion审批时先停下，未经审批不进入正式搜索/抓放。
- [ ] 验证测量driver和live case 实际调用新IPC与shard，不只改路径/名字。证据按配置 ROOT 同路径挂载；Host receipt 按原业务范围/hash 合同验证，不做路径改写。实现有变则回上一冻结边界，无变化只记录运行证据。
- [ ] 使用已核对 `--help` 的当前业务CLI，逐批运行测量/聚合/bundle；命令和输入路径从run登记文件读回，不从历史tmux摘要拼参数。核心调用形状如下，变量均在run清单绑定到真实不可覆盖文件。

```zsh
ros2 run so101_demo_py act_measure_pick_place_calibration \
  --contract "$ACT_MEASUREMENT_CONTRACT" --identities "$ACT_MEASUREMENT_IDENTITIES" \
  --batch-root "$ACT_MEASUREMENT_BATCH" --context "$ACT_MEASUREMENT_CONTEXT" --ledger "$ACT_LEDGER"
ros2 run so101_demo_py act_build_pick_place_calibration_report \
  --contract "$ACT_MEASUREMENT_CONTRACT" --identities "$ACT_MEASUREMENT_IDENTITIES" \
  --batch-root "$ACT_MEASUREMENT_BATCH" --output-root "$ACT_CALIBRATION_OUTPUT"
ros2 run so101_demo_py act_prepare_pick_place_validation \
  --anchors "$ACT_ANCHORS" --source "$ACT_SOURCE_PROVENANCE" \
  --runtime-config "$ACT_CONTROLLED_RUNTIME" --collection-config "$ACT_COLLECTION_CONFIG" \
  --policy-fingerprint "$ACT_POLICY_FINGERPRINT" --calibration-report "$ACT_CALIBRATION_REPORT" \
  --output "$ACT_VALIDATION_BUNDLE"
```

- [ ] Head Search资格反读已在首轮顺序中完成；再核对新拓扑可控八路同时head请求的原始时延证据：序列化/发送/queue/inference/decode 端到端、source age、late refusal均按批准值判断。此检查不变成逐实例容量表，不代替W8采集资格。
- [ ] 按当前manifest完成9阶段前缀与连续5次完整抓放，每case `FULL_RESTART`；实际安装入口必须走已实现的container case port，两个共享服务在所属campaign内保留，case shard/ROS/controller完整重启。不能用旧宿主栈收集新拓扑证据。

```zsh
ros2 run so101_demo_py act_run_pick_place_validation --spec "$ACT_CASE_SPEC" \
  --journal "$ACT_CASE_JOURNAL" --artifact-bundle "$ACT_VALIDATION_BUNDLE" \
  --journal-run-root "$ACT_VALIDATION_RUN"
ros2 run so101_demo_py act_build_pick_place_validation_qualified_report \
  --pick-place-calibration-ready "$ACT_CALIBRATION_REPORT" \
  --preparation-receipt "$ACT_VALIDATION_RECEIPT" --campaign-result "$ACT_LIVE_RESULT" \
  --case-root "$ACT_VALIDATION_RUN" --output "$ACT_PICK_PLACE_QUALIFIED"
```

- [ ] 独立反读生成抓放 QUALIFIED；检查head/measurement证据、MuJoCo物理和contact、MoveIt shadow、controller/joint/TF、原始图像/目标轨迹。纯headless报告视觉N/A并给数值证据；若使用可见GUI，按gui-capture保存并实际查看本轮fresh图像，不用日志替代。
- [ ] 校准/Head Search/抓放live审查PASS后进入功能验证；任何资源/采样/QC停点报告原始路径和最小人工决定，不降阈值、不resume自动硬撑。

## 容器功能等价与独立 exact-W8

文件：新 `D/test/runtime/container_campaign/test_end_to_end.py`、freeze后运行合同和业务清单。这些是产品验收，不是pytest worker并发资格。所有新增容器测试镜像对应源码目录，不新建`test/integration/`旁路。

- [ ] 首先W1真实链路一case，readback双RGB/状态/action、原始MCAP、10Hz因果采样、独立QC、seal→Host verifier→commit。Teacher success与data VALID分别验证。保留执行/停止/资源证据。
- [ ] 同一完整八场景清单分别W1/W2功能验证：场景对应结果、质量、隔离和时序等价；W2实际吞吐与W1按同口径记录比较，不设通过线。正式模式拒绝W1/W2，测试模式不能偷换为正式。cleanup后两个服务只在该功能campaign结束时关闭。
- [ ] 在运行 W8 前无覆盖冻结 40 场景清单、两个 20 项 wave、数据用途/分母与四项 quality_rules；功能场景及正式 split 均不重叠。Recorder lossless、逐间隔 10 Hz 连续性、Teacher 物理成功率、QC 合格率的规则/hash 从现有 QC/业务合同反读，真实缺项报告人工决定。CPU/GPU/RAM、磁盘 I/O、RTF、队列与吞吐只保留可用日志，不要求齐全字段/coverage/reducer 或容量预算。磁盘见底停止新派发并保留日志。
- [ ] W2通过直接启动独立exact-W8，YOLO教师，两个完整wave、八个ready shard，不W4/W6。每wave保证每worker至少两个terminal lease，余下四场景按冻结顺序派发；八路并行物理/录制/离线处理负载真实存在，不用mock或串行driver替代。
- [ ] 零infra/retry/crash-resume、四项质量/业务门槛成立、身份/拓扑/原始质量证据完整、cleanup收敛，才写QUALIFIED。其他观测指标如实汇总并说明缺测，不用于资格拒绝；不能因吞吐低或RTF低而自动降档。业务失败保留分母，由既有冻结成功率规则判断；单个业务失败不自动取消其他case。
- [ ] 调用新增报告/独立验证CLI（此处命令是目标接口，需在前述资格步骤实现并测试）：

```zsh
ros2 run so101_demo_py act_build_parallel_qualification_report \
  --contract "$ACT_W8_CONTRACT" --campaign-root "$ACT_W8_RUN" \
  --registered-root "$ACT_EVIDENCE_ROOT" --output "$ACT_W8_REPORT"
ros2 run so101_demo_py act_verify_parallel_qualification \
  --report "$ACT_W8_REPORT" --registered-root "$ACT_EVIDENCE_ROOT" \
  --campaign-config "$ACT_CAMPAIGN_CONFIG"
```

- [ ] 独立复审完整报告和真实正式admission正例；无40原始证据或9+5替代的一律不通过。资源不足停止等待人工；人工若决定下一campaign调整实例数，仅运营配置变化不重做旧calibration/资格，不制作容量表，同campaign不热改。

## 正式采集与数据交付

依赖：独立W8报告和正式准入证据已审PASS，用户执行授权覆盖仿真正式采集范围。文件：当前训练输入/manifest消费者以及运行账本；训练算法和 `act_train` 不执行。

- [ ] 新正式campaign subroot、Head Search目标来源、冻结split/候选清单，YOLO教师、exact-W8和实际选定模型实例数。先只读引用资格原件，真实admission读回controlled身份/原始证据链再spawn，不重新签发资格。运营参数与权重/阈值按campaign记录，不做模型QUALIFIED门禁。
- [ ] 使用扩展后的 `act_collect_parallel`；qualification与formal两plane的CLI contract测试已通过。运行输入从唯一campaign配置及manifest反读，不能手工补猜hash；正式 `--qualification-receipt` 指向只读资格报告，不指向预运行contract。
- [ ] 按已冻结正式 manifest 与原 ACT 数据配额收集，不因失败扩张清单补成功率。每 scene 结果、原始 bag、QC 与 commit 可追溯；低频记录可用资源，磁盘见底停派，真实采集/服务故障按既有合同处理，保存在途证据并等待必要人工决定。Host 崩溃直接结束旧 campaign；跨 campaign 重采必须新数据身份/批准 manifest，旧分母不改写。
- [ ] Host 活着时单 shard 故障只用前述 generation/single-flight 路径；已 commit 不重做、业务 FAILED 不重试、unknown owner 不抢占。Host 崩溃后只清理已确认 owned 的旧资源，不接管服务/继续旧 campaign。正式清单耗尽或崩溃后仍缺原配额时，报告缺额与最小新 campaign 决策，不自动生成新 scene。
- [ ] 从冻结campaign index回放commit/receipt构建训练manifest，拒绝qualification/surplus/partial/INVALID/仅seal未commit数据；独立复核split无泄漏、10Hz时间/accepted action因果、逐文件hash、QC及原来源，不能目录扫描“发现”样本。
- [ ] 交付最终checkpoint：实现SHA/镜像与配置hash、所有major gate结果、scene分母/Teacher成功/数据有效/infra分别计数、训练输入manifest、原始bag保留、scratch/临时日志 deletion candidates、archived/retained列表、owned进程清理和preserved进程。若冻结后修了受控源码，列明失效证据并在新run重走相关资格，不沿用PASS。
- [ ] 最后仅在此阶段修了代码时重跑受影响包完整xdist/package gate，并重新冻结/验收；无代码变化不重复全量单测。审查最终交付，停止在“正式数据可用于训练”的边界，后续训练另行批准。

## 自检与交接判据

| 设计要求 | 实现/验收位置 |
| --- | --- |
| 单当前格式、业务命名、21测量/十identity | 推理合同与配置身份；集成冻结 |
| 无状态共享服务、mask、进程配置、deadline/迟到/队列 | 共享YOLO；Worker接入 |
| 可配置 ROOT、同路径私有挂载、两类镜像、source/install/GPU/EGL | 镜像与shard；容器校准 |
| campaign/wave 生命周期、Host 崩溃终止、单 shard 清理、轻量日志/磁盘停派 | Host生命周期；正式交付 |
| 独立40、两20、真实lease、完整report→admission | 独立报告；exact-W8 |
| 不目录扫描、不模型QUALIFIED、不运营hash隐含门禁 | 配置身份；准入正负例；训练manifest交付 |

本计划审查PASS只表示步骤和验收可供执行，不代表代码、live、W8或正式数据已经完成。交接前须由用户明确批准本计划；批准后才启动或复用ai-station tmux中的 `dst`，不得自动转为Codex实施，也不得自动publish。

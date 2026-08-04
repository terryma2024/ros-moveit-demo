# SO-101 TCP 六维可达位姿空间采样工具设计

**日期：** 2026-08-04

**状态：** 设计已获用户逐段批准；等待书面 spec 复核

**源码基线：** `moveit-demo/main@b40a5eb4afe9f8af6c4d8ea861108a2429ed2fa0`

## 1. 背景

当前 `so101_gazebo_demo` 已有完整 SO-101 URDF/SRDF、MoveIt `RobotState`、
Planning Scene 碰撞检查、TCP FK 和 Halton 关节采样能力，但没有一个可重复生成完整 TCP
可达位姿数据集的独立工具。此前对当前模型做过一百万组关节状态的只读 FK 采样，得到过
三维几何包络；该结果没有保存每个位置对应的完整朝向集合，也没有用固定桌面场景过滤
碰撞，不能作为长期可重复的分析工件。

用户需要在 ai-station 上离线运行一个批量分析工具，观察 SO-101 的 TCP 全部可达范围，
并保存每个采样位置对应的全部已发现朝向。结果在 Mac 上用 CloudCompare 查看，但 Mac
不承担 FK 或碰撞计算。

## 2. 问题定义与事实边界

五个 arm joint 组成关节向量：

\[
q=[q_1,q_2,q_3,q_4,q_5],\qquad q_i^{min}\le q_i\le q_i^{max}
\]

工具近似计算当前模型下的 TCP 可达位姿集合：

\[
W_{SE(3)}=\left\{
\left(p_{tcp}(q),R_{tcp}(q)\right)\mid q\in Q
\right\}
\]

以及固定 `q6=preopen`、满足自碰撞和固定场景碰撞约束的子集：

\[
W_{free}=\left\{
\left(p_{tcp}(q),R_{tcp}(q)\right)\in W_{SE(3)}
\mid collision(q,q_6^{preopen})=false
\right\}
\]

SO-101 arm group 只有 5 DoF，因此它在六维 `SE(3)` 中形成最高约五维的连续子集，
不是填满某个六维体积。同一个位置可能对应多个朝向，也可能只有很窄的朝向集合。
连续集合不可能由有限文件逐点穷尽；本工具输出的是在明确位置/朝向分辨率、样本数量和
时间预算下的确定性近似，并报告收敛程度和剩余不确定性。

`q6` 不改变 `so101_tcp` 位姿，但会改变夹爪碰撞几何。首版固定为当前 canonical profile
的 `preopen`，并在 manifest 中记录精确值。

## 3. 目标

1. 从当前安装包的 URDF、SRDF 和 canonical scene 配置构建可追溯的离线模型。
2. 在关节 `1-5` 限位内进行确定性低差异采样，保存每条关节状态和 TCP 六维位姿。
3. 分开输出几何可达集合和固定 `preopen` 下的无碰撞子集。
4. 在三维位置体素内统计所有已发现 TCP 朝向，显示各位置的朝向丰富程度。
5. 在约 30 分钟默认预算内分批运行、检查收敛、可中断恢复并保留有效结果。
6. 生成 CloudCompare 可查看的 PLY、规范 CSV 和包含 provenance/收敛证据的 JSON。

## 4. 非目标

- 不建立 Cartesian pose 网格，也不调用 IK。
- 不从 Home 对每个目标做路径规划。
- 不启动或连接 `/move_group`、Gazebo、controller 或 RViz。
- 不执行仿真或真实机械臂动作。
- 不限定垂直向下、水平侧抓或其他抓取方向。
- 不提供在线 reachability API。
- 不把 `plastic_cup` 加入通用工作空间碰撞场景。
- 不把离线采样结果称为实机安全范围或规划可达范围。
- 不自动把采样位姿转成运动命令。

## 5. 方案比较与选择

### 5.1 方案 A：低差异关节采样加确定性局部细化

在五维关节空间中使用 Halton 序列生成全局样本，并对几何边界、碰撞边界和低朝向覆盖
区域做确定性局部细化。每批更新位置体素、位置—朝向簇和收敛统计。

优点是直接覆盖真实五维关节自由度，不依赖 IK seed，能保留多解分支，任意时刻停止均有
有效前缀结果。当前代码已有 Halton、RobotState、FK 和 Planning Scene 碰撞语义可借鉴。
缺点是只能得到分辨率受限的近似，薄边界需要额外细化。

### 5.2 方案 B：规则五维关节网格

每个关节均匀划分后取笛卡尔积。方案简单、确定，但每轴分辨率加倍会让样本量扩大 32
倍，大量预算浪费在内部重复位置体素，不适合作为 30 分钟正式采样的主算法。它只用于
小型回归基准。

### 5.3 方案 C：六维目标网格加 IK

先生成位置和朝向目标，再逐个调用 IK。SO-101 的可达集合在六维空间中很薄，绝大多数
目标天然不可达；求解结果还受 seed、timeout 和局部收敛影响，容易把“没找到”误判成
“不可达”。该方案适合以后验证指定目标，不适合发现完整工作空间。

**选择：方案 A。**

## 6. 总体架构

新增 C++ 库目标 `so101_workspace_sampling` 和可执行程序
`sample_so101_workspace`：

```text
so101_workspace_sample.launch.py
        |
        v
sample_so101_workspace
        |
        +-- WorkspaceModelLoader
        |     `-- expanded URDF + SRDF + joint limits
        |
        +-- CanonicalWorkspaceSceneFactory
        |     `-- local PlanningScene: pedestal + table
        |
        +-- JointSampleGenerator
        |     `-- explicit boundaries + Halton + local refinement
        |
        +-- WorkspaceStateEvaluator
        |     +-- RobotState FK
        |     +-- q6 = preopen
        |     +-- self collision
        |     `-- pedestal/table collision
        |
        +-- PoseCoverageIndex
        |     +-- position voxels
        |     +-- per-voxel orientation clusters
        |     `-- convergence history
        |
        `-- WorkspaceArtifactWriter
              +-- resumable batch chunks
              +-- CSV / binary PLY
              `-- manifest / summary / checkpoint
```

公共 launch 使用当前安装包展开 Xacro，并把 `robot_description`、SRDF 和采样配置传给唯一
采样节点。采样节点可以短暂出现在 ROS graph 中，但不查询或依赖任何其他 node、topic、
service 或 action。没有 `/move_group` 或 Gazebo 时也必须完整运行。

`WorkspaceModelLoader` 使用 MoveIt `RobotModelLoader` 构建模型，但禁用 kinematics solver
加载，因为工具只从关节空间做 FK。它必须从模型读取实际 joint bounds，不复制一份手写
限位。

`CanonicalWorkspaceSceneFactory` 创建进程内 `planning_scene::PlanningScene`，使用当前
`SO101Profile` 中的 world frame、table/pedestal ID、尺寸和 pose，并继承 SRDF Allowed
Collision Matrix。场景只包含 table 和 pedestal；不包含 task object。

## 7. 数据模型

每个关节样本产生一条 `PoseSample`：

```cpp
struct PoseSample
{
  std::uint64_t sample_id;
  SampleSource source;
  std::array<double, 5> arm_joints;
  double gripper_q6;
  Pose3d tcp_pose;
  bool bounds_valid;
  bool self_collision;
  bool scene_collision;
  bool collision_free;
  PositionVoxelKey position_voxel;
  std::uint32_t orientation_cluster_id;
};
```

`SampleSource` 至少区分 `EXPLICIT_BOUNDARY`、`REGULAR_BASELINE`、`HALTON_GLOBAL` 和
`LOCAL_REFINEMENT`。`collision_free` 必须等于
`bounds_valid && !self_collision && !scene_collision`，不能由 writer 重新推导另一套语义。

四元数写出前归一化并采用固定半球规范：先令 `qw > 0`；当 `qw == 0` 时，依次选择
`qz`、`qy`、`qx` 中第一个非零分量为正。这样 `q` 与 `-q` 有唯一表示。

每条样本进入 CSV 和对应 PLY。字符串形式的 collision pairs 不重复写入每个 PLY vertex；
按 pair 的聚合计数写入 `collision_pairs.csv`，并为每个 pair 保存有限数量的最小 sample ID
作为代表证据。

## 8. 采样算法

### 8.1 显式与规则基线

采样首先加入：

- Home；
- 全部关节同时位于上下限中点；
- 每个关节单独取 min/max、其余关节取中点；
- 当前 Home 附近的小型规则网格；
- 固定测试 profile 指定的规则五维网格。

重复关节向量按量化后的五维 key 去重。显式样本不改变 Halton global index。

### 8.2 全局 Halton 采样

全局样本使用 bases `[2,3,5,7,11]`。第 `i` 个 Halton 值线性映射到模型读取的对应 joint
bounds。序列从 index 1 开始，checkpoint 保存下一未使用 index。相同模型、参数、index
区间必须生成完全相同的关节序列。

### 8.3 确定性局部细化

前两个 batch 全部使用全局 Halton。之后每个 batch 默认 80% 为全局样本、20% 为局部
细化；没有可用 seed 时回退为 100% 全局样本。

细化 seed 按以下优先级选择：

1. 同一位置体素同时出现 collision-free 与 colliding 样本；
2. 已占据位置体素与未占据 6-neighbor 相邻；
3. 样本数不低于全体中位数、但 orientation cluster 数位于最低四分位的体素。

候选按 `(priority, position_voxel_key, sample_id)` 排序并 round-robin。局部扰动使用独立
Halton index 和固定 bases，把 `[-1,1]` 值乘以 joint range 的 2%；每轮再次选中同一 seed
时尺度减半，最小为 joint range 的 0.125%。扰动越界时镜像回 joint bounds，而不是截断
到边界。所有 local index、seed ID 和 scale level 写入 checkpoint。

### 8.4 状态评估顺序

每个样本严格执行：

```text
set q1-q5 and q6_preopen
-> RobotState::update
-> satisfiesBounds
-> getGlobalLinkTransform(so101_tcp)
-> PlanningScene::checkSelfCollision
-> PlanningScene::checkCollision with contacts enabled
-> PoseSample
```

`self_collision` 只取 `checkSelfCollision` 的结果。第二次完整 collision query 同时可能返回
self/world contacts；`scene_collision` 只在 contact pair 中至少一端是 canonical table 或
pedestal object ID 时为 true。其他未知 world object ID 表示 scene factory 违反了首版契约，
必须终止而不是归入 table collision。这样 self 与 scene 分类不会因第二次 query 重复包含
self-collision 而混淆。

即使发生碰撞，合法关节样本及其 TCP 位姿仍进入几何数据集；只有
`collision_free_poses.ply` 过滤它。NaN、非单位四元数无法规范化、link transform 不有限等
模型/计算错误必须终止运行，不能只跳过坏样本。

## 9. 六维覆盖与收敛

### 9.1 位置体素

默认位置体素边长为 `0.005 m`。key 使用以 world origin 为基准的有符号整数：

\[
k_x=\lfloor x/s_p\rfloor,\quad
k_y=\lfloor y/s_p\rfloor,\quad
k_z=\lfloor z/s_p\rfloor
\]

因此正负坐标遵循同一规则，体素中心可唯一重建。

### 9.2 每个位置的朝向集合

每个位置体素保留原始样本引用和一组 orientation representatives。两个单位四元数的角
距离为：

\[
d_R(q_a,q_b)=2\arccos\left(\mathrm{clamp}(|q_a\cdot q_b|,0,1)\right)
\]

默认聚类阈值为 `10 deg`。新样本按 cluster ID 顺序寻找距离不超过阈值的 representative；
若多个 cluster 同时匹配，选择角距离最小者，完全相等时选择较小 ID；没有匹配时建立新
cluster，并以该样本四元数作为固定 representative。由于样本顺序确定，该贪心聚类可
复现，但 cluster count 只是覆盖估计，不证明 cluster 之间连续可达。

原始 CSV/PLY 从不因位置体素或朝向聚类而丢弃样本。

### 9.3 收敛规则

每批计算：

\[
r_p=\frac{\text{new position voxels}}{\max(1,\text{existing position voxels before batch})}
\]

\[
r_o=\frac{\text{new position-orientation clusters}}
{\max(1,\text{existing clusters before batch})}
\]

`full` 默认值：

- time budget：`1800 s`；
- batch size：`25000`；
- minimum samples：`250000`；
- maximum samples：`2000000`；
- position voxel：`0.005 m`；
- orientation threshold：`10 deg`；
- stable batches：`5`；
- `r_p < 0.001` 且 `r_o < 0.002` 才算一个 stable batch。

达到 minimum samples 后连续五批稳定，停止原因为
`converged_at_configured_resolution`。达到 maximum samples 则为 `sample_cap_reached`。
达到 1800 s 且已有至少 250000 个已完成样本则为 `budget_exhausted`；这是有效结果但不是
收敛声明。时间耗尽时不足 minimum samples，运行失败为 `minimum_samples_not_reached`。

确定性保证以相同样本数量和 checkpoint 状态为准，不以墙钟时间为准。

`quick` 默认 time budget `300 s`、batch size `10000`、minimum samples `10000`、maximum
samples `100000`、stable batches `3`，其体素和朝向阈值与 `full` 相同。`deep` 要求调用者
显式提供 time budget 和 maximum samples，其他默认值继承 `full`。

## 10. 运行接口

公共入口：

```bash
ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-full \
  profile:=full
```

恢复入口：

```bash
ros2 launch so101_gazebo_demo so101_workspace_sample.launch.py \
  output_dir:=/tmp/so101-workspace-full \
  profile:=full \
  resume:=true
```

launch arguments 至少包括：

- `output_dir`：必填绝对路径；
- `profile`：`quick | full | deep`；
- `resume`：默认 false；
- `time_budget_seconds`、`batch_size`、`minimum_samples`、`maximum_samples`；
- `position_voxel_size_m`、`orientation_threshold_deg`；
- `stable_batches`、`position_new_rate_threshold`、`orientation_new_rate_threshold`。

`output_dir` 不存在时创建；存在且为空时使用；存在且非空时只有 `resume:=true` 且通过完整
checkpoint 校验才允许写入。禁止隐式覆盖。

## 11. 结果工件

```text
<output_dir>/
|-- manifest.json
|-- summary.json
|-- checkpoint.json
|-- samples.csv
|-- all_poses.ply
|-- collision_free_poses.ply
|-- position_voxels.ply
|-- collision_pairs.csv
`-- chunks/
    |-- batch-000001.csv
    |-- batch-000001-all.ply
    |-- batch-000001-free.ply
    `-- ...
```

PLY 使用 binary little-endian。`all_poses.ply` 和 `collision_free_poses.ply` 每个 vertex
至少带以下数值 property：

```text
x y z
qx qy qz qw
q1 q2 q3 q4 q5 q6
sample_id sample_source
self_collision scene_collision collision_free
position_voxel_x position_voxel_y position_voxel_z orientation_cluster_id
```

为保持标准 PLY reader 兼容，PLY 中 `sample_id` 和 `orientation_cluster_id` 使用 32-bit
unsigned integer，`sample_source`/碰撞标志使用 `uchar`，voxel key 使用 32-bit signed
integer，坐标使用 `double`，关节角和四元数使用 `float`。`maximum_samples` 必须小于
`2^32`；CSV 中继续使用 64-bit `sample_id` 和 double precision，它才是数值精度的事实源。

`position_voxels.ply` 每个已占据位置体素一个 vertex，至少带：

```text
x y z
sample_count collision_free_count colliding_count
orientation_count collision_free_orientation_count
```

`samples.csv` 是规范可查询数据源。PLY 用于 CloudCompare 展示；若 viewer 忽略自定义
property，不影响 CSV 的事实完整性。

每个 batch 先写临时 chunk，flush/close 成功后原子 rename，再原子更新 checkpoint。
最终 artifacts 从已提交 chunk 流式合并，不要求全部样本驻留内存。恢复时只能从最后一个
完整 batch 继续；临时文件不计入 checkpoint，可安全忽略并由恢复流程移到 output 下的
`orphaned/`，不得静默删除。

`resume` 允许两类来源：异常中断留下的 incomplete run，以及 stop reason 为
`budget_exhausted` 的完整 run。后者把现有 final artifacts 原子移动到
`snapshots/<completed-sample-count>/` 后继续追加；新的 final artifacts 只有在下一次正常
finalization 完成后才原子发布。`converged_at_configured_resolution`、`sample_cap_reached`
或 `failed` run 不允许用同一配置继续；改变 time/sample/config 参数也视为 hash mismatch，
必须使用新的 output directory。time budget 按每次 invocation 单独计时，因此同一配置的
`budget_exhausted` run 可以再追加一个相同预算窗口。

## 12. Provenance 与恢复契约

`manifest.json` 至少记录：

- expanded URDF SHA-256；
- SRDF SHA-256；
- table/pedestal scene 的规范序列化内容和 SHA-256；
- `q6_preopen`；
- arm joint names、bounds、TCP link、world frame；
- profile 和全部展开后的采样参数；
- global/local Halton bases、起止 index；
- package prefix、executable SHA-256、ROS distribution、host；
- start/end timestamp、completed sample count、peak memory；
- stop reason 和 convergence history。

checkpoint 同时保存模型/场景/配置哈希、下一 global index、下一 local index、batch number、
completed sample count、refinement seed/scale 状态和已提交 chunk 哈希。resume 对任何字段不
匹配均返回 `checkpoint_mismatch`，不得把不同模型或参数的数据拼在一起。

Git commit 仅在能从安装产物可靠发现时作为附加字段；它不能替代内容哈希，也不能因缺失
而阻止采样。

## 13. 错误处理与退出语义

以下情况非零退出，manifest 状态为 `failed`，且不得生成 final PLY/CSV：

- model、SRDF、arm group、TCP 或 `q6` 缺失；
- joint group/bounds 与五关节采样契约不一致；
- canonical table/pedestal scene 构建失败；
- collision detector 未初始化；
- 出现不可规范化四元数、NaN/Inf transform；
- 输出目录非法、chunk 写入失败、磁盘空间不足；
- checkpoint/provenance 不匹配；
- 时间耗尽但未达到 minimum samples。

已完成 chunk 在失败时保留用于取证，但 `summary.json` 明确标为 incomplete，且 final artifact
名称不存在。达到 minimum samples 后的 `budget_exhausted` 和 `sample_cap_reached` 返回零，
但 summary 不得写 `converged=true`。

## 14. 测试设计

### 14.1 单元测试

- Halton 已知前缀、joint bound 映射和显式样本去重；
- local seed 排序、扰动、镜像 bounds 和 scale decay；
- 四元数归一化、半球规范及 `q/-q` 等价；
- 位置体素在正负坐标和边界上的索引；
- 朝向阈值两侧、最近 cluster 和 tie-break；
- convergence minimum/stable-batch/sample/time cap 状态机；
- checkpoint 续跑与不中断序列一致；
- CSV schema、PLY header/property/vertex count 和 chunk merge。

### 14.2 模型契约测试

使用当前测试用 expanded URDF/SRDF 验证：

- arm group 为关节 `1-5`；
- `so101_tcp` 属于正确运动链；
- 改变 `q6` 不改变 TCP pose；
- `q6_preopen` 在 bounds 内；
- existing golden joint vectors 的 FK 保持当前锁定值；
- 缺失或错误 group/link/config 时 fail closed。

### 14.3 Planning Scene 测试

- scene 只含预期 table/pedestal，不含 `plastic_cup`；
- SRDF Allowed Collision Matrix 生效；
- fixture 分别证明 free、自碰撞、table collision 和 pedestal collision；
- collision-free 分类与 `PlanningScene::checkCollision` 独立直接调用一致。

碰撞 fixture 由实现阶段在当前模型上做确定性搜索、通过独立 MoveIt 查询复核后冻结。测试
不能用肉眼判断关节角“应该碰撞”。模型哈希改变导致 fixture 失效时，测试必须失败并要求
显式重新标定。

### 14.4 集成测试

固定 `10000` 个样本的 test profile：

1. 无 `/move_group`、Gazebo、controller 时运行；
2. 生成完整工件；
3. 用独立 reader 核对 CSV/PLY row/vertex 数和有限值；
4. 证明 free samples 是 all samples 的严格子集或相等集合，且每个 free sample 的分类字段
   一致；
5. 在 batch 边界强制停止后 resume；
6. 与一次性运行的规范化数据文件逐字节一致；
7. 改变任一模型/场景/采样哈希后 resume 被拒绝；
8. 非空目录且未指定 resume 时拒绝覆盖。

## 15. ai-station 验收

1. 记录 root/submodule checkout、branch、dirty files 和 package prefix；
2. 新测试先取得预期 RED；
3. build、source installed overlay 并确认 executable/config provenance；
4. 运行定向测试；
5. 运行整个 `so101_gazebo_demo` package 测试，无新增失败；
6. 确认采样没有启动或连接第二套 MoveIt/Gazebo/controller stack；
7. 运行 `quick` 并独立读取全部格式；
8. 运行一次最长 1800 秒的 `full`；
9. 独立核对 manifest、CSV、PLY、checkpoint 和 chunk 数量/哈希；
10. 将结果复制到 Mac，用 CloudCompare 打开三份 PLY，并保存本轮新截图。

最终报告必须包含：

- 模型、SRDF、场景、参数和 executable 哈希；
- samples/free samples、position voxels、position-orientation clusters 数；
- geometry/free AABB 和最大水平半径；
- collision pair 统计；
- 每批 `r_p/r_o`；
- stop reason、wall time、peak memory；
- CloudCompare 新截图；
- 保留的用户既有改动；
- 明确结论：“当前模型、固定 preopen 和离线 table/pedestal scene 下的离散近似”，不得
  扩大为路径可达、Gazebo 执行或实机安全结论。

## 16. 实施边界

实现应把 sampler、state evaluator、coverage index 和 artifact writer 保持为可独立测试的
小组件。可以复用现有 SO-101 profile、数学类型和 MoveIt 语义，但不得把批量分析逻辑塞入
现有 pick-place state machine 或 Teleop server。不得借本功能重构无关 pick-place、camera、
reset 或 shared-kernel 代码。

设计提交只包含本文件；实施必须在后续独立计划和明确范围内进行。

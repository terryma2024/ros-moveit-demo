# prepare_horizon 第二轮 CPU 优化

用户已通过“以此为goal，进行优化”批准此前讨论的方案。当前 Codex 会话在 mac-mini 执行并 inline 自审，不启动 dst 或其他 agent。

目标是相对已推送的 `e1030ccf474f02105fdb62db19568255b1fce289`，将四个冻结案例等权聚合 median 再降低至少 50%。历史参考为 579.948 ms，目标约 289.974 ms；最终按同期交错对照的 ratio <= 0.50 验收。保持单计算线程和 BLAS/OMP 线程数 1。

唯一证据根继续使用 `/opt/data/work/so101-evidence/prepare-horizon-ik/20261004-01a10735`，本轮制品保存于其中的 `native50/`。原 baseline、协议、harness、失败运行和证据均保留。新协议为 `native50/protocol-v2.json`，沿用原 fixtures、harness 和计时边界。

## 实施顺序

1. 冻结 e1030ccf 源码与新协议，先测新 baseline。检查原工作树、运行时和源码归属。
2. 先建立差分回归和重复计算计数的 RED，再复用有限差分 FK 的共同前缀及不变关节旋转矩阵。保留左到右乘法顺序、五列有限差分和所有迭代、门控、评分及 receipt 行为。单独保存这一版本的输出和耗时。
3. 将热点数值循环提取为可编译内核，优先验证 Cython；它仅安装在证据根的隔离构建工具目录，不修改共享 venv。保留 Python 参考路径；必要时使用等价的小型 C 扩展。每个内核阶段先差分测试，浮点不一致的变体不进入验收。
4. 用固定 ROS Python 构建到任务私有安装目录，核验实际加载产物。依次运行定向测试、完整普通包 xdist 8 worker 门禁、独立 profile/计数和三轮正式 A/B。任何每次调用必需的初始化均在计时内；导入、构造和首次调用另报。
5. inline 审阅 scoped diff，核验搜索与业务逻辑未改变，更新账本、结果和证据分类。只在 latency、精确输出、新安装产物和测试全部通过后将 goal 标 complete。

## 一致性与取舍

保留原 14 路点、beam 3、seed 集和顺序、200 迭代上限、epsilon、阻尼、步长限制、关节余量、误差阈值、9 点路径采样、异常及审计输出。缓存仍只存在于单次 horizon。完整 fixture 输出必须精确相同；扩充随机与边界 FK、残差、Jacobian 和实际求解的差分覆盖。编译选项不能代替这些检查。

本轮保持现有计算资源预算。若无法达到目标，继续依据测量寻找同范围内的热点；不能减少失败案例、改变权重、放宽数值契约或隐藏冷启动成本。产品运行仍用固定 `/opt/ros/jazzy/.venv/bin/python` 和同一 NumPy。构建工具与 scratch 均保留，并在完成时分类，不自行删除。

## 当前状态

- [x] 用户批准方案；启动原生 goal。
- [x] 新 baseline 与冻结协议。
- [x] FK 前缀复用及独立测量。
- [x] 编译内核及逐项精确差分。
- [x] 新安装产物、定向与完整包测试。
- [x] 最终交错对照、审阅和交付。

最终三轮对照使用正常 colcon 安装产物：聚合 median 581.149 → 279.888 ms，ratio 0.481612，降低 51.84%；p95 为 585.263 → 285.539 ms。每个案例每个版本 15 个样本，完整输出精确相同。另有 64 个求解案例的 6043 次更新，其输入矩阵、向量和原始步长数组均逐位相同。定向测试 52 项通过，完整普通包 xdist 8 门禁 3920 项通过、30 项跳过。

原生部分由 Cython 编写；生成的 `_ik_numeric.c` 随源码提交。正常构建只需 C 编译器和 Python headers，不依赖安装 Cython。重生成时使用 Cython 3.3.0，在 package 目录执行：

```sh
python -m cython -3 --module-name so101_demo.control.moveit._ik_numeric \
  src/control/moveit/_ik_numeric.pyx -o src/control/moveit/_ik_numeric.c
```

任务内重生成的 C 文件与提交源码逐字一致。矩阵乘法、trace 和线性求解继续用原 NumPy 路径。没有原生扩展时使用 Python 前缀复用路径；重复关节布局和 solver 子类沿用原完整 FK 算法，兼容已有坐标定义及自定义模型。正式结果、数值对照、跳过原因和全部失败运行见证据根的 `native50/review/result.md`。

# SO-101 LLM Planner JSON Schema

## 目标

LLM Planner 把用户自然语言转换为确定性的任务意图。它只回答“操作哪个对象、执行什么动作、有哪些语义约束”，不生成目标 Pose、关节角或轨迹。

当前 V5 固定空间课程的数据流为：

```text
用户指令
  -> LLM Planner 结构化任务
  -> 感知或 VLM 选择目标实例
  -> RGB-D 与 tf2 生成 world Pose
  -> MoveIt 2 规划
  -> 控制器与 MuJoCo 执行
```

## 输入

输入是只包含一条用户指令的 JSON object：

```json
{
  "instruction": "请帮我拿右边的杯子，动作慢一点"
}
```

约束：

- `instruction` 必须是非空字符串；
- 一次请求只表达一个当前 schema 能支持的动作；
- 输入不是当前世界状态的事实来源。

## 输出

输出必须是 JSON object，并且恰好包含三个必填字段：

```json
{
  "target_object": "plastic_cup",
  "action": "pick",
  "constraints": {
    "spatial_relation": "right",
    "speed": "slow"
  }
}
```

### `target_object`

- 类型：string
- V5 当前允许值：`plastic_cup`
- 含义：课程内部稳定对象类型，不包含“左边”“右边”等实例选择条件。

自然语言中的“杯子”“水杯”等别名应归一化为 `plastic_cup`。若当前感知结果包含多个杯子，未来可由 `constraints` 和感知模块共同选择实例；当前 V5-T003 执行路径不消费实例选择约束。

### `action`

- 类型：string
- V5 当前允许值：`pick`
- 含义：请求抓取指定对象。

当前 MuJoCo demo 可以把 `pick` 映射到已有的固定位置抓取工作流；工作流中的安全放置和恢复动作属于确定性执行策略，不表示 LLM 可以虚构用户没有指定的放置目的地。

### `constraints`

- 类型：object
- 没有额外约束时：`{}`
- schema 认识、但当前 V5-T003 执行路径尚未消费的预留键：

| 键 | 允许值 | 计划消费者 |
|---|---|---|
| `spatial_relation` | `left`、`right`、`center`、`nearest` | 感知或 VLM 目标选择 |
| `speed` | `slow`、`normal` | 状态机选择已验证的速度策略，MoveIt/控制层执行对应缩放 |

当前 Dispatcher 仅接受 `{}`；任何非空 `constraints` 都以 `CONSTRAINT_UNCONSUMED` 拒绝，且不会启动 ROS runtime。表中的键只有在对应消费者实现并通过验收后，才能进入可执行子集。LLM 不直接生成关节速度、笛卡尔坐标、关节角或轨迹点。

## Fail-closed 规则

出现以下任一情况时，Planner 输出或下游校验必须拒绝任务，并且不能启动机械臂运动：

- 输入为空、不是单一可支持指令或语义含糊；
- 缺少必填字段，字段类型错误或包含未知字段；
- `target_object`、`action`、约束键或约束值不在允许集合中；
- 约束互相冲突；
- 当前、新鲜的感知结果中没有满足约束的目标；
- 感知消息缺失、过期、坐标系不连通或 Pose 非法。

不得因为目标缺失而改抓另一个对象，也不得复用旧 Pose。

## 边界示例

无实例选择条件：

```json
{
  "target_object": "plastic_cup",
  "action": "pick",
  "constraints": {}
}
```

schema 可表达、但当前 V5-T003 会 fail closed 的目标选择和速度策略：

```json
{
  "target_object": "plastic_cup",
  "action": "pick",
  "constraints": {
    "spatial_relation": "right",
    "speed": "slow"
  }
}
```

上例当前返回 `CONSTRAINT_UNCONSUMED`，不会进入机械臂执行链。

## 组件职责

| 组件 | 负责 | 不负责 |
|---|---|---|
| LLM Planner | 语言归一化、对象类型、动作和语义约束 | 实时坐标、IK、轨迹和物理结果 |
| 感知或 VLM | 检测候选对象并按语义约束选择实例 | 规划机械臂轨迹 |
| RGB-D 与 tf2 | 从观测生成新鲜的 `world` Pose | 决定用户意图 |
| 状态机与策略层 | 校验任务、选择已验证的执行策略 | 自由补全未知目标 |
| MoveIt 2 与控制器 | IK、碰撞检查、轨迹规划和执行 | 判断自然语言含义 |
| MuJoCo | 接触、摩擦、抓取和放置的物理事实 | 替代 MoveIt Planning Scene |

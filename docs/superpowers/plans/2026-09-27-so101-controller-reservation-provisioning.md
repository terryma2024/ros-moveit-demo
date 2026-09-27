# SO-101 控制器私有预留凭据交付实施计划

> **执行方式：** 当前 GPT-6 Sol 单写者 inline 完成；每项先 RED 再 GREEN，不启动第二执行者。

**目标：** 在 broker 与控制器启动顺序不同的情况下，把本轮 broker 的进程身份和每个控制器的独立 capability 交给关闭状态的控制器服务。

**架构：** broker 自己生成秘密，在权限为 `0700` 的本轮目录原子发布两份二进制文件。控制器用 Linux 文件身份检查读回角色、session、PID/start ticks 与 capability。此计划只建立交付原语；生产插件的停稳/所有权 `arm` 和两个启动入口的接线留在 EXP-517 后续步骤，文件出现本身不给目标准入。

**技术栈：** Python 3、C++17、Linux `/proc`、ROS 2 Jazzy、pytest-xdist、colcon。

**规格：** [控制器目标预留传输规格](../specs/2026-09-27-so101-controller-reservation-transport-design.md)。

## 全局约束

- 只用当前 worktree、branch 和 `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`；保留原有 dirty 文件和证据。
- capability 不得进入 argv、环境变量、ROS 参数或日志；每个角色独立随机生成，文件只能在本轮私有目录发布一次。
- 文件头严格采用规格中的 `SOPR` 版本 `1` 和 `56 + session_length` 字节；无效文件、错误身份、符号链接、宽松权限和旧进程均拒绝。
- 交付成功不调用 `arm`，不启动 ROS/MuJoCo stack，不发送 goal，不操作真实机械臂。
- 测试使用本轮 evidence root 下此前不存在的 `/data` NVMe scratch，设置 `TMPDIR/TMP/TEMP` 并用实际 Python 验证。

## 审阅重点

- standalone 的文件可在 simulator 启动后出现；worker 的文件可在 simulator 启动前出现。读取方对缺失文件保持关闭，对非法文件明确失败。
- PID 被复用或 broker 已退出时，即使 UID 与 capability 匹配也不能接收旧身份。
- 另一个相同 UID 的本机进程仍在现有信任域内；文件权限不被描述为隔离同 UID 恶意进程。
- 原子发布不能覆盖前一份文件；读方不能接受尚未写完的临时文件或双链接瞬间。
- arm 与 gripper 的 role/session 不能互换，capability 不能重复使用。

### 1. broker 写入与格式

**文件：**

- 新建 `src/so101_demo_py/src/adapters/act/controller_reservation_provision.py`：构造二进制内容，取得当前 PID/start ticks，以私有临时文件和不覆盖发布写出，并返回仅供内存中的客户端使用的 capability。
- 新建 `src/so101_demo_py/test/test_controller_reservation_provision.py`：验证确切格式、权限、双角色独立、旧文件拒绝、错误目录和 symlink 拒绝；运行一个真实子进程检查 capability 未出现在 argv/env。

**接口：** `write_controller_reservation_provision(path: Path, *, role: str, session_id: str) -> bytes`。`role` 只接受 `arm|gripper`。路径是目标文件路径，不是目录；调用者独占本轮私有目录。

- [ ] 先写定向测试并运行至缺少模块/函数的 RED；记录退出码和 scratch。
- [ ] 实现上面的唯一公开接口。临时文件必须先完整写入，再用不覆盖目标的原子发布；任何失败清理自己的临时文件，不碰已有目标。
- [ ] 定向 GREEN；运行普通 source Python 全量 `src/so101_demo_py/test/ -n 8`，记录 JUnit、跳过数和耗时。
- [ ] 只提交本项的源文件、测试和必要规格修订，不夹带现有 dirty batch。

### 2. 控制器读回与真实跨进程校验

**文件：**

- 新建 `src/so101_mujoco_support/include/so101_mujoco_support/controller_reservation_provision.hpp` 与 `src/so101_mujoco_support/src/controller_reservation_provision.cpp`：Linux 只读加载器，验证路径、文件元数据、固定格式和当前进程出生标识，返回现有 socket 所需的 peer/capability。
- 新建 `src/so101_mujoco_support/test/test_controller_reservation_provision.cpp`：由真实 Python 子进程写文件并保持存活，C++ 读回并核对；退出、错误角色/session、截断、追加、symlink、权限、旧文件都拒绝。
- 修改 `src/so101_mujoco_support/CMakeLists.txt`：把加载器加入现有预留库并注册测试。

**接口：** `read_controller_reservation_provision(path, expected_role, expected_session) -> ControllerReservationProvision`；返回 `ControllerReservationSocket::ExpectedPeer` 与 `ControllerReservationCapability`，不触及 `ControllerGoalAdmission`。

- [ ] 先写 C++ 定向测试，编译到缺少加载器的预期 RED。
- [ ] 实现只读加载器；不在 ROS graph、参数或日志暴露 capability。
- [ ] 定向 GREEN；在现有 overlay 上完整 build、`colcon test --packages-select so101_mujoco_support` 和 `test-result --verbose`，再做只读 `ament_uncrustify`。
- [ ] 记录源码/执行文件、ROS domain、scratch、RED/GREEN/全量门禁、证据哈希。更新 EXP-517 账本并提交本项文件。

两个原语都通过后，下一步才接入 standalone/worker 生命周期及本地停稳所有权证明。没有这两项时，控制器保持默认关闭。

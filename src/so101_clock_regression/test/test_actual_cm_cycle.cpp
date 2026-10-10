#include <chrono>
#include <functional>
#include <memory>
#include <thread>
#include <vector>
#include <iostream>
#include <dlfcn.h>
#include <filesystem>
#include "gtest/gtest.h"
#include "controller_manager/controller_manager.hpp"
#include "joint_trajectory_controller/joint_trajectory_controller.hpp"
#include "rosgraph_msgs/msg/clock.hpp"
#include "mujoco_ros2_control/control_cycle.hpp"

using namespace std::chrono_literals;
using Native = joint_trajectory_controller::JointTrajectoryController;
struct Sample {int64_t time; int64_t period;};
// Expose existing lifecycle operations without replacing their implementation.
class ManagerAccess : public controller_manager::ControllerManager {
public:
  using controller_manager::ControllerManager::ControllerManager;
  using controller_manager::ControllerManager::activate_controllers;
  using controller_manager::ControllerManager::deactivate_controllers;
  struct OperationInput {mujoco_ros2_control::CycleOperation operation; Sample sample;};
  std::vector<OperationInput> operations;
  void read(const rclcpp::Time & time, const rclcpp::Duration & period) {
    operations.push_back({mujoco_ros2_control::CycleOperation::Read,
      {time.nanoseconds(), period.nanoseconds()}});
    controller_manager::ControllerManager::read(time, period);
  }
  controller_interface::return_type update(const rclcpp::Time & time, const rclcpp::Duration & period) {
    operations.push_back({mujoco_ros2_control::CycleOperation::Update,
      {time.nanoseconds(), period.nanoseconds()}});
    return controller_manager::ControllerManager::update(time, period);
  }
  void write(const rclcpp::Time & time, const rclcpp::Duration & period) {
    operations.push_back({mujoco_ros2_control::CycleOperation::Write,
      {time.nanoseconds(), period.nanoseconds()}});
    controller_manager::ControllerManager::write(time, period);
  }
};
// Observe the inputs at the real native update entry, then execute its original body.
class ObservedNative : public Native {
public:
  explicit ObservedNative(int rate = 500) : rate_(rate) {}
  std::vector<Sample> samples;
  std::function<void()> after_native;
  controller_interface::return_type update(
    const rclcpp::Time & time, const rclcpp::Duration & period) override {
    samples.push_back({time.nanoseconds(), period.nanoseconds()});
    const auto result = Native::update(time, period);
    if (after_native) {after_native();}
    return result;
  }
  rclcpp::NodeOptions define_custom_node_options() const override {
    auto options = Native::define_custom_node_options();
    options.parameter_overrides({
      rclcpp::Parameter("update_rate", rate_),
      rclcpp::Parameter("joints", std::vector<std::string>{"neck_yaw_joint"}),
      rclcpp::Parameter("command_interfaces", std::vector<std::string>{"position"}),
      rclcpp::Parameter("state_interfaces", std::vector<std::string>{"position", "velocity"})});
    return options;
  }
private:
  int rate_;
};

class ActualCM : public ::testing::Test {
protected:
  static void SetUpTestSuite() {rclcpp::init(0, nullptr);}
  static void TearDownTestSuite() {rclcpp::shutdown();}
  std::shared_ptr<rclcpp::executors::SingleThreadedExecutor> executor;
  std::shared_ptr<ManagerAccess> cm;
  std::shared_ptr<rclcpp::Node> publisher_node;
  rclcpp::Publisher<rosgraph_msgs::msg::Clock>::SharedPtr publisher;
  std::vector<std::shared_ptr<ObservedNative>> natives;
  std::vector<hardware_interface::CommandInterface::SharedPtr> commands;
  std::vector<hardware_interface::StateInterface::SharedPtr> states;
  virtual int neck_rate() const {return 500;}
  virtual bool sim_time() const {return true;}
  virtual bool start_clock() const {return true;}
  void SetUp() override {
    Dl_info manager_library{};
    ASSERT_NE(dladdr(reinterpret_cast<void*>(&controller_manager::get_cm_node_options),
      &manager_library), 0);
    ASSERT_NE(manager_library.dli_fname, nullptr);
    ASSERT_EQ(std::filesystem::canonical(manager_library.dli_fname),
      std::filesystem::canonical(EXPECTED_CM_LIBRARY));
    // GCC/Clang on Linux/macOS use this Itanium symbol for the qualified
    // Native::update call below. Check the function, since an ELF copy
    // relocation can put even the real Native vtable in this executable.
    const auto native_update = dlsym(RTLD_DEFAULT,
      "_ZN27joint_trajectory_controller25JointTrajectoryController6updateERKN6rclcpp4TimeERKNS1_8DurationE");
    ASSERT_NE(native_update, nullptr) << dlerror();
    Dl_info native_library{};
    ASSERT_NE(dladdr(native_update, &native_library), 0);
    ASSERT_NE(native_library.dli_fname, nullptr);
    ASSERT_EQ(std::filesystem::canonical(native_library.dli_fname),
      std::filesystem::canonical(EXPECTED_NATIVE_LIBRARY));
    std::cout << "ACTUAL_CM_DSO " << manager_library.dli_fname << '\n'
      << "ACTUAL_NATIVE_DSO " << native_library.dli_fname << '\n';
    executor = std::make_shared<rclcpp::executors::SingleThreadedExecutor>();
    auto options = controller_manager::get_cm_node_options();
    options.parameter_overrides({rclcpp::Parameter("use_sim_time", sim_time()),
      rclcpp::Parameter("update_rate", 500)});
    auto rm_node = std::make_shared<rclcpp::Node>("regression_rm");
    auto rm = std::make_unique<hardware_interface::ResourceManager>(
      rm_node->get_node_clock_interface(), rm_node->get_node_logging_interface());
    cm = std::make_shared<ManagerAccess>(
      std::move(rm), executor, "regression_cm", "", options);
    std_msgs::msg::String description;
    description.data = "<robot name='cycle'><link name='base'/><link name='head'/>"
      "<joint name='neck_yaw_joint' type='revolute'><parent link='base'/>"
      "<child link='head'/><axis xyz='0 0 1'/>"
      "<limit lower='-3' upper='3' effort='1' velocity='1'/></joint>"
      "<ros2_control name='cycle_hardware' type='system'><hardware>"
      "<plugin>mock_components/GenericSystem</plugin></hardware>"
      "<joint name='neck_yaw_joint'><command_interface name='position'/>"
      "<state_interface name='position'><param name='initial_value'>0</param>"
      "</state_interface><state_interface name='velocity'>"
      "<param name='initial_value'>0</param></state_interface>"
      "</joint></ros2_control></robot>";
    cm->robot_description_callback(description);
    executor->add_node(cm);
    publisher_node = std::make_shared<rclcpp::Node>("regression_clock_publisher");
    publisher = publisher_node->create_publisher<rosgraph_msgs::msg::Clock>(
      "/clock", rclcpp::ClockQoS());
    executor->add_node(publisher_node);
    if (sim_time() && start_clock()) {tick(10000000000LL);}
    for (const std::string name : {"arm_controller", "gripper_controller", "neck_controller"}) {
      auto native = std::make_shared<ObservedNative>(name == "neck_controller" ? neck_rate() : 500);
      controller_manager::ControllerSpec spec;
      spec.c = native;spec.info.name = name;
      spec.info.type = "joint_trajectory_controller/JointTrajectoryController";
      spec.last_update_cycle_time = std::make_shared<rclcpp::Time>(
        0, 0, cm->get_trigger_clock()->get_clock_type());
      ASSERT_TRUE(cm->add_controller(spec));
      ASSERT_EQ(cm->configure_controller(name), controller_interface::return_type::OK);
      ASSERT_FALSE(native->is_async());
      hardware_interface::InterfaceInfo position;position.name = "position";position.initial_value = "0";
      hardware_interface::InterfaceInfo velocity;velocity.name = "velocity";velocity.initial_value = "0";
      auto command = std::make_shared<hardware_interface::CommandInterface>(
        hardware_interface::InterfaceDescription("neck_yaw_joint", position));
      auto pos = std::make_shared<hardware_interface::StateInterface>(
        hardware_interface::InterfaceDescription("neck_yaw_joint", position));
      auto vel = std::make_shared<hardware_interface::StateInterface>(
        hardware_interface::InterfaceDescription("neck_yaw_joint", velocity));
      commands.push_back(command);states.push_back(pos);states.push_back(vel);
      std::vector<hardware_interface::LoanedCommandInterface> loaned_commands;
      loaned_commands.emplace_back(command, []() {});
      std::vector<hardware_interface::LoanedStateInterface> loaned_states;
      loaned_states.emplace_back(pos);loaned_states.emplace_back(vel);
      native->assign_interfaces(std::move(loaned_commands), std::move(loaned_states));
      ASSERT_EQ(native->get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
      natives.push_back(native);
    }
  }
  void TearDown() override {
    for (auto & n : natives) {n->after_native = {};n->get_node()->deactivate();n->release_interfaces();}
    if (executor && cm) {executor->remove_node(cm);}
    if (executor && publisher_node) {executor->remove_node(publisher_node);}
    cm.reset();natives.clear();executor.reset();publisher.reset();publisher_node.reset();
  }
  void tick(int64_t ns) {
    rosgraph_msgs::msg::Clock message;message.clock = rclcpp::Time(ns, RCL_ROS_TIME);
    const auto deadline = std::chrono::steady_clock::now() + 2s;
    while (cm->now().nanoseconds() != ns && std::chrono::steady_clock::now() < deadline) {
      publisher->publish(message);executor->spin_some();std::this_thread::sleep_for(1ms);
    }
    ASSERT_EQ(cm->now().nanoseconds(), ns);
    ASSERT_TRUE(cm->get_clock()->started());
  }
  void update(int64_t ns, int64_t period = 2000000) {
    ASSERT_EQ(cm->update(rclcpp::Time(ns, RCL_ROS_TIME), rclcpp::Duration::from_nanoseconds(period)),
      controller_interface::return_type::OK);
    for (auto & n : natives) {
      ASSERT_FALSE(n->samples.empty());
      const auto s = n->samples.back();
      std::cout << "NATIVE_SAMPLE " << n->get_node()->get_name() << ' ' << ns << ' '
        << cm->now().nanoseconds() << ' ' << s.time << ' ' << s.period << '\n';
    }
  }
  void expect(int64_t ns, int64_t period) {
    for (auto & n : natives) {
      ASSERT_FALSE(n->samples.empty());
      EXPECT_EQ(n->samples.back().time, ns) << n->get_node()->get_name();
      EXPECT_EQ(n->samples.back().period, period) << n->get_node()->get_name();
    }
  }
  void exercise_outer_cycle(bool traced) {
    using mujoco_ros2_control::CycleOperation;
    update(10000000000LL);cm->operations.clear();
    tick(10002000000LL);const auto sampled = cm->now();
    std::vector<std::string> callbacks;
    std::vector<ManagerAccess::OperationInput> trace;
    size_t getters = 0;
    const bool complete = mujoco_ros2_control::execute_control_cycle(
      *cm, sampled, rclcpp::Duration::from_nanoseconds(2000000), true,
      [&] {++getters;return cm->now();},
      [&](CycleOperation phase) {if(traced)callbacks.push_back("begin"+std::to_string(int(phase)));return uint64_t(17);},
      [&](CycleOperation phase, const rclcpp::Time & time, uint64_t start) {
        if(traced) {EXPECT_EQ(start,17u);callbacks.push_back("end"+std::to_string(int(phase)));
          trace.push_back({phase,{time.nanoseconds(),2000000}});}
        if(phase==CycleOperation::Update)tick(10006000000LL);
      },
      [&] {callbacks.push_back("probe");tick(10004000000LL);return true;});
    EXPECT_TRUE(complete);EXPECT_EQ(getters,0u);
    ASSERT_EQ(cm->operations.size(),3u);
    for(size_t index=0;index<3;++index) {
      EXPECT_EQ(int(cm->operations[index].operation),int(index));
      EXPECT_EQ(cm->operations[index].sample.time,10002000000LL);
      EXPECT_EQ(cm->operations[index].sample.period,2000000);
    }
    expect(10002000000LL,2000000);
    EXPECT_EQ(cm->now().nanoseconds(),10006000000LL);
    if(traced) {
      EXPECT_EQ(callbacks,(std::vector<std::string>{"begin0","end0","probe","begin1","end1","begin2","end2"}));
      ASSERT_EQ(trace.size(),3u);
      for(size_t index=0;index<3;++index)EXPECT_EQ(trace[index].sample.time,cm->operations[index].sample.time);
    } else {EXPECT_EQ(callbacks,(std::vector<std::string>{"probe"}));EXPECT_TRUE(trace.empty());}
  }
};

TEST_F(ActualCM, SharedProductionTracedDispatchKeepsReadUpdateWriteCoherent) {exercise_outer_cycle(true);}
TEST_F(ActualCM, SharedProductionUntracedDispatchKeepsReadUpdateWriteCoherent) {exercise_outer_cycle(false);}

TEST_F(ActualCM, SharedDispatchProbeRefusalStopsBeforeUpdateAndWrite) {
  using mujoco_ros2_control::CycleOperation;
  size_t endings=0;
  const bool complete=mujoco_ros2_control::execute_control_cycle(
    *cm,cm->now(),rclcpp::Duration::from_nanoseconds(2000000),true,
    [&]{return cm->now();},[](CycleOperation){return uint64_t(0);},
    [&](CycleOperation,const rclcpp::Time &,uint64_t){++endings;},[]{return false;});
  EXPECT_FALSE(complete);ASSERT_EQ(cm->operations.size(),1u);
  EXPECT_EQ(cm->operations.front().operation,CycleOperation::Read);EXPECT_EQ(endings,1u);
  for(auto & n:natives)EXPECT_TRUE(n->samples.empty());
}

TEST_F(ActualCM, RealClockAdvanceAfterReadUsesSampledCycleAtNativeBoundary) {
  update(10000000000LL);expect(10000000000LL, 2000000);
  tick(10002000000LL);const auto sampled = cm->now();
  cm->read(sampled, rclcpp::Duration::from_nanoseconds(2000000));
  tick(10004000000LL);
  update(sampled.nanoseconds());expect(10002000000LL, 2000000);
  update(cm->now().nanoseconds());expect(10004000000LL, 2000000);
}

TEST_F(ActualCM, GenuineSampledGapAndDuplicateRemainVisible) {
  update(10000000000LL);
  tick(10004000000LL);update(10004000000LL, 4000000);expect(10004000000LL, 4000000);
  update(10004000000LL, 0);expect(10004000000LL, 0);
}

TEST_F(ActualCM, ClockAdvanceBetweenControllersKeepsCycleCoherent) {
  update(10000000000LL);
  tick(10002000000LL);
  const auto ordered = cm->get_loaded_controllers();
  auto first = std::dynamic_pointer_cast<ObservedNative>(ordered.front().c);
  ASSERT_TRUE(first);
  first->after_native = [this]() {tick(10004000000LL);};
  update(10002000000LL);first->after_native = {};
  expect(10002000000LL, 2000000);
  update(10004000000LL);expect(10004000000LL, 2000000);
}

TEST_F(ActualCM, OrdinaryCyclesRemainTwoMilliseconds) {
  for (int64_t index = 0; index < 8; ++index) {
    const auto ns = 10000000000LL + index * 2000000;
    tick(ns);update(ns);expect(ns, 2000000);
  }
}

TEST_F(ActualCM, BackwardsClockAndReactivationKeepExistingSemantics) {
  update(10000000000LL);
  tick(9998000000LL);update(9998000000LL, -2000000);expect(9998000000LL, -2000000);
  for (auto & n : natives) {
    ASSERT_EQ(n->get_node()->deactivate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
    ASSERT_EQ(n->get_node()->activate().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  }
  tick(10000000000LL);update(10000000000LL);expect(10000000000LL, 2000000);
}

TEST_F(ActualCM, ActualManagerReactivationResetsFirstPeriodAfterLongGap) {
  update(10000000000LL);
  const auto ordered = cm->get_loaded_controllers();
  cm->deactivate_controllers(ordered, {"arm_controller", "gripper_controller", "neck_controller"});
  for (auto & n : natives) {
    ASSERT_EQ(n->get_lifecycle_state().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_INACTIVE);
  }
  tick(11000000000LL);
  cm->activate_controllers(ordered, {"neck_controller"},
    controller_manager_msgs::srv::SwitchController::Request::STRICT);
  ASSERT_EQ(natives.back()->get_lifecycle_state().id(), lifecycle_msgs::msg::State::PRIMARY_STATE_ACTIVE);
  ASSERT_EQ(cm->update(cm->now(), rclcpp::Duration::from_nanoseconds(2000000)),
    controller_interface::return_type::OK);
  ASSERT_EQ(natives.back()->samples.size(), 2u);
  EXPECT_EQ(natives.back()->samples.back().time, 11000000000LL);
  EXPECT_EQ(natives.back()->samples.back().period, 2000000);
}

class UnstartedCM : public ActualCM {
protected:
  bool start_clock() const override {return false;}
};
TEST_F(UnstartedCM, ZeroUnstartedClockRefusesThenFirstClockStartsNormally) {
  ASSERT_FALSE(cm->get_clock()->started());
  EXPECT_THROW(cm->update(rclcpp::Time(0, 0, RCL_ROS_TIME),
    rclcpp::Duration::from_nanoseconds(2000000)), std::runtime_error);
  for (auto & n : natives) {EXPECT_TRUE(n->samples.empty());}
  tick(10000000000LL);update(10000000000LL);expect(10000000000LL, 2000000);
}

TEST_F(UnstartedCM, SharedDispatchPropagatesActualUpdateExceptionWithoutWriteOrEnd) {
  using mujoco_ros2_control::CycleOperation;
  std::vector<CycleOperation> endings;
  EXPECT_THROW(mujoco_ros2_control::execute_control_cycle(
    *cm,rclcpp::Time(0,0,RCL_ROS_TIME),rclcpp::Duration::from_nanoseconds(2000000),true,
    [&]{return cm->now();},[](CycleOperation){return uint64_t(0);},
    [&](CycleOperation phase,const rclcpp::Time &,uint64_t){endings.push_back(phase);},[]{return true;}),std::runtime_error);
  ASSERT_EQ(cm->operations.size(),2u);
  EXPECT_EQ(cm->operations.back().operation,CycleOperation::Update);
  EXPECT_EQ(endings,(std::vector<CycleOperation>{CycleOperation::Read}));
}

class LowerRateCM : public ActualCM {
protected:
  int neck_rate() const override {return 125;}
};
TEST_F(LowerRateCM, LowerRateKeepsElapsedTimeSinceActualDispatch) {
  update(10000000000LL);
  ASSERT_EQ(natives.back()->get_update_rate(), 125u);
  ASSERT_EQ(natives.back()->samples.size(), 1u);
  EXPECT_EQ(natives.back()->samples.back().period, 8000000);
  for (int64_t index = 1; index < 4; ++index) {
    const auto ns = 10000000000LL + index * 2000000;
    tick(ns);update(ns);
    EXPECT_EQ(natives.back()->samples.size(), 1u);
  }
  tick(10008000000LL);const auto sampled = cm->now();tick(10010000000LL);
  update(sampled.nanoseconds());
  ASSERT_EQ(natives.back()->samples.size(), 2u);
  EXPECT_EQ(natives.back()->samples.back().time, 10008000000LL);
  EXPECT_EQ(natives.back()->samples.back().period, 8000000);
}

class NonSimCM : public ActualCM {
protected:
  bool sim_time() const override {return false;}
};
TEST_F(NonSimCM, SharedProductionDispatchSamplesFreshSteadyTimeForEveryOperation) {
  using mujoco_ros2_control::CycleOperation;
  size_t getters=0;
  EXPECT_TRUE(mujoco_ros2_control::execute_control_cycle(
    *cm,rclcpp::Time(10000000000LL,RCL_STEADY_TIME),rclcpp::Duration::from_nanoseconds(2000000),false,
    [&]{++getters;return cm->get_trigger_clock()->now();},
    [](CycleOperation){std::this_thread::sleep_for(1ms);return uint64_t(0);},
    [](CycleOperation,const rclcpp::Time &,uint64_t){},[]{return true;}));
  EXPECT_EQ(getters,3u);ASSERT_EQ(cm->operations.size(),3u);
  EXPECT_GT(cm->operations[1].sample.time,cm->operations[0].sample.time);
  EXPECT_GT(cm->operations[2].sample.time,cm->operations[1].sample.time);
}

// Only an otherwise unreachable update-return branch uses a narrow double.
TEST(ControlCycleReturnContract, NonOkUpdateReturnDoesNotAddANewEarlyExit) {
  struct ReturningManager {
    std::vector<int> calls;
    void read(const rclcpp::Time &,const rclcpp::Duration &){calls.push_back(0);}
    controller_interface::return_type update(const rclcpp::Time &,const rclcpp::Duration &){calls.push_back(1);return controller_interface::return_type::ERROR;}
    void write(const rclcpp::Time &,const rclcpp::Duration &){calls.push_back(2);}
  } manager;
  using mujoco_ros2_control::CycleOperation;
  const auto time=rclcpp::Time(1,0,RCL_ROS_TIME);
  EXPECT_TRUE(mujoco_ros2_control::execute_control_cycle(manager,time,rclcpp::Duration::from_nanoseconds(2000000),true,
    [&]{return time;},[](CycleOperation){return uint64_t(0);},
    [](CycleOperation,const rclcpp::Time &,uint64_t){},[]{return true;}));
  EXPECT_EQ(manager.calls,(std::vector<int>{0,1,2}));
}
TEST_F(NonSimCM, NonSimNativeTimestampAndPeriodStillUseOriginalClocks) {
  const auto fake_caller = rclcpp::Time(10000000000LL, RCL_STEADY_TIME);
  const auto period = rclcpp::Duration::from_nanoseconds(2000000);
  ASSERT_EQ(cm->get_trigger_clock()->get_clock_type(), RCL_STEADY_TIME);
  const auto before = cm->now().nanoseconds();
  ASSERT_EQ(cm->update(fake_caller, period), controller_interface::return_type::OK);
  const auto after = cm->now().nanoseconds();
  for (auto & n : natives) {
    ASSERT_EQ(n->samples.size(), 1u);
    EXPECT_GE(n->samples.back().time, before);
    EXPECT_LE(n->samples.back().time, after);
    EXPECT_NE(n->samples.back().time, fake_caller.nanoseconds());
    EXPECT_EQ(n->samples.back().period, 2000000);
  }
  std::this_thread::sleep_for(3ms);
  ASSERT_EQ(cm->update(fake_caller, period), controller_interface::return_type::OK);
  for (auto & n : natives) {
    ASSERT_EQ(n->samples.size(), 2u);
    EXPECT_GT(n->samples.back().period, 0);
    EXPECT_LT(n->samples.back().period, 500000000);
  }
}

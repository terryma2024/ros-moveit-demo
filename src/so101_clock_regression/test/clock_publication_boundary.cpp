#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <realtime_tools/realtime_publisher.hpp>
#include <mujoco/mujoco.h>
#include <mujoco_ros2_control/clock_trace.hpp>
#include <nlohmann/json.hpp>
#include <dlfcn.h>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <thread>
#include <vector>

// Deliberately reduced fixture class. The included method body is extracted verbatim
// from the bound production source; all publisher, context, time and trace types are real.
namespace mujoco_ros2_control {
class MujocoSimulation {
public:
  void publish_clock();
  void record_transition_for_testing(const char*) {}
  rclcpp::Node::SharedPtr node_;
  mjData data_{};
  mjData* mj_data_{&data_};
  std::shared_ptr<rclcpp::Publisher<rosgraph_msgs::msg::Clock>> clock_publisher_;
  realtime_tools::RealtimePublisher<rosgraph_msgs::msg::Clock>::SharedPtr clock_realtime_publisher_;
  std::unique_ptr<ClockTrace> clock_trace_;
  uint64_t diagnostic_successful_step_{1};
};
#include "publish_clock_body.inc"
}

class LegacySlotLock {
public:
  explicit LegacySlotLock(realtime_tools::RealtimePublisher<rosgraph_msgs::msg::Clock>& p):publisher_(p){publisher_.lock();}
  ~LegacySlotLock(){publisher_.unlock();}
private:
  realtime_tools::RealtimePublisher<rosgraph_msgs::msg::Clock>& publisher_;
};

class ClockPublicationBoundary:public ::testing::Test {
protected:
  void SetUp() override {
    context_=std::make_shared<rclcpp::Context>();context_->init(0,nullptr);
    simulation_.node_=std::make_shared<rclcpp::Node>("clock_publication_boundary",rclcpp::NodeOptions().context(context_));
    rclcpp::ExecutorOptions options;options.context=context_;
    executor_=std::make_unique<rclcpp::executors::SingleThreadedExecutor>(options);
    executor_->add_node(simulation_.node_);
    simulation_.clock_publisher_=simulation_.node_->create_publisher<rosgraph_msgs::msg::Clock>("/boundary_clock",1);
    simulation_.clock_realtime_publisher_=std::make_shared<realtime_tools::RealtimePublisher<rosgraph_msgs::msg::Clock>>(simulation_.clock_publisher_);
    subscription_=simulation_.node_->create_subscription<rosgraph_msgs::msg::Clock>("/boundary_clock",rclcpp::QoS(10),[this](const rosgraph_msgs::msg::Clock& message){received_.push_back(rclcpp::Time(message.clock,RCL_ROS_TIME).nanoseconds());});
    ASSERT_TRUE(wait_until([this]{return subscription_->get_publisher_count()==1;}));
    directory_=std::filesystem::path(std::getenv("TMPDIR"))/::testing::UnitTest::GetInstance()->current_test_info()->name();
    ASSERT_TRUE(std::filesystem::create_directory(directory_));
    simulation_.clock_trace_=std::make_unique<mujoco_ros2_control::ClockTrace>(directory_.string(),"{\"scope\":\"exact_method_fixture\",\"clock_publication_mode\":\"direct_publish_return_v1\"}","physics",256);
  }
  void TearDown() override {
    simulation_.clock_trace_.reset();
    simulation_.clock_realtime_publisher_.reset();
    subscription_.reset();executor_.reset();simulation_.clock_publisher_.reset();simulation_.node_.reset();
    if(context_->is_valid())context_->shutdown("boundary test complete");
  }
  template<class Predicate> bool wait_until(Predicate predicate) {
    const auto end=std::chrono::steady_clock::now()+std::chrono::milliseconds(500);
    while(std::chrono::steady_clock::now()<end){executor_->spin_some();if(predicate())return true;std::this_thread::sleep_for(std::chrono::milliseconds(1));}
    return predicate();
  }
  std::vector<std::array<uint64_t,11>> closed_records() {
    EXPECT_TRUE(simulation_.clock_trace_->finish());
    std::ifstream input(directory_/"physics.bin",std::ios::binary);char magic[8];uint64_t header_size;
    input.read(magic,8);input.read(reinterpret_cast<char*>(&header_size),8);input.seekg(header_size,std::ios::cur);
    std::vector<std::array<uint64_t,11>> rows;std::array<uint64_t,11> row;
    while(input.read(reinterpret_cast<char*>(row.data()),88))rows.push_back(row);
    return rows;
  }
  mujoco_ros2_control::MujocoSimulation simulation_;
  std::shared_ptr<rclcpp::Context> context_;
  std::unique_ptr<rclcpp::executors::SingleThreadedExecutor> executor_;
  rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr subscription_;
  std::vector<int64_t> received_;
  std::filesystem::path directory_;
};

TEST_F(ClockPublicationBoundary, BusyLegacySlotCannotDiscardCommittedTick) {
  simulation_.data_.time=13.382;
  {LegacySlotLock pressure(*simulation_.clock_realtime_publisher_);simulation_.publish_clock();}
  ASSERT_TRUE(wait_until([this]{return received_.size()==1;}));
  EXPECT_EQ(received_[0],13382000000);
  EXPECT_DOUBLE_EQ(simulation_.data_.time,13.382);
}
TEST_F(ClockPublicationBoundary, BusyLegacySlotCannotOmitSecondActualTick) {
  simulation_.data_.time=13.380;simulation_.publish_clock();
  ASSERT_TRUE(wait_until([this]{return received_.size()==1;}));
  simulation_.data_.time=13.382;
  {LegacySlotLock pressure(*simulation_.clock_realtime_publisher_);simulation_.publish_clock();}
  ASSERT_TRUE(wait_until([this]{return received_.size()==2;}));
  EXPECT_EQ(received_,(std::vector<int64_t>{13380000000,13382000000}));
}
TEST_F(ClockPublicationBoundary, InvalidActualContextIsExplicitlyExcluded) {
  ASSERT_TRUE(context_->shutdown("actual shutdown regression"));
  simulation_.data_.time=13.382;simulation_.publish_clock();
  const auto rows=closed_records();ASSERT_EQ(rows.size(),2u);
  EXPECT_EQ(rows.back()[0],4u);EXPECT_EQ(rows.back()[5],11u);
  EXPECT_TRUE(received_.empty());
}
TEST_F(ClockPublicationBoundary, NormalClockPreservesActualQuantizedTime) {
  simulation_.data_.time=std::nextafter(19.630,0.0);simulation_.publish_clock();
  ASSERT_TRUE(wait_until([this]{return received_.size()==1;}));
  EXPECT_EQ(received_[0],19630000000);
  EXPECT_DOUBLE_EQ(simulation_.data_.time,std::nextafter(19.630,0.0));
}
TEST_F(ClockPublicationBoundary, CompiledTraceDeclaresDirectReturnSemantics) {
  simulation_.data_.time=13.382;simulation_.publish_clock();
  const auto rows=closed_records();ASSERT_EQ(rows.size(),2u);EXPECT_EQ(rows.back()[5],10u);
  std::ifstream input(directory_/"physics.bin",std::ios::binary);char magic[8];uint64_t size;
  input.read(magic,8);input.read(reinterpret_cast<char*>(&size),8);
  std::string header(size,'\0');input.read(header.data(),size);
  const auto parsed=nlohmann::json::parse(header);
  EXPECT_EQ(parsed.value("clock_publication_mode","MISSING"),"direct_publish_return_v1");
  Dl_info library{};
  ASSERT_NE(dladdr(reinterpret_cast<void*>(&mujoco_ros2_control::ClockTrace::monotonic_ns),&library),0);
  ASSERT_NE(library.dli_fname,nullptr);
  EXPECT_EQ(std::filesystem::canonical(library.dli_fname),std::filesystem::canonical(std::getenv("CLOCK_EXPECTED_TRACE_LIBRARY")));
}

#include <chrono>
#include <condition_variable>
#include <future>
#include <limits>
#include <mutex>

#include <gtest/gtest.h>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>

#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/node_spinner.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

class FakeCancellation final : public spp::IRequestScopedGoalCancellation
{
public:
  spp::ActionResult requestCancel(double) override
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      cancel_requested_ = true;
    }
    cv_.notify_all();
    return cancel_result;
  }

  std::optional<spp::RequestScopedGoalTerminal> waitForTerminal(double timeout_seconds) override
  {
    std::unique_lock<std::mutex> lock(mutex_);
    cv_.wait_for(lock, std::chrono::duration<double>(timeout_seconds),
                 [this] { return terminal_.has_value(); });
    return terminal_;
  }

  void waitUntilCancelRequested()
  {
    std::unique_lock<std::mutex> lock(mutex_);
    cv_.wait(lock, [this] { return cancel_requested_; });
  }

  void setTerminal(spp::RequestScopedGoalTerminal terminal)
  {
    {
      std::lock_guard<std::mutex> lock(mutex_);
      terminal_ = terminal;
    }
    cv_.notify_all();
  }

  spp::ActionResult cancel_result{spp::ActionStatus::SUCCEEDED, std::nullopt};

private:
  std::mutex mutex_;
  std::condition_variable cv_;
  bool cancel_requested_{false};
  std::optional<spp::RequestScopedGoalTerminal> terminal_;
};

}  // namespace

TEST(RequestScopedGoalCancellation, WaitsForDelayedTerminalAfterCancelAcknowledgement)
{
  FakeCancellation goal;
  auto result = std::async(std::launch::async, [&goal] {
    return spp::cancelRequestScopedGoalAndWait(goal, 0.1, 0.5);
  });
  goal.waitUntilCancelRequested();
  EXPECT_EQ(result.wait_for(std::chrono::milliseconds(10)), std::future_status::timeout);
  goal.setTerminal(spp::RequestScopedGoalTerminal::CANCELED);
  EXPECT_EQ(result.wait_for(std::chrono::milliseconds(100)), std::future_status::ready);
  EXPECT_EQ(result.get().status, spp::ActionStatus::SUCCEEDED);
}

TEST(RequestScopedGoalCancellation, FailsClosedWhenGoalNeverBecomesTerminal)
{
  FakeCancellation goal;
  const auto result = spp::cancelRequestScopedGoalAndWait(goal, 0.01, 0.01);
  EXPECT_EQ(result.status, spp::ActionStatus::TIMED_OUT);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "MOVE_GROUP_CANCEL_TERMINAL_TIMEOUT");
}

TEST(RequestScopedGoalCancellation, PropagatesCancelAcknowledgementFailure)
{
  FakeCancellation goal;
  goal.cancel_result = {
    spp::ActionStatus::TIMED_OUT,
    spp::Failure{spp::FailureCategory::PLANNING, "MOVE_GROUP_CANCEL_ACK_TIMEOUT",
                 "cancel acknowledgement timed out", {}}};
  const auto result = spp::cancelRequestScopedGoalAndWait(goal, 0.01, 0.01);
  EXPECT_EQ(result.status, spp::ActionStatus::TIMED_OUT);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "MOVE_GROUP_CANCEL_ACK_TIMEOUT");
}

TEST(ValidatedMotionArtifact, ReconstructsTheExactValidatedTrajectoryWithoutPlanning)
{
  spp::MotionPlanArtifact artifact;
  artifact.trajectory_points = 2;
  artifact.joint_names = {"1", "2", "3", "4", "5"};
  artifact.start_joint_positions = {0.0, 0.1, 0.2, 0.3, 0.4};
  artifact.goal_joint_positions = {0.5, 0.6, 0.7, 0.8, 0.9};
  artifact.samples = {
    {spp::Pose3d{}, artifact.start_joint_positions, 0.0, true, {}, std::nullopt},
    {spp::Pose3d{}, artifact.goal_joint_positions, 1.25, true, {}, std::nullopt},
  };
  artifact.collision_aware = true;
  artifact.time_parameterized = true;
  artifact.moveit_success = true;

  const auto trajectory = spp::executableTrajectoryFromValidatedArtifact(
    artifact, {"1", "2", "3", "4", "5"});

  ASSERT_TRUE(trajectory);
  EXPECT_EQ(trajectory->joint_trajectory.joint_names, artifact.joint_names);
  ASSERT_EQ(trajectory->joint_trajectory.points.size(), 2U);
  EXPECT_EQ(trajectory->joint_trajectory.points[0].positions,
            artifact.start_joint_positions);
  EXPECT_EQ(trajectory->joint_trajectory.points[1].positions,
            artifact.goal_joint_positions);
  EXPECT_EQ(trajectory->joint_trajectory.points[1].time_from_start.sec, 1);
  EXPECT_EQ(trajectory->joint_trajectory.points[1].time_from_start.nanosec, 250000000U);
}

TEST(ValidatedMotionArtifact, RejectsAnythingThatIsNotCompleteValidatedEvidence)
{
  spp::MotionPlanArtifact artifact;
  artifact.trajectory_points = 1;
  artifact.joint_names = {"1", "2", "3", "4", "5"};
  artifact.samples.resize(1);
  artifact.samples[0].joint_positions = {0.0, 0.0, 0.0, 0.0, 0.0};
  artifact.samples[0].time_from_start_seconds = 1.0;

  EXPECT_FALSE(spp::executableTrajectoryFromValidatedArtifact(
    artifact, {"1", "2", "3", "4", "5"}));
  artifact.moveit_success = true;
  artifact.collision_aware = true;
  artifact.time_parameterized = true;
  artifact.trajectory_points = 2;
  artifact.start_joint_positions = artifact.samples[0].joint_positions;
  artifact.goal_joint_positions = {0.1, 0.1, 0.1, 0.1, 0.1};
  artifact.samples.push_back(
    {spp::Pose3d{}, artifact.goal_joint_positions, 2.0, true, {}, std::nullopt});
  EXPECT_TRUE(spp::executableTrajectoryFromValidatedArtifact(
    artifact, {"1", "2", "3", "4", "5"}));
  artifact.samples[0].joint_positions[0] = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(spp::executableTrajectoryFromValidatedArtifact(
    artifact, {"1", "2", "3", "4", "5"}));
}

TEST(CurrentJointStateEvidence, UsesTheReceivedJointMessageForAllSixJointsAndSourceAge)
{
  const auto & profile = spp::SO101Profile::canonical();
  sensor_msgs::msg::JointState message;
  message.name = {"6", "3", "1", "5", "2", "4"};
  message.position = {0.7, 0.3, 0.1, 0.5, 0.2, 0.4};
  message.velocity = {0.06, 0.03, 0.01, 0.05, 0.02, 0.04};
  message.header.stamp.sec = 17;
  const auto received_at = std::chrono::steady_clock::now();

  const auto evidence = spp::currentJointStateEvidenceFromMessage(
    message, profile, received_at);

  ASSERT_TRUE(evidence);
  EXPECT_EQ(evidence->joint_names, profile.arm_joints);
  EXPECT_EQ(evidence->positions, (std::vector<double>{0.1, 0.2, 0.3, 0.4, 0.5}));
  EXPECT_EQ(evidence->velocities, (std::vector<double>{0.01, 0.02, 0.03, 0.04, 0.05}));
  EXPECT_EQ(evidence->gripper_position, 0.7);
  EXPECT_EQ(evidence->gripper_velocity, 0.06);
  EXPECT_EQ(evidence->received_at, received_at);
  EXPECT_EQ(evidence->observed_stamp_nanoseconds, 17000000000ULL);

  message.velocity.clear();
  EXPECT_FALSE(spp::currentJointStateEvidenceFromMessage(message, profile, received_at));
}

TEST(MoveItJointPlanningBoundary, WaitsForTheFirstCompleteJointState)
{
  if (!rclcpp::ok()) rclcpp::init(0, nullptr);
  const auto isolated_topic = "/test/joint_state_wait";
  auto observer_node = std::make_shared<rclcpp::Node>(
    "joint_state_wait_observer",
    rclcpp::NodeOptions().arguments(
      {"--ros-args", "-r", "/joint_states:=" + std::string(isolated_topic)}));
  spp::NodeSpinner spinner(observer_node);
  spp::MoveItJointPlanningBoundary boundary(
    observer_node, spp::SO101Profile::canonical(), "RRTConnectkConfigDefault",
    0.1, 0.1, 0.5);
  auto publisher_node = std::make_shared<rclcpp::Node>("joint_state_wait_publisher");
  auto publisher = publisher_node->create_publisher<sensor_msgs::msg::JointState>(
    isolated_topic, rclcpp::SensorDataQoS());
  const auto discovery_deadline = std::chrono::steady_clock::now() +
                                  std::chrono::seconds(2);
  while (publisher->get_subscription_count() == 0 &&
         std::chrono::steady_clock::now() < discovery_deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  ASSERT_GT(publisher->get_subscription_count(), 0U);

  auto state = std::async(std::launch::async, [&boundary] { return boundary.currentState(); });
  EXPECT_EQ(std::future_status::timeout,
            state.wait_for(std::chrono::milliseconds(30)));

  sensor_msgs::msg::JointState message;
  message.name = {"1", "2", "3", "4", "5", "6"};
  message.position = {0.1, 0.2, 0.3, 0.4, 0.5, 0.795386732};
  message.velocity = {0.0, 0.0, 0.0, 0.0, 0.0, 0.0};
  publisher->publish(message);

  ASSERT_EQ(std::future_status::ready,
            state.wait_for(std::chrono::milliseconds(500)));
  const auto evidence = state.get();
  ASSERT_TRUE(evidence);
  EXPECT_EQ((std::vector<double>{0.1, 0.2, 0.3, 0.4, 0.5}), evidence->positions);
  EXPECT_DOUBLE_EQ(0.795386732, *evidence->gripper_position);
}

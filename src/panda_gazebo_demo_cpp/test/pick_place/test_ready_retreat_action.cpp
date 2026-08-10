#include <gtest/gtest.h>

#include <memory>
#include <string>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/ready_retreat_action.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

const std::map<std::string, double> kReadyJoints{{"panda_joint1", 0.0}, {"panda_joint2", -0.785}};

MotionPlanEvidence readyEvidence(State state, State next_state)
{
  MotionPlanEvidence evidence;
  evidence.state = state;
  evidence.next_state = next_state;
  evidence.kind = MotionKind::NAMED_TARGET;
  evidence.named_target = "ready";
  evidence.trajectory_points = 2;
  evidence.target_joint_positions = kReadyJoints;
  evidence.planned_end_joint_positions = kReadyJoints;
  return evidence;
}

WorldSnapshot readySnapshot(bool stationary = true)
{
  WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = stationary;
  snapshot.joint_positions = kReadyJoints;
  return snapshot;
}

ReadyRetreatConfig config(State state, State next_state)
{
  return {state, next_state, "ready", kReadyJoints, 0.010, 0.0, 0.0, 0.987};
}

class RecordingMotionAdapter final : public IMoveItMotionAdapter
{
public:
  PlanResult plan(const MotionPlanningRequest &, const ObservationResult &) override
  {
    return {{ActionStatus::NOT_SUPPORTED, std::nullopt}, nullptr};
  }

  PlanResult planSafeNamedTarget(const SafeNamedTargetPlanningRequest & request,
                                 const ObservationResult &) override
  {
    events->emplace_back("motion.plan_safe_named_target");
    safe_requests.push_back(request);
    const auto evidence =
      std::make_shared<MotionPlanEvidence>(readyEvidence(request.state, request.next_state));
    return {{ActionStatus::SUCCEEDED, std::nullopt}, evidence};
  }

  ActionResult execute(const MotionPlanEvidence &) override
  {
    events->emplace_back("motion.execute");
    return execution_result;
  }

  ActionResult cancel() override
  {
    events->emplace_back("motion.cancel");
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  std::shared_ptr<std::vector<std::string>> events{std::make_shared<std::vector<std::string>>()};
  std::vector<SafeNamedTargetPlanningRequest> safe_requests;
  ActionResult execution_result{ActionStatus::SUCCEEDED, std::nullopt};
};

class RecordingGripperAdapter final : public IGripperCommandAdapter
{
public:
  ActionResult command(double target_position, double max_effort) override
  {
    events->emplace_back("gripper.command");
    targets.emplace_back(target_position, max_effort);
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancelAndWait() override
  {
    events->emplace_back("gripper.cancel");
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  std::shared_ptr<std::vector<std::string>> events{std::make_shared<std::vector<std::string>>()};
  std::vector<std::pair<double, double>> targets;
};

class RecordingWorldObserver final : public IWorldObserver
{
public:
  explicit RecordingWorldObserver(WorldSnapshot snapshot) : snapshot_(std::move(snapshot)) {}

  ObservationResult observe() override
  {
    events->emplace_back("observer.observe");
    return {snapshot_, std::nullopt};
  }

  std::shared_ptr<std::vector<std::string>> events{std::make_shared<std::vector<std::string>>()};

private:
  WorldSnapshot snapshot_;
};

TEST(ReadyRetreatAction, ExecutesReadyArmThenObservesThenClosesGripper)
{
  const auto events = std::make_shared<std::vector<std::string>>();
  const auto motion = std::make_shared<RecordingMotionAdapter>();
  const auto gripper = std::make_shared<RecordingGripperAdapter>();
  const auto observer = std::make_shared<RecordingWorldObserver>(readySnapshot());
  motion->events = events;
  gripper->events = events;
  observer->events = events;
  ReadyRetreatAction action(motion, gripper, observer, config(State::RETREAT, State::DONE));

  const auto plan =
    action.plan(State::RETREAT, State::DONE, ObservationResult{readySnapshot(), std::nullopt});
  ASSERT_EQ(plan.action.status, ActionStatus::SUCCEEDED);
  ASSERT_TRUE(plan.artifact);
  const auto result = action.execute({State::RETREAT, State::DONE, readySnapshot(), plan.artifact});

  EXPECT_EQ(result.status, ActionStatus::SUCCEEDED);
  EXPECT_EQ(*events, (std::vector<std::string>{"motion.plan_safe_named_target", "motion.execute",
                                               "observer.observe", "gripper.command"}));
  ASSERT_EQ(motion->safe_requests.size(), 1U);
  EXPECT_DOUBLE_EQ(motion->safe_requests.front().clearance_pose.x,
                   readySnapshot().tcp_pose_world.x);
  EXPECT_DOUBLE_EQ(motion->safe_requests.front().clearance_pose.y,
                   readySnapshot().tcp_pose_world.y);
  EXPECT_DOUBLE_EQ(motion->safe_requests.front().clearance_pose.z, 0.987);
  ASSERT_EQ(gripper->targets.size(), 1U);
  EXPECT_DOUBLE_EQ(gripper->targets.front().first, 0.0);
}

TEST(ReadyRetreatAction, PlanningNeverCommandsGripper)
{
  const auto motion = std::make_shared<RecordingMotionAdapter>();
  const auto gripper = std::make_shared<RecordingGripperAdapter>();
  const auto observer = std::make_shared<RecordingWorldObserver>(readySnapshot());
  ReadyRetreatAction action(motion, gripper, observer,
                            config(State::RECOVER_RETREAT, State::ERROR));

  const auto plan = action.plan(State::RECOVER_RETREAT, State::ERROR,
                                ObservationResult{readySnapshot(), std::nullopt});

  EXPECT_EQ(plan.action.status, ActionStatus::SUCCEEDED);
  EXPECT_TRUE(gripper->targets.empty());
}

TEST(ReadyRetreatAction, ArmFailurePreventsGripperClose)
{
  const auto motion = std::make_shared<RecordingMotionAdapter>();
  const auto gripper = std::make_shared<RecordingGripperAdapter>();
  const auto observer = std::make_shared<RecordingWorldObserver>(readySnapshot());
  motion->execution_result = {ActionStatus::FAILED,
                              Failure{FailureCategory::EXECUTION, "ARM_FAILED", "arm failed", {}}};
  ReadyRetreatAction action(motion, gripper, observer, config(State::RETREAT, State::DONE));
  const auto plan =
    action.plan(State::RETREAT, State::DONE, ObservationResult{readySnapshot(), std::nullopt});
  ASSERT_TRUE(plan.artifact);

  const auto result = action.execute({State::RETREAT, State::DONE, readySnapshot(), plan.artifact});

  EXPECT_EQ(result.status, ActionStatus::FAILED);
  EXPECT_TRUE(gripper->targets.empty());
}

TEST(ReadyRetreatAction, NonstationaryArmPreventsGripperClose)
{
  const auto motion = std::make_shared<RecordingMotionAdapter>();
  const auto gripper = std::make_shared<RecordingGripperAdapter>();
  const auto observer = std::make_shared<RecordingWorldObserver>(readySnapshot(false));
  ReadyRetreatAction action(motion, gripper, observer, config(State::RETREAT, State::DONE));
  const auto plan =
    action.plan(State::RETREAT, State::DONE, ObservationResult{readySnapshot(), std::nullopt});
  ASSERT_TRUE(plan.artifact);

  const auto result = action.execute({State::RETREAT, State::DONE, readySnapshot(), plan.artifact});

  EXPECT_EQ(result.status, ActionStatus::FAILED);
  EXPECT_TRUE(gripper->targets.empty());
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place

#include <gtest/gtest.h>

#include <memory>
#include <optional>
#include <tuple>
#include <utility>
#include <vector>

#include "panda_gazebo_demo/pick_place/motion_state_action.hpp"

namespace panda_gazebo_demo::pick_place
{
namespace
{

class RecordingTargetPolicy final : public PickPlaceTargetPolicy
{
public:
  TargetPoseResult targetPose(
    State current_state, State next_state,
    const ObservationResult & observation) const override
  {
    calls.emplace_back(current_state, next_state, observation.snapshot.has_value());
    return {Pose3d{0.31, 0.12, 0.98, 1.0, 0.0, 0.0, 0.0}, std::nullopt};
  }

  std::string configurationSignature() const override
  {
    return "recording";
  }

  mutable std::vector<std::tuple<State, State, bool>> calls;
};

class RecordingMotionAdapter final : public IMoveItMotionAdapter
{
public:
  PlanResult plan(
    const MotionPlanningRequest & request,
    const ObservationResult & observation) override
  {
    requests.push_back(request);
    observations.push_back(observation);
    auto evidence = std::make_shared<MotionPlanEvidence>();
    evidence->state = request.state;
    evidence->next_state = request.next_state;
    evidence->kind = request.kind;
    evidence->carrying = request.carrying;
    evidence->trajectory_points = 1;
    return {{ActionStatus::SUCCEEDED, std::nullopt}, evidence};
  }

  ActionResult execute(const MotionPlanEvidence & evidence) override
  {
    executed_states.push_back(evidence.state);
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  ActionResult cancel() override
  {
    ++cancel_calls;
    return {ActionStatus::SUCCEEDED, std::nullopt};
  }

  std::vector<MotionPlanningRequest> requests;
  std::vector<ObservationResult> observations;
  std::vector<State> executed_states;
  int cancel_calls{0};
};

ObservationResult observation()
{
  WorldSnapshot snapshot;
  snapshot.fresh = true;
  return {snapshot, std::nullopt};
}

TEST(MotionStateAction, EveryForwardMotionUsesConfiguredTargetAndCarryingFlag)
{
  const std::vector<MotionStateConfig> configurations{
    {State::MOVE_ABOVE_OBJECT, State::DESCEND, MotionKind::POSE, false},
    {State::DESCEND, State::CLOSE_GRIPPER, MotionKind::CARTESIAN_DOWN, false},
    {State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true},
    {State::MOVE_ABOVE_PLACE, State::DESCEND_TO_PLACE, MotionKind::POSE, true},
    {State::DESCEND_TO_PLACE, State::OPEN_GRIPPER, MotionKind::CARTESIAN_DOWN, true},
    {State::RETREAT, State::DONE, MotionKind::CARTESIAN_UP, false},
  };
  auto policy = std::make_shared<RecordingTargetPolicy>();
  auto adapter = std::make_shared<RecordingMotionAdapter>();

  for (const auto & configuration : configurations) {
    MotionStateAction action(adapter, policy, configuration);
    const auto result = action.plan(
      configuration.state, configuration.next_state, observation());
    ASSERT_EQ(result.action.status, ActionStatus::SUCCEEDED);
  }

  ASSERT_EQ(policy->calls.size(), configurations.size());
  ASSERT_EQ(adapter->requests.size(), configurations.size());
  for (std::size_t index = 0; index < configurations.size(); ++index) {
    EXPECT_EQ(std::get<0>(policy->calls[index]), configurations[index].state);
    EXPECT_EQ(std::get<1>(policy->calls[index]), configurations[index].next_state);
    EXPECT_TRUE(std::get<2>(policy->calls[index]));
    EXPECT_EQ(adapter->requests[index].state, configurations[index].state);
    EXPECT_EQ(adapter->requests[index].next_state, configurations[index].next_state);
    EXPECT_EQ(adapter->requests[index].kind, configurations[index].kind);
    EXPECT_EQ(adapter->requests[index].carrying, configurations[index].carrying);
    EXPECT_DOUBLE_EQ(adapter->requests[index].target_pose.x, 0.31);
  }
}

TEST(MotionStateAction, RejectsMismatchedTransitionBeforeCallingDependencies)
{
  auto policy = std::make_shared<RecordingTargetPolicy>();
  auto adapter = std::make_shared<RecordingMotionAdapter>();
  MotionStateAction action(adapter, policy,
    {State::LIFT, State::MOVE_ABOVE_PLACE, MotionKind::CARTESIAN_UP, true});

  const auto result = action.plan(State::LIFT, State::DONE, observation());

  EXPECT_EQ(result.action.status, ActionStatus::NOT_SUPPORTED);
  EXPECT_TRUE(policy->calls.empty());
  EXPECT_TRUE(adapter->requests.empty());
}

TEST(MotionStateAction, ExecutesOnlyTypedEvidenceForItsConfiguredState)
{
  auto policy = std::make_shared<RecordingTargetPolicy>();
  auto adapter = std::make_shared<RecordingMotionAdapter>();
  MotionStateAction action(adapter, policy,
    {State::RETREAT, State::DONE, MotionKind::CARTESIAN_UP, false});
  MotionPlanEvidence wrong_evidence;
  wrong_evidence.state = State::LIFT;
  wrong_evidence.next_state = State::MOVE_ABOVE_PLACE;
  wrong_evidence.kind = MotionKind::CARTESIAN_UP;
  wrong_evidence.carrying = true;
  wrong_evidence.trajectory_points = 1;
  ExecutionContext context{
    State::RETREAT, State::DONE, WorldSnapshot{},
    std::make_shared<MotionPlanEvidence>(wrong_evidence)};

  const auto result = action.execute(context);

  EXPECT_EQ(result.status, ActionStatus::FAILED);
  EXPECT_TRUE(adapter->executed_states.empty());
}

}  // namespace
}  // namespace panda_gazebo_demo::pick_place

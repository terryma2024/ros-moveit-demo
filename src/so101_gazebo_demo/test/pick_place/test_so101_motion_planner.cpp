#include <memory>

#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/so101_motion_planner.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

class FakePolicy final : public spp::IJointMotionTargetPolicy
{
public:
  spp::JointMotionTargetResult target(spp::State state, spp::State next,
                                      const spp::ObservationResult &) const override
  {
    seen_state = state;
    seen_next = next;
    return result;
  }
  mutable spp::State seen_state{spp::State::ERROR};
  mutable spp::State seen_next{spp::State::ERROR};
  spp::JointMotionTargetResult result;
};

class FakeAdapter final : public spp::IMoveItJointMotionAdapter
{
public:
  spp::PlanResult plan(const spp::JointMotionRequest & request,
                       const spp::ObservationResult &) override
  {
    seen = request;
    return result;
  }
  spp::ActionResult execute(const spp::MotionPlanArtifact &) override
  {
    return {spp::ActionStatus::NOT_SUPPORTED, std::nullopt};
  }
  spp::ActionResult cancel() override { return {spp::ActionStatus::SUCCEEDED, std::nullopt}; }
  std::optional<spp::JointMotionRequest> seen;
  spp::PlanResult result;
};

spp::ObservationResult observation()
{
  spp::WorldSnapshot snapshot;
  snapshot.fresh = true;
  snapshot.arm_stationary = true;
  return {snapshot, std::nullopt};
}

}  // namespace

TEST(SO101MotionPlanner, SendsPolicyJointGoalToAdapterWithoutPoseTarget)
{
  auto policy = std::make_shared<FakePolicy>();
  policy->result.target = spp::JointMotionTarget{{"1", "2", "3", "4", "5"},
                                                 {{0.1, 0.2, 0.3, 0.4, 0.5}}, false};
  auto adapter = std::make_shared<FakeAdapter>();
  auto artifact = std::make_shared<spp::MotionPlanArtifact>();
  artifact->trajectory_points = 3;
  adapter->result = {{spp::ActionStatus::SUCCEEDED, std::nullopt}, artifact};
  spp::SO101MotionPlanner planner(policy, adapter);

  const auto result = planner.plan(spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                                   observation());
  EXPECT_EQ(result.artifact, artifact);
  ASSERT_TRUE(adapter->seen);
  EXPECT_EQ(adapter->seen->state, spp::State::MOVE_ABOVE_OBJECT);
  EXPECT_EQ(adapter->seen->next_state, spp::State::DESCEND);
  EXPECT_FALSE(adapter->seen->ladder);
  EXPECT_EQ(adapter->seen->joint_waypoints[0],
            (std::vector<double>{0.1, 0.2, 0.3, 0.4, 0.5}));
}

TEST(SO101MotionPlanner, PreservesLadderAndCarryingSemantics)
{
  auto policy = std::make_shared<FakePolicy>();
  policy->result.target = spp::JointMotionTarget{{"1", "2", "3", "4", "5"},
    {{0, 0, 0, 0, 0}, {0.1, 0.1, 0.1, 0.1, 0.1}}, true};
  auto adapter = std::make_shared<FakeAdapter>();
  adapter->result = {{spp::ActionStatus::SUCCEEDED, std::nullopt},
                     std::make_shared<spp::MotionPlanArtifact>()};
  spp::SO101MotionPlanner planner(policy, adapter);

  planner.plan(spp::State::LIFT, spp::State::MOVE_ABOVE_PLACE, observation());
  ASSERT_TRUE(adapter->seen);
  EXPECT_TRUE(adapter->seen->ladder);
  EXPECT_TRUE(adapter->seen->carrying);
  EXPECT_TRUE(adapter->seen->allowed_touch_pairs.empty());
  EXPECT_FALSE(adapter->seen->temporal_contact_policy.has_value());
}

TEST(SO101MotionPlanner, KeepsPreopenDescendCollisionFreeInMoveIt)
{
  auto policy = std::make_shared<FakePolicy>();
  policy->result.target = spp::JointMotionTarget{{"1", "2", "3", "4", "5"},
                                                 {{0, 0, 0, 0, 0}}, false};
  auto adapter = std::make_shared<FakeAdapter>();
  adapter->result = {{spp::ActionStatus::SUCCEEDED, std::nullopt},
                     std::make_shared<spp::MotionPlanArtifact>()};
  spp::SO101MotionPlanner planner(policy, adapter);

  planner.plan(spp::State::DESCEND, spp::State::CLOSE_GRIPPER, observation());
  ASSERT_TRUE(adapter->seen);
  // DESCEND runs at preopen q6.  Its full native-pad and legacy collision
  // envelopes must remain in MoveIt's collision check; CLOSE_GRIPPER is not
  // an arm trajectory and therefore cannot require a DESCEND touch waiver.
  EXPECT_TRUE(adapter->seen->allowed_touch_pairs.empty());

  planner.plan(spp::State::RECOVER_RETREAT, spp::State::ERROR, observation());
  EXPECT_TRUE(adapter->seen->allowed_touch_pairs.empty());

  planner.plan(spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND, observation());
  EXPECT_TRUE(adapter->seen->allowed_touch_pairs.empty());

  planner.plan(spp::State::LIFT, spp::State::MOVE_ABOVE_PLACE, observation());
  EXPECT_TRUE(adapter->seen->allowed_touch_pairs.empty());
}

TEST(SO101MotionPlanner, FailsBeforeAdapterWhenPolicyHasNoTarget)
{
  auto policy = std::make_shared<FakePolicy>();
  policy->result.failure = spp::Failure{spp::FailureCategory::CONFIGURATION,
    "MOTION_TARGET_UNAVAILABLE", "missing", {}};
  auto adapter = std::make_shared<FakeAdapter>();
  spp::SO101MotionPlanner planner(policy, adapter);

  const auto result = planner.plan(spp::State::MOVE_ABOVE_OBJECT, spp::State::DESCEND,
                                   observation());
  EXPECT_EQ(result.action.status, spp::ActionStatus::FAILED);
  EXPECT_FALSE(adapter->seen);
  ASSERT_TRUE(result.action.failure);
  EXPECT_EQ(result.action.failure->code, "MOTION_TARGET_UNAVAILABLE");
}

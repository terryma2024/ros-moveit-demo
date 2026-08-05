#include <gtest/gtest.h>

#include "panda_gazebo_demo/pick_place/simulation_session_id.hpp"

namespace panda_gazebo_demo::pick_place
{

TEST(SimulationSessionId, GeneratesForInitialExecute)
{
  const auto result = resolveSimulationSessionId(RunMode::EXECUTE, false, "", 1784779200123ULL);

  ASSERT_TRUE(result.error.empty());
  ASSERT_TRUE(result.value);
  EXPECT_EQ(*result.value, "execute-1784779200123");
}

TEST(SimulationSessionId, PreservesExplicitExecuteAndResumeIds)
{
  const auto execute = resolveSimulationSessionId(RunMode::EXECUTE, false, "operator-session", 1);
  const auto resume = resolveSimulationSessionId(RunMode::PLAN_ONLY, true, "operator-session", 2);

  ASSERT_TRUE(execute.value);
  ASSERT_TRUE(resume.value);
  EXPECT_EQ(*execute.value, "operator-session");
  EXPECT_EQ(*resume.value, "operator-session");
}

TEST(SimulationSessionId, RejectsResumeWithoutExplicitId)
{
  const auto result = resolveSimulationSessionId(RunMode::EXECUTE, true, "", 1784779200123ULL);

  EXPECT_FALSE(result.value);
  EXPECT_EQ(result.error,
            "simulation_session_id is required for resume to reject stale checkpoints");
}

TEST(SimulationSessionId, GeneratesForInitialPlanOnly)
{
  const auto generated =
    resolveSimulationSessionId(RunMode::PLAN_ONLY, false, "", 1784779200123ULL);
  const auto explicit_id =
    resolveSimulationSessionId(RunMode::PLAN_ONLY, false, "operator-session", 1);

  ASSERT_TRUE(generated.value);
  ASSERT_TRUE(explicit_id.value);
  EXPECT_EQ("plan-only-1784779200123", *generated.value);
  EXPECT_EQ("operator-session", *explicit_id.value);
}

TEST(SimulationSessionId, DoesNotGenerateForDryRun)
{
  const auto result = resolveSimulationSessionId(RunMode::DRY_RUN, false, "ignored", 1);

  EXPECT_TRUE(result.error.empty());
  EXPECT_FALSE(result.value);
}

}  // namespace panda_gazebo_demo::pick_place

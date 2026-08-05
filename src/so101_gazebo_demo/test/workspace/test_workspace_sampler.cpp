#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/workspace/workspace_sampler.hpp"

namespace ws = so101_gazebo_demo::workspace;
namespace spp = so101_gazebo_demo::pick_place;

namespace
{
std::string readFile(const std::string & path)
{
  std::ifstream stream(path);
  std::ostringstream output;
  output << stream.rdbuf();
  return output.str();
}

std::unique_ptr<ws::WorkspaceStateEvaluator> evaluator()
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  rclcpp::NodeOptions options;
  options.parameter_overrides(
    {rclcpp::Parameter("robot_description", readFile(SO101_TEST_URDF)),
     rclcpp::Parameter("robot_description_semantic", readFile(SO101_TEST_SRDF))});
  auto node = std::make_shared<rclcpp::Node>("workspace_sampler_test", options);
  auto result = ws::WorkspaceStateEvaluator::create(node, spp::SO101Profile::canonical());
  EXPECT_FALSE(result.failure);
  return std::move(result.evaluator);
}

ws::JointBounds bounds()
{
  return {{{-1.91986, 1.91986},
           {-1.74533, 1.74533},
           {-1.74533, 1.5708},
           {-1.65806, 1.65806},
           {-2.79253, 2.79253}}};
}

ws::WorkspaceSamplingConfig fixedConfig()
{
  auto config = ws::configForProfile(ws::WorkspaceProfile::QUICK);
  config.batch_size = 10;
  config.minimum_samples = 20;
  config.maximum_samples = 20;
  config.stable_batches = 100;
  return config;
}

std::filesystem::path output(const std::string & name)
{
  const auto path = std::filesystem::temp_directory_path() / ("workspace-sampler-" + name);
  std::filesystem::remove_all(path);
  return path;
}

ws::RunSummary run(const std::filesystem::path & path, const ws::RunControl & control)
{
  auto state_evaluator = evaluator();
  ws::WorkspaceArtifactWriter writer(path);
  const ws::WorkspaceProvenance provenance{"u", "s", "w", ws::configSha256(fixedConfig()),
                                           "e", "p"};
  ws::WorkspaceCheckpointStore checkpoint(path, provenance);
  ws::WorkspaceSampler sampler(fixedConfig(), ws::JointSampleGenerator(bounds()), *state_evaluator,
                               ws::PoseCoverageIndex(0.005, 0.17453292519943295), writer,
                               checkpoint);
  return sampler.run(control);
}

ws::RunControl noStop()
{
  return {[] { return std::chrono::steady_clock::time_point{}; }, [] { return false; }};
}
}  // namespace

TEST(WorkspaceSampler, SampleCapFinalizesArtifactsAtBatchBoundary)
{
  const auto result = run(output("complete"), noStop());
  EXPECT_TRUE(result.success);
  EXPECT_EQ(result.stop_reason, ws::StopReason::SAMPLE_CAP_REACHED);
  EXPECT_EQ(result.completed_samples, 20U);
  ASSERT_TRUE(result.artifacts);
  EXPECT_TRUE(std::filesystem::exists(result.artifacts->samples_csv));
  EXPECT_NE(readFile(result.artifacts->samples_csv.parent_path() / "collision_pairs.csv")
              .find("representative_sample_ids"),
            std::string::npos);
}

TEST(WorkspaceSampler, StartsWithDeterministicExplicitBaseline)
{
  const auto path = output("explicit");
  const auto result = run(path, noStop());
  ASSERT_TRUE(result.success);
  const auto csv = readFile(result.artifacts->samples_csv);
  EXPECT_NE(csv.find("0,0,0.000000000000000,0.000000000000000,0.000000000000000"),
            std::string::npos);
}

TEST(WorkspaceSampler, InterruptedRunResumesToIdenticalCanonicalSamples)
{
  const auto uninterrupted_path = output("one");
  const auto uninterrupted = run(uninterrupted_path, noStop());
  const auto resumed_path = output("two");
  int checks = 0;
  const ws::RunControl interrupt{[] { return std::chrono::steady_clock::time_point{}; },
                                 [&checks] { return checks++ >= 1; }};
  const auto interrupted = run(resumed_path, interrupt);
  ASSERT_EQ(interrupted.stop_reason, ws::StopReason::INTERRUPTED);
  EXPECT_FALSE(interrupted.artifacts);
  const auto resumed = run(resumed_path, noStop());
  ASSERT_TRUE(uninterrupted.artifacts);
  ASSERT_TRUE(resumed.artifacts);
  EXPECT_EQ(readFile(uninterrupted.artifacts->samples_csv),
            readFile(resumed.artifacts->samples_csv));
}

TEST(WorkspaceSampler, BudgetExhaustionBeforeMinimumFails)
{
  auto state_evaluator = evaluator();
  const auto path = output("budget");
  auto config = fixedConfig();
  config.time_budget = std::chrono::seconds(1);
  ws::WorkspaceArtifactWriter writer(path);
  ws::WorkspaceProvenance provenance{"u", "s", "w", ws::configSha256(config), "e", "p"};
  ws::WorkspaceCheckpointStore checkpoint(path, provenance);
  ws::WorkspaceSampler sampler(config, ws::JointSampleGenerator(bounds()), *state_evaluator,
                               ws::PoseCoverageIndex(0.005, 0.17453292519943295), writer,
                               checkpoint);
  int calls = 0;
  const ws::RunControl control{[&calls] {
                                 return std::chrono::steady_clock::time_point{} +
                                        std::chrono::seconds(calls++ * 2);
                               },
                               [] { return false; }};
  const auto result = sampler.run(control);
  EXPECT_FALSE(result.success);
  ASSERT_TRUE(result.failure);
  EXPECT_EQ(result.failure->code, "minimum_samples_not_reached");
}

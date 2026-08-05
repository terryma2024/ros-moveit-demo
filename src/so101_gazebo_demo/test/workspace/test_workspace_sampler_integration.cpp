#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>

#include <nlohmann/json.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/workspace/workspace_sampler.hpp"

namespace ws = so101_gazebo_demo::workspace;
namespace spp = so101_gazebo_demo::pick_place;

namespace
{
std::string readFile(const std::string & path)
{
  std::ifstream stream(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

std::uint64_t csvRows(const std::filesystem::path & path)
{
  std::ifstream stream(path);
  std::uint64_t lines = 0;
  std::string line;
  while (std::getline(stream, line))
    ++lines;
  return lines - 1;
}

std::uint64_t plyVertices(const std::filesystem::path & path)
{
  std::ifstream stream(path, std::ios::binary);
  std::string line;
  while (std::getline(stream, line)) {
    constexpr std::string_view prefix = "element vertex ";
    if (line.rfind(prefix, 0) == 0)
      return std::stoull(line.substr(prefix.size()));
  }
  throw std::runtime_error("PLY vertex declaration missing");
}

std::uint64_t freeCsvRows(const std::filesystem::path & path)
{
  std::ifstream stream(path);
  std::string line;
  std::getline(stream, line);
  std::uint64_t count = 0;
  while (std::getline(stream, line)) {
    std::istringstream row(line);
    std::string field;
    for (std::size_t index = 0; std::getline(row, field, ','); ++index) {
      if (index == 18 && field == "1")
        ++count;
    }
  }
  return count;
}

ws::RunSummary runSampler(const std::filesystem::path & output, std::uint64_t samples,
                          const ws::RunControl & control)
{
  if (!rclcpp::ok())
    rclcpp::init(0, nullptr);
  rclcpp::NodeOptions options;
  options.parameter_overrides(
    {rclcpp::Parameter("robot_description", readFile(SO101_TEST_URDF)),
     rclcpp::Parameter("robot_description_semantic", readFile(SO101_TEST_SRDF))});
  auto node = std::make_shared<rclcpp::Node>("workspace_integration_test", options);
  auto evaluator = ws::WorkspaceStateEvaluator::create(node, spp::SO101Profile::canonical());
  if (evaluator.failure)
    throw std::runtime_error(evaluator.failure->message);
  const ws::JointBounds bounds{{{-1.91986, 1.91986},
                                {-1.74533, 1.74533},
                                {-1.74533, 1.5708},
                                {-1.65806, 1.65806},
                                {-2.79253, 2.79253}}};
  auto config = ws::configForProfile(ws::WorkspaceProfile::QUICK);
  config.batch_size = 1000;
  config.minimum_samples = samples;
  config.maximum_samples = samples;
  config.stable_batches = 100;
  const ws::WorkspaceProvenance provenance{ws::sha256(readFile(SO101_TEST_URDF)),
                                           ws::sha256(readFile(SO101_TEST_SRDF)),
                                           ws::sha256("base_pedestal,table"),
                                           ws::configSha256(config),
                                           "fixture",
                                           "fixture"};
  ws::WorkspaceArtifactWriter writer(output);
  ws::WorkspaceCheckpointStore store(output, provenance);
  ws::WorkspaceSampler sampler(
    config, ws::JointSampleGenerator(bounds), *evaluator.evaluator,
    ws::PoseCoverageIndex(config.position_voxel_size_m, config.orientation_threshold_rad), writer,
    store);
  return sampler.run(control);
}

ws::RunControl noStop()
{
  return {[] { return std::chrono::steady_clock::time_point{}; }, [] { return false; }};
}
}  // namespace

TEST(WorkspaceSamplerIntegration, TenThousandSamplesProduceConsistentArtifacts)
{
  const auto output = std::filesystem::temp_directory_path() / "workspace-integration-10000";
  std::filesystem::remove_all(output);
  const auto result = runSampler(output, 10000, noStop());
  ASSERT_TRUE(result.success);
  ASSERT_TRUE(result.artifacts);
  EXPECT_EQ(csvRows(result.artifacts->samples_csv), 10000U);
  EXPECT_EQ(plyVertices(result.artifacts->all_poses_ply), 10000U);
  EXPECT_EQ(plyVertices(result.artifacts->collision_free_poses_ply), result.collision_free_samples);
  const auto manifest = nlohmann::json::parse(readFile((output / "manifest.json").string()));
  EXPECT_EQ(manifest.at("completed_samples"), 10000U);
  EXPECT_EQ(manifest.at("scene_objects"), nlohmann::json::array({"base_pedestal", "table"}));
  EXPECT_DOUBLE_EQ(manifest.at("q6_preopen"), spp::SO101Profile::canonical().q6_preopen);
  EXPECT_EQ(freeCsvRows(result.artifacts->samples_csv), result.collision_free_samples);
}

TEST(WorkspaceSamplerIntegration, BatchBoundaryResumeMatchesUninterruptedCsvAndPly)
{
  const auto uninterrupted_path =
    std::filesystem::temp_directory_path() / "workspace-integration-uninterrupted";
  const auto resumed_path = std::filesystem::temp_directory_path() / "workspace-integration-resume";
  std::filesystem::remove_all(uninterrupted_path);
  std::filesystem::remove_all(resumed_path);
  const auto uninterrupted = runSampler(uninterrupted_path, 10000, noStop());
  ASSERT_TRUE(uninterrupted.success);
  int batch_boundaries = 0;
  const auto interrupted = runSampler(resumed_path, 10000,
                                      {[] { return std::chrono::steady_clock::time_point{}; },
                                       [&batch_boundaries] { return batch_boundaries++ >= 2; }});
  ASSERT_EQ(interrupted.stop_reason, ws::StopReason::INTERRUPTED);
  ASSERT_EQ(interrupted.completed_samples, 2000U);
  const auto resumed = runSampler(resumed_path, 10000, noStop());
  ASSERT_TRUE(resumed.success);
  ASSERT_TRUE(uninterrupted.artifacts);
  ASSERT_TRUE(resumed.artifacts);
  EXPECT_EQ(readFile(uninterrupted.artifacts->samples_csv.string()),
            readFile(resumed.artifacts->samples_csv.string()));
  EXPECT_EQ(readFile(uninterrupted.artifacts->all_poses_ply.string()),
            readFile(resumed.artifacts->all_poses_ply.string()));
  EXPECT_EQ(readFile(uninterrupted.artifacts->collision_free_poses_ply.string()),
            readFile(resumed.artifacts->collision_free_poses_ply.string()));
}

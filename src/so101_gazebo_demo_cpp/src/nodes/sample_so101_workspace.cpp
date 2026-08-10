#include <chrono>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <string>

#include <ament_index_cpp/get_package_prefix.hpp>
#include <moveit/robot_model_loader/robot_model_loader.hpp>
#include <nlohmann/json.hpp>
#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/so101_profile.hpp"
#include "so101_gazebo_demo/workspace/workspace_sampler.hpp"

namespace ws = so101_gazebo_demo::workspace;
namespace spp = so101_gazebo_demo::pick_place;

namespace
{
std::string readFile(const std::filesystem::path & path)
{
  std::ifstream stream(path, std::ios::binary);
  if (!stream)
    throw std::runtime_error("cannot read " + path.string());
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

std::filesystem::path executablePath()
{
  return std::filesystem::canonical("/proc/self/exe");
}

ws::WorkspaceSamplingConfig readConfig(const std::shared_ptr<rclcpp::Node> & node,
                                       ws::WorkspaceProfile profile)
{
  auto config = ws::configForProfile(profile);
  const auto time = node->declare_parameter<std::int64_t>("time_budget_seconds", 1800);
  const auto batch = node->declare_parameter<std::int64_t>("batch_size", 25000);
  const auto minimum = node->declare_parameter<std::int64_t>("minimum_samples", 250000);
  const auto maximum = node->declare_parameter<std::int64_t>("maximum_samples", 2000000);
  const auto stable = node->declare_parameter<std::int64_t>("stable_batches", 5);
  const bool full_defaults =
    time == 1800 && batch == 25000 && minimum == 250000 && maximum == 2000000 && stable == 5;
  if (profile == ws::WorkspaceProfile::FULL || profile == ws::WorkspaceProfile::DEEP ||
      !full_defaults) {
    config.time_budget = std::chrono::seconds(time);
    config.batch_size = static_cast<std::size_t>(batch);
    config.minimum_samples = static_cast<std::uint64_t>(minimum);
    config.maximum_samples = static_cast<std::uint64_t>(maximum);
    config.stable_batches = static_cast<std::size_t>(stable);
  }
  config.position_voxel_size_m = node->declare_parameter("position_voxel_size_m", 0.005);
  const auto degrees = node->declare_parameter("orientation_threshold_deg", 10.0);
  config.orientation_threshold_rad = degrees * 3.14159265358979323846 / 180.0;
  config.position_new_rate_threshold =
    node->declare_parameter("position_new_rate_threshold", 0.001);
  config.orientation_new_rate_threshold =
    node->declare_parameter("orientation_new_rate_threshold", 0.002);
  return config;
}

int execute(const std::shared_ptr<rclcpp::Node> & node)
{
  const auto output = std::filesystem::path(node->declare_parameter<std::string>("output_dir", ""));
  const auto profile_name = node->declare_parameter<std::string>("profile", "full");
  const bool resume = node->declare_parameter("resume", false);
  const auto profile = ws::workspaceProfileFromString(profile_name);
  if (!profile)
    throw std::invalid_argument("profile must be quick, full, or deep");
  if (output.empty() || !output.is_absolute())
    throw std::invalid_argument("output_dir must be absolute");
  if (std::filesystem::exists(output) && !std::filesystem::is_empty(output) && !resume) {
    throw std::invalid_argument("nonempty output_dir requires resume:=true");
  }
  const auto config = readConfig(node, *profile);
  if (const auto validation = ws::validateConfig(config))
    throw std::invalid_argument(*validation);

  robot_model_loader::RobotModelLoader::Options model_options("robot_description");
  model_options.load_kinematics_solvers = false;
  robot_model_loader::RobotModelLoader model_loader(node, model_options);
  const auto & model = model_loader.getModel();
  if (!model)
    throw std::runtime_error("failed to load RobotModel");
  ws::JointBounds bounds{};
  const auto & canonical = spp::SO101Profile::canonical();
  for (std::size_t index = 0; index < bounds.size(); ++index) {
    const auto & variable = model->getVariableBounds(canonical.arm_joints[index]);
    bounds[index] = {variable.min_position_, variable.max_position_};
  }
  auto evaluator_result = ws::WorkspaceStateEvaluator::create(node, canonical);
  if (evaluator_result.failure)
    throw std::runtime_error(evaluator_result.failure->message);

  const auto urdf = node->get_parameter("robot_description").as_string();
  const auto srdf = node->get_parameter("robot_description_semantic").as_string();
  const nlohmann::ordered_json scene{
    {"objects", {canonical.pedestal_object, canonical.table_object}},
    {"pedestal_size", canonical.pedestal_size},
    {"table_size", canonical.table_size},
    {"pedestal_pose",
     {canonical.pedestal_pose.x, canonical.pedestal_pose.y, canonical.pedestal_pose.z}},
    {"table_pose", {canonical.table_pose.x, canonical.table_pose.y, canonical.table_pose.z}}};
  const ws::WorkspaceProvenance provenance{
    ws::sha256(urdf),
    ws::sha256(srdf),
    ws::sha256(scene.dump()),
    ws::configSha256(config),
    ws::sha256(readFile(executablePath())),
    ament_index_cpp::get_package_prefix("so101_gazebo_demo_cpp")};
  ws::WorkspaceArtifactWriter writer(output, config.position_voxel_size_m);
  ws::WorkspaceCheckpointStore checkpoint_store(output, provenance);
  ws::WorkspaceSampler sampler(
    config, ws::JointSampleGenerator(bounds), *evaluator_result.evaluator,
    ws::PoseCoverageIndex(config.position_voxel_size_m, config.orientation_threshold_rad), writer,
    checkpoint_store);
  const ws::RunControl control{[] { return std::chrono::steady_clock::now(); },
                               [] { return !rclcpp::ok(); }};
  const auto result = sampler.run(control);
  std::cout << "WORKSPACE_RESULT status=" << (result.success ? "success" : "failed")
            << " stop_reason=" << ws::toString(result.stop_reason)
            << " samples=" << result.completed_samples << " output=" << output.string() << '\n';
  if (result.failure)
    std::cerr << result.failure->code << ": " << result.failure->message << '\n';
  return result.success ? 0 : 2;
}
}  // namespace

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  int result = 2;
  try {
    result = execute(std::make_shared<rclcpp::Node>("sample_so101_workspace"));
  } catch (const std::exception & error) {
    std::cerr << "WORKSPACE_RESULT status=failed stop_reason=failed samples=0 output=unknown\n"
              << "configuration_or_model_error: " << error.what() << '\n';
  }
  rclcpp::shutdown();
  return result;
}

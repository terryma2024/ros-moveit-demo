#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"

#include <fstream>
#include <system_error>

#include <nlohmann/json.hpp>

namespace panda_gazebo_demo::pick_place
{

namespace
{

using Json = nlohmann::json;

Json poseToJson(const Pose3d & pose)
{
  return {{"x", pose.x}, {"y", pose.y}, {"z", pose.z}, {"qx", pose.qx}, {"qy", pose.qy},
    {"qz", pose.qz}, {"qw", pose.qw}};
}

Pose3d poseFromJson(const Json & json)
{
  return {json.at("x").get<double>(), json.at("y").get<double>(), json.at("z").get<double>(),
    json.at("qx").get<double>(), json.at("qy").get<double>(), json.at("qz").get<double>(),
    json.at("qw").get<double>()};
}

Json poseMapToJson(const std::map<std::string, Pose3d> & poses)
{
  Json json = Json::object();
  for (const auto & [name, pose] : poses) {
    json[name] = poseToJson(pose);
  }
  return json;
}

std::map<std::string, Pose3d> poseMapFromJson(const Json & json)
{
  std::map<std::string, Pose3d> poses;
  for (const auto & [name, pose] : json.items()) {
    poses.emplace(name, poseFromJson(pose));
  }
  return poses;
}

Failure checkpointFailure(std::string code, std::string message)
{
  return {FailureCategory::CHECKPOINT, std::move(code), std::move(message), {}};
}

}  // namespace

FileCheckpointStore::FileCheckpointStore(std::filesystem::path path)
: path_(std::move(path))
{
}

std::optional<Failure> FileCheckpointStore::commit(const Checkpoint & checkpoint)
{
  std::error_code error;
  if (!path_.parent_path().empty()) {
    std::filesystem::create_directories(path_.parent_path(), error);
  }
  if (error) {
    return checkpointFailure("CHECKPOINT_DIRECTORY_CREATE_FAILED",
      "Unable to create checkpoint directory: " + error.message());
  }
  const Json json{{"schema_version", checkpoint.schema_version}, {"run_id", checkpoint.run_id},
    {"sequence", checkpoint.sequence}, {"source_mode", toString(checkpoint.source_mode)},
    {"last_completed_state", toString(checkpoint.last_completed_state)},
    {"next_state", toString(checkpoint.next_state)},
    {"configuration_hash", checkpoint.configuration_hash},
    {"simulation_session_id", checkpoint.simulation_session_id},
    {"resumable", checkpoint.resumable},
    {"expected", {{"tcp_pose_world", poseToJson(checkpoint.expected.tcp_pose_world)},
        {"gripper_open", checkpoint.expected.gripper_open},
        {"joint_positions", checkpoint.expected.joint_positions},
        {"moveit_world_object_poses", poseMapToJson(checkpoint.expected.moveit_world_object_poses)},
        {"moveit_coke_attached", checkpoint.expected.moveit_coke_attached ?
          Json(*checkpoint.expected.moveit_coke_attached) : Json(nullptr)},
        {"gazebo_coke_pose_world", checkpoint.expected.gazebo_coke_pose_world ?
          poseToJson(*checkpoint.expected.gazebo_coke_pose_world) : Json(nullptr)},
        {"gazebo_coke_attached", checkpoint.expected.gazebo_coke_attached ?
          Json(*checkpoint.expected.gazebo_coke_attached) : Json(nullptr)},
        {"required_world_objects", checkpoint.expected.required_world_objects}}}};
  const auto temporary_path = path_.string() + ".tmp";
  {
    std::ofstream output(temporary_path, std::ios::out | std::ios::trunc);
    if (!output) {
      return checkpointFailure("CHECKPOINT_WRITE_OPEN_FAILED",
        "Unable to open temporary checkpoint file");
    }
    output << json.dump(2) << '\n';
    if (!output) {
      return checkpointFailure("CHECKPOINT_WRITE_FAILED",
        "Failed while writing temporary checkpoint file");
    }
  }
  std::filesystem::rename(temporary_path, path_, error);
  if (error) {
    std::filesystem::remove(temporary_path);
    return checkpointFailure("CHECKPOINT_ATOMIC_RENAME_FAILED",
      "Unable to atomically commit checkpoint: " + error.message());
  }
  return std::nullopt;
}

CheckpointLoadResult FileCheckpointStore::loadLatestCompatible()
{
  std::ifstream input(path_);
  if (!input) {
    return {std::nullopt, checkpointFailure("CHECKPOINT_NOT_FOUND",
      "No checkpoint exists at " + path_.string())};
  }
  try {
    Json json;
    input >> json;
    const auto source_mode = runModeFromString(json.at("source_mode").get<std::string>());
    const auto last_completed = stateFromString(json.at("last_completed_state").get<std::string>());
    const auto next_state = stateFromString(json.at("next_state").get<std::string>());
    if (!source_mode || !last_completed || !next_state) {
      return {std::nullopt, checkpointFailure("CHECKPOINT_INVALID_ENUM",
        "Checkpoint contains an unsupported mode or state")};
    }
    const auto & expected = json.at("expected");
    Checkpoint checkpoint;
    checkpoint.schema_version = json.at("schema_version").get<std::uint32_t>();
    checkpoint.run_id = json.at("run_id").get<std::string>();
    checkpoint.sequence = json.at("sequence").get<std::uint64_t>();
    checkpoint.source_mode = *source_mode;
    checkpoint.last_completed_state = *last_completed;
    checkpoint.next_state = *next_state;
    checkpoint.resumable = json.at("resumable").get<bool>();
    checkpoint.configuration_hash = json.at("configuration_hash").get<std::string>();
    checkpoint.simulation_session_id = json.at("simulation_session_id").get<std::string>();
    checkpoint.expected.tcp_pose_world = poseFromJson(expected.at("tcp_pose_world"));
    checkpoint.expected.gripper_open = expected.at("gripper_open").get<bool>();
    checkpoint.expected.joint_positions =
      expected.at("joint_positions").get<std::map<std::string, double>>();
    checkpoint.expected.moveit_world_object_poses =
      poseMapFromJson(expected.at("moveit_world_object_poses"));
    if (!expected.at("moveit_coke_attached").is_null()) {
      checkpoint.expected.moveit_coke_attached = expected.at("moveit_coke_attached").get<bool>();
    }
    if (!expected.at("gazebo_coke_pose_world").is_null()) {
      checkpoint.expected.gazebo_coke_pose_world =
        poseFromJson(expected.at("gazebo_coke_pose_world"));
    }
    if (!expected.at("gazebo_coke_attached").is_null()) {
      checkpoint.expected.gazebo_coke_attached = expected.at("gazebo_coke_attached").get<bool>();
    }
    checkpoint.expected.required_world_objects =
      expected.at("required_world_objects").get<std::vector<std::string>>();
    return {checkpoint, std::nullopt};
  } catch (const std::exception & exception) {
    return {std::nullopt, checkpointFailure("CHECKPOINT_PARSE_FAILED",
      "Unable to parse checkpoint JSON: " + std::string(exception.what()))};
  }
}

}  // namespace panda_gazebo_demo::pick_place

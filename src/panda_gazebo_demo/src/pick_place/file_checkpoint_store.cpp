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
  return {{"x", pose.x},   {"y", pose.y},   {"z", pose.z},  {"qx", pose.qx},
          {"qy", pose.qy}, {"qz", pose.qz}, {"qw", pose.qw}};
}

Pose3d poseFromJson(const Json & json)
{
  return {json.at("x").get<double>(),  json.at("y").get<double>(),  json.at("z").get<double>(),
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

const char * checkpointPhaseToString(CheckpointPhase phase) noexcept
{
  switch (phase) {
    case CheckpointPhase::FORWARD:
      return "FORWARD";
    case CheckpointPhase::RECOVERY:
      return "RECOVERY";
  }
  return "UNKNOWN";
}

std::optional<CheckpointPhase> checkpointPhaseFromString(const std::string & value)
{
  if (value == "FORWARD") {
    return CheckpointPhase::FORWARD;
  }
  if (value == "RECOVERY") {
    return CheckpointPhase::RECOVERY;
  }
  return std::nullopt;
}

Json failureToJson(const Failure & failure)
{
  return {{"category", static_cast<int>(failure.category)},
          {"code", failure.code},
          {"message", failure.message},
          {"metrics", failure.metrics}};
}

Failure failureFromJson(const Json & json)
{
  const auto category = json.at("category").get<int>();
  if (category < static_cast<int>(FailureCategory::CONFIGURATION) ||
      category > static_cast<int>(FailureCategory::INTERNAL)) {
    throw std::out_of_range("failure category is outside the supported range");
  }
  return {static_cast<FailureCategory>(category), json.at("code").get<std::string>(),
          json.at("message").get<std::string>(),
          json.at("metrics").get<std::map<std::string, double>>()};
}

}  // namespace

FileCheckpointStore::FileCheckpointStore(std::filesystem::path path) : path_(std::move(path)) {}

std::optional<Failure> FileCheckpointStore::commit(const Checkpoint & checkpoint)
{
  if (checkpoint.schema_version != 3) {
    return checkpointFailure("CHECKPOINT_INCOMPATIBLE",
                             "Only checkpoint schema version 3 can be committed");
  }
  std::error_code error;
  if (!path_.parent_path().empty()) {
    std::filesystem::create_directories(path_.parent_path(), error);
  }
  if (error) {
    return checkpointFailure("CHECKPOINT_DIRECTORY_CREATE_FAILED",
                             "Unable to create checkpoint directory: " + error.message());
  }
  const Json json{
    {"schema_version", checkpoint.schema_version},
    {"run_id", checkpoint.run_id},
    {"sequence", checkpoint.sequence},
    {"source_mode", toString(checkpoint.source_mode)},
    {"phase", checkpointPhaseToString(checkpoint.phase)},
    {"last_completed_state", toString(checkpoint.last_completed_state)},
    {"failed_state",
     checkpoint.failed_state ? Json(toString(*checkpoint.failed_state)) : Json(nullptr)},
    {"original_failure",
     checkpoint.original_failure ? failureToJson(*checkpoint.original_failure) : Json(nullptr)},
    {"next_state", toString(checkpoint.next_state)},
    {"configuration_hash", checkpoint.configuration_fingerprint},
    {"simulation_session_id", checkpoint.simulation_session_id},
    {"resumable", checkpoint.resumable},
    {"expected",
     {{"tcp_pose_world", poseToJson(checkpoint.expected.tcp_pose_world)},
      {"gripper_open", checkpoint.expected.gripper_open},
      {"joint_positions", checkpoint.expected.joint_positions},
      {"moveit_world_object_poses", poseMapToJson(checkpoint.expected.moveit_world_object_poses)},
      {"moveit_coke_attached", checkpoint.expected.moveit_task_object_attached
                                 ? Json(*checkpoint.expected.moveit_task_object_attached)
                                 : Json(nullptr)},
      {"gazebo_coke_pose_world", checkpoint.expected.gazebo_task_object_pose_world
                                   ? poseToJson(*checkpoint.expected.gazebo_task_object_pose_world)
                                   : Json(nullptr)},
      {"gazebo_coke_attached", checkpoint.expected.gazebo_task_object_attached
                                 ? Json(*checkpoint.expected.gazebo_task_object_attached)
                                 : Json(nullptr)},
      {"gazebo_coke_stationary", checkpoint.expected.gazebo_task_object_stationary
                                   ? Json(*checkpoint.expected.gazebo_task_object_stationary)
                                   : Json(nullptr)},
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
    return {std::nullopt,
            checkpointFailure("CHECKPOINT_NOT_FOUND", "No checkpoint exists at " + path_.string())};
  }
  try {
    Json json;
    input >> json;
    const auto schema_version = json.at("schema_version").get<std::uint32_t>();
    if (schema_version != 3) {
      return {std::nullopt, checkpointFailure("CHECKPOINT_INCOMPATIBLE",
                                              "Only checkpoint schema version 3 is supported")};
    }
    const auto source_mode = runModeFromString(json.at("source_mode").get<std::string>());
    const auto phase = checkpointPhaseFromString(json.at("phase").get<std::string>());
    const auto last_completed = stateFromString(json.at("last_completed_state").get<std::string>());
    const auto next_state = stateFromString(json.at("next_state").get<std::string>());
    if (!source_mode || !phase || !last_completed || !next_state) {
      return {std::nullopt,
              checkpointFailure("CHECKPOINT_INVALID_ENUM",
                                "Checkpoint contains an unsupported mode, phase, or state")};
    }
    const auto & expected = json.at("expected");
    Checkpoint checkpoint;
    checkpoint.schema_version = schema_version;
    checkpoint.run_id = json.at("run_id").get<std::string>();
    checkpoint.sequence = json.at("sequence").get<std::uint64_t>();
    checkpoint.source_mode = *source_mode;
    checkpoint.phase = *phase;
    checkpoint.last_completed_state = *last_completed;
    if (!json.at("failed_state").is_null()) {
      checkpoint.failed_state = stateFromString(json.at("failed_state").get<std::string>());
      if (!checkpoint.failed_state) {
        return {std::nullopt, checkpointFailure("CHECKPOINT_INVALID_ENUM",
                                                "Checkpoint contains an unsupported failed state")};
      }
    }
    if (!json.at("original_failure").is_null()) {
      checkpoint.original_failure = failureFromJson(json.at("original_failure"));
    }
    checkpoint.next_state = *next_state;
    checkpoint.resumable = json.at("resumable").get<bool>();
    checkpoint.configuration_fingerprint = json.at("configuration_hash").get<std::string>();
    checkpoint.simulation_session_id = json.at("simulation_session_id").get<std::string>();
    checkpoint.expected.tcp_pose_world = poseFromJson(expected.at("tcp_pose_world"));
    checkpoint.expected.gripper_open = expected.at("gripper_open").get<bool>();
    checkpoint.expected.joint_positions =
      expected.at("joint_positions").get<std::map<std::string, double>>();
    checkpoint.expected.moveit_world_object_poses =
      poseMapFromJson(expected.at("moveit_world_object_poses"));
    if (!expected.at("moveit_coke_attached").is_null()) {
      checkpoint.expected.moveit_task_object_attached =
        expected.at("moveit_coke_attached").get<bool>();
    }
    if (!expected.at("gazebo_coke_pose_world").is_null()) {
      checkpoint.expected.gazebo_task_object_pose_world =
        poseFromJson(expected.at("gazebo_coke_pose_world"));
    }
    if (!expected.at("gazebo_coke_attached").is_null()) {
      checkpoint.expected.gazebo_task_object_attached =
        expected.at("gazebo_coke_attached").get<bool>();
    }
    if (!expected.at("gazebo_coke_stationary").is_null()) {
      checkpoint.expected.gazebo_task_object_stationary =
        expected.at("gazebo_coke_stationary").get<bool>();
    }
    checkpoint.expected.required_world_objects =
      expected.at("required_world_objects").get<std::vector<std::string>>();
    return {checkpoint, std::nullopt};
  } catch (const std::exception & exception) {
    return {std::nullopt,
            checkpointFailure("CHECKPOINT_PARSE_FAILED",
                              "Unable to parse checkpoint JSON: " + std::string(exception.what()))};
  }
}

}  // namespace panda_gazebo_demo::pick_place

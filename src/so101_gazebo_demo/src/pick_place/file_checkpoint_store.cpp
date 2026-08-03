#include "so101_gazebo_demo/pick_place/file_checkpoint_store.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <set>
#include <string_view>
#include <system_error>
#include <unistd.h>
#include <vector>

#include <nlohmann/json.hpp>

namespace so101_gazebo_demo::pick_place
{

namespace
{

using Json = nlohmann::json;

Failure checkpointFailure(std::string code, std::string message)
{
  return {FailureCategory::CHECKPOINT, std::move(code), std::move(message), {}};
}

std::optional<std::string_view> stateName(State state) noexcept
{
  const auto value = static_cast<int>(state);
  if (value < static_cast<int>(State::IDLE) || value > static_cast<int>(State::ERROR)) {
    return std::nullopt;
  }
  return toString(state);
}

std::optional<std::string_view> runModeName(RunMode mode) noexcept
{
  switch (mode) {
    case RunMode::DRY_RUN:
      return "dry_run";
    case RunMode::PLAN_ONLY:
      return "plan_only";
    case RunMode::EXECUTE:
      return "execute";
  }
  return std::nullopt;
}

std::optional<std::string_view> checkpointPhaseName(CheckpointPhase phase) noexcept
{
  switch (phase) {
    case CheckpointPhase::FORWARD:
      return "FORWARD";
    case CheckpointPhase::RECOVERY:
      return "RECOVERY";
  }
  return std::nullopt;
}

std::optional<CheckpointPhase> checkpointPhaseFromName(std::string_view value) noexcept
{
  if (value == "FORWARD") {
    return CheckpointPhase::FORWARD;
  }
  if (value == "RECOVERY") {
    return CheckpointPhase::RECOVERY;
  }
  return std::nullopt;
}

std::optional<std::string_view> failureCategoryName(FailureCategory category) noexcept
{
  switch (category) {
    case FailureCategory::CONFIGURATION:
      return "CONFIGURATION";
    case FailureCategory::OBSERVATION:
      return "OBSERVATION";
    case FailureCategory::PRECONDITION:
      return "PRECONDITION";
    case FailureCategory::PLANNING:
      return "PLANNING";
    case FailureCategory::PLAN_VALIDATION:
      return "PLAN_VALIDATION";
    case FailureCategory::EXECUTION:
      return "EXECUTION";
    case FailureCategory::POSTCONDITION:
      return "POSTCONDITION";
    case FailureCategory::COLLISION:
      return "COLLISION";
    case FailureCategory::TF:
      return "TF";
    case FailureCategory::GRIPPER:
      return "GRIPPER";
    case FailureCategory::GAZEBO_ATTACHMENT:
      return "GAZEBO_ATTACHMENT";
    case FailureCategory::MOVEIT_SCENE:
      return "MOVEIT_SCENE";
    case FailureCategory::WORLD_INCONSISTENCY:
      return "WORLD_INCONSISTENCY";
    case FailureCategory::CHECKPOINT:
      return "CHECKPOINT";
    case FailureCategory::RESUME_VALIDATION:
      return "RESUME_VALIDATION";
    case FailureCategory::INTERNAL:
      return "INTERNAL";
  }
  return std::nullopt;
}

std::optional<FailureCategory> failureCategoryFromName(std::string_view value) noexcept
{
  for (int raw = static_cast<int>(FailureCategory::CONFIGURATION);
       raw <= static_cast<int>(FailureCategory::INTERNAL); ++raw) {
    const auto category = static_cast<FailureCategory>(raw);
    if (failureCategoryName(category) == value) {
      return category;
    }
  }
  return std::nullopt;
}

bool poseIsFinite(const Pose3d & pose) noexcept
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

template <typename Value> bool mapHasValidNames(const std::map<std::string, Value> & values)
{
  return std::all_of(values.begin(), values.end(),
                     [](const auto & item) { return !item.first.empty(); });
}

std::optional<Failure> validateCheckpoint(const Checkpoint & checkpoint)
{
  if (checkpoint.schema_version != 3) {
    return checkpointFailure("CHECKPOINT_INCOMPATIBLE",
                             "Only checkpoint schema version 3 is supported");
  }
  if (!runModeName(checkpoint.source_mode) || !checkpointPhaseName(checkpoint.phase) ||
      !stateName(checkpoint.last_completed_state) || !stateName(checkpoint.next_state) ||
      (checkpoint.failed_state && !stateName(*checkpoint.failed_state))) {
    return checkpointFailure("CHECKPOINT_INVALID_ENUM",
                             "Checkpoint contains an unsupported mode, phase, or state");
  }
  if (checkpoint.original_failure && !failureCategoryName(checkpoint.original_failure->category)) {
    return checkpointFailure("CHECKPOINT_INVALID_ENUM",
                             "Checkpoint contains an unsupported failure category");
  }
  const bool has_failed_state = checkpoint.failed_state.has_value();
  const bool has_original_failure = checkpoint.original_failure.has_value();
  const bool is_physical_validation_checkpoint =
    checkpoint.phase == CheckpointPhase::FORWARD &&
    checkpoint.last_completed_state == State::VERIFY_PHYSICAL_GRASP &&
    checkpoint.failed_state == State::VERIFY_PHYSICAL_GRASP &&
    checkpoint.next_state == State::VALIDATION_FAILED && checkpoint.original_failure &&
    checkpoint.original_failure->category == FailureCategory::POSTCONDITION &&
    checkpoint.original_failure->code.rfind("PHYSICAL_GRASP_", 0) == 0;
  if (checkpoint.source_mode == RunMode::DRY_RUN ||
      (checkpoint.phase == CheckpointPhase::RECOVERY &&
       (checkpoint.source_mode != RunMode::EXECUTE || !checkpoint.resumable))) {
    return checkpointFailure("CHECKPOINT_INVALID_DATA",
                             "Recovery checkpoints require execute mode and a resumable context");
  }
  if (has_failed_state != has_original_failure ||
      (checkpoint.phase == CheckpointPhase::RECOVERY && !has_failed_state) ||
      (checkpoint.phase == CheckpointPhase::FORWARD && has_failed_state &&
       !is_physical_validation_checkpoint)) {
    return checkpointFailure("CHECKPOINT_INVALID_DATA",
                             "Checkpoint recovery context does not match its phase");
  }
  if (!poseIsFinite(checkpoint.expected.tcp_pose_world) ||
      (checkpoint.expected.gazebo_task_object_pose_world &&
       !poseIsFinite(*checkpoint.expected.gazebo_task_object_pose_world)) ||
      !mapHasValidNames(checkpoint.expected.joint_positions) ||
      !mapHasValidNames(checkpoint.expected.moveit_world_object_poses)) {
    return checkpointFailure("CHECKPOINT_INVALID_DATA",
                             "Checkpoint world expectation contains invalid names or poses");
  }
  for (const auto & [name, value] : checkpoint.expected.joint_positions) {
    (void)name;
    if (!std::isfinite(value)) {
      return checkpointFailure("CHECKPOINT_INVALID_DATA",
                               "Checkpoint joint positions must be finite");
    }
  }
  for (const auto & [name, pose] : checkpoint.expected.moveit_world_object_poses) {
    (void)name;
    if (!poseIsFinite(pose)) {
      return checkpointFailure("CHECKPOINT_INVALID_DATA",
                               "Checkpoint MoveIt world poses must be finite");
    }
  }
  if (checkpoint.original_failure) {
    if (!mapHasValidNames(checkpoint.original_failure->metrics)) {
      return checkpointFailure("CHECKPOINT_INVALID_DATA",
                               "Checkpoint failure metric names must not be empty");
    }
    for (const auto & [name, value] : checkpoint.original_failure->metrics) {
      (void)name;
      if (!std::isfinite(value)) {
        return checkpointFailure("CHECKPOINT_INVALID_DATA",
                                 "Checkpoint failure metrics must be finite");
      }
    }
  }
  std::set<std::string> required_objects;
  for (const auto & object : checkpoint.expected.required_world_objects) {
    if (object.empty() || !required_objects.insert(object).second) {
      return checkpointFailure("CHECKPOINT_INVALID_DATA",
                               "Required world-object names must be non-empty and unique");
    }
  }
  return std::nullopt;
}

Json poseToJson(const Pose3d & pose)
{
  return {{"x", pose.x},   {"y", pose.y},   {"z", pose.z},  {"qx", pose.qx},
          {"qy", pose.qy}, {"qz", pose.qz}, {"qw", pose.qw}};
}

Json poseMapToJson(const std::map<std::string, Pose3d> & poses)
{
  auto json = Json::object();
  for (const auto & [name, pose] : poses) {
    json[name] = poseToJson(pose);
  }
  return json;
}

Json failureToJson(const Failure & failure)
{
  return {{"category", *failureCategoryName(failure.category)},
          {"code", failure.code},
          {"message", failure.message},
          {"metrics", failure.metrics}};
}

Json checkpointToJson(const Checkpoint & checkpoint)
{
  return {
    {"schema_version", checkpoint.schema_version},
    {"run_id", checkpoint.run_id},
    {"sequence", checkpoint.sequence},
    {"source_mode", *runModeName(checkpoint.source_mode)},
    {"phase", *checkpointPhaseName(checkpoint.phase)},
    {"last_completed_state", *stateName(checkpoint.last_completed_state)},
    {"failed_state",
     checkpoint.failed_state ? Json(*stateName(*checkpoint.failed_state)) : Json(nullptr)},
    {"original_failure",
     checkpoint.original_failure ? failureToJson(*checkpoint.original_failure) : Json(nullptr)},
    {"next_state", *stateName(checkpoint.next_state)},
    {"expected",
     {{"tcp_pose_world", poseToJson(checkpoint.expected.tcp_pose_world)},
      {"gripper_open", checkpoint.expected.gripper_open},
      {"joint_positions", checkpoint.expected.joint_positions},
      {"moveit_world_object_poses", poseMapToJson(checkpoint.expected.moveit_world_object_poses)},
      {"moveit_task_object_attached", checkpoint.expected.moveit_task_object_attached
                                        ? Json(*checkpoint.expected.moveit_task_object_attached)
                                        : Json(nullptr)},
      {"gazebo_task_object_pose_world",
       checkpoint.expected.gazebo_task_object_pose_world
         ? poseToJson(*checkpoint.expected.gazebo_task_object_pose_world)
         : Json(nullptr)},
      {"gazebo_task_object_attached", checkpoint.expected.gazebo_task_object_attached
                                        ? Json(*checkpoint.expected.gazebo_task_object_attached)
                                        : Json(nullptr)},
      {"gazebo_task_object_stationary", checkpoint.expected.gazebo_task_object_stationary
                                          ? Json(*checkpoint.expected.gazebo_task_object_stationary)
                                          : Json(nullptr)},
      {"required_world_objects", checkpoint.expected.required_world_objects}}},
    {"policy_bundle_sha256", checkpoint.policy_bundle_sha256},
    {"simulation_session_id", checkpoint.simulation_session_id},
    {"resumable", checkpoint.resumable},
  };
}

bool hasExactKeys(const Json & json, std::initializer_list<std::string_view> expected)
{
  if (!json.is_object() || json.size() != expected.size()) {
    return false;
  }
  return std::all_of(expected.begin(), expected.end(),
                     [&](const auto key) { return json.contains(std::string(key)); });
}

bool isFiniteNumber(const Json & json)
{
  return json.is_number() && std::isfinite(json.get<double>());
}

bool isStrictPose(const Json & json)
{
  if (!hasExactKeys(json, {"x", "y", "z", "qx", "qy", "qz", "qw"})) {
    return false;
  }
  constexpr std::array keys{"x", "y", "z", "qx", "qy", "qz", "qw"};
  return std::all_of(keys.begin(), keys.end(),
                     [&](const auto key) { return isFiniteNumber(json.at(key)); });
}

bool isFiniteNumberMap(const Json & json)
{
  if (!json.is_object()) {
    return false;
  }
  return std::all_of(json.items().begin(), json.items().end(), [](const auto & item) {
    return !item.key().empty() && isFiniteNumber(item.value());
  });
}

bool isPoseMap(const Json & json)
{
  if (!json.is_object()) {
    return false;
  }
  return std::all_of(json.items().begin(), json.items().end(), [](const auto & item) {
    return !item.key().empty() && isStrictPose(item.value());
  });
}

bool isOptionalBool(const Json & json)
{
  return json.is_null() || json.is_boolean();
}

bool isRequiredObjectArray(const Json & json)
{
  if (!json.is_array()) {
    return false;
  }
  std::set<std::string> names;
  for (const auto & value : json) {
    if (!value.is_string()) {
      return false;
    }
    const auto name = value.get<std::string>();
    if (name.empty() || !names.insert(name).second) {
      return false;
    }
  }
  return true;
}

Pose3d poseFromJson(const Json & json)
{
  return {json.at("x").get<double>(),  json.at("y").get<double>(),  json.at("z").get<double>(),
          json.at("qx").get<double>(), json.at("qy").get<double>(), json.at("qz").get<double>(),
          json.at("qw").get<double>()};
}

std::map<std::string, Pose3d> poseMapFromJson(const Json & json)
{
  std::map<std::string, Pose3d> poses;
  for (const auto & [name, pose] : json.items()) {
    poses.emplace(name, poseFromJson(pose));
  }
  return poses;
}

std::optional<Failure> validateJsonShape(const Json & json)
{
  if (!json.is_object() || !json.contains("schema_version") ||
      !json.at("schema_version").is_number_unsigned()) {
    return checkpointFailure("CHECKPOINT_PARSE_FAILED",
                             "Checkpoint root or schema_version has the wrong type");
  }
  if (json.at("schema_version").get<std::uint32_t>() != 3) {
    return checkpointFailure("CHECKPOINT_INCOMPATIBLE",
                             "Only checkpoint schema version 3 is supported");
  }
  if (!hasExactKeys(json,
                    {"schema_version", "run_id", "sequence", "source_mode", "phase",
                     "last_completed_state", "failed_state", "original_failure", "next_state",
                     "expected", "policy_bundle_sha256", "simulation_session_id", "resumable"})) {
    return checkpointFailure("CHECKPOINT_PARSE_FAILED",
                             "Checkpoint root keys do not match schema v3");
  }
  if (!json.at("run_id").is_string() || !json.at("sequence").is_number_unsigned() ||
      !json.at("source_mode").is_string() || !json.at("phase").is_string() ||
      !json.at("last_completed_state").is_string() ||
      !(json.at("failed_state").is_null() || json.at("failed_state").is_string()) ||
      !(json.at("original_failure").is_null() || json.at("original_failure").is_object()) ||
      !json.at("next_state").is_string() || !json.at("policy_bundle_sha256").is_string() ||
      !json.at("simulation_session_id").is_string() || !json.at("resumable").is_boolean()) {
    return checkpointFailure("CHECKPOINT_PARSE_FAILED",
                             "Checkpoint scalar or optional fields have the wrong type");
  }
  const auto & expected = json.at("expected");
  if (!hasExactKeys(expected, {"tcp_pose_world", "gripper_open", "joint_positions",
                               "moveit_world_object_poses", "moveit_task_object_attached",
                               "gazebo_task_object_pose_world", "gazebo_task_object_attached",
                               "gazebo_task_object_stationary", "required_world_objects"}) ||
      !isStrictPose(expected.at("tcp_pose_world")) || !expected.at("gripper_open").is_boolean() ||
      !isFiniteNumberMap(expected.at("joint_positions")) ||
      !isPoseMap(expected.at("moveit_world_object_poses")) ||
      !isOptionalBool(expected.at("moveit_task_object_attached")) ||
      !(expected.at("gazebo_task_object_pose_world").is_null() ||
        isStrictPose(expected.at("gazebo_task_object_pose_world"))) ||
      !isOptionalBool(expected.at("gazebo_task_object_attached")) ||
      !isOptionalBool(expected.at("gazebo_task_object_stationary")) ||
      !isRequiredObjectArray(expected.at("required_world_objects"))) {
    return checkpointFailure("CHECKPOINT_PARSE_FAILED",
                             "Checkpoint world expectation does not match schema v3");
  }
  if (!json.at("original_failure").is_null()) {
    const auto & failure = json.at("original_failure");
    if (!hasExactKeys(failure, {"category", "code", "message", "metrics"}) ||
        !failure.at("category").is_string() || !failure.at("code").is_string() ||
        !failure.at("message").is_string() || !isFiniteNumberMap(failure.at("metrics"))) {
      return checkpointFailure("CHECKPOINT_PARSE_FAILED",
                               "Checkpoint failure context does not match schema v3");
    }
  }
  return std::nullopt;
}

CheckpointLoadResult checkpointFromJson(const Json & json)
{
  if (const auto shape_failure = validateJsonShape(json)) {
    return {std::nullopt, shape_failure};
  }
  const auto source_mode = runModeFromString(json.at("source_mode").get<std::string>());
  const auto phase = checkpointPhaseFromName(json.at("phase").get<std::string>());
  const auto last_completed = stateFromString(json.at("last_completed_state").get<std::string>());
  const auto next_state = stateFromString(json.at("next_state").get<std::string>());
  std::optional<State> failed_state;
  if (!json.at("failed_state").is_null()) {
    failed_state = stateFromString(json.at("failed_state").get<std::string>());
  }
  std::optional<FailureCategory> failure_category;
  if (!json.at("original_failure").is_null()) {
    failure_category =
      failureCategoryFromName(json.at("original_failure").at("category").get<std::string>());
  }
  if (!source_mode || !phase || !last_completed || !next_state ||
      (!json.at("failed_state").is_null() && !failed_state) ||
      (!json.at("original_failure").is_null() && !failure_category)) {
    return {std::nullopt, checkpointFailure("CHECKPOINT_INVALID_ENUM",
                                            "Checkpoint contains an unsupported enum name")};
  }

  Checkpoint checkpoint;
  checkpoint.schema_version = json.at("schema_version").get<std::uint32_t>();
  checkpoint.run_id = json.at("run_id").get<std::string>();
  checkpoint.sequence = json.at("sequence").get<std::uint64_t>();
  checkpoint.source_mode = *source_mode;
  checkpoint.phase = *phase;
  checkpoint.last_completed_state = *last_completed;
  checkpoint.failed_state = failed_state;
  if (failure_category) {
    const auto & failure = json.at("original_failure");
    checkpoint.original_failure =
      Failure{*failure_category, failure.at("code").get<std::string>(),
              failure.at("message").get<std::string>(),
              failure.at("metrics").get<std::map<std::string, double>>()};
  }
  checkpoint.next_state = *next_state;
  const auto & expected = json.at("expected");
  checkpoint.expected.tcp_pose_world = poseFromJson(expected.at("tcp_pose_world"));
  checkpoint.expected.gripper_open = expected.at("gripper_open").get<bool>();
  checkpoint.expected.joint_positions =
    expected.at("joint_positions").get<std::map<std::string, double>>();
  checkpoint.expected.moveit_world_object_poses =
    poseMapFromJson(expected.at("moveit_world_object_poses"));
  if (!expected.at("moveit_task_object_attached").is_null()) {
    checkpoint.expected.moveit_task_object_attached =
      expected.at("moveit_task_object_attached").get<bool>();
  }
  if (!expected.at("gazebo_task_object_pose_world").is_null()) {
    checkpoint.expected.gazebo_task_object_pose_world =
      poseFromJson(expected.at("gazebo_task_object_pose_world"));
  }
  if (!expected.at("gazebo_task_object_attached").is_null()) {
    checkpoint.expected.gazebo_task_object_attached =
      expected.at("gazebo_task_object_attached").get<bool>();
  }
  if (!expected.at("gazebo_task_object_stationary").is_null()) {
    checkpoint.expected.gazebo_task_object_stationary =
      expected.at("gazebo_task_object_stationary").get<bool>();
  }
  checkpoint.expected.required_world_objects =
    expected.at("required_world_objects").get<std::vector<std::string>>();
  checkpoint.policy_bundle_sha256 = json.at("policy_bundle_sha256").get<std::string>();
  checkpoint.simulation_session_id = json.at("simulation_session_id").get<std::string>();
  checkpoint.resumable = json.at("resumable").get<bool>();
  if (const auto validation_failure = validateCheckpoint(checkpoint)) {
    return {std::nullopt, validation_failure};
  }
  return {checkpoint, std::nullopt};
}

std::string errnoMessage(int error)
{
  return std::error_code(error, std::generic_category()).message();
}

bool writeAll(int descriptor, std::string_view data, int & error)
{
  std::size_t written = 0;
  while (written < data.size()) {
    const auto result = ::write(descriptor, data.data() + written, data.size() - written);
    if (result < 0 && errno == EINTR) {
      continue;
    }
    if (result <= 0) {
      error = result < 0 ? errno : EIO;
      return false;
    }
    written += static_cast<std::size_t>(result);
  }
  return true;
}

}  // namespace

std::optional<Failure> FileCheckpointStore::commit(const Checkpoint & checkpoint)
{
  if (const auto validation_failure = validateCheckpoint(checkpoint)) {
    return validation_failure;
  }
  if (path_.empty()) {
    return checkpointFailure("CHECKPOINT_WRITE_OPEN_FAILED", "Checkpoint path must not be empty");
  }

  std::error_code error;
  const auto parent =
    path_.parent_path().empty() ? std::filesystem::path(".") : path_.parent_path();
  std::filesystem::create_directories(parent, error);
  if (error) {
    return checkpointFailure("CHECKPOINT_DIRECTORY_CREATE_FAILED",
                             "Unable to create checkpoint directory: " + error.message());
  }

  auto temporary_template = path_.string() + ".tmp.XXXXXX";
  std::vector<char> temporary_buffer(temporary_template.begin(), temporary_template.end());
  temporary_buffer.push_back('\0');
  const int descriptor = ::mkstemp(temporary_buffer.data());
  if (descriptor < 0) {
    return checkpointFailure("CHECKPOINT_WRITE_OPEN_FAILED",
                             "Unable to open temporary checkpoint file: " + errnoMessage(errno));
  }
  const std::filesystem::path temporary_path(temporary_buffer.data());
  (void)::fcntl(descriptor, F_SETFD, FD_CLOEXEC);
  const auto data = checkpointToJson(checkpoint).dump(2) + '\n';
  int write_error = 0;
  if (!writeAll(descriptor, data, write_error) || ::fsync(descriptor) != 0) {
    const auto saved_error = write_error != 0 ? write_error : errno;
    (void)::close(descriptor);
    std::filesystem::remove(temporary_path, error);
    return checkpointFailure("CHECKPOINT_WRITE_FAILED",
                             "Unable to durably write temporary checkpoint file: " +
                               errnoMessage(saved_error));
  }
  if (::close(descriptor) != 0) {
    const auto saved_error = errno;
    std::filesystem::remove(temporary_path, error);
    return checkpointFailure("CHECKPOINT_WRITE_FAILED",
                             "Unable to close temporary checkpoint file: " +
                               errnoMessage(saved_error));
  }
  if (::rename(temporary_path.c_str(), path_.c_str()) != 0) {
    const auto saved_error = errno;
    std::filesystem::remove(temporary_path, error);
    return checkpointFailure("CHECKPOINT_ATOMIC_RENAME_FAILED",
                             "Unable to atomically commit checkpoint: " +
                               errnoMessage(saved_error));
  }

  const int directory_descriptor = ::open(parent.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
  if (directory_descriptor < 0) {
    return checkpointFailure("CHECKPOINT_DIRECTORY_SYNC_FAILED",
                             "Unable to open checkpoint directory for fsync: " +
                               errnoMessage(errno));
  }
  if (::fsync(directory_descriptor) != 0) {
    const auto saved_error = errno;
    (void)::close(directory_descriptor);
    return checkpointFailure("CHECKPOINT_DIRECTORY_SYNC_FAILED",
                             "Unable to fsync checkpoint directory: " + errnoMessage(saved_error));
  }
  if (::close(directory_descriptor) != 0) {
    return checkpointFailure("CHECKPOINT_DIRECTORY_SYNC_FAILED",
                             "Unable to close checkpoint directory: " + errnoMessage(errno));
  }
  return std::nullopt;
}

CheckpointLoadResult FileCheckpointStore::loadLatestCompatible()
{
  std::ifstream input(path_, std::ios::in | std::ios::binary);
  if (!input) {
    return {std::nullopt,
            checkpointFailure("CHECKPOINT_NOT_FOUND", "No checkpoint exists at " + path_.string())};
  }
  try {
    const std::string contents((std::istreambuf_iterator<char>(input)),
                               std::istreambuf_iterator<char>());
    if (!input.eof() && input.fail()) {
      return {std::nullopt, checkpointFailure("CHECKPOINT_READ_FAILED",
                                              "Unable to read checkpoint at " + path_.string())};
    }
    const auto json = Json::parse(contents);
    return checkpointFromJson(json);
  } catch (const std::exception & exception) {
    return {std::nullopt,
            checkpointFailure("CHECKPOINT_PARSE_FAILED",
                              "Unable to parse checkpoint JSON: " + std::string(exception.what()))};
  }
}

}  // namespace so101_gazebo_demo::pick_place

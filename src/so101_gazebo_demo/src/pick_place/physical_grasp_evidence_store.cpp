#include "so101_gazebo_demo/pick_place/physical_grasp_evidence_store.hpp"

#include <cerrno>
#include <chrono>
#include <cmath>
#include <fcntl.h>
#include <fstream>
#include <nlohmann/json.hpp>
#include <string_view>
#include <system_error>
#include <unistd.h>

#include "pick_place_common/pose_geometry.hpp"

namespace so101_gazebo_demo::pick_place
{
namespace
{
using Json = nlohmann::json;

Failure failure(std::string code, std::string message)
{
  return {FailureCategory::OBSERVATION, std::move(code), std::move(message), {}};
}

bool validSample(const PhysicalGraspSample & sample, State expected)
{
  return sample.capture_state == expected && sample.captured_at_unix_ns > 0 &&
         pick_place_common::isFinitePose(sample.tcp_pose_world) &&
         pick_place_common::hasUsableQuaternion(sample.tcp_pose_world) &&
         pick_place_common::isFinitePose(sample.task_object_pose_world) &&
         pick_place_common::hasUsableQuaternion(sample.task_object_pose_world);
}

Json poseJson(const Pose3d & pose)
{
  return {{"x", pose.x},   {"y", pose.y},   {"z", pose.z},  {"qx", pose.qx},
          {"qy", pose.qy}, {"qz", pose.qz}, {"qw", pose.qw}};
}

Pose3d parsePose(const Json & value)
{
  return {value.at("x").get<double>(),  value.at("y").get<double>(),  value.at("z").get<double>(),
          value.at("qx").get<double>(), value.at("qy").get<double>(), value.at("qz").get<double>(),
          value.at("qw").get<double>()};
}

Json sampleJson(const PhysicalGraspSample & sample)
{
  return {{"capture_state", toString(sample.capture_state)},
          {"captured_at_unix_ns", sample.captured_at_unix_ns},
          {"tcp_pose_world", poseJson(sample.tcp_pose_world)},
          {"task_object_pose_world", poseJson(sample.task_object_pose_world)},
          {"gripper_contact", sample.gripper_contact}};
}

PhysicalGraspSample parseSample(const Json & value)
{
  const auto state = stateFromString(value.at("capture_state").get<std::string>());
  if (!state)
    throw std::runtime_error("unknown capture state");
  return {*state, value.at("captured_at_unix_ns").get<std::int64_t>(),
          parsePose(value.at("tcp_pose_world")), parsePose(value.at("task_object_pose_world")),
          value.at("gripper_contact").get<bool>()};
}

std::string_view phaseName(PhysicalGraspRetryPhase phase)
{
  switch (phase) {
    case PhysicalGraspRetryPhase::IDLE:
      return "IDLE";
    case PhysicalGraspRetryPhase::OPEN_PENDING:
      return "OPEN_PENDING";
    case PhysicalGraspRetryPhase::DESCEND_PENDING:
      return "DESCEND_PENDING";
    case PhysicalGraspRetryPhase::CLOSE_PENDING:
      return "CLOSE_PENDING";
    case PhysicalGraspRetryPhase::LIFT_PENDING:
      return "LIFT_PENDING";
    case PhysicalGraspRetryPhase::VERIFY_PENDING:
      return "VERIFY_PENDING";
    case PhysicalGraspRetryPhase::COMPLETE:
      return "COMPLETE";
  }
  return "UNKNOWN";
}

PhysicalGraspRetryPhase parsePhase(const std::string & value)
{
  if (value == "IDLE")
    return PhysicalGraspRetryPhase::IDLE;
  if (value == "OPEN_PENDING")
    return PhysicalGraspRetryPhase::OPEN_PENDING;
  if (value == "DESCEND_PENDING")
    return PhysicalGraspRetryPhase::DESCEND_PENDING;
  if (value == "CLOSE_PENDING")
    return PhysicalGraspRetryPhase::CLOSE_PENDING;
  if (value == "LIFT_PENDING")
    return PhysicalGraspRetryPhase::LIFT_PENDING;
  if (value == "VERIFY_PENDING")
    return PhysicalGraspRetryPhase::VERIFY_PENDING;
  if (value == "COMPLETE")
    return PhysicalGraspRetryPhase::COMPLETE;
  throw std::runtime_error("unknown retry phase");
}

Json retryJson(const PhysicalGraspRetryEvidence & retry)
{
  return {{"attempt_index", retry.progress.attempt_index},
          {"contact_missing_count", retry.progress.contact_missing_count},
          {"current_reclose_target_q6", retry.progress.current_reclose_target_q6},
          {"micro_lift_preload_target_q6", retry.micro_lift_preload_target_q6},
          {"phase", phaseName(retry.phase)}};
}

Json recordJson(const PhysicalGraspEvidenceRecord & record)
{
  return {{"schema_version", 2},
          {"simulation_session_id", record.simulation_session_id},
          {"configuration_fingerprint", record.configuration_fingerprint},
          {"retry", retryJson(record.retry)},
          {"before_lift", record.before_lift ? sampleJson(*record.before_lift) : Json(nullptr)},
          {"after_lift", record.after_lift ? sampleJson(*record.after_lift) : Json(nullptr)}};
}

std::optional<Failure> writeAtomically(const std::filesystem::path & path, const Json & document)
{
  const auto temporary = path.string() + ".tmp";
  const auto body = document.dump();
  const int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0600);
  if (fd < 0)
    return failure("PHYSICAL_GRASP_EVIDENCE_WRITE_FAILED", "Unable to create evidence sidecar");
  std::size_t offset = 0;
  while (offset < body.size()) {
    const auto written = ::write(fd, body.data() + offset, body.size() - offset);
    if (written <= 0) {
      ::close(fd);
      return failure("PHYSICAL_GRASP_EVIDENCE_WRITE_FAILED", "Unable to write evidence sidecar");
    }
    offset += static_cast<std::size_t>(written);
  }
  if (::fsync(fd) != 0 || ::close(fd) != 0 || ::rename(temporary.c_str(), path.c_str()) != 0)
    return failure("PHYSICAL_GRASP_EVIDENCE_WRITE_FAILED", "Unable to commit evidence sidecar");
  const int directory = ::open(path.parent_path().c_str(), O_RDONLY | O_DIRECTORY);
  if (directory < 0 || ::fsync(directory) != 0) {
    if (directory >= 0)
      ::close(directory);
    return failure("PHYSICAL_GRASP_EVIDENCE_WRITE_FAILED",
                   "Unable to sync evidence sidecar directory");
  }
  ::close(directory);
  return std::nullopt;
}
}  // namespace

FilePhysicalGraspEvidenceStore::FilePhysicalGraspEvidenceStore(
  std::filesystem::path path, std::string simulation_session_id,
  std::string configuration_fingerprint) :
    path_(std::move(path)), simulation_session_id_(std::move(simulation_session_id)),
    configuration_fingerprint_(std::move(configuration_fingerprint))
{
}

std::optional<Failure> FilePhysicalGraspEvidenceStore::resetForFreshRun()
{
  if (simulation_session_id_.empty() || configuration_fingerprint_.empty())
    return failure("PHYSICAL_GRASP_EVIDENCE_PROVENANCE_INVALID",
                   "Evidence provenance identifiers are required");
  std::error_code error;
  std::filesystem::remove(path_, error);
  if (error)
    return failure("PHYSICAL_GRASP_EVIDENCE_RESET_FAILED",
                   "Unable to remove prior evidence sidecar");
  return std::nullopt;
}

std::optional<Failure> FilePhysicalGraspEvidenceStore::saveBefore(const WorldSnapshot & snapshot)
{
  if (!snapshot.gazebo_task_object_pose_world)
    return failure("PHYSICAL_GRASP_EVIDENCE_SAMPLE_INVALID", "Before-lift cup pose is required");
  PhysicalGraspSample sample{State::WAIT_GRASP_STABLE,
                             std::chrono::duration_cast<std::chrono::nanoseconds>(
                               std::chrono::system_clock::now().time_since_epoch())
                               .count(),
                             snapshot.tcp_pose_world, *snapshot.gazebo_task_object_pose_world,
                             snapshot.gazebo_task_object_gripper_contact.value_or(false)};
  if (!validSample(sample, State::WAIT_GRASP_STABLE))
    return failure("PHYSICAL_GRASP_EVIDENCE_SAMPLE_INVALID", "Before-lift evidence is invalid");
  PhysicalGraspEvidenceRecord record;
  record.simulation_session_id = simulation_session_id_;
  record.configuration_fingerprint = configuration_fingerprint_;
  record.before_lift = sample;
  if (std::filesystem::exists(path_)) {
    auto loaded = load();
    if (std::holds_alternative<Failure>(loaded))
      return std::get<Failure>(loaded);
    record.retry = std::get<PhysicalGraspEvidenceRecord>(loaded).retry;
  }
  return writeAtomically(path_, recordJson(record));
}

std::optional<Failure> FilePhysicalGraspEvidenceStore::saveAfter(const WorldSnapshot & snapshot)
{
  auto loaded = load();
  if (std::holds_alternative<Failure>(loaded))
    return std::get<Failure>(std::move(loaded));
  auto record = std::get<PhysicalGraspEvidenceRecord>(std::move(loaded));
  if (!snapshot.gazebo_task_object_pose_world)
    return failure("PHYSICAL_GRASP_EVIDENCE_SAMPLE_INVALID", "After-lift cup pose is required");
  PhysicalGraspSample sample{State::WAIT_MICRO_LIFT_STABLE,
                             std::chrono::duration_cast<std::chrono::nanoseconds>(
                               std::chrono::system_clock::now().time_since_epoch())
                               .count(),
                             snapshot.tcp_pose_world, *snapshot.gazebo_task_object_pose_world,
                             snapshot.gazebo_task_object_gripper_contact.value_or(false)};
  if (!record.before_lift || !validSample(sample, State::WAIT_MICRO_LIFT_STABLE) ||
      sample.captured_at_unix_ns < record.before_lift->captured_at_unix_ns)
    return failure("PHYSICAL_GRASP_EVIDENCE_SAMPLE_INVALID", "After-lift evidence is invalid");
  record.after_lift = sample;
  return writeAtomically(path_, recordJson(record));
}

std::optional<Failure>
FilePhysicalGraspEvidenceStore::saveRetryEvidence(const PhysicalGraspRetryEvidence & retry)
{
  PhysicalGraspEvidenceRecord record;
  record.simulation_session_id = simulation_session_id_;
  record.configuration_fingerprint = configuration_fingerprint_;
  if (std::filesystem::exists(path_)) {
    auto loaded = load();
    if (std::holds_alternative<Failure>(loaded))
      return std::get<Failure>(loaded);
    record = std::get<PhysicalGraspEvidenceRecord>(std::move(loaded));
  }
  record.retry = retry;
  return writeAtomically(path_, recordJson(record));
}

std::variant<PhysicalGraspEvidenceRecord, Failure> FilePhysicalGraspEvidenceStore::load() const
{
  if (simulation_session_id_.empty() || configuration_fingerprint_.empty())
    return failure("PHYSICAL_GRASP_EVIDENCE_PROVENANCE_INVALID",
                   "Evidence provenance identifiers are required");
  try {
    std::ifstream input(path_);
    if (!input)
      return failure("PHYSICAL_GRASP_EVIDENCE_MISSING",
                     "Physical-grasp evidence sidecar is missing");
    Json document;
    input >> document;
    if (document.at("schema_version").get<int>() != 2)
      return failure("PHYSICAL_GRASP_EVIDENCE_SCHEMA_UNSUPPORTED",
                     "Evidence sidecar schema is unsupported");
    PhysicalGraspEvidenceRecord record;
    record.simulation_session_id = document.at("simulation_session_id").get<std::string>();
    record.configuration_fingerprint = document.at("configuration_fingerprint").get<std::string>();
    const auto & retry = document.at("retry");
    record.retry.progress.attempt_index = retry.at("attempt_index").get<std::size_t>();
    record.retry.progress.contact_missing_count =
      retry.at("contact_missing_count").get<std::size_t>();
    record.retry.progress.current_reclose_target_q6 =
      retry.at("current_reclose_target_q6").get<double>();
    record.retry.micro_lift_preload_target_q6 =
      retry.at("micro_lift_preload_target_q6").get<double>();
    record.retry.phase = parsePhase(retry.at("phase").get<std::string>());
    record.before_lift = document.at("before_lift").is_null()
                           ? std::nullopt
                           : std::optional{parseSample(document.at("before_lift"))};
    record.after_lift = document.at("after_lift").is_null()
                          ? std::nullopt
                          : std::optional{parseSample(document.at("after_lift"))};
    if (record.simulation_session_id != simulation_session_id_)
      return failure("PHYSICAL_GRASP_EVIDENCE_SESSION_MISMATCH",
                     "Evidence session does not match current simulation");
    if (record.configuration_fingerprint != configuration_fingerprint_)
      return failure("PHYSICAL_GRASP_EVIDENCE_FINGERPRINT_MISMATCH",
                     "Evidence fingerprint does not match current policy");
    if (record.retry.progress.attempt_index == 0 || record.retry.progress.attempt_index > 5 ||
        record.retry.progress.contact_missing_count >= record.retry.progress.attempt_index ||
        !std::isfinite(record.retry.progress.current_reclose_target_q6) ||
        !std::isfinite(record.retry.micro_lift_preload_target_q6))
      return failure("PHYSICAL_GRASP_EVIDENCE_RETRY_INVALID", "Retry evidence is invalid");
    if ((record.before_lift && !validSample(*record.before_lift, State::WAIT_GRASP_STABLE)) ||
        (record.after_lift &&
         (!record.before_lift || !validSample(*record.after_lift, State::WAIT_MICRO_LIFT_STABLE) ||
          record.after_lift->captured_at_unix_ns < record.before_lift->captured_at_unix_ns)))
      return failure("PHYSICAL_GRASP_EVIDENCE_SAMPLE_INVALID",
                     "Evidence sidecar samples are invalid");
    return record;
  } catch (const std::exception &) {
    return failure("PHYSICAL_GRASP_EVIDENCE_CORRUPT", "Evidence sidecar is corrupt or truncated");
  }
}
}  // namespace so101_gazebo_demo::pick_place

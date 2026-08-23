#include "so101_gazebo_demo/pick_place/planning_failure_diagnostics.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <iterator>
#include <stdexcept>
#include <system_error>
#include <type_traits>

#include <openssl/evp.h>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>

#include <fcntl.h>
#include <sys/stat.h>
#if defined(__linux__)
#include <sys/syscall.h>
#endif
#include <unistd.h>

namespace so101_gazebo_demo::pick_place
{
namespace
{
constexpr char kBase64Alphabet[] =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

Failure invalidArtifact(std::string message)
{
  return {FailureCategory::CONFIGURATION,
          "PLANNING_DIAGNOSTIC_ARTIFACT_INVALID",
          std::move(message),
          {}};
}

Failure writeFailure(const std::filesystem::path & directory, std::string message)
{
  return {FailureCategory::INTERNAL,
          "PLANNING_DIAGNOSTIC_WRITE_FAILED",
          std::move(message),
          {{"directory_path_length", static_cast<double>(directory.string().size())}}};
}

Failure invalidDirectory(const std::filesystem::path & directory, std::string message)
{
  return {FailureCategory::CONFIGURATION,
          "PLANNING_DIAGNOSTICS_DIR_INVALID",
          std::move(message),
          {{"directory_path_length", static_cast<double>(directory.string().size())}}};
}

std::string base64Encode(const std::uint8_t * bytes, std::size_t size)
{
  std::string encoded;
  encoded.reserve(((size + 2U) / 3U) * 4U);
  for (std::size_t index = 0; index < size; index += 3U) {
    const std::uint32_t first = bytes[index];
    const std::uint32_t second = index + 1U < size ? bytes[index + 1U] : 0U;
    const std::uint32_t third = index + 2U < size ? bytes[index + 2U] : 0U;
    const std::uint32_t value = (first << 16U) | (second << 8U) | third;
    encoded.push_back(kBase64Alphabet[(value >> 18U) & 0x3fU]);
    encoded.push_back(kBase64Alphabet[(value >> 12U) & 0x3fU]);
    encoded.push_back(index + 1U < size ? kBase64Alphabet[(value >> 6U) & 0x3fU] : '=');
    encoded.push_back(index + 2U < size ? kBase64Alphabet[value & 0x3fU] : '=');
  }
  return encoded;
}

std::vector<std::uint8_t> base64Decode(std::string_view encoded)
{
  if (encoded.empty() || encoded.size() % 4U != 0U)
    throw std::runtime_error("invalid CDR base64 length");
  std::array<int, 256> decode{};
  decode.fill(-1);
  for (std::size_t index = 0; index < 64U; ++index)
    decode[static_cast<unsigned char>(kBase64Alphabet[index])] = static_cast<int>(index);
  std::vector<std::uint8_t> bytes;
  bytes.reserve((encoded.size() / 4U) * 3U);
  for (std::size_t index = 0; index < encoded.size(); index += 4U) {
    std::array<int, 4> values{};
    for (std::size_t offset = 0; offset < 4U; ++offset) {
      const char character = encoded[index + offset];
      values[offset] = character == '=' ? 0 : decode[static_cast<unsigned char>(character)];
      if (values[offset] < 0)
        throw std::runtime_error("invalid CDR base64 character");
    }
    const std::uint32_t value = (static_cast<std::uint32_t>(values[0]) << 18U) |
                                (static_cast<std::uint32_t>(values[1]) << 12U) |
                                (static_cast<std::uint32_t>(values[2]) << 6U) |
                                static_cast<std::uint32_t>(values[3]);
    bytes.push_back(static_cast<std::uint8_t>((value >> 16U) & 0xffU));
    if (encoded[index + 2U] != '=')
      bytes.push_back(static_cast<std::uint8_t>((value >> 8U) & 0xffU));
    if (encoded[index + 3U] != '=')
      bytes.push_back(static_cast<std::uint8_t>(value & 0xffU));
  }
  return bytes;
}

template <typename MessageT> std::string serializeCdr(const MessageT & message)
{
  rclcpp::Serialization<MessageT> serializer;
  rclcpp::SerializedMessage serialized;
  serializer.serialize_message(&message, &serialized);
  const auto & raw = serialized.get_rcl_serialized_message();
  return base64Encode(raw.buffer, raw.buffer_length);
}

template <typename MessageT> MessageT deserializeCdr(const std::string & encoded)
{
  const auto bytes = base64Decode(encoded);
  rclcpp::SerializedMessage serialized(bytes.size());
  auto & raw = serialized.get_rcl_serialized_message();
  std::memcpy(raw.buffer, bytes.data(), bytes.size());
  raw.buffer_length = bytes.size();
  MessageT message;
  rclcpp::Serialization<MessageT> serializer;
  serializer.deserialize_message(&serialized, &message);
  return message;
}

PlanningDiagnosticsJson headerJson(const std_msgs::msg::Header & header)
{
  return {{"stamp", {{"sec", header.stamp.sec}, {"nanosec", header.stamp.nanosec}}},
          {"frame_id", header.frame_id}};
}

PlanningDiagnosticsJson poseJson(const geometry_msgs::msg::Pose & pose)
{
  return {{"position", {pose.position.x, pose.position.y, pose.position.z}},
          {"orientation",
           {pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w}}};
}

PlanningDiagnosticsJson poseJson(const Pose3d & pose)
{
  return {{"position", {pose.x, pose.y, pose.z}},
          {"orientation", {pose.qx, pose.qy, pose.qz, pose.qw}}};
}

template <typename ValuesT> PlanningDiagnosticsJson presentVector(const ValuesT & values)
{
  if (values.empty())
    return nullptr;
  return values;
}

PlanningDiagnosticsJson jointStateJson(const sensor_msgs::msg::JointState & state)
{
  return {
    {"header", headerJson(state.header)},          {"name", state.name},
    {"position", presentVector(state.position)},   {"velocity", presentVector(state.velocity)},
    {"effort", presentVector(state.effort)},       {"position_present", !state.position.empty()},
    {"velocity_present", !state.velocity.empty()}, {"effort_present", !state.effort.empty()}};
}

PlanningDiagnosticsJson constraintsSummary(const moveit_msgs::msg::Constraints & constraints)
{
  PlanningDiagnosticsJson joint_constraints = PlanningDiagnosticsJson::array();
  for (const auto & joint : constraints.joint_constraints) {
    joint_constraints.push_back({{"joint_name", joint.joint_name},
                                 {"position", joint.position},
                                 {"tolerance_above", joint.tolerance_above},
                                 {"tolerance_below", joint.tolerance_below},
                                 {"weight", joint.weight}});
  }
  PlanningDiagnosticsJson positions = PlanningDiagnosticsJson::array();
  for (const auto & position : constraints.position_constraints) {
    positions.push_back({{"header", headerJson(position.header)},
                         {"link_name", position.link_name},
                         {"target_point_offset",
                          {position.target_point_offset.x, position.target_point_offset.y,
                           position.target_point_offset.z}},
                         {"weight", position.weight},
                         {"primitive_count", position.constraint_region.primitives.size()},
                         {"mesh_count", position.constraint_region.meshes.size()}});
  }
  PlanningDiagnosticsJson orientations = PlanningDiagnosticsJson::array();
  for (const auto & orientation : constraints.orientation_constraints) {
    orientations.push_back(
      {{"header", headerJson(orientation.header)},
       {"link_name", orientation.link_name},
       {"orientation",
        {orientation.orientation.x, orientation.orientation.y, orientation.orientation.z,
         orientation.orientation.w}},
       {"absolute_axis_tolerances",
        {orientation.absolute_x_axis_tolerance, orientation.absolute_y_axis_tolerance,
         orientation.absolute_z_axis_tolerance}},
       {"parameterization", orientation.parameterization},
       {"weight", orientation.weight}});
  }
  return {{"name", constraints.name},
          {"joint_constraints", joint_constraints},
          {"position_constraints", positions},
          {"orientation_constraints", orientations},
          {"visibility_constraint_count", constraints.visibility_constraints.size()}};
}

PlanningDiagnosticsJson collisionObjectSummary(const moveit_msgs::msg::CollisionObject & object)
{
  PlanningDiagnosticsJson primitives = PlanningDiagnosticsJson::array();
  for (const auto & primitive : object.primitives)
    primitives.push_back({{"type", primitive.type}, {"dimensions", primitive.dimensions}});
  PlanningDiagnosticsJson primitive_poses = PlanningDiagnosticsJson::array();
  for (const auto & pose : object.primitive_poses)
    primitive_poses.push_back(poseJson(pose));
  PlanningDiagnosticsJson mesh_shapes = PlanningDiagnosticsJson::array();
  for (const auto & mesh : object.meshes) {
    mesh_shapes.push_back(
      {{"triangles", mesh.triangles.size()}, {"vertices", mesh.vertices.size()}});
  }
  PlanningDiagnosticsJson mesh_poses = PlanningDiagnosticsJson::array();
  for (const auto & pose : object.mesh_poses)
    mesh_poses.push_back(poseJson(pose));
  PlanningDiagnosticsJson plane_shapes = PlanningDiagnosticsJson::array();
  for (const auto & plane : object.planes)
    plane_shapes.push_back(plane.coef);
  PlanningDiagnosticsJson plane_poses = PlanningDiagnosticsJson::array();
  for (const auto & pose : object.plane_poses)
    plane_poses.push_back(poseJson(pose));
  return {{"header", headerJson(object.header)},
          {"pose", poseJson(object.pose)},
          {"id", object.id},
          {"type", {{"key", object.type.key}, {"db", object.type.db}}},
          {"operation", object.operation},
          {"primitives", primitives},
          {"primitive_poses", primitive_poses},
          {"meshes", mesh_shapes},
          {"mesh_poses", mesh_poses},
          {"planes", plane_shapes},
          {"plane_poses", plane_poses},
          {"subframe_names", object.subframe_names},
          {"subframe_poses", object.subframe_poses.size()}};
}

PlanningDiagnosticsJson sceneMirror(const moveit_msgs::msg::PlanningScene & scene)
{
  PlanningDiagnosticsJson world = PlanningDiagnosticsJson::array();
  for (const auto & object : scene.world.collision_objects)
    world.push_back(collisionObjectSummary(object));
  PlanningDiagnosticsJson attached = PlanningDiagnosticsJson::array();
  for (const auto & body : scene.robot_state.attached_collision_objects) {
    attached.push_back({{"link_name", body.link_name},
                        {"object", collisionObjectSummary(body.object)},
                        {"touch_links", body.touch_links},
                        {"weight", body.weight}});
  }
  PlanningDiagnosticsJson acm_rows = PlanningDiagnosticsJson::array();
  for (const auto & row : scene.allowed_collision_matrix.entry_values)
    acm_rows.push_back(row.enabled);
  return {{"name", scene.name},
          {"robot_model_name", scene.robot_model_name},
          {"robot_state",
           {{"joint_state", jointStateJson(scene.robot_state.joint_state)},
            {"attached_collision_objects", attached},
            {"is_diff", scene.robot_state.is_diff}}},
          {"fixed_frame_transform_count", scene.fixed_frame_transforms.size()},
          {"allowed_collision_matrix",
           {{"entry_names", scene.allowed_collision_matrix.entry_names},
            {"entry_values", acm_rows},
            {"default_entry_names", scene.allowed_collision_matrix.default_entry_names},
            {"default_entry_values", scene.allowed_collision_matrix.default_entry_values}}},
          {"world", world},
          {"link_padding_count", scene.link_padding.size()},
          {"link_scale_count", scene.link_scale.size()},
          {"object_color_count", scene.object_colors.size()},
          {"is_diff", scene.is_diff}};
}

moveit_msgs::msg::PlanningScene stableReplayScene(const moveit_msgs::msg::PlanningScene & source)
{
  moveit_msgs::msg::PlanningScene stable;
  stable.robot_model_name = source.robot_model_name;
  stable.allowed_collision_matrix = source.allowed_collision_matrix;
  stable.world.collision_objects = source.world.collision_objects;
  stable.robot_state.attached_collision_objects = source.robot_state.attached_collision_objects;
  for (auto & object : stable.world.collision_objects)
    object.header.stamp = builtin_interfaces::msg::Time{};
  for (auto & body : stable.robot_state.attached_collision_objects) {
    body.object.header.stamp = builtin_interfaces::msg::Time{};
    body.detach_posture.header.stamp = builtin_interfaces::msg::Time{};
  }
  return stable;
}

PlanningFailureStage stageFromName(const std::string & name)
{
  static const std::map<std::string, PlanningFailureStage> stages{
    {"GOAL_ACCEPT_TIMEOUT", PlanningFailureStage::GOAL_ACCEPT_TIMEOUT},
    {"GOAL_REJECTED", PlanningFailureStage::GOAL_REJECTED},
    {"RESULT_TIMEOUT", PlanningFailureStage::RESULT_TIMEOUT},
    {"TRANSPORT_FAILURE", PlanningFailureStage::TRANSPORT_FAILURE},
    {"MISSING_RESULT", PlanningFailureStage::MISSING_RESULT},
    {"MOVEIT_ERROR", PlanningFailureStage::MOVEIT_ERROR},
    {"EMPTY_TRAJECTORY", PlanningFailureStage::EMPTY_TRAJECTORY}};
  return stages.at(name);
}

std::string stageName(PlanningFailureStage stage)
{
  switch (stage) {
    case PlanningFailureStage::GOAL_ACCEPT_TIMEOUT:
      return "GOAL_ACCEPT_TIMEOUT";
    case PlanningFailureStage::GOAL_REJECTED:
      return "GOAL_REJECTED";
    case PlanningFailureStage::RESULT_TIMEOUT:
      return "RESULT_TIMEOUT";
    case PlanningFailureStage::TRANSPORT_FAILURE:
      return "TRANSPORT_FAILURE";
    case PlanningFailureStage::MISSING_RESULT:
      return "MISSING_RESULT";
    case PlanningFailureStage::MOVEIT_ERROR:
      return "MOVEIT_ERROR";
    case PlanningFailureStage::EMPTY_TRAJECTORY:
      return "EMPTY_TRAJECTORY";
  }
  throw std::runtime_error("unsupported planning failure stage");
}

template <typename ValueT> PlanningDiagnosticsJson optionalJson(const std::optional<ValueT> & value)
{
  if (!value)
    return nullptr;
  return *value;
}

PlanningDiagnosticsJson artifactDocument(const PlanningFailureArtifact & artifact)
{
  const auto request = canonicalMoveGroupGoalJson(artifact.request);
  const auto scene = canonicalPlanningSceneJson(artifact.observed_scene);
  const auto failure = artifact.result.original.failure;
  PlanningDiagnosticsJson cancel_terminal = nullptr;
  if (artifact.result.cancel_terminal)
    cancel_terminal = static_cast<int>(*artifact.result.cancel_terminal);
  return {
    {"schema_version", 1},
    {"artifact_kind", "SO101_PLANNING_FAILURE"},
    {"operation", "MICRO_LIFT_WORLD_Z"},
    {"captured_at_unix_ns", artifact.captured_at_unix_ns},
    {"process_sequence", artifact.process_sequence},
    {"simulation_session_id", artifact.simulation_session_id},
    {"configuration_fingerprint", artifact.configuration_fingerprint},
    {"request_sha256", planningDiagnosticsSha256(request.dump())},
    {"scene_sha256", planningDiagnosticsSha256(scene.dump())},
    {"replay_scene_fingerprint", replaySceneFingerprint(artifact.observed_scene)},
    {"source_tcp_world", poseJson(artifact.source_tcp_world)},
    {"world_z_delta_m", artifact.world_z_delta_m},
    {"request", request},
    {"scene", scene},
    {"contacts",
     {{"raw_collision", artifact.contacts.raw_collision},
      {"request_collision", artifact.contacts.request_collision},
      {"raw_contacts", artifact.contacts.raw_contacts},
      {"request_contacts", artifact.contacts.request_contacts}}},
    {"profile_identity",
     {{"world_frame", artifact.profile_identity.world_frame},
      {"planning_group", artifact.profile_identity.planning_group},
      {"tcp_link", artifact.profile_identity.tcp_link},
      {"task_object_id", artifact.profile_identity.task_object_id},
      {"table_object", artifact.profile_identity.table_object},
      {"pedestal_object", artifact.profile_identity.pedestal_object},
      {"moveit_attach_link", artifact.profile_identity.moveit_attach_link},
      {"moveit_touch_links", artifact.profile_identity.moveit_touch_links}}},
    {"result",
     {{"failure_stage", stageName(artifact.result.stage)},
      {"original_status", static_cast<int>(artifact.result.original.status)},
      {"original_failure_category", failure
                                      ? PlanningDiagnosticsJson(static_cast<int>(failure->category))
                                      : PlanningDiagnosticsJson(nullptr)},
      {"original_failure_code",
       failure ? PlanningDiagnosticsJson(failure->code) : PlanningDiagnosticsJson(nullptr)},
      {"original_failure_message",
       failure ? PlanningDiagnosticsJson(failure->message) : PlanningDiagnosticsJson(nullptr)},
      {"transport_result_code", optionalJson(artifact.result.transport_result_code)},
      {"moveit_error_code", optionalJson(artifact.result.moveit_error_code)},
      {"planning_time", optionalJson(artifact.result.planning_time)},
      {"trajectory_joint_names", artifact.result.trajectory_joint_names},
      {"trajectory_points", artifact.result.trajectory_points},
      {"trajectory_duration_seconds", optionalJson(artifact.result.trajectory_duration_seconds)},
      {"cancel_acknowledged", optionalJson(artifact.result.cancel_acknowledged)},
      {"cancel_terminal", cancel_terminal}}}};
}

bool writeAll(int descriptor, std::string_view bytes)
{
  std::size_t written = 0;
  while (written < bytes.size()) {
    const ssize_t result = ::write(descriptor, bytes.data() + written, bytes.size() - written);
    if (result < 0 && errno == EINTR)
      continue;
    if (result <= 0)
      return false;
    written += static_cast<std::size_t>(result);
  }
  return true;
}

int renameWithoutReplacement(const std::filesystem::path & from, const std::filesystem::path & to)
{
#if defined(__linux__)
  return static_cast<int>(
    ::syscall(SYS_renameat2, AT_FDCWD, from.c_str(), AT_FDCWD, to.c_str(), RENAME_NOREPLACE));
#else
  // link(2) atomically fails with EEXIST and both paths are in directory_,
  // so it provides the same no-replace publish guarantee on macOS.
  if (::link(from.c_str(), to.c_str()) != 0)
    return -1;
  return ::unlink(from.c_str());
#endif
}

}  // namespace

PlanningDiagnosticsJson
canonicalMoveGroupGoalJson(const moveit_msgs::action::MoveGroup::Goal & goal)
{
  PlanningDiagnosticsJson goals = PlanningDiagnosticsJson::array();
  for (const auto & constraints : goal.request.goal_constraints)
    goals.push_back(constraintsSummary(constraints));
  PlanningDiagnosticsJson trajectory_constraints = PlanningDiagnosticsJson::array();
  for (const auto & constraints : goal.request.trajectory_constraints.constraints)
    trajectory_constraints.push_back(constraintsSummary(constraints));
  const auto & request = goal.request;
  return {
    {"cdr_encoding", "ros2_cdr_base64"},
    {"cdr_base64", serializeCdr(goal)},
    {"human_readable",
     {{"request",
       {{"workspace_parameters",
         {{"header", headerJson(request.workspace_parameters.header)},
          {"min_corner",
           {request.workspace_parameters.min_corner.x, request.workspace_parameters.min_corner.y,
            request.workspace_parameters.min_corner.z}},
          {"max_corner",
           {request.workspace_parameters.max_corner.x, request.workspace_parameters.max_corner.y,
            request.workspace_parameters.max_corner.z}}}},
        {"start_state",
         {{"joint_state", jointStateJson(request.start_state.joint_state)},
          {"multi_dof_joint_names", request.start_state.multi_dof_joint_state.joint_names},
          {"attached_collision_object_count",
           request.start_state.attached_collision_objects.size()},
          {"is_diff", request.start_state.is_diff}}},
        {"goal_constraints", goals},
        {"path_constraints", constraintsSummary(request.path_constraints)},
        {"trajectory_constraints", trajectory_constraints},
        {"reference_trajectory_count", request.reference_trajectories.size()},
        {"pipeline_id", request.pipeline_id},
        {"planner_id", request.planner_id},
        {"group_name", request.group_name},
        {"num_planning_attempts", request.num_planning_attempts},
        {"allowed_planning_time", request.allowed_planning_time},
        {"max_velocity_scaling_factor", request.max_velocity_scaling_factor},
        {"max_acceleration_scaling_factor", request.max_acceleration_scaling_factor},
        {"cartesian_speed_limited_link", request.cartesian_speed_limited_link},
        {"max_cartesian_speed", request.max_cartesian_speed}}},
      {"planning_options",
       {{"planning_scene_diff", sceneMirror(goal.planning_options.planning_scene_diff)},
        {"plan_only", goal.planning_options.plan_only},
        {"look_around", goal.planning_options.look_around},
        {"look_around_attempts", goal.planning_options.look_around_attempts},
        {"max_safe_execution_cost", goal.planning_options.max_safe_execution_cost},
        {"replan", goal.planning_options.replan},
        {"replan_attempts", goal.planning_options.replan_attempts},
        {"replan_delay", goal.planning_options.replan_delay}}}}}};
}

PlanningDiagnosticsJson canonicalPlanningSceneJson(const moveit_msgs::msg::PlanningScene & scene)
{
  return {{"cdr_encoding", "ros2_cdr_base64"},
          {"cdr_base64", serializeCdr(scene)},
          {"human_readable", sceneMirror(scene)}};
}

std::string replaySceneFingerprint(const moveit_msgs::msg::PlanningScene & scene)
{
  const auto stable = stableReplayScene(scene);
  PlanningDiagnosticsJson world = PlanningDiagnosticsJson::array();
  for (const auto & object : stable.world.collision_objects) {
    auto summary = collisionObjectSummary(object);
    summary.at("header").erase("stamp");
    world.push_back(std::move(summary));
  }
  PlanningDiagnosticsJson attached = PlanningDiagnosticsJson::array();
  for (const auto & body : stable.robot_state.attached_collision_objects) {
    auto object = collisionObjectSummary(body.object);
    object.at("header").erase("stamp");
    attached.push_back({{"link_name", body.link_name},
                        {"object", std::move(object)},
                        {"touch_links", body.touch_links}});
  }
  PlanningDiagnosticsJson acm_rows = PlanningDiagnosticsJson::array();
  for (const auto & row : stable.allowed_collision_matrix.entry_values)
    acm_rows.push_back(row.enabled);
  const PlanningDiagnosticsJson topology{
    {"robot_model_name", stable.robot_model_name},
    {"world", world},
    {"attached", attached},
    {"allowed_collision_matrix",
     {{"entry_names", stable.allowed_collision_matrix.entry_names},
      {"entry_values", acm_rows},
      {"default_entry_names", stable.allowed_collision_matrix.default_entry_names},
      {"default_entry_values", stable.allowed_collision_matrix.default_entry_values}}}};
  return planningDiagnosticsSha256(topology.dump());
}

std::string planningDiagnosticsSha256(std::string_view bytes)
{
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int length = 0;
  EVP_MD_CTX * context = EVP_MD_CTX_new();
  if (!context)
    throw std::runtime_error("could not allocate SHA-256 context");
  const bool success = EVP_DigestInit_ex(context, EVP_sha256(), nullptr) == 1 &&
                       EVP_DigestUpdate(context, bytes.data(), bytes.size()) == 1 &&
                       EVP_DigestFinal_ex(context, digest.data(), &length) == 1;
  EVP_MD_CTX_free(context);
  if (!success)
    throw std::runtime_error("could not compute SHA-256");
  constexpr char hexadecimal[] = "0123456789abcdef";
  std::string result;
  result.reserve(length * 2U);
  for (unsigned int index = 0; index < length; ++index) {
    result.push_back(hexadecimal[digest[index] >> 4U]);
    result.push_back(hexadecimal[digest[index] & 0x0fU]);
  }
  return result;
}

std::variant<moveit_msgs::action::MoveGroup::Goal, Failure>
reconstructMoveGroupGoal(const PlanningDiagnosticsJson & artifact_document)
{
  try {
    const auto & request = artifact_document.at("request");
    if (request.at("cdr_encoding") != "ros2_cdr_base64")
      return invalidArtifact("unsupported MoveGroup request encoding");
    auto goal = deserializeCdr<moveit_msgs::action::MoveGroup::Goal>(
      request.at("cdr_base64").get<std::string>());
    const auto canonical = canonicalMoveGroupGoalJson(goal);
    if (canonical.at("human_readable") != request.at("human_readable"))
      return invalidArtifact("MoveGroup request canonical round-trip mismatch");
    return goal;
  } catch (const std::exception & error) {
    return invalidArtifact(std::string("could not reconstruct MoveGroup request: ") + error.what());
  }
}

std::variant<PlanningFailureArtifact, Failure>
loadPlanningFailureArtifact(const std::filesystem::path & artifact_path)
{
  try {
    std::ifstream stream(artifact_path, std::ios::binary);
    if (!stream)
      return invalidArtifact("could not open planning diagnostic artifact");
    const std::string bytes((std::istreambuf_iterator<char>(stream)),
                            std::istreambuf_iterator<char>());
    const auto document = PlanningDiagnosticsJson::parse(bytes);
    if (document.at("schema_version") != 1 ||
        document.at("artifact_kind") != "SO101_PLANNING_FAILURE" ||
        document.at("operation") != "MICRO_LIFT_WORLD_Z") {
      return invalidArtifact("unsupported planning diagnostic schema or artifact kind");
    }
    if (planningDiagnosticsSha256(document.at("request").dump()) !=
          document.at("request_sha256").get<std::string>() ||
        planningDiagnosticsSha256(document.at("scene").dump()) !=
          document.at("scene_sha256").get<std::string>()) {
      return invalidArtifact("planning diagnostic hash mismatch");
    }
    const auto reconstructed = reconstructMoveGroupGoal(document);
    if (std::holds_alternative<Failure>(reconstructed))
      return std::get<Failure>(reconstructed);
    const auto & scene_json = document.at("scene");
    auto scene = deserializeCdr<moveit_msgs::msg::PlanningScene>(
      scene_json.at("cdr_base64").get<std::string>());
    const auto canonical_scene = canonicalPlanningSceneJson(scene);
    if (canonical_scene.at("human_readable") != scene_json.at("human_readable") ||
        replaySceneFingerprint(scene) !=
          document.at("replay_scene_fingerprint").get<std::string>()) {
      return invalidArtifact("planning scene canonical round-trip mismatch");
    }
    const auto & source = document.at("source_tcp_world");
    const auto & position = source.at("position");
    const auto & orientation = source.at("orientation");
    const auto & result = document.at("result");
    ActionResult original;
    original.status = static_cast<ActionStatus>(result.at("original_status").get<int>());
    if (!result.at("original_failure_code").is_null()) {
      original.failure =
        Failure{static_cast<FailureCategory>(result.at("original_failure_category").get<int>()),
                result.at("original_failure_code").get<std::string>(),
                result.at("original_failure_message").get<std::string>(),
                {}};
    }
    SO101Profile profile = SO101Profile::canonical();
    const auto & identity = document.at("profile_identity");
    profile.world_frame = identity.at("world_frame").get<std::string>();
    profile.planning_group = identity.at("planning_group").get<std::string>();
    profile.tcp_link = identity.at("tcp_link").get<std::string>();
    profile.task_object_id = identity.at("task_object_id").get<std::string>();
    profile.table_object = identity.at("table_object").get<std::string>();
    profile.pedestal_object = identity.at("pedestal_object").get<std::string>();
    profile.moveit_attach_link = identity.at("moveit_attach_link").get<std::string>();
    profile.moveit_touch_links = identity.at("moveit_touch_links").get<std::vector<std::string>>();
    PlanningFailureResultEvidence result_evidence{
      stageFromName(result.at("failure_stage").get<std::string>()), original};
    if (!result.at("transport_result_code").is_null())
      result_evidence.transport_result_code = result.at("transport_result_code").get<std::int8_t>();
    if (!result.at("moveit_error_code").is_null())
      result_evidence.moveit_error_code = result.at("moveit_error_code").get<std::int32_t>();
    if (!result.at("planning_time").is_null())
      result_evidence.planning_time = result.at("planning_time").get<double>();
    result_evidence.trajectory_joint_names =
      result.at("trajectory_joint_names").get<std::vector<std::string>>();
    result_evidence.trajectory_points = result.at("trajectory_points").get<std::size_t>();
    if (!result.at("trajectory_duration_seconds").is_null()) {
      result_evidence.trajectory_duration_seconds =
        result.at("trajectory_duration_seconds").get<double>();
    }
    if (!result.at("cancel_acknowledged").is_null())
      result_evidence.cancel_acknowledged = result.at("cancel_acknowledged").get<bool>();
    PlanningSceneContactEvidence contacts;
    const auto & contact_json = document.at("contacts");
    contacts.raw_collision = contact_json.at("raw_collision").get<bool>();
    contacts.request_collision = contact_json.at("request_collision").get<bool>();
    contacts.raw_contacts =
      contact_json.at("raw_contacts").get<std::map<std::string, std::size_t>>();
    contacts.request_contacts =
      contact_json.at("request_contacts").get<std::map<std::string, std::size_t>>();
    return PlanningFailureArtifact{
      document.at("captured_at_unix_ns").get<std::int64_t>(),
      document.at("process_sequence").get<std::uint64_t>(),
      document.at("simulation_session_id").get<std::string>(),
      document.at("configuration_fingerprint").get<std::string>(),
      {position.at(0).get<double>(), position.at(1).get<double>(), position.at(2).get<double>(),
       orientation.at(0).get<double>(), orientation.at(1).get<double>(),
       orientation.at(2).get<double>(), orientation.at(3).get<double>()},
      document.at("world_z_delta_m").get<double>(),
      std::get<moveit_msgs::action::MoveGroup::Goal>(reconstructed),
      std::move(scene),
      std::move(contacts),
      std::move(profile),
      std::move(result_evidence)};
  } catch (const std::exception & error) {
    return invalidArtifact(std::string("could not parse planning diagnostic artifact: ") +
                           error.what());
  }
}

std::optional<Failure>
NullPlanningFailureDiagnosticsSink::record(const PlanningFailureArtifact & artifact)
{
  static_cast<void>(artifact);
  return std::nullopt;
}

FilePlanningFailureDiagnosticsSink::FilePlanningFailureDiagnosticsSink(
  std::filesystem::path directory) : directory_(std::move(directory))
{
}

std::optional<Failure>
FilePlanningFailureDiagnosticsSink::record(const PlanningFailureArtifact & artifact)
{
  std::filesystem::path temporary_path;
  int descriptor = -1;
  try {
    const auto document = artifactDocument(artifact);
    const std::string bytes = document.dump(2) + "\n";
    const std::string request_prefix =
      document.at("request_sha256").get<std::string>().substr(0, 12);
    for (std::uint64_t attempt = 0; attempt < 10000; ++attempt) {
      static_cast<void>(attempt);
      const std::uint64_t sequence =
        artifact.process_sequence + collision_sequence_.fetch_add(1, std::memory_order_relaxed);
      const std::string filename = std::to_string(artifact.captured_at_unix_ns) + "-" +
                                   std::to_string(sequence) + "-micro-lift-" + request_prefix +
                                   ".json";
      const auto final_path = directory_ / filename;
      temporary_path = directory_ / ("." + filename + ".tmp-" + std::to_string(::getpid()));
      descriptor = ::open(temporary_path.c_str(), O_CREAT | O_EXCL | O_WRONLY | O_CLOEXEC, 0600);
      if (descriptor < 0) {
        if (errno == EEXIST)
          continue;
        return writeFailure(directory_, "could not create exclusive diagnostic temporary file");
      }
      if (!writeAll(descriptor, bytes) || ::fsync(descriptor) != 0 || ::close(descriptor) != 0) {
        descriptor = -1;
        ::unlink(temporary_path.c_str());
        return writeFailure(directory_, "could not durably write diagnostic temporary file");
      }
      descriptor = -1;
      if (renameWithoutReplacement(temporary_path, final_path) != 0) {
        const int rename_error = errno;
        ::unlink(temporary_path.c_str());
        if (rename_error == EEXIST)
          continue;
        return writeFailure(directory_, "could not atomically publish diagnostic artifact");
      }
      const int directory_descriptor =
        ::open(directory_.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
      if (directory_descriptor < 0)
        return writeFailure(directory_, "could not open diagnostic directory for sync");
      const bool directory_synced = ::fsync(directory_descriptor) == 0;
      const bool directory_closed = ::close(directory_descriptor) == 0;
      if (!directory_synced || !directory_closed) {
        return writeFailure(directory_, "could not sync diagnostic directory");
      }
      return std::nullopt;
    }
    return writeFailure(directory_, "could not allocate a unique diagnostic artifact name");
  } catch (const std::exception & error) {
    if (descriptor >= 0)
      ::close(descriptor);
    if (!temporary_path.empty())
      ::unlink(temporary_path.c_str());
    return writeFailure(directory_,
                        std::string("could not serialize diagnostic artifact: ") + error.what());
  }
}

PlanningFailureDiagnosticsSelection
selectPlanningFailureDiagnostics(const std::filesystem::path & directory)
{
  if (directory.empty())
    return {std::make_shared<NullPlanningFailureDiagnosticsSink>(), std::nullopt};
  if (!directory.is_absolute())
    return {nullptr,
            invalidDirectory(directory, "planning diagnostics directory must be absolute")};
  struct stat status
  {
  };
  if (::stat(directory.c_str(), &status) != 0) {
    if (errno != ENOENT || ::mkdir(directory.c_str(), 0700) != 0) {
      return {nullptr,
              invalidDirectory(directory, "planning diagnostics directory could not be created")};
    }
    if (::stat(directory.c_str(), &status) != 0) {
      return {nullptr,
              invalidDirectory(directory, "planning diagnostics directory could not be inspected")};
    }
  }
  if (!S_ISDIR(status.st_mode) || ::access(directory.c_str(), W_OK | X_OK) != 0 ||
      (status.st_mode & 0222) == 0) {
    return {nullptr, invalidDirectory(directory, "planning diagnostics path is not writable")};
  }
  if (::chmod(directory.c_str(), 0700) != 0) {
    return {nullptr,
            invalidDirectory(directory, "planning diagnostics permissions could not be secured")};
  }
  return {std::make_shared<FilePlanningFailureDiagnosticsSink>(directory), std::nullopt};
}

}  // namespace so101_gazebo_demo::pick_place

#pragma once
#include <string>
#include "so101_gazebo_demo/pick_place/checkpoint.hpp"
namespace so101_gazebo_demo::pick_place { class CommonResumeValidator { public:
  CommonResumeValidator(std::string configuration_hash, std::string simulation_session_id) : configuration_hash_(std::move(configuration_hash)), simulation_session_id_(std::move(simulation_session_id)) {}
  [[nodiscard]] std::optional<Failure> validate(const Checkpoint & checkpoint) const {
    if (checkpoint.schema_version != 3 || checkpoint.configuration_hash != configuration_hash_ || checkpoint.simulation_session_id != simulation_session_id_) return Failure{FailureCategory::RESUME_VALIDATION, "CHECKPOINT_BOUNDARY_MISMATCH", "checkpoint does not match the active configuration/session", {}}; return std::nullopt; }
private: std::string configuration_hash_; std::string simulation_session_id_; }; }

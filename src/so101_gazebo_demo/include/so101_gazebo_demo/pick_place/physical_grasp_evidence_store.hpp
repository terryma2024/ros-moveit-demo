#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <string>
#include <variant>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

struct PhysicalGraspSample
{
  State capture_state;
  std::int64_t captured_at_unix_ns;
  Pose3d tcp_pose_world;
  Pose3d task_object_pose_world;
  bool gripper_contact;
};

struct PhysicalGraspEvidenceRecord
{
  std::string simulation_session_id;
  std::string configuration_fingerprint;
  std::optional<PhysicalGraspSample> before_lift;
  std::optional<PhysicalGraspSample> after_lift;
};

class IPhysicalGraspEvidenceStore
{
public:
  virtual ~IPhysicalGraspEvidenceStore() = default;
  virtual std::optional<Failure> resetForFreshRun() = 0;
  virtual std::optional<Failure> saveBefore(const WorldSnapshot &) = 0;
  virtual std::optional<Failure> saveAfter(const WorldSnapshot &) = 0;
  [[nodiscard]] virtual std::variant<PhysicalGraspEvidenceRecord, Failure> load() const = 0;
};

class FilePhysicalGraspEvidenceStore final : public IPhysicalGraspEvidenceStore
{
public:
  FilePhysicalGraspEvidenceStore(std::filesystem::path path, std::string simulation_session_id,
                                 std::string configuration_fingerprint);

  std::optional<Failure> resetForFreshRun() override;
  std::optional<Failure> saveBefore(const WorldSnapshot &) override;
  std::optional<Failure> saveAfter(const WorldSnapshot &) override;
  [[nodiscard]] std::variant<PhysicalGraspEvidenceRecord, Failure> load() const override;

private:
  std::filesystem::path path_;
  std::string simulation_session_id_;
  std::string configuration_fingerprint_;
};

}  // namespace so101_gazebo_demo::pick_place

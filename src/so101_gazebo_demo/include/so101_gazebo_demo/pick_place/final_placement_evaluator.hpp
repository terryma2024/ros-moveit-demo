#pragma once

#include <cstddef>
#include <cstdint>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/policy_config.hpp"
#include "so101_gazebo_demo/pick_place/world_observer.hpp"

namespace so101_gazebo_demo::pick_place
{

struct ReleaseEpoch
{
  std::string id;
  std::string simulation_session_id;
  std::uint64_t start_sequence{0};
};

struct FinalPlacementSample
{
  std::uint64_t sequence{0};
  Pose3d pose;
  double linear_speed_m_s{0.0};
  double angular_speed_rad_s{0.0};
  double upright_tilt_rad{0.0};
  std::set<std::string> violated_predicates;
};

struct FinalPlacementMetrics
{
  std::size_t observed_sample_count{0};
  std::size_t post_release_sample_count{0};
  std::size_t pre_release_rejected_count{0};
  std::size_t derived_speed_sample_count{0};
  std::size_t consecutive_samples{0};
  double consecutive_duration_s{0.0};
  double min_linear_speed_m_s{0.0};
  double max_linear_speed_m_s{0.0};
  double mean_linear_speed_m_s{0.0};
  double min_angular_speed_rad_s{0.0};
  double max_angular_speed_rad_s{0.0};
  double mean_angular_speed_rad_s{0.0};
  std::set<std::string> violated_predicates;
  std::vector<FinalPlacementSample> retained_samples;
};

struct FinalPlacementEvidence
{
  ReleaseEpoch epoch;
  std::uint64_t first_counted_sequence{0};
  std::uint64_t final_sequence{0};
  Pose3d final_pose;
  std::size_t counted_samples{0};
  double stable_duration_s{0.0};
};

struct FinalPlacementEvaluation
{
  bool stable{false};
  bool terminal_failure{false};
  std::optional<Failure> failure;
  FinalPlacementMetrics metrics;
  std::optional<FinalPlacementEvidence> evidence;
};

class FinalPlacementEvaluator
{
public:
  explicit FinalPlacementEvaluator(PhysicalOutcomePolicyConfig policy);
  [[nodiscard]] FinalPlacementEvaluation
  evaluate(const ReleaseEpoch & epoch, const std::vector<WorldSnapshot> & snapshots) const;

private:
  PhysicalOutcomePolicyConfig policy_;
};

}  // namespace so101_gazebo_demo::pick_place

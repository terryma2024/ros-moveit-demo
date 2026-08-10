#include "so101_gazebo_demo/workspace/pose_coverage_index.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace so101_gazebo_demo::workspace
{
namespace
{
std::int32_t checkedInt32(double value)
{
  if (!std::isfinite(value) || value < std::numeric_limits<std::int32_t>::min() ||
      value > std::numeric_limits<std::int32_t>::max()) {
    throw std::overflow_error("position voxel key is outside int32 range");
  }
  return static_cast<std::int32_t>(value);
}

std::array<double, 4> canonicalQuaternion(const pick_place::Pose3d & pose)
{
  std::array<double, 4> value{pose.qx, pose.qy, pose.qz, pose.qw};
  double norm_squared = 0.0;
  for (double component : value)
    norm_squared += component * component;
  if (!std::isfinite(norm_squared) || norm_squared <= 0.0) {
    throw std::invalid_argument("quaternion cannot be normalized");
  }
  const double inverse_norm = 1.0 / std::sqrt(norm_squared);
  for (double & component : value)
    component *= inverse_norm;
  const bool negate =
    value[3] < 0.0 ||
    (value[3] == 0.0 &&
     (value[2] < 0.0 ||
      (value[2] == 0.0 && (value[1] < 0.0 || (value[1] == 0.0 && value[0] < 0.0)))));
  if (negate)
    for (double & component : value)
      component = -component;
  return value;
}

double quaternionAngularDistance(const std::array<double, 4> & first,
                                 const std::array<double, 4> & second)
{
  double dot = 0.0;
  for (std::size_t i = 0; i < first.size(); ++i)
    dot += first[i] * second[i];
  return 2.0 * std::acos(std::clamp(std::abs(dot), 0.0, 1.0));
}
}  // namespace

PoseCoverageIndex::PoseCoverageIndex(double position_voxel_size_m,
                                     double orientation_threshold_rad) :
    voxel_size_(position_voxel_size_m), orientation_threshold_(orientation_threshold_rad)
{
  if (!std::isfinite(voxel_size_) || voxel_size_ <= 0.0 || !std::isfinite(orientation_threshold_) ||
      orientation_threshold_ <= 0.0) {
    throw std::invalid_argument("coverage resolutions must be finite and positive");
  }
}

PositionVoxelKey PoseCoverageIndex::keyFor(const std::array<double, 3> & xyz) const
{
  return {checkedInt32(std::floor(xyz[0] / voxel_size_)),
          checkedInt32(std::floor(xyz[1] / voxel_size_)),
          checkedInt32(std::floor(xyz[2] / voxel_size_))};
}

OrientationAssignment PoseCoverageIndex::insert(PoseSample & sample)
{
  const auto key = keyFor({sample.tcp_pose.x, sample.tcp_pose.y, sample.tcp_pose.z});
  sample.position_voxel = key;
  const auto quaternion = canonicalQuaternion(sample.tcp_pose);
  sample.tcp_pose.qx = quaternion[0];
  sample.tcp_pose.qy = quaternion[1];
  sample.tcp_pose.qz = quaternion[2];
  sample.tcp_pose.qw = quaternion[3];
  const bool created_voxel = voxels_.find(key) == voxels_.end();
  auto & voxel = voxels_[key];
  if (created_voxel)
    voxel.summary.key = key;

  std::uint32_t selected = 0;
  bool created_cluster = true;
  double best_distance = std::numeric_limits<double>::infinity();
  for (const auto & cluster : voxel.clusters) {
    const double distance = quaternionAngularDistance(quaternion, cluster.representative_xyzw);
    if (distance <= orientation_threshold_ && distance < best_distance) {
      selected = cluster.cluster_id;
      best_distance = distance;
      created_cluster = false;
    }
  }
  if (created_cluster) {
    selected = static_cast<std::uint32_t>(voxel.clusters.size());
    voxel.clusters.push_back({selected, quaternion, sample.collision_free});
  } else if (sample.collision_free) {
    voxel.clusters[selected].has_collision_free_sample = true;
  }
  sample.orientation_cluster_id = selected;
  ++voxel.summary.sample_count;
  if (sample.collision_free)
    ++voxel.summary.collision_free_count;
  else
    voxel.has_colliding = true;
  voxel.summary.orientation_count = static_cast<std::uint32_t>(voxel.clusters.size());
  voxel.summary.collision_free_orientation_count = static_cast<std::uint32_t>(
    std::count_if(voxel.clusters.begin(), voxel.clusters.end(),
                  [](const auto & cluster) { return cluster.has_collision_free_sample; }));
  voxel.seed_candidates.push_back({sample.sample_id, 3, key, sample.arm_joints, 0});
  return {key, selected, created_voxel, created_cluster};
}

BatchCoverageDelta PoseCoverageIndex::finishBatch()
{
  std::uint64_t orientations = 0;
  for (const auto & [key, voxel] : voxels_) {
    static_cast<void>(key);
    orientations += voxel.clusters.size();
  }
  const BatchCoverageDelta delta{voxels_.size() - positions_at_batch_start_,
                                 orientations - orientations_at_batch_start_,
                                 positions_at_batch_start_, orientations_at_batch_start_};
  positions_at_batch_start_ = voxels_.size();
  orientations_at_batch_start_ = orientations;
  return delta;
}

std::vector<PositionVoxelSummary> PoseCoverageIndex::voxelSummaries() const
{
  std::vector<PositionVoxelSummary> output;
  output.reserve(voxels_.size());
  for (const auto & [key, voxel] : voxels_) {
    static_cast<void>(key);
    output.push_back(voxel.summary);
  }
  return output;
}

std::vector<RefinementSeed> PoseCoverageIndex::refinementSeeds() const
{
  std::vector<RefinementSeed> output;
  for (const auto & [key, voxel] : voxels_) {
    const bool mixed = voxel.has_colliding && voxel.summary.collision_free_count > 0;
    const std::array<PositionVoxelKey, 6> neighbors{{{key.x - 1, key.y, key.z},
                                                     {key.x + 1, key.y, key.z},
                                                     {key.x, key.y - 1, key.z},
                                                     {key.x, key.y + 1, key.z},
                                                     {key.x, key.y, key.z - 1},
                                                     {key.x, key.y, key.z + 1}}};
    const bool boundary =
      std::any_of(neighbors.begin(), neighbors.end(),
                  [this](const auto & item) { return voxels_.find(item) == voxels_.end(); });
    for (auto seed : voxel.seed_candidates) {
      seed.priority = mixed ? 1 : (boundary ? 2 : 3);
      output.push_back(seed);
    }
  }
  std::sort(output.begin(), output.end(), [](const auto & lhs, const auto & rhs) {
    if (lhs.priority != rhs.priority)
      return lhs.priority < rhs.priority;
    if (lhs.voxel < rhs.voxel)
      return true;
    if (rhs.voxel < lhs.voxel)
      return false;
    return lhs.sample_id < rhs.sample_id;
  });
  return output;
}

PoseCoverageCheckpoint PoseCoverageIndex::checkpoint() const
{
  PoseCoverageCheckpoint output{};
  for (const auto & [key, voxel] : voxels_) {
    static_cast<void>(key);
    output.voxels.push_back({voxel.summary, voxel.clusters, voxel.seed_candidates});
  }
  return output;
}

void PoseCoverageIndex::restore(const PoseCoverageCheckpoint & checkpoint)
{
  voxels_.clear();
  positions_at_batch_start_ = 0;
  orientations_at_batch_start_ = 0;
  for (const auto & snapshot : checkpoint.voxels) {
    VoxelState state;
    state.summary = snapshot.summary;
    state.clusters = snapshot.clusters;
    state.seed_candidates = snapshot.seed_candidates;
    state.has_colliding = state.summary.sample_count > state.summary.collision_free_count;
    orientations_at_batch_start_ += state.clusters.size();
    voxels_.emplace(state.summary.key, std::move(state));
  }
  positions_at_batch_start_ = voxels_.size();
}

ConvergenceTracker::ConvergenceTracker(WorkspaceSamplingConfig config) : config_(config) {}

bool ConvergenceTracker::observe(const BatchCoverageDelta & delta, std::uint64_t completed_samples)
{
  if (completed_samples < config_.minimum_samples) {
    consecutive_stable_batches_ = 0;
    return false;
  }
  const double position_rate =
    static_cast<double>(delta.new_position_voxels) /
    static_cast<double>(std::max<std::uint64_t>(1, delta.existing_position_voxels_before_batch));
  const double orientation_rate = static_cast<double>(delta.new_orientation_clusters) /
                                  static_cast<double>(std::max<std::uint64_t>(
                                    1, delta.existing_orientation_clusters_before_batch));
  if (position_rate < config_.position_new_rate_threshold &&
      orientation_rate < config_.orientation_new_rate_threshold) {
    ++consecutive_stable_batches_;
  } else {
    consecutive_stable_batches_ = 0;
  }
  return consecutive_stable_batches_ >= config_.stable_batches;
}

std::size_t ConvergenceTracker::consecutiveStableBatches() const noexcept
{
  return consecutive_stable_batches_;
}

void ConvergenceTracker::restore(std::size_t consecutive_stable_batches)
{
  consecutive_stable_batches_ = consecutive_stable_batches;
}
}  // namespace so101_gazebo_demo::workspace

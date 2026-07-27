#include "so101_gazebo_demo/pick_place/gazebo_world_observer.hpp"
#include <chrono>
#include <algorithm>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <optional>
#include <utility>

#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/transport/Node.hh>

namespace so101_gazebo_demo::pick_place
{

namespace
{

Pose3d toPose3d(const gz::msgs::Pose & pose)
{
  return {pose.position().x(),    pose.position().y(),    pose.position().z(),
          pose.orientation().x(), pose.orientation().y(), pose.orientation().z(),
          pose.orientation().w()};
}

Failure observationFailure(std::string code, std::string message)
{
  return {FailureCategory::OBSERVATION, std::move(code), std::move(message), {}};
}

bool finitePose(const Pose3d & pose)
{
  return std::isfinite(pose.x) && std::isfinite(pose.y) && std::isfinite(pose.z) &&
         std::isfinite(pose.qx) && std::isfinite(pose.qy) && std::isfinite(pose.qz) &&
         std::isfinite(pose.qw);
}

double positionDistance(const Pose3d & a, const Pose3d & b)
{
  return std::hypot(std::hypot(a.x - b.x, a.y - b.y), a.z - b.z);
}

double orientationDistance(const Pose3d & a, const Pose3d & b)
{
  const auto dot = std::abs(a.qx * b.qx + a.qy * b.qy + a.qz * b.qz + a.qw * b.qw);
  return 2.0 * std::acos(std::clamp(dot, 0.0, 1.0));
}

class CokePoseStabilityTracker
{
public:
  CokePoseStabilityTracker(std::size_t required_samples, double position_tolerance,
                           double orientation_tolerance) :
      required_samples_(required_samples), position_tolerance_(position_tolerance),
      orientation_tolerance_(orientation_tolerance)
  {
  }

  void addSample(const Pose3d & pose, std::chrono::steady_clock::time_point observed_at)
  {
    samples_.push_back({pose, observed_at});
    while (samples_.size() > required_samples_) {
      samples_.pop_front();
    }
  }

  std::optional<bool> stationary() const
  {
    if (required_samples_ < 2 || samples_.size() < required_samples_) {
      return std::nullopt;
    }
    for (std::size_t i = 1; i < samples_.size(); ++i) {
      if (samples_[i].observed_at <= samples_[i - 1].observed_at ||
          positionDistance(samples_[i - 1].pose, samples_[i].pose) > position_tolerance_ ||
          orientationDistance(samples_[i - 1].pose, samples_[i].pose) > orientation_tolerance_) {
        return false;
      }
    }
    return true;
  }

private:
  struct Sample
  {
    Pose3d pose;
    std::chrono::steady_clock::time_point observed_at;
  };
  std::size_t required_samples_;
  double position_tolerance_;
  double orientation_tolerance_;
  std::deque<Sample> samples_;
};

}  // namespace

class GazeboWorldObserver::Impl
{
public:
  Impl(const std::string & world_name, std::string coke_model, const std::string & attachment_topic,
       std::string simulation_session_id, double max_observation_age_seconds,
       std::size_t coke_settle_samples, double coke_settle_interval_seconds,
       double coke_settle_position_tolerance, double coke_settle_orientation_tolerance_rad,
       bool initially_detached) :
      coke_model_(std::move(coke_model)), simulation_session_id_(std::move(simulation_session_id)),
      max_observation_age_(std::chrono::duration<double>(max_observation_age_seconds)),
      coke_pose_stability_(coke_settle_samples, coke_settle_position_tolerance,
                           coke_settle_orientation_tolerance_rad),
      coke_settle_interval_(std::chrono::duration<double>(coke_settle_interval_seconds))
  {
    static_cast<void>(initially_detached);
    const auto pose_topic = "/world/" + world_name + "/pose/info";
    pose_subscription_ok_ = transport_.Subscribe(pose_topic, &Impl::onPoses, this);
    attachment_subscription_ok_ = transport_.Subscribe(attachment_topic, &Impl::onAttachment, this);
  }

  void onPoses(const gz::msgs::Pose_V & message)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto & pose : message.pose()) {
      if (pose.name() == coke_model_ || pose.name().find("::" + coke_model_) != std::string::npos) {
        const auto observed_at = std::chrono::steady_clock::now();
        coke_pose_ = toPose3d(pose);
        coke_pose_received_at_ = observed_at;
        if (last_stability_sample_at_ == std::chrono::steady_clock::time_point{} ||
            observed_at - last_stability_sample_at_ >= coke_settle_interval_) {
          coke_pose_stability_.addSample(*coke_pose_, observed_at);
          last_stability_sample_at_ = observed_at;
        }
        condition_.notify_all();
        return;
      }
    }
  }

  void onAttachment(const gz::msgs::StringMsg & message)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (message.data() == "attached") {
      coke_attached_ = true;
    } else if (message.data() == "detached") {
      coke_attached_ = false;
    } else {
      return;
    }
    attachment_received_at_ = std::chrono::steady_clock::now();
    condition_.notify_all();
  }

  [[nodiscard]] ObservationResult enrich(WorldSnapshot snapshot) const
  {
    if (!pose_subscription_ok_ || !attachment_subscription_ok_) {
      return {std::nullopt,
              observationFailure("GAZEBO_SUBSCRIPTION_FAILED",
                                 "Unable to subscribe to Gazebo Coke pose or attachment topic")};
    }
    std::unique_lock<std::mutex> lock(mutex_);
    condition_.wait_for(lock, max_observation_age_, [this]() {
      const auto now = std::chrono::steady_clock::now();
      return coke_pose_.has_value() && coke_attached_.has_value() &&
             coke_pose_stability_.stationary().has_value() &&
             now - coke_pose_received_at_ <= max_observation_age_ &&
             now - attachment_received_at_ <= max_observation_age_;
    });
    const auto now = std::chrono::steady_clock::now();
    if (!coke_pose_) {
      return {std::nullopt, observationFailure("GAZEBO_COKE_POSE_UNAVAILABLE",
                                               "Gazebo Coke pose is missing or stale")};
    }
    if (!finitePose(*coke_pose_)) {
      return {std::nullopt,
              observationFailure("GAZEBO_COKE_POSE_NONFINITE",
                                 "Gazebo Coke pose contains nonfinite evidence")};
    }
    if (!coke_attached_ || now - attachment_received_at_ > max_observation_age_) {
      return {std::nullopt,
              observationFailure(
                "GAZEBO_ATTACHMENT_STATE_UNAVAILABLE",
                "Gazebo attachment state relay has not published a fresh validated state")};
    }
    if (now - coke_pose_received_at_ > max_observation_age_) {
      return {std::nullopt, observationFailure("GAZEBO_COKE_POSE_UNAVAILABLE",
                                               "Gazebo Coke pose is missing or stale")};
    }
    snapshot.gazebo_coke_pose_world = coke_pose_;
    snapshot.gazebo_coke_attached = coke_attached_;
    snapshot.gazebo_coke_stationary = coke_pose_stability_.stationary();
    snapshot.simulation_session_id = simulation_session_id_;
    return {snapshot, std::nullopt};
  }

private:
  std::string coke_model_;
  std::string simulation_session_id_;
  std::chrono::duration<double> max_observation_age_;
  gz::transport::Node transport_;
  bool pose_subscription_ok_{false};
  bool attachment_subscription_ok_{false};
  mutable std::mutex mutex_;
  mutable std::condition_variable condition_;
  std::optional<Pose3d> coke_pose_;
  std::optional<bool> coke_attached_;
  std::chrono::steady_clock::time_point attachment_received_at_{};
  CokePoseStabilityTracker coke_pose_stability_;
  std::chrono::duration<double> coke_settle_interval_;
  std::chrono::steady_clock::time_point last_stability_sample_at_{};
  std::chrono::steady_clock::time_point coke_pose_received_at_{};
};

GazeboWorldObserver::GazeboWorldObserver(
  IWorldObserver & moveit_observer, const std::string & world_name, std::string coke_model,
  const std::string & attachment_topic, std::string simulation_session_id,
  double max_observation_age_seconds, std::size_t coke_settle_samples,
  double coke_settle_interval_seconds, double coke_settle_position_tolerance,
  double coke_settle_orientation_tolerance_rad, bool initially_detached) :
    moveit_observer_(moveit_observer),
    impl_(std::make_unique<Impl>(
      world_name, std::move(coke_model), attachment_topic, std::move(simulation_session_id),
      max_observation_age_seconds, coke_settle_samples, coke_settle_interval_seconds,
      coke_settle_position_tolerance, coke_settle_orientation_tolerance_rad, initially_detached))
{
}

GazeboWorldObserver::~GazeboWorldObserver() = default;

ObservationResult GazeboWorldObserver::observe()
{
  auto moveit = moveit_observer_.observe();
  if (!moveit.snapshot) {
    return moveit;
  }
  return impl_->enrich(*moveit.snapshot);
}

}  // namespace so101_gazebo_demo::pick_place

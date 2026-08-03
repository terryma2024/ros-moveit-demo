#include "so101_gazebo_demo/pick_place/gazebo_world_observer.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <deque>
#include <map>
#include <mutex>
#include <optional>
#include <utility>

#include <gz/msgs/pose_v.pb.h>
#include <gz/msgs/contacts.pb.h>
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

ContactVector3 rotateByInverseQuaternion(const ContactVector3 & vector, const Pose3d & pose)
{
  const double norm = std::hypot(std::hypot(pose.qx, pose.qy), std::hypot(pose.qz, pose.qw));
  if (norm <= 1e-12)
    return {};
  const double qx = -pose.qx / norm;
  const double qy = -pose.qy / norm;
  const double qz = -pose.qz / norm;
  const double qw = pose.qw / norm;
  const double tx = 2.0 * (qy * vector.z - qz * vector.y);
  const double ty = 2.0 * (qz * vector.x - qx * vector.z);
  const double tz = 2.0 * (qx * vector.y - qy * vector.x);
  return {vector.x + qw * tx + (qy * tz - qz * ty), vector.y + qw * ty + (qz * tx - qx * tz),
          vector.z + qw * tz + (qx * ty - qy * tx)};
}

std::string unscopedCollisionName(const std::string & scoped)
{
  const auto separator = scoped.rfind("::");
  return separator == std::string::npos ? scoped : scoped.substr(separator + 2);
}

class TaskObjectPoseStabilityTracker
{
public:
  TaskObjectPoseStabilityTracker(std::size_t required_samples, double position_tolerance,
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

  [[nodiscard]] std::optional<bool> stationary() const
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
  Impl(const std::string & world_name, std::string task_object_id,
       const std::string & attachment_topic, std::string simulation_session_id,
       double max_observation_age_seconds, std::size_t task_object_settle_samples,
       double task_object_settle_interval_seconds, double task_object_settle_position_tolerance,
       double task_object_settle_orientation_tolerance_rad, bool initially_detached) :
      task_object_id_(std::move(task_object_id)),
      simulation_session_id_(std::move(simulation_session_id)),
      max_observation_age_(std::chrono::duration<double>(max_observation_age_seconds)),
      task_object_pose_stability_(task_object_settle_samples, task_object_settle_position_tolerance,
                                  task_object_settle_orientation_tolerance_rad),
      task_object_settle_interval_(
        std::chrono::duration<double>(task_object_settle_interval_seconds))
  {
    static_cast<void>(initially_detached);
    const auto pose_topic = "/world/" + world_name + "/pose/info";
    pose_subscription_ok_ = transport_.Subscribe(pose_topic, &Impl::onPoses, this);
    attachment_subscription_ok_ = transport_.Subscribe(attachment_topic, &Impl::onAttachment, this);
    std::vector<std::string> contact_sensors{"task_object_contact_wall_near"};
    for (int index = 1; index < 12; ++index) {
      const auto suffix = index < 10 ? "0" + std::to_string(index) : std::to_string(index);
      contact_sensors.push_back(index == 6 ? "task_object_contact_wall_opposite"
                                           : "task_object_contact_wall_" + suffix);
    }
    contact_sensors.emplace_back("task_object_contact_bottom");
    contact_subscription_ok_ = true;
    for (const auto & sensor : contact_sensors) {
      auto topic = "/world/" + world_name;
      topic += "/model/" + task_object_id_;
      topic += "/link/body/sensor/" + sensor + "/contact";
      contact_subscription_ok_ =
        transport_.Subscribe<gz::msgs::Contacts>(
          topic,
          [this, sensor](const gz::msgs::Contacts & contacts) { onContacts(sensor, contacts); }) &&
        contact_subscription_ok_;
    }
  }

  void onPoses(const gz::msgs::Pose_V & message)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    for (const auto & pose : message.pose()) {
      if (pose.name() == task_object_id_ ||
          pose.name().find("::" + task_object_id_) != std::string::npos) {
        const auto observed_at = std::chrono::steady_clock::now();
        task_object_pose_ = toPose3d(pose);
        task_object_pose_received_at_ = observed_at;
        if (last_stability_sample_at_ == std::chrono::steady_clock::time_point{} ||
            observed_at - last_stability_sample_at_ >= task_object_settle_interval_) {
          task_object_pose_stability_.addSample(*task_object_pose_, observed_at);
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
      task_object_attached_ = true;
    } else if (message.data() == "detached") {
      task_object_attached_ = false;
    } else {
      return;
    }
    attachment_received_at_ = std::chrono::steady_clock::now();
    condition_.notify_all();
  }

  void onContacts(const std::string & sensor, const gz::msgs::Contacts & message)
  {
    ContactEvidence evidence;
    std::optional<Pose3d> object_pose;
    {
      std::lock_guard<std::mutex> lock(mutex_);
      object_pose = task_object_pose_;
    }
    const auto include_height = [](double height, std::optional<double> & minimum,
                                   std::optional<double> & maximum) {
      minimum = minimum ? std::min(*minimum, height) : height;
      maximum = maximum ? std::max(*maximum, height) : height;
    };
    for (const auto & contact : message.contact()) {
      const auto & first = contact.collision1().name();
      const auto & second = contact.collision2().name();
      const bool first_task_object = first.find(task_object_id_ + "::") != std::string::npos;
      const bool second_task_object = second.find(task_object_id_ + "::") != std::string::npos;
      const auto & other = first_task_object ? second : first;
      const bool fixed = other.find("fixed_finger_contact_convex_") != std::string::npos ||
                         other.find("fixed_fingertip_pad_collision_") != std::string::npos;
      const bool moving = other.find("moving_jaw_contact_convex_") != std::string::npos ||
                          other.find("moving_fingertip_pad_collision_") != std::string::npos;
      const bool robot_gripper = fixed || moving;
      if (!(robot_gripper && (first_task_object || second_task_object)))
        continue;
      const auto & object_collision = first_task_object ? first : second;
      const double normal_sign = first_task_object ? 1.0 : -1.0;
      bool has_physical_point = false;
      for (int index = 0; index < contact.position_size(); ++index) {
        // Bullet contact manifolds may contain separated support points with a
        // negative depth beside the penetrating points.  They are useful to
        // the solver but are not physical contact evidence for the grasp
        // contract.  Missing and non-finite depths likewise cannot establish
        // contact.
        if (index >= contact.depth_size() || !std::isfinite(contact.depth(index)) ||
            contact.depth(index) < 0.0) {
          continue;
        }
        has_physical_point = true;
        TaskObjectContactSample sample;
        sample.task_object_collision = unscopedCollisionName(object_collision);
        sample.finger_collision = other;
        const auto & point = contact.position(index);
        sample.point_world = {point.x(), point.y(), point.z()};
        if (index < contact.normal_size()) {
          const auto & normal = contact.normal(index);
          sample.normal_toward_finger_world = {normal_sign * normal.x(), normal_sign * normal.y(),
                                               normal_sign * normal.z()};
        }
        sample.depth = contact.depth(index);
        evidence.max_depth = std::max(evidence.max_depth, sample.depth);
        if (fixed)
          include_height(point.z(), evidence.fixed_min_height, evidence.fixed_max_height);
        if (moving)
          include_height(point.z(), evidence.moving_min_height, evidence.moving_max_height);
        if (object_pose) {
          sample.point_task_object = rotateByInverseQuaternion(
            {point.x() - object_pose->x, point.y() - object_pose->y, point.z() - object_pose->z},
            *object_pose);
          sample.normal_toward_finger_task_object =
            rotateByInverseQuaternion(sample.normal_toward_finger_world, *object_pose);
        }
        if (fixed)
          evidence.fixed_samples.push_back(sample);
        if (moving)
          evidence.moving_samples.push_back(std::move(sample));
      }
      if (!has_physical_point)
        continue;
      evidence.gripper = true;
      evidence.collision_names.insert(other);
      evidence.fixed = evidence.fixed || fixed;
      evidence.moving = evidence.moving || moving;
    }
    evidence.observed_at = std::chrono::steady_clock::now();
    std::lock_guard<std::mutex> lock(mutex_);
    contact_evidence_[sensor] = std::move(evidence);
    mergeFreshContactEvidence();
    condition_.notify_all();
  }

  [[nodiscard]] ObservationResult enrich(WorldSnapshot snapshot) const
  {
    if (!pose_subscription_ok_ || !attachment_subscription_ok_) {
      return {std::nullopt, observationFailure(
                              "GAZEBO_SUBSCRIPTION_FAILED",
                              "Unable to subscribe to Gazebo TaskObject pose or attachment topic")};
    }
    std::unique_lock<std::mutex> lock(mutex_);
    condition_.wait_for(lock, max_observation_age_, [this]() {
      const auto now = std::chrono::steady_clock::now();
      return task_object_pose_.has_value() && task_object_attached_.has_value() &&
             task_object_pose_stability_.stationary().has_value() &&
             now - task_object_pose_received_at_ <= max_observation_age_ &&
             now - attachment_received_at_ <= max_observation_age_;
    });
    const auto now = std::chrono::steady_clock::now();
    if (!task_object_pose_) {
      return {std::nullopt, observationFailure("GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE",
                                               "Gazebo TaskObject pose is missing or stale")};
    }
    if (!finitePose(*task_object_pose_)) {
      return {std::nullopt,
              observationFailure("GAZEBO_TASK_OBJECT_POSE_NONFINITE",
                                 "Gazebo TaskObject pose contains nonfinite evidence")};
    }
    if (!task_object_attached_ || now - attachment_received_at_ > max_observation_age_) {
      return {std::nullopt,
              observationFailure(
                "GAZEBO_ATTACHMENT_STATE_UNAVAILABLE",
                "Gazebo attachment state relay has not published a fresh validated state")};
    }
    if (now - task_object_pose_received_at_ > max_observation_age_) {
      return {std::nullopt, observationFailure("GAZEBO_TASK_OBJECT_POSE_UNAVAILABLE",
                                               "Gazebo TaskObject pose is missing or stale")};
    }
    snapshot.gazebo_task_object_pose_world = task_object_pose_;
    snapshot.gazebo_task_object_attached = task_object_attached_;
    snapshot.gazebo_task_object_stationary = task_object_pose_stability_.stationary();
    if (contact_subscription_ok_ && now - contact_received_at_ <= max_observation_age_) {
      snapshot.gazebo_task_object_gripper_contact = task_object_gripper_contact_;
      snapshot.gazebo_task_object_fixed_finger_contact = task_object_fixed_finger_contact_;
      snapshot.gazebo_task_object_moving_jaw_contact = task_object_moving_jaw_contact_;
      snapshot.gazebo_task_object_gripper_max_depth = task_object_gripper_max_depth_;
      snapshot.gazebo_task_object_gripper_collision_names = task_object_gripper_collision_names_;
      snapshot.gazebo_task_object_fixed_contact_min_height = task_object_fixed_contact_min_height_;
      snapshot.gazebo_task_object_fixed_contact_max_height = task_object_fixed_contact_max_height_;
      snapshot.gazebo_task_object_moving_contact_min_height =
        task_object_moving_contact_min_height_;
      snapshot.gazebo_task_object_moving_contact_max_height =
        task_object_moving_contact_max_height_;
      snapshot.gazebo_task_object_fixed_finger_contacts = task_object_fixed_finger_contacts_;
      snapshot.gazebo_task_object_moving_jaw_contacts = task_object_moving_jaw_contacts_;
    }
    snapshot.simulation_session_id = simulation_session_id_;
    return {snapshot, std::nullopt};
  }

private:
  struct ContactEvidence
  {
    bool gripper{false};
    bool fixed{false};
    bool moving{false};
    double max_depth{0.0};
    std::set<std::string> collision_names;
    std::optional<double> fixed_min_height;
    std::optional<double> fixed_max_height;
    std::optional<double> moving_min_height;
    std::optional<double> moving_max_height;
    std::vector<TaskObjectContactSample> fixed_samples;
    std::vector<TaskObjectContactSample> moving_samples;
    std::chrono::steady_clock::time_point observed_at{};
  };

  void mergeFreshContactEvidence()
  {
    const auto now = std::chrono::steady_clock::now();
    task_object_gripper_contact_ = false;
    task_object_fixed_finger_contact_ = false;
    task_object_moving_jaw_contact_ = false;
    task_object_gripper_max_depth_ = 0.0;
    task_object_gripper_collision_names_.clear();
    task_object_fixed_contact_min_height_.reset();
    task_object_fixed_contact_max_height_.reset();
    task_object_moving_contact_min_height_.reset();
    task_object_moving_contact_max_height_.reset();
    task_object_fixed_finger_contacts_.clear();
    task_object_moving_jaw_contacts_.clear();
    const auto merge_height = [](const std::optional<double> & source,
                                 std::optional<double> & destination, bool minimum) {
      if (!source)
        return;
      destination =
        destination ? (minimum ? std::min(*destination, *source) : std::max(*destination, *source))
                    : source;
    };
    for (const auto & [_, evidence] : contact_evidence_) {
      if (now - evidence.observed_at > max_observation_age_)
        continue;
      task_object_gripper_contact_ = task_object_gripper_contact_ || evidence.gripper;
      task_object_fixed_finger_contact_ = task_object_fixed_finger_contact_ || evidence.fixed;
      task_object_moving_jaw_contact_ = task_object_moving_jaw_contact_ || evidence.moving;
      task_object_gripper_max_depth_ = std::max(task_object_gripper_max_depth_, evidence.max_depth);
      task_object_gripper_collision_names_.insert(evidence.collision_names.begin(),
                                                  evidence.collision_names.end());
      merge_height(evidence.fixed_min_height, task_object_fixed_contact_min_height_, true);
      merge_height(evidence.fixed_max_height, task_object_fixed_contact_max_height_, false);
      merge_height(evidence.moving_min_height, task_object_moving_contact_min_height_, true);
      merge_height(evidence.moving_max_height, task_object_moving_contact_max_height_, false);
      task_object_fixed_finger_contacts_.insert(task_object_fixed_finger_contacts_.end(),
                                                evidence.fixed_samples.begin(),
                                                evidence.fixed_samples.end());
      task_object_moving_jaw_contacts_.insert(task_object_moving_jaw_contacts_.end(),
                                              evidence.moving_samples.begin(),
                                              evidence.moving_samples.end());
    }
    contact_received_at_ = now;
  }

  std::string task_object_id_;
  std::string simulation_session_id_;
  std::chrono::duration<double> max_observation_age_;
  bool pose_subscription_ok_{false};
  bool attachment_subscription_ok_{false};
  bool contact_subscription_ok_{false};
  mutable std::mutex mutex_;
  mutable std::condition_variable condition_;
  std::optional<Pose3d> task_object_pose_;
  std::optional<bool> task_object_attached_;
  bool task_object_gripper_contact_{false};
  bool task_object_fixed_finger_contact_{false};
  bool task_object_moving_jaw_contact_{false};
  double task_object_gripper_max_depth_{0.0};
  std::set<std::string> task_object_gripper_collision_names_;
  std::map<std::string, ContactEvidence> contact_evidence_;
  std::vector<TaskObjectContactSample> task_object_fixed_finger_contacts_;
  std::vector<TaskObjectContactSample> task_object_moving_jaw_contacts_;
  std::optional<double> task_object_fixed_contact_min_height_;
  std::optional<double> task_object_fixed_contact_max_height_;
  std::optional<double> task_object_moving_contact_min_height_;
  std::optional<double> task_object_moving_contact_max_height_;
  std::chrono::steady_clock::time_point contact_received_at_{};
  std::chrono::steady_clock::time_point attachment_received_at_{};
  TaskObjectPoseStabilityTracker task_object_pose_stability_;
  std::chrono::duration<double> task_object_settle_interval_;
  std::chrono::steady_clock::time_point last_stability_sample_at_{};
  std::chrono::steady_clock::time_point task_object_pose_received_at_{};
  // Keep the transport last so it is destroyed first and unsubscribes every
  // callback before the mutexes and callback-owned evidence above disappear.
  gz::transport::Node transport_;
};

GazeboWorldObserver::GazeboWorldObserver(
  IWorldObserver & moveit_observer, const std::string & world_name, std::string task_object_id,
  const std::string & attachment_topic, std::string simulation_session_id,
  double max_observation_age_seconds, std::size_t task_object_settle_samples,
  double task_object_settle_interval_seconds, double task_object_settle_position_tolerance,
  double task_object_settle_orientation_tolerance_rad, bool initially_detached) :
    moveit_observer_(moveit_observer),
    impl_(std::make_unique<Impl>(world_name, std::move(task_object_id), attachment_topic,
                                 std::move(simulation_session_id), max_observation_age_seconds,
                                 task_object_settle_samples, task_object_settle_interval_seconds,
                                 task_object_settle_position_tolerance,
                                 task_object_settle_orientation_tolerance_rad, initially_detached))
{
}

GazeboWorldObserver::~GazeboWorldObserver() = default;

ObservationResult GazeboWorldObserver::observe()
{
  auto initial_moveit = moveit_observer_.observe();
  if (!initial_moveit.snapshot) {
    return initial_moveit;
  }
  auto gazebo_ready = impl_->enrich(*initial_moveit.snapshot);
  if (!gazebo_ready.snapshot) {
    return gazebo_ready;
  }
  auto final_moveit = moveit_observer_.observe();
  if (!final_moveit.snapshot) {
    return final_moveit;
  }
  return impl_->enrich(*final_moveit.snapshot);
}

}  // namespace so101_gazebo_demo::pick_place

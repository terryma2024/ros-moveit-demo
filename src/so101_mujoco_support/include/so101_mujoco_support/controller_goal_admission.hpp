#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_ADMISSION_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_ADMISSION_HPP_

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <mutex>
#include <optional>
#include <set>
#include <stdexcept>
#include <utility>

#include "control_msgs/action/follow_joint_trajectory.hpp"
#include "rclcpp/serialization.hpp"
#include "rclcpp/serialized_message.hpp"

namespace so101_mujoco_support
{

// Local admission primitive. The controller must separately prove stop, owner,
// registration caller and callback ownership before wiring this to actions.
class ControllerGoalAdmission final
{
public:
  using GoalUUID = std::array<uint8_t, 16>;
  using Goal = control_msgs::action::FollowJointTrajectory::Goal;
  using Clock = std::function<int64_t()>;

  enum class Result {ALLOW, DENY_CLOSED, DENY_FAULT};

  explicit ControllerGoalAdmission(
    Clock clock = steady_now_ns, int64_t validity_ns = 250000000,
    size_t max_goal_bytes = 1048576, size_t max_goals_per_generation = 2048)
  : clock_(std::move(clock)), validity_ns_(validity_ns), max_goal_bytes_(max_goal_bytes),
    max_goals_per_generation_(max_goals_per_generation)
  {
    if (!clock_ || validity_ns_ <= 0 || max_goal_bytes_ == 0 || max_goals_per_generation_ == 0) {
      throw std::invalid_argument("CONTROLLER_GOAL_ADMISSION_CONFIG_INVALID");
    }
  }

  bool arm(uint64_t generation)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto now = read_clock();
    if (!now || generation == 0 || generation <= generation_ || clock_bad_) {
      return false;
    }
    generation_ = generation;
    reservation_.reset();
    used_uuids_.clear();
    mode_ = Mode::EXCLUSIVE;
    return true;
  }

  void close()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    fault_close();
  }

  bool close_generation(uint64_t generation)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (generation == 0 || generation != generation_) {return false;}
    fault_close();
    return true;
  }

  bool is_exclusive_generation(uint64_t generation)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return generation != 0 && generation == generation_ && mode_ == Mode::EXCLUSIVE &&
           !clock_bad_;
  }

  bool reserve(const GoalUUID & uuid, const Goal & goal, uint64_t generation)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (mode_ != Mode::EXCLUSIVE) {
      return false;
    }
    const auto now = read_clock();
    if (!now || generation != generation_ || reservation_ ||
      used_uuids_.size() >= max_goals_per_generation_ ||
      used_uuids_.find(uuid) != used_uuids_.end() ||
      std::all_of(uuid.begin(), uuid.end(), [](uint8_t value) {return value == 0;}) ||
      goal.trajectory.joint_names.empty() || goal.trajectory.points.empty() ||
      *now > std::numeric_limits<int64_t>::max() - validity_ns_)
    {
      fault_close();
      return false;
    }
    try {
      rclcpp::SerializedMessage serialized;
      rclcpp::Serialization<Goal>().serialize_message(&goal, &serialized);
      if (serialized.size() > max_goal_bytes_) {
        fault_close();
        return false;
      }
      reservation_ = Reservation{uuid, goal, *now + validity_ns_};
      used_uuids_.insert(uuid);
    } catch (...) {
      fault_close();
      return false;
    }
    return true;
  }

  Result admit(const GoalUUID & uuid, const Goal & goal, uint64_t generation)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return admit_locked(uuid, goal, generation);
  }

  Result admit_current(const GoalUUID & uuid, const Goal & goal)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return admit_locked(uuid, goal, generation_);
  }

private:
  Result admit_locked(const GoalUUID & uuid, const Goal & goal, uint64_t generation)
  {
    if (mode_ != Mode::EXCLUSIVE) {
      return Result::DENY_CLOSED;
    }
    const auto now = read_clock();
    if (!now || generation != generation_ || !reservation_ ||
      *now >= reservation_->expires_ns || uuid != reservation_->uuid ||
      goal != reservation_->goal)
    {
      fault_close();
      return Result::DENY_FAULT;
    }
    reservation_.reset();
    return Result::ALLOW;
  }

  enum class Mode {CLOSED, EXCLUSIVE};
  struct Reservation
  {
    GoalUUID uuid;
    Goal goal;
    int64_t expires_ns;
  };

  static int64_t steady_now_ns()
  {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  }

  std::optional<int64_t> read_clock()
  {
    int64_t now;
    try {
      now = clock_();
    } catch (...) {
      clock_bad_ = true;
      fault_close();
      return std::nullopt;
    }
    if (now < 0 || (last_now_ns_ && now < *last_now_ns_)) {
      clock_bad_ = true;
      fault_close();
      return std::nullopt;
    }
    last_now_ns_ = now;
    return now;
  }

  void fault_close()
  {
    reservation_.reset();
    mode_ = Mode::CLOSED;
  }

  std::mutex mutex_;
  Clock clock_;
  int64_t validity_ns_;
  size_t max_goal_bytes_;
  size_t max_goals_per_generation_;
  Mode mode_{Mode::CLOSED};
  uint64_t generation_{0};
  std::optional<int64_t> last_now_ns_;
  bool clock_bad_{false};
  std::optional<Reservation> reservation_;
  std::set<GoalUUID> used_uuids_;
};

}  // namespace so101_mujoco_support

#endif  // SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_ADMISSION_HPP_

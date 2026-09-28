#ifndef SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_ADMISSION_HPP_
#define SO101_MUJOCO_SUPPORT__CONTROLLER_GOAL_ADMISSION_HPP_

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <map>
#include <mutex>
#include <optional>
#include <set>

#include "so101_mujoco_support/controller_reservation_role.hpp"
#include <string>

#include "so101_mujoco_support/bound_reservation.hpp"
#include "so101_mujoco_support/sha256.hpp"
#include <optional>
#include <set>

#include "so101_mujoco_support/controller_reservation_role.hpp"
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
  using GoalUUID = ControllerGoalUUID;
  using Goal = ControllerGoal;
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

  explicit ControllerGoalAdmission(
    Clock clock, int64_t validity_ns, size_t max_goal_bytes, size_t max_goals_per_generation,
    ServiceControllerIdentity identity)
  : ControllerGoalAdmission(
      std::move(clock), validity_ns, max_goal_bytes,
      max_goals_per_generation)
  {
    const int role = static_cast<int>(identity.role);
    if (role < 1 || role > 3 || identity.incarnation.empty() || identity.boot.empty() ||
      identity.incarnation.size() > kMaxIncarnationBytes ||
      identity.boot.size() > kMaxIncarnationBytes)
    {
      throw std::invalid_argument("CONTROLLER_GOAL_ADMISSION_IDENTITY_INVALID");
    }
    for (const std::string * value : {&identity.incarnation, &identity.boot}) {
      for (const char character : *value) {
        const auto code = static_cast<unsigned char>(character);
        if (code < 0x20 || code > 0x7e) {
          throw std::invalid_argument("CONTROLLER_GOAL_ADMISSION_IDENTITY_INVALID");
        }
      }
    }
    service_identity_ = std::move(identity);
  }

  // --- bound reservation state machine (v2 protocol) ----------------------
  // No serialization happens under this lock: the parser already stored the goal
  // digest in the request, and admit_bound_action digests before taking the lock.
  BoundReserveStatus reserve_bound(const BoundControllerReservationRequest & request)
  {
    // digest the *actual* goal before taking the lock: nothing in the request is
    // trusted as a precomputed authority value
    const auto digest = compute_goal_digest(request.goal);
    if (!digest) {
      std::lock_guard<std::mutex> lock(mutex_);
      fault_close();
      return BoundReserveStatus::DENY_CLOSED;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (mode_ != Mode::EXCLUSIVE || closed_) {return BoundReserveStatus::DENY_CLOSED;}
    if (clock_bad_) {return BoundReserveStatus::DENY_CLOSED;}
    const auto now = bound_now_locked();
    if (!now) {return BoundReserveStatus::DENY_CLOSED;}
    if (generation_ == 0 || request.generation != generation_) {
      return tombstone_and_close(request, BoundReserveStatus::DENY_GENERATION);
    }
    if (!service_identity_) {return tombstone_and_close(request, BoundReserveStatus::DENY_CLOSED);}
    if (request.role != service_identity_->role) {
      return tombstone_and_close(request, BoundReserveStatus::DENY_ROLE);
    }
    if (request.controller_incarnation != service_identity_->incarnation) {
      return tombstone_and_close(request, BoundReserveStatus::DENY_INCARNATION);
    }
    if (request.controller_boot_incarnation != service_identity_->boot) {
      return tombstone_and_close(request, BoundReserveStatus::DENY_BOOT);
    }
    if (*now > request.deadline_ns || *now < request.claim_monotonic_ns) {
      return tombstone_and_close(request, BoundReserveStatus::DENY_EXPIRED);
    }
    if (*digest != request.target_digest) {
      return tombstone_and_close(request, BoundReserveStatus::DENY_DIGEST_MISMATCH);
    }
    if (bound_.count(request.uuid) != 0 || used_bound_uuids_.count(request.uuid) != 0 ||
      bound_permits_.count(request.permit_uuid) != 0 ||
      used_permits_.count(request.permit_uuid) != 0)
    {
      return tombstone_and_close(request, BoundReserveStatus::DENY_UUID_REPLAY);
    }
    if (!bound_.empty()) {
      // one outstanding bound reservation per role/gate, exactly like the legacy
      // optional reservation: a second distinct permit while the first is
      // unconsumed is refused and closes the gate
      return tombstone_and_close(request, BoundReserveStatus::DENY_UUID_REPLAY);
    }
    if (bound_.size() >= max_goals_per_generation_ ||
      used_bound_uuids_.size() >= max_goals_per_generation_)
    {
      return tombstone_and_close(request, BoundReserveStatus::DENY_UUID_REPLAY);
    }
    bound_[request.uuid] = BoundReservation{request.permit_uuid, request.target_digest,
      request.claim_monotonic_ns, request.deadline_ns};
    bound_permits_[request.permit_uuid] = request.uuid;
    return BoundReserveStatus::ACCEPTED;
  }

  BoundReserveStatus admit_bound_action(
    const GoalUUID & uuid, const Goal & goal, uint64_t generation)
  {
    // serialize and digest *before* the lock: no large copy under the gate mutex
    const auto digest = compute_goal_digest(goal);
    if (!digest) {
      std::lock_guard<std::mutex> lock(mutex_);
      fault_close();
      return BoundReserveStatus::DENY_CLOSED;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (mode_ != Mode::EXCLUSIVE || closed_ || clock_bad_) {
      return BoundReserveStatus::DENY_CLOSED;
    }
    const auto now = bound_now_locked();
    if (!now) {return BoundReserveStatus::DENY_CLOSED;}
    if (generation_ == 0 || generation != generation_) {
      return drop_and_close(uuid, BoundReserveStatus::DENY_GENERATION);
    }
    const auto entry = bound_.find(uuid);
    if (entry == bound_.end()) {
      // an admit that cannot find its reservation is a protocol violation: the
      // gate closes, so even a previously valid outstanding uuid can never be
      // admitted afterwards
      fault_close();
      return BoundReserveStatus::DENY_UUID_REPLAY;
    }
    if (*now > entry->second.deadline_ns) {
      return drop_and_close(uuid, BoundReserveStatus::DENY_EXPIRED);
    }
    if (*digest != entry->second.target_digest) {
      return drop_and_close(uuid, BoundReserveStatus::DENY_DIGEST_MISMATCH);
    }
    used_bound_uuids_.insert(uuid);
    used_permits_.insert(entry->second.permit_uuid);
    bound_permits_.erase(entry->second.permit_uuid);
    bound_.erase(entry);                          // single use, atomically
    return BoundReserveStatus::ACCEPTED;
  }

  bool cancel_bound(const GoalUUID & uuid)
  {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto entry = bound_.find(uuid);
    if (entry == bound_.end()) {return false;}
    used_bound_uuids_.insert(uuid);
    used_permits_.insert(entry->second.permit_uuid);
    bound_permits_.erase(entry->second.permit_uuid);
    bound_.erase(entry);
    return true;
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
    // a rearm clears outstanding bound state and its tombstones; the old
    // generation can never admit again because the generation check precedes
    // every lookup
    bound_.clear();
    bound_permits_.clear();
    used_bound_uuids_.clear();
    used_permits_.clear();
    last_bound_now_ = now;
    // a successful arm to a strictly higher generation reopens the gate for the
    // new generation; clock_bad_ stays unrecoverable
    closed_ = false;
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
  struct BoundReservation
  {
    std::array<uint8_t, 16> permit_uuid;
    std::array<uint8_t, 32> target_digest;
    int64_t claim_monotonic_ns;
    int64_t deadline_ns;
  };

  // A failed request on a known permit becomes an irrevocable single-use tombstone
  // and closes the gate: it can never be corrected into a live permit later.
  BoundReserveStatus tombstone_and_close(
    const BoundControllerReservationRequest & request, BoundReserveStatus status)
  {
    used_bound_uuids_.insert(request.uuid);
    used_permits_.insert(request.permit_uuid);
    fault_close();
    return status;
  }

  BoundReserveStatus drop_and_close(const GoalUUID & uuid, BoundReserveStatus status)
  {
    const auto entry = bound_.find(uuid);
    if (entry != bound_.end()) {
      used_bound_uuids_.insert(uuid);
      used_permits_.insert(entry->second.permit_uuid);
      bound_permits_.erase(entry->second.permit_uuid);
      bound_.erase(entry);
    } else {
      used_bound_uuids_.insert(uuid);
    }
    fault_close();
    return status;
  }

  // Reads the gate's own clock fail-closed: an exception or a regression below the
  // last accepted instant closes the gate instead of propagating to the caller.
  std::optional<int64_t> bound_now_locked()
  {
    try {
      const int64_t now = clock_();
      if (now <= 0 || (last_bound_now_ && now < *last_bound_now_)) {
        fault_close();
        return std::nullopt;
      }
      last_bound_now_ = now;
      return now;
    } catch (...) {
      fault_close();
      return std::nullopt;
    }
  }

  std::optional<std::array<uint8_t, 32>> compute_goal_digest(const Goal & goal) const
  {
    try {
      rclcpp::SerializedMessage serialized;
      rclcpp::Serialization<Goal>().serialize_message(&goal, &serialized);
      const auto & raw = serialized.get_rcl_serialized_message();
      if (raw.buffer_length == 0 || raw.buffer_length > max_goal_bytes_) {
        return std::nullopt;                       // oversize goals close the gate
      }
      const std::vector<uint8_t> bytes(raw.buffer, raw.buffer + raw.buffer_length);
      return sha256::digest(bytes);
    } catch (...) {
      return std::nullopt;
    }
  }

  std::optional<ServiceControllerIdentity> service_identity_;
  bool closed_{false};
  std::map<GoalUUID, BoundReservation> bound_;
  std::map<std::array<uint8_t, 16>, GoalUUID> bound_permits_;
  std::set<GoalUUID> used_bound_uuids_;
  std::set<std::array<uint8_t, 16>> used_permits_;
  std::optional<int64_t> last_bound_now_;
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
    // outstanding bound reservations are dropped; the single-use tombstones in
    // used_bound_uuids_ / used_permits_ are deliberately kept so a failed request
    // can never be corrected into a live permit
    bound_.clear();
    bound_permits_.clear();
    closed_ = true;
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

// Copyright 2026 SO-101 maintainers

#ifndef SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_
#define SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_

#include <mujoco/mujoco.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <functional>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include <mujoco_ros2_control_plugins/mujoco_ros2_control_plugin_capabilities.hpp>
#include <mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp>
#include <rclcpp/rclcpp.hpp>
#include <realtime_tools/realtime_publisher.hpp>

#include "so101_mujoco_support/msg/physics_hazard_latch.hpp"
#include "so101_mujoco_support/msg/physics_cancellation_ack.hpp"
#include "so101_mujoco_support/msg/physics_cancellation_request.hpp"
#include "so101_mujoco_support/msg/physics_step_evidence.hpp"
#include "so101_mujoco_support/msg/physics_step_evidence_chunk.hpp"
#include "so101_mujoco_support/physics_step_fence.hpp"
#include "so101_mujoco_support/msg/simulation_evidence.hpp"
#include "so101_mujoco_support/msg/scalar_joint_evidence.hpp"
#include "so101_mujoco_support/msg/robot_contact_evidence.hpp"
#include "so101_mujoco_support/msg/scene_state_evidence.hpp"

namespace so101_mujoco_support
{
class SceneStateBuilder
{
public:
  bool configure(const mjModel * model);
  const std::string & model_sha256() const {return model_sha256_;}
  msg::SceneStateEvidence build(const mjModel * model, const mjData * data,
    const std::string & session, uint64_t epoch, uint64_t step, bool paused,
    int64_t clock_begin_ns) const;
private:
  const mjModel * model_{nullptr};
  std::string model_sha256_;
};

struct EvidenceState
{
  std::string simulation_session_id;
  uint64_t publisher_sequence{0};
  uint64_t simulation_step{0};
  uint64_t reset_epoch{0};
  uint64_t consumed_reset_generation{0};
  double previous_time{0.0};
  bool initialized{false};
};

class EvidenceBuilder
{
public:
  bool configure(
    const mjModel * model, const std::string & object_body,
    const std::string & left_geom, const std::string & right_geom,
    const std::vector<std::string> & other_geoms, std::size_t max_contacts);
  bool configure(
    const mjModel * model, const std::string & object_body,
    const std::vector<std::string> & left_geoms,
    const std::vector<std::string> & right_geoms,
    const std::vector<std::string> & other_geoms, std::size_t max_contacts);
  msg::SimulationEvidence build(
    const mjModel * model, const mjData * data, bool paused,
    EvidenceState & state, uint64_t reset_generation = 0,
    bool advance_physics_step = true) const;
  msg::PhysicsStepEvidence build_step(
    const mjModel * model, const mjData * data, bool paused,
    EvidenceState & state, uint64_t reset_generation,
    double static_shadow_force_n,
    double diagnostic_hard_stop_force_n) const;

private:
  bool object_geom(int geom_id) const;
  int object_body_id_{-1};
  std::vector<int> left_geom_ids_;
  std::vector<int> right_geom_ids_;
  std::vector<int> object_geom_ids_;
  std::vector<int> other_geom_ids_;
  std::vector<std::string> body_names_;
  std::vector<std::string> geom_names_;
  std::string object_body_name_;
  std::size_t max_contacts_{128};
};

msg::PhysicsStepEvidence make_physics_step_evidence(
  const msg::SimulationEvidence & snapshot, double simulation_time_s,
  double static_shadow_force_n, double diagnostic_hard_stop_force_n);
msg::PhysicsCancellationAck make_cancellation_ack(
  const msg::PhysicsCancellationRequest & request, uint64_t reset_epoch,
  uint64_t observed_physics_step, double observed_simulation_time_s);

msg::ScalarJointEvidence make_scalar_joint_evidence(
  const mjModel * model, const mjData * data, const std::vector<std::string> & joint_names,
  const std::string & session, uint64_t reset_epoch, uint64_t simulation_step, bool paused);

class PhysicsStepEvidenceBuffer
{
public:
  PhysicsStepEvidenceBuffer(
    std::size_t capacity, std::size_t flush_step_count,
    double diagnostic_hard_stop_force_n);
  bool append(const msg::PhysicsStepEvidence & sample);
  bool ready() const;
  msg::PhysicsStepEvidenceChunk prepare_chunk() const;
  void mark_publish_failed();
  void mark_published();
  std::optional<msg::PhysicsHazardLatch> hazard_latch() const;
  bool evidence_loss_latched() const;
  void reset();

private:
  std::size_t capacity_;
  std::size_t flush_step_count_;
  double diagnostic_hard_stop_force_n_;
  std::deque<msg::PhysicsStepEvidence> samples_;
  uint64_t chunk_sequence_{0};
  uint64_t failed_publish_attempts_{0};
  uint64_t publish_deferrals_total_{0};
  bool evidence_loss_{false};
  std::optional<msg::PhysicsStepEvidence> last_observed_;
  std::optional<msg::PhysicsHazardLatch> hazard_latch_;
};

/// Publishes physics-step chunks from its own thread and stamps the moment it is about to call `publish()`.
///
/// The physics thread only posts (never blocks): `try_post()` refuses while the previous post has not been taken by the
/// publishing thread. `realtime_tools::RealtimePublisher` offers no hook at the publish call, so the stamp
/// (`publish_monotonic_ns`, the clock of the samples' clock intervals) is taken here.
class StampingChunkPublisher
{
public:
  using Chunk = msg::PhysicsStepEvidenceChunk;
  explicit StampingChunkPublisher(rclcpp::Publisher<Chunk>::SharedPtr publisher);
  ~StampingChunkPublisher();
  StampingChunkPublisher(const StampingChunkPublisher &) = delete;
  StampingChunkPublisher & operator=(const StampingChunkPublisher &) = delete;
  bool try_post(const Chunk & chunk);

private:
  void loop();
  rclcpp::Publisher<Chunk>::SharedPtr publisher_;
  std::mutex mutex_;
  std::condition_variable condition_;
  Chunk slot_;
  bool full_{false};
  bool stop_{false};
  std::thread thread_;
};

class RobotContactBuilder
{
public:
  bool configure(const mjModel * model, const std::vector<std::string> & roots,
    std::size_t max_contacts);
  msg::RobotContactEvidence build(const mjModel * model, const mjData * data,
    const std::string & session, uint64_t epoch, uint64_t step) const;
private:
  std::vector<bool> protected_geoms_;
  std::vector<std::string> names_;
  std::size_t max_contacts_{128};
};

class RobotContactBuffer
{
public:
  explicit RobotContactBuffer(std::size_t capacity);
  bool append(const msg::RobotContactEvidence & sample);
  bool empty() const;
  msg::RobotContactEvidence front() const;
  void pop_published();
  void reset(uint64_t epoch);
  // Observation / loss helpers for the publishing thread (plan A21).
  std::size_t size() const;
  void note_loss();
private:
  std::size_t capacity_;
  std::deque<msg::RobotContactEvidence> samples_;
  std::optional<msg::RobotContactEvidence> last_;
  std::optional<uint64_t> epoch_;
  bool loss_{false};
};

// Ordered, bounded hand-off of RobotContactEvidence from the physics step to a dedicated NON-real-time publishing
// thread (plan A21). The physics thread only takes a short mutex to push (never touches DDS); the thread publishes
// EVERY queued message per wake, in order, through the sink. Overflow, invalid and truncated samples keep the
// RobotContactBuffer semantics (the loss flag persists on every later message until an explicit reset(epoch)).
class RobotContactPublisher
{
public:
  using Sink = std::function<void(const msg::RobotContactEvidence &)>;
  using Log = std::function<void(const std::string &)>;
  struct Stats
  {
    uint64_t pushed{0};
    uint64_t published{0};
    uint64_t dropped{0};       // overflow / invalid samples refused by the buffer
    uint64_t sink_errors{0};   // sink exceptions (counted as evidence loss)
    std::size_t depth{0};
    std::size_t high_water{0};
  };
  RobotContactPublisher(
    std::size_t capacity, Sink sink, Log log = nullptr,
    std::chrono::milliseconds stats_period = std::chrono::milliseconds(5000));
  ~RobotContactPublisher();
  RobotContactPublisher(const RobotContactPublisher &) = delete;
  RobotContactPublisher & operator=(const RobotContactPublisher &) = delete;
  // Physics thread. Never blocks on the sink; false when the sample was refused (overflow or invalid).
  bool push(const msg::RobotContactEvidence & sample);
  // Physics thread, rare. Clears the queue and starts the new epoch; waits (bounded) for the one message that may be
  // in flight so no old-epoch message can follow the new epoch.
  void reset(uint64_t epoch);
  // Stops and joins the thread; queued messages are discarded. Idempotent.
  void stop();
  Stats stats() const;
private:
  void run();
  static constexpr std::size_t kBatch = 512;
  mutable std::mutex mutex_;
  std::condition_variable wake_;
  std::condition_variable idle_;
  RobotContactBuffer buffer_;
  Sink sink_;
  Log log_;
  std::chrono::milliseconds stats_period_;
  bool stop_{false};
  bool inflight_{false};
  uint64_t generation_{0};
  Stats stats_;
  std::thread thread_;
};

/// Index of the publish grid cell containing `time_s`: floor(llround(time_s * 1e9) / period_ns).
int64_t publish_grid_index(double time_s, int64_t period_ns);

/// A publish period is usable when it is a whole, positive number of physics steps.
bool publish_grid_valid(int64_t period_ns, int64_t step_ns);

class SimulationEvidencePlugin final
  : public mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase,
    public mujoco_ros2_control_plugins::MuJoCoROS2ControlSimulationObserver
{
public:
  bool init(rclcpp::Node::SharedPtr node, const mjModel * model, mjData * data) override;
  void update(const mjModel * model, mjData * data) override;
  void on_physics_step(const mjModel * model, const mjData * data) override;
  void on_reset() override;
  void on_pause(bool paused) override;
  void on_state_snapshot(const mjModel * model, const mjData * data, bool paused) override;
  void cleanup() override;

private:
  using Evidence = msg::SimulationEvidence;
  using EvidenceChunk = msg::PhysicsStepEvidenceChunk;
  /// True when the evidence frame was published. A paused snapshot that finds its publisher busy is NOT lost: see
  /// `retry_paused_snapshot()`.
  bool try_publish_snapshot(
    const mjModel * model, const mjData * data, bool paused,
    uint64_t reset_generation, bool advance_physics_step);
  /// The scene-state frame that goes with a snapshot. A paused one that finds its publisher busy is retried.
  bool publish_scene_snapshot(
    const mjModel * model, const mjData * data, bool paused, int64_t clock_begin_ns);
  /// Controller-cycle retry of the authoritative paused frame (evidence and scene state) that the pause/reset hook
  /// could not publish; each frame is published exactly once and never after the simulation resumed.
  void retry_paused_snapshot(const mjModel * model, const mjData * data);
  /// What follows a successfully published reset snapshot: the raw-step state, buffers and fence move to the new epoch.
  void complete_reset_snapshot(const mjData * data, uint64_t generation, bool reset_pending);
  void try_publish_chunk();
  void publish_hazard_if_needed();
  void acknowledge_cancellation_request(
    const msg::PhysicsCancellationRequest & request);
  rclcpp::Node::SharedPtr node_;
  rclcpp::Publisher<Evidence>::SharedPtr publisher_;
  std::unique_ptr<realtime_tools::RealtimePublisher<Evidence>> realtime_publisher_;
  rclcpp::Publisher<EvidenceChunk>::SharedPtr chunk_publisher_;
  std::unique_ptr<StampingChunkPublisher> chunk_stamping_publisher_;
  rclcpp::Publisher<msg::PhysicsHazardLatch>::SharedPtr hazard_publisher_;
  rclcpp::Subscription<msg::PhysicsCancellationRequest>::SharedPtr
    cancellation_request_subscription_;
  rclcpp::Publisher<msg::PhysicsCancellationAck>::SharedPtr cancellation_ack_publisher_;
  rclcpp::Subscription<msg::PhysicsStepFenceRequest>::SharedPtr step_fence_request_subscription_;
  rclcpp::Publisher<msg::PhysicsStepFenceAck>::SharedPtr step_fence_ack_publisher_;
  std::unique_ptr<realtime_tools::RealtimePublisher<msg::PhysicsStepFenceAck>>
  realtime_step_fence_ack_publisher_;
  rclcpp::Publisher<msg::ScalarJointEvidence>::SharedPtr scalar_joint_publisher_;
  std::vector<std::string> scalar_joint_names_;
  SceneStateBuilder scene_builder_;
  rclcpp::Publisher<msg::SceneStateEvidence>::SharedPtr scene_publisher_;
  std::unique_ptr<realtime_tools::RealtimePublisher<msg::SceneStateEvidence>> realtime_scene_publisher_;
  rclcpp::Publisher<msg::RobotContactEvidence>::SharedPtr robot_publisher_;
  RobotContactBuilder robot_builder_;
  std::unique_ptr<RobotContactPublisher> robot_contacts_;
  EvidenceBuilder builder_;
  EvidenceState state_;
  EvidenceState physics_state_;
  std::unique_ptr<PhysicsStepEvidenceBuffer> physics_step_buffer_;
  // Publication is gated on an integer-nanosecond grid: the simulation time is an accumulated double, and gating on
  // `time - last >= period` rounded differently in each binade (5 or 6 steps of 2 ms per message, 10 or 12 ms). A message is
  // published when floor(time_ns / period_ns) differs from that of the last one; period_ns is a multiple of the step in ns.
  int64_t publish_period_ns_{10000000};
  int64_t last_publish_grid_{0};
  double static_shadow_force_n_{1.1579004532160448};
  double diagnostic_hard_stop_force_n_{11.60};
  bool published_{false};
  // Set when the pause/reset hook could not publish its (single) paused frame because a publisher was busy.
  std::atomic<bool> evidence_snapshot_retry_{false};
  std::atomic<bool> scene_snapshot_retry_{false};
  bool hazard_published_{false};
  std::atomic<uint64_t> reset_generation_{0};
  std::atomic<bool> authoritative_paused_{false};
  std::atomic<uint64_t> current_reset_epoch_{0};
  std::atomic<uint64_t> current_physics_step_{0};
  std::atomic<double> current_simulation_time_s_{0.0};
  PhysicsStepFence step_fence_{"unconfigured-session"};
};
}  // namespace so101_mujoco_support
#endif  // SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_

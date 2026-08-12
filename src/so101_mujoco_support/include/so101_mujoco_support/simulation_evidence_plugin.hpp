#ifndef SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_
#define SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <mujoco/mujoco.h>
#include <mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp>
#include <rclcpp/rclcpp.hpp>
#include <realtime_tools/realtime_publisher.hpp>

#include "so101_mujoco_support/msg/physics_hazard_latch.hpp"
#include "so101_mujoco_support/msg/physics_cancellation_ack.hpp"
#include "so101_mujoco_support/msg/physics_cancellation_request.hpp"
#include "so101_mujoco_support/msg/physics_step_evidence.hpp"
#include "so101_mujoco_support/msg/physics_step_evidence_chunk.hpp"
#include "so101_mujoco_support/msg/simulation_evidence.hpp"

namespace so101_mujoco_support
{
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
  bool evidence_loss_{false};
  std::optional<msg::PhysicsStepEvidence> last_observed_;
  std::optional<msg::PhysicsHazardLatch> hazard_latch_;
};

class SimulationEvidencePlugin final
  : public mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase
{
public:
  bool init(rclcpp::Node::SharedPtr node, const mjModel * model, mjData * data) override;
  void update(const mjModel * model, mjData * data) override;
  void on_reset() override;
  void on_pause(bool paused) override;
  void on_state_snapshot(const mjModel * model, const mjData * data, bool paused) override;
  void cleanup() override;

private:
  using Evidence = msg::SimulationEvidence;
  using EvidenceChunk = msg::PhysicsStepEvidenceChunk;
  void try_publish_snapshot(
    const mjModel * model, const mjData * data, bool paused,
    uint64_t reset_generation, bool advance_physics_step);
  void try_publish_chunk();
  void publish_hazard_if_needed();
  void acknowledge_cancellation_request(
    const msg::PhysicsCancellationRequest & request);
  rclcpp::Node::SharedPtr node_;
  rclcpp::Publisher<Evidence>::SharedPtr publisher_;
  std::unique_ptr<realtime_tools::RealtimePublisher<Evidence>> realtime_publisher_;
  rclcpp::Publisher<EvidenceChunk>::SharedPtr chunk_publisher_;
  std::unique_ptr<realtime_tools::RealtimePublisher<EvidenceChunk>>
  realtime_chunk_publisher_;
  rclcpp::Publisher<msg::PhysicsHazardLatch>::SharedPtr hazard_publisher_;
  rclcpp::Subscription<msg::PhysicsCancellationRequest>::SharedPtr
    cancellation_request_subscription_;
  rclcpp::Publisher<msg::PhysicsCancellationAck>::SharedPtr cancellation_ack_publisher_;
  EvidenceBuilder builder_;
  EvidenceState state_;
  std::unique_ptr<PhysicsStepEvidenceBuffer> physics_step_buffer_;
  double publish_period_s_{0.01};
  double last_publish_time_s_{0.0};
  double static_shadow_force_n_{1.1579004532160448};
  double diagnostic_hard_stop_force_n_{11.60};
  bool published_{false};
  bool hazard_published_{false};
  std::atomic<uint64_t> reset_generation_{0};
  std::atomic<bool> authoritative_paused_{false};
  std::atomic<uint64_t> current_reset_epoch_{0};
  std::atomic<uint64_t> current_physics_step_{0};
  std::atomic<double> current_simulation_time_s_{0.0};
};
}  // namespace so101_mujoco_support
#endif

#ifndef SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_
#define SO101_MUJOCO_SUPPORT__SIMULATION_EVIDENCE_PLUGIN_HPP_

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include <mujoco/mujoco.h>
#include <mujoco_ros2_control_plugins/mujoco_ros2_control_plugins_base.hpp>
#include <rclcpp/rclcpp.hpp>
#include <realtime_tools/realtime_publisher.hpp>

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
  bool configure(const mjModel * model, const std::string & object_body,
                 const std::string & left_geom, const std::string & right_geom,
                 const std::vector<std::string> & other_geoms, std::size_t max_contacts);
  msg::SimulationEvidence build(const mjModel * model, const mjData * data, bool paused,
                                EvidenceState & state, uint64_t reset_generation = 0) const;

private:
  bool object_geom(int geom_id) const;
  int object_body_id_{-1};
  int left_geom_id_{-1};
  int right_geom_id_{-1};
  std::vector<int> object_geom_ids_;
  std::vector<int> other_geom_ids_;
  std::vector<std::string> body_names_;
  std::vector<std::string> geom_names_;
  std::string object_body_name_;
  std::size_t max_contacts_{128};
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
  void try_publish_snapshot(const mjModel * model, const mjData * data, bool paused,
                            uint64_t reset_generation);
  rclcpp::Node::SharedPtr node_;
  rclcpp::Publisher<Evidence>::SharedPtr publisher_;
  std::unique_ptr<realtime_tools::RealtimePublisher<Evidence>> realtime_publisher_;
  EvidenceBuilder builder_;
  EvidenceState state_;
  double publish_period_s_{0.01};
  double last_publish_time_s_{0.0};
  bool published_{false};
  std::atomic<uint64_t> reset_generation_{0};
  std::atomic<bool> authoritative_paused_{false};
};
}  // namespace so101_mujoco_support
#endif

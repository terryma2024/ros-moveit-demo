#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

#include <algorithm>
#include <cmath>
#include <exception>
#include <limits>
#include <string>
#include <utility>
#include <vector>

#include <pluginlib/class_list_macros.hpp>

namespace so101_mujoco_support
{
namespace
{
template <typename T>
T parameter(const rclcpp::Node::SharedPtr & node, const std::string & name, const T & fallback)
{
  return node->has_parameter(name) ? node->get_parameter(name).get_value<T>()
                                   : node->declare_parameter<T>(name, fallback);
}

std::string name(const mjModel * model, mjtObj type, int id)
{
  const char * value = mj_id2name(model, type, id);
  return value == nullptr ? "" : value;
}

bool finite_contact(const mjContact & contact)
{
  return std::isfinite(contact.pos[0]) && std::isfinite(contact.pos[1]) &&
         std::isfinite(contact.pos[2]) && std::isfinite(contact.frame[0]) &&
         std::isfinite(contact.frame[1]) && std::isfinite(contact.frame[2]) &&
         std::isfinite(contact.dist);
}
}  // namespace

bool EvidenceBuilder::configure(const mjModel * model, const std::string & object_body,
                                const std::string & left_geom, const std::string & right_geom,
                                const std::vector<std::string> & other_geoms,
                                std::size_t max_contacts)
{
  if (model == nullptr || object_body.empty() || left_geom.empty() || right_geom.empty()) {
    return false;
  }
  object_body_id_ = mj_name2id(model, mjOBJ_BODY, object_body.c_str());
  left_geom_id_ = mj_name2id(model, mjOBJ_GEOM, left_geom.c_str());
  right_geom_id_ = mj_name2id(model, mjOBJ_GEOM, right_geom.c_str());
  if (object_body_id_ < 0 || left_geom_id_ < 0 || right_geom_id_ < 0) {
    return false;
  }
  object_body_name_ = object_body;
  max_contacts_ = max_contacts;
  object_geom_ids_.clear();
  other_geom_ids_.clear();
  body_names_.clear();
  geom_names_.clear();
  for (int id = 0; id < model->nbody; ++id) {
    body_names_.push_back(name(model, mjOBJ_BODY, id));
  }
  for (int id = 0; id < model->ngeom; ++id) {
    geom_names_.push_back(name(model, mjOBJ_GEOM, id));
    int body = model->geom_bodyid[id];
    while (body != 0 && body != object_body_id_) {
      body = model->body_parentid[body];
    }
    if (body == object_body_id_) {
      object_geom_ids_.push_back(id);
    }
  }
  for (const auto & geom : other_geoms) {
    const int id = mj_name2id(model, mjOBJ_GEOM, geom.c_str());
    if (id < 0) {
      return false;
    }
    other_geom_ids_.push_back(id);
  }
  return !object_geom_ids_.empty();
}

bool EvidenceBuilder::object_geom(int geom_id) const
{
  return std::find(object_geom_ids_.begin(), object_geom_ids_.end(), geom_id) !=
         object_geom_ids_.end();
}

msg::SimulationEvidence EvidenceBuilder::build(const mjModel * model, mjData * data, bool paused,
                                               EvidenceState & state,
                                               uint64_t reset_generation) const
{
  msg::SimulationEvidence output;
  if (model == nullptr || data == nullptr || object_body_id_ < 0 || !std::isfinite(data->time)) {
    output.truncated = true;
    return output;
  }
  if (reset_generation != state.consumed_reset_generation) {
    state.consumed_reset_generation = reset_generation;
    state.reset_epoch = reset_generation;
    state.simulation_step = 0;
  } else if (state.initialized && data->time > state.previous_time) {
    ++state.simulation_step;
  }
  output.publisher_sequence = state.publisher_sequence++;
  output.simulation_step = state.simulation_step;
  output.reset_epoch = state.reset_epoch;
  output.simulation_session_id = state.simulation_session_id;
  output.paused = paused;
  state.previous_time = data->time;
  state.initialized = true;
  const auto nanoseconds = static_cast<int64_t>(std::llround(data->time * 1.0e9));
  output.header.stamp.sec = static_cast<int32_t>(nanoseconds / 1000000000LL);
  output.header.stamp.nanosec = static_cast<uint32_t>(nanoseconds % 1000000000LL);
  output.header.frame_id = "world";
  output.object_body_id = object_body_id_;
  output.object_body = object_body_name_;
  const mjtNum * position = data->xpos + 3 * object_body_id_;
  const mjtNum * quaternion = data->xquat + 4 * object_body_id_;
  output.object_pose_world.position.x = position[0];
  output.object_pose_world.position.y = position[1];
  output.object_pose_world.position.z = position[2];
  output.object_pose_world.orientation.x = quaternion[1];
  output.object_pose_world.orientation.y = quaternion[2];
  output.object_pose_world.orientation.z = quaternion[3];
  output.object_pose_world.orientation.w = quaternion[0];
  mjtNum velocity[6]{};
  mj_objectVelocity(model, data, mjOBJ_BODY, object_body_id_, velocity, 0);
  output.object_twist_world.angular.x = velocity[0];
  output.object_twist_world.angular.y = velocity[1];
  output.object_twist_world.angular.z = velocity[2];
  output.object_twist_world.linear.x = velocity[3];
  output.object_twist_world.linear.y = velocity[4];
  output.object_twist_world.linear.z = velocity[5];
  output.minimum_signed_distance_m = std::numeric_limits<double>::infinity();
  std::size_t count = 0;
  for (int index = 0; index < data->ncon; ++index) {
    const auto & contact = data->contact[index];
    const bool first_object = object_geom(contact.geom1);
    const bool second_object = object_geom(contact.geom2);
    if (first_object == second_object || !finite_contact(contact)) {
      continue;
    }
    const int object_id = first_object ? contact.geom1 : contact.geom2;
    const int other_id = first_object ? contact.geom2 : contact.geom1;
    const bool left = other_id == left_geom_id_;
    const bool right = other_id == right_geom_id_;
    const bool other =
      std::find(other_geom_ids_.begin(), other_geom_ids_.end(), other_id) != other_geom_ids_.end();
    if (!left && !right && !other) {
      continue;
    }
    if (count++ >= max_contacts_) {
      output.truncated = true;
      continue;
    }
    mjtNum wrench[6]{};
    mj_contactForce(model, data, index, wrench);
    if (!std::isfinite(wrench[0])) {
      continue;
    }
    msg::ContactSample sample;
    sample.geom1_id = object_id;
    sample.body1_id = model->geom_bodyid[object_id];
    sample.geom1 = geom_names_[object_id];
    sample.body1 = body_names_[sample.body1_id];
    sample.geom2_id = other_id;
    sample.body2_id = model->geom_bodyid[other_id];
    sample.geom2 = geom_names_[other_id];
    sample.body2 = body_names_[sample.body2_id];
    sample.position_world.x = contact.pos[0];
    sample.position_world.y = contact.pos[1];
    sample.position_world.z = contact.pos[2];
    const double direction = first_object ? 1.0 : -1.0;
    sample.normal_world.x = direction * contact.frame[0];
    sample.normal_world.y = direction * contact.frame[1];
    sample.normal_world.z = direction * contact.frame[2];
    sample.signed_distance_m = contact.dist;
    sample.normal_force_n = std::max(0.0, static_cast<double>(wrench[0]));
    output.has_contact = true;
    output.minimum_signed_distance_m =
      std::min(output.minimum_signed_distance_m, sample.signed_distance_m);
    output.maximum_normal_force_n = std::max(output.maximum_normal_force_n, sample.normal_force_n);
    if (left)
      output.left_fingertip_contacts.push_back(sample);
    else if (right)
      output.right_fingertip_contacts.push_back(sample);
    else
      output.other_object_contacts.push_back(sample);
  }
  if (!output.has_contact) {
    output.minimum_signed_distance_m = 0.0;
  }
  return output;
}

bool SimulationEvidencePlugin::init(rclcpp::Node::SharedPtr node, const mjModel * model,
                                    mjData * data)
{
  cleanup();
  if (!node || model == nullptr || data == nullptr)
    return false;
  try {
    const auto object = parameter<std::string>(node, "object_body", "task_object");
    const auto left = parameter<std::string>(node, "left_fingertip_geom", "left_fingertip");
    const auto right = parameter<std::string>(node, "right_fingertip_geom", "right_fingertip");
    const auto other = parameter<std::vector<std::string>>(node, "other_contact_geoms", {});
    const auto max_contacts = parameter<int64_t>(node, "max_contacts", 128);
    const auto rate = parameter<double>(node, "publish_rate", 100.0);
    state_.simulation_session_id =
      parameter<std::string>(node, "simulation_session_id", "unconfigured-session");
    const auto topic = parameter<std::string>(node, "topic", "/so101/simulation/evidence");
    if (max_contacts < 0 || !std::isfinite(rate) || rate <= 0.0 ||
        state_.simulation_session_id.empty() ||
        !builder_.configure(model, object, left, right, other,
                            static_cast<std::size_t>(max_contacts)))
      return false;
    node_ = std::move(node);
    publisher_ = node_->create_publisher<Evidence>(topic, rclcpp::SensorDataQoS());
    realtime_publisher_ = std::make_unique<realtime_tools::RealtimePublisher<Evidence>>(publisher_);
    publish_period_s_ = 1.0 / rate;
    last_publish_time_s_ = data->time;
    return true;
  } catch (const std::exception &) {
    cleanup();
    return false;
  }
}

void SimulationEvidencePlugin::update(const mjModel * model, mjData * data)
{
  if (!realtime_publisher_ || model == nullptr || data == nullptr || !std::isfinite(data->time))
    return;
  const bool paused = published_ && data->time == last_publish_time_s_;
  if (!paused && published_ && data->time > last_publish_time_s_ &&
      data->time - last_publish_time_s_ < publish_period_s_)
    return;
  if (!realtime_publisher_->trylock())
    return;
  try {
    realtime_publisher_->msg_ =
      builder_.build(model, data, paused, state_, reset_generation_.load(std::memory_order_acquire));
    realtime_publisher_->unlockAndPublish();
    last_publish_time_s_ = data->time;
    published_ = true;
  } catch (...) {
    realtime_publisher_->unlock();
  }
}

void SimulationEvidencePlugin::on_reset()
{
  reset_generation_.fetch_add(1, std::memory_order_release);
}

void SimulationEvidencePlugin::cleanup()
{
  realtime_publisher_.reset();
  publisher_.reset();
  node_.reset();
  state_ = EvidenceState{};
  publish_period_s_ = 0.01;
  last_publish_time_s_ = 0.0;
  published_ = false;
  reset_generation_.store(0, std::memory_order_release);
}
}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(so101_mujoco_support::SimulationEvidencePlugin,
                       mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase)

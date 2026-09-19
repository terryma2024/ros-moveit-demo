// Copyright 2026 SO-101 maintainers

#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

#include <algorithm>
#include <cmath>
#include <exception>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <pluginlib/class_list_macros.hpp>
#include <rcutils/sha256.h>

namespace so101_mujoco_support
{
namespace
{
template<typename T>
T parameter(const rclcpp::Node::SharedPtr & node, const std::string & name, const T & fallback)
{
  return node->has_parameter(name) ? node->get_parameter(name).get_value<T>() :
         node->declare_parameter<T>(name, fallback);
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

bool SceneStateBuilder::configure(const mjModel * model)
{
  model_ = nullptr;
  model_sha256_.clear();
  if (!model || mj_version() != 340) {return false;}
  const auto size = mj_sizeModel(model);
  if (size <= 0) {return false;}
  std::vector<uint8_t> bytes(static_cast<std::size_t>(size));
  mj_saveModel(model, nullptr, bytes.data(), size);
  rcutils_sha256_ctx_t context;
  rcutils_sha256_init(&context);
  rcutils_sha256_update(&context, bytes.data(), bytes.size());
  uint8_t digest[RCUTILS_SHA256_BLOCK_SIZE];
  rcutils_sha256_final(&context, digest);
  constexpr char hex[] = "0123456789abcdef";
  for (const auto value : digest) {
    model_sha256_ += hex[value >> 4];
    model_sha256_ += hex[value & 15];
  }
  model_ = model;
  return true;
}

msg::SceneStateEvidence SceneStateBuilder::build(
  const mjModel * model, const mjData * data, const std::string & session,
  uint64_t epoch, uint64_t step, bool paused) const
{
  if (!model_ || model != model_ || !data || session.empty() ||
    !std::isfinite(data->time) || data->time < 0.0)
  {
    throw std::invalid_argument("invalid full-scene snapshot");
  }
  msg::SceneStateEvidence output;
  output.simulation_session_id = session;
  output.reset_epoch = epoch;
  output.simulation_step = step;
  output.paused = paused;
  output.model_sha256 = model_sha256_;
  const auto nanoseconds = static_cast<int64_t>(std::llround(data->time * 1.0e9));
  output.header.stamp.sec = static_cast<int32_t>(nanoseconds / 1000000000LL);
  output.header.stamp.nanosec = static_cast<uint32_t>(nanoseconds % 1000000000LL);
  output.header.frame_id = "world";
  output.qpos.assign(data->qpos, data->qpos + model->nq);
  output.qvel.assign(data->qvel, data->qvel + model->nv);
  if (!std::all_of(output.qpos.begin(), output.qpos.end(), [](double v) {return std::isfinite(v);}) ||
    !std::all_of(output.qvel.begin(), output.qvel.end(), [](double v) {return std::isfinite(v);}))
  {
    throw std::invalid_argument("non-finite full-scene state");
  }
  return output;
}

msg::ScalarJointEvidence make_scalar_joint_evidence(
  const mjModel * model, const mjData * data, const std::vector<std::string> & joint_names,
  const std::string & session, uint64_t reset_epoch, uint64_t simulation_step, bool paused)
{
  if (!model || !data || !std::isfinite(data->time) || data->time < 0.0 || session.empty() ||
    joint_names.empty())
  {
    throw std::invalid_argument("invalid scalar joint snapshot");
  }
  msg::ScalarJointEvidence output;
  output.simulation_session_id = session;
  output.reset_epoch = reset_epoch;
  output.simulation_step = simulation_step;
  output.paused = paused;
  const auto nanoseconds = static_cast<int64_t>(std::llround(data->time * 1.0e9));
  output.header.stamp.sec = static_cast<int32_t>(nanoseconds / 1000000000LL);
  output.header.stamp.nanosec = static_cast<uint32_t>(nanoseconds % 1000000000LL);
  output.header.frame_id = "world";
  for (const auto & joint : joint_names) {
    const int id = mj_name2id(model, mjOBJ_JOINT, joint.c_str());
    if (id < 0 || model->jnt_type[id] != mjJNT_HINGE ||
      std::find(output.joint_names.begin(), output.joint_names.end(), joint) !=
      output.joint_names.end())
    {
      throw std::invalid_argument("unknown, repeated or non-hinge audit joint");
    }
    const auto position = data->qpos[model->jnt_qposadr[id]];
    const auto velocity = data->qvel[model->jnt_dofadr[id]];
    if (!std::isfinite(position) || !std::isfinite(velocity)) {
      throw std::invalid_argument("non-finite scalar joint state");
    }
    output.joint_names.push_back(joint);
    output.positions_rad.push_back(position);
    output.velocities_rad_s.push_back(velocity);
  }
  return output;
}

bool EvidenceBuilder::configure(
  const mjModel * model, const std::string & object_body,
  const std::string & left_geom, const std::string & right_geom,
  const std::vector<std::string> & other_geoms,
  std::size_t max_contacts)
{
  return configure(model, object_body, std::vector<std::string>{left_geom},
                   std::vector<std::string>{right_geom}, other_geoms, max_contacts);
}

bool EvidenceBuilder::configure(
  const mjModel * model, const std::string & object_body,
  const std::vector<std::string> & left_geoms,
  const std::vector<std::string> & right_geoms,
  const std::vector<std::string> & other_geoms,
  std::size_t max_contacts)
{
  if (model == nullptr || object_body.empty() || left_geoms.empty() || right_geoms.empty()) {
    return false;
  }
  object_body_id_ = mj_name2id(model, mjOBJ_BODY, object_body.c_str());
  if (object_body_id_ < 0) {
    return false;
  }
  object_body_name_ = object_body;
  max_contacts_ = max_contacts;
  object_geom_ids_.clear();
  left_geom_ids_.clear();
  right_geom_ids_.clear();
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
  const auto resolve = [model](const std::vector<std::string> & names, std::vector<int> & ids) {
      for (const auto & geom : names) {
        const int id = mj_name2id(model, mjOBJ_GEOM, geom.c_str());
        if (id < 0) {
          return false;
        }
        ids.push_back(id);
      }
      return true;
    };
  if (!resolve(left_geoms, left_geom_ids_) || !resolve(right_geoms, right_geom_ids_)) {
    return false;
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

msg::SimulationEvidence EvidenceBuilder::build(
  const mjModel * model, const mjData * data,
  bool paused, EvidenceState & state,
  uint64_t reset_generation,
  bool advance_physics_step) const
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
  } else if (advance_physics_step && state.initialized && data->time > state.previous_time) {
    const double timestep = model->opt.timestep;
    const double elapsed = data->time - state.previous_time;
    const auto advanced =
      std::max<uint64_t>(1, static_cast<uint64_t>(std::llround(elapsed / timestep)));
    state.simulation_step += advanced;
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
    const bool left =
      std::find(left_geom_ids_.begin(), left_geom_ids_.end(), other_id) != left_geom_ids_.end();
    const bool right =
      std::find(right_geom_ids_.begin(), right_geom_ids_.end(), other_id) != right_geom_ids_.end();
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
    if (contact.efc_address >= 0) {
      if (data->efc_force == nullptr || contact.efc_address >= data->nefc) {
        output.truncated = true;
        continue;
      }
      mj_contactForce(model, data, index, wrench);
    }
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
    if (left) {
      output.left_fingertip_contacts.push_back(sample);
    } else if (right) {
      output.right_fingertip_contacts.push_back(sample);
    } else {
      output.other_object_contacts.push_back(sample);
    }
  }
  if (!output.has_contact) {
    output.minimum_signed_distance_m = 0.0;
  }
  return output;
}

msg::PhysicsStepEvidence make_physics_step_evidence(
  const msg::SimulationEvidence & snapshot, double simulation_time_s,
  double static_shadow_force_n, double diagnostic_hard_stop_force_n)
{
  msg::PhysicsStepEvidence output;
  output.simulation_session_id = snapshot.simulation_session_id;
  output.reset_epoch = snapshot.reset_epoch;
  output.physics_step = snapshot.simulation_step;
  output.simulation_time_s = simulation_time_s;
  output.object_pose_world = snapshot.object_pose_world;
  output.object_twist_world = snapshot.object_twist_world;
  output.has_contact = snapshot.has_contact;
  output.truncated = snapshot.truncated;
  output.maximum_normal_force_n = snapshot.maximum_normal_force_n;
  output.global_max_single_contact_force_n = snapshot.maximum_normal_force_n;
  output.left_fingertip_contacts = snapshot.left_fingertip_contacts;
  output.right_fingertip_contacts = snapshot.right_fingertip_contacts;
  output.other_object_contacts = snapshot.other_object_contacts;
  const auto accumulate = [&output](const auto & contacts, double * total_force,
    double * maximum_force, double * compression) {
      for (const auto & contact : contacts) {
        *total_force += contact.normal_force_n;
        *maximum_force = std::max(*maximum_force, contact.normal_force_n);
        *compression = std::max(*compression, std::max(0.0, -contact.signed_distance_m));
        output.net_contact_force_world_n.x += contact.normal_world.x * contact.normal_force_n;
        output.net_contact_force_world_n.y += contact.normal_world.y * contact.normal_force_n;
        output.net_contact_force_world_n.z += contact.normal_world.z * contact.normal_force_n;
      }
    };
  accumulate(output.left_fingertip_contacts, &output.left_fingertip_total_normal_force_n,
             &output.fingertip_max_single_contact_force_n,
             &output.left_fingertip_compression_m);
  accumulate(output.right_fingertip_contacts, &output.right_fingertip_total_normal_force_n,
             &output.fingertip_max_single_contact_force_n,
             &output.right_fingertip_compression_m);
  double ignored_total = 0.0;
  double ignored_maximum = 0.0;
  double ignored_compression = 0.0;
  accumulate(output.other_object_contacts, &ignored_total, &ignored_maximum, &ignored_compression);
  output.static_shadow_crossed = output.maximum_normal_force_n > static_shadow_force_n;
  output.diagnostic_hazard_breached =
    output.global_max_single_contact_force_n >= diagnostic_hard_stop_force_n;
  return output;
}

msg::PhysicsCancellationAck make_cancellation_ack(
  const msg::PhysicsCancellationRequest & request, uint64_t reset_epoch,
  uint64_t observed_physics_step, double observed_simulation_time_s)
{
  msg::PhysicsCancellationAck output;
  output.simulation_session_id = request.simulation_session_id;
  output.reset_epoch = reset_epoch;
  output.hazard_physics_step = request.hazard_physics_step;
  output.request_sequence = request.request_sequence;
  output.observed_physics_step = observed_physics_step;
  output.observed_simulation_time_s = observed_simulation_time_s;
  return output;
}

msg::PhysicsStepEvidence EvidenceBuilder::build_step(
  const mjModel * model, const mjData * data, bool paused, EvidenceState & state,
  uint64_t reset_generation, double static_shadow_force_n,
  double diagnostic_hard_stop_force_n) const
{
  const auto snapshot = build(model, data, paused, state, reset_generation, true);
  return make_physics_step_evidence(snapshot, data == nullptr ? 0.0 : data->time,
                                    static_shadow_force_n, diagnostic_hard_stop_force_n);
}

PhysicsStepEvidenceBuffer::PhysicsStepEvidenceBuffer(
  std::size_t capacity, std::size_t flush_step_count, double diagnostic_hard_stop_force_n)
: capacity_(capacity),
  flush_step_count_(flush_step_count),
  diagnostic_hard_stop_force_n_(diagnostic_hard_stop_force_n)
{
  if (capacity_ == 0 || flush_step_count_ == 0 || flush_step_count_ > capacity_ ||
    !std::isfinite(diagnostic_hard_stop_force_n_) || diagnostic_hard_stop_force_n_ <= 0.0)
  {
    throw std::invalid_argument("invalid physics-step buffer configuration");
  }
}

bool PhysicsStepEvidenceBuffer::append(const msg::PhysicsStepEvidence & sample)
{
  if (last_observed_.has_value()) {
    const auto & previous = *last_observed_;
    if (sample.simulation_session_id != previous.simulation_session_id ||
      sample.reset_epoch != previous.reset_epoch ||
      sample.physics_step != previous.physics_step + 1 ||
      !std::isfinite(sample.simulation_time_s) ||
      sample.simulation_time_s <= previous.simulation_time_s)
    {
      evidence_loss_ = true;
      return false;
    }
  }
  if (samples_.size() >= capacity_) {
    evidence_loss_ = true;
    return false;
  }
  samples_.push_back(sample);
  last_observed_ = sample;
  if (!hazard_latch_.has_value() &&
    sample.global_max_single_contact_force_n >= diagnostic_hard_stop_force_n_)
  {
    msg::PhysicsHazardLatch hazard;
    hazard.simulation_session_id = sample.simulation_session_id;
    hazard.reset_epoch = sample.reset_epoch;
    hazard.physics_step = sample.physics_step;
    hazard.simulation_time_s = sample.simulation_time_s;
    hazard.force_n = sample.global_max_single_contact_force_n;
    hazard.threshold_n = diagnostic_hard_stop_force_n_;
    hazard.evidence_loss = evidence_loss_;
    hazard_latch_ = hazard;
  }
  return true;
}

bool PhysicsStepEvidenceBuffer::ready() const
{
  return samples_.size() >= flush_step_count_ || evidence_loss_ || hazard_latch_.has_value();
}

msg::PhysicsStepEvidenceChunk PhysicsStepEvidenceBuffer::prepare_chunk() const
{
  msg::PhysicsStepEvidenceChunk chunk;
  chunk.chunk_sequence = chunk_sequence_;
  chunk.failed_publish_attempts = failed_publish_attempts_;
  chunk.evidence_loss = evidence_loss_;
  if (samples_.empty()) {
    if (last_observed_.has_value()) {
      chunk.simulation_session_id = last_observed_->simulation_session_id;
      chunk.reset_epoch = last_observed_->reset_epoch;
    }
    return chunk;
  }
  chunk.simulation_session_id = samples_.front().simulation_session_id;
  chunk.reset_epoch = samples_.front().reset_epoch;
  chunk.first_physics_step = samples_.front().physics_step;
  chunk.last_physics_step = samples_.back().physics_step;
  chunk.first_simulation_time_s = samples_.front().simulation_time_s;
  chunk.last_simulation_time_s = samples_.back().simulation_time_s;
  chunk.samples.assign(samples_.begin(), samples_.end());
  return chunk;
}

void PhysicsStepEvidenceBuffer::mark_publish_failed()
{
  ++failed_publish_attempts_;
}

void PhysicsStepEvidenceBuffer::mark_published()
{
  samples_.clear();
  ++chunk_sequence_;
  failed_publish_attempts_ = 0;
}

std::optional<msg::PhysicsHazardLatch> PhysicsStepEvidenceBuffer::hazard_latch() const
{
  return hazard_latch_;
}

bool PhysicsStepEvidenceBuffer::evidence_loss_latched() const
{
  return evidence_loss_;
}

void PhysicsStepEvidenceBuffer::reset()
{
  samples_.clear();
  chunk_sequence_ = 0;
  failed_publish_attempts_ = 0;
  evidence_loss_ = false;
  last_observed_.reset();
  hazard_latch_.reset();
}

bool RobotContactBuilder::configure(
  const mjModel * model, const std::vector<std::string> & roots, std::size_t max_contacts)
{
  if (!model || roots.empty() || max_contacts == 0) {return false;}
  std::vector<int> root_ids;
  for (const auto & root : roots) {
    const int id = mj_name2id(model, mjOBJ_BODY, root.c_str());
    if (id <= 0) {return false;}
    root_ids.push_back(id);
  }
  protected_geoms_.assign(model->ngeom, false);
  names_.clear();
  max_contacts_ = max_contacts;
  for (int geom = 0; geom < model->ngeom; ++geom) {
    names_.push_back(name(model, mjOBJ_GEOM, geom));
    int body = model->geom_bodyid[geom];
    while (body != 0) {
      if (std::find(root_ids.begin(), root_ids.end(), body) != root_ids.end()) {
        protected_geoms_[geom] = true;
        if (names_.back().empty()) {return false;}
        break;
      }
      body = model->body_parentid[body];
    }
  }
  return std::find(protected_geoms_.begin(), protected_geoms_.end(), true) != protected_geoms_.end();
}

msg::RobotContactEvidence RobotContactBuilder::build(
  const mjModel * model, const mjData * data, const std::string & session,
  uint64_t epoch, uint64_t step) const
{
  msg::RobotContactEvidence output;
  output.simulation_session_id = session;
  output.reset_epoch = epoch;
  output.physics_step = step;
  if (!model || !data || protected_geoms_.size() != static_cast<std::size_t>(model->ngeom) ||
    !std::isfinite(data->time) || session.empty())
  {
    output.truncated = output.evidence_loss = true;
    return output;
  }
  output.simulation_time_s = data->time;
  for (int index = 0; index < data->ncon; ++index) {
    const auto & contact = data->contact[index];
    const int a = contact.geom[0];
    const int b = contact.geom[1];
    if (a < 0 || b < 0 || a >= model->ngeom || b >= model->ngeom) {
      output.truncated = output.evidence_loss = true;
      continue;
    }
    if (!protected_geoms_[a] && !protected_geoms_[b]) {continue;}
    if (output.geom_a.size() >= max_contacts_ || !finite_contact(contact) ||
      names_[a].empty() || names_[b].empty())
    {
      output.truncated = output.evidence_loss = true;
      continue;
    }
    mjtNum wrench[6]{};
    mj_contactForce(model, data, index, wrench);
    if (!std::isfinite(wrench[0])) {
      output.truncated = output.evidence_loss = true;
      continue;
    }
    output.geom_a.push_back(names_[a]);
    output.geom_b.push_back(names_[b]);
    output.signed_distance_m.push_back(contact.dist);
    output.normal_force_n.push_back(std::max(0.0, wrench[0]));
  }
  return output;
}

RobotContactBuffer::RobotContactBuffer(std::size_t capacity) : capacity_(capacity)
{
  if (capacity == 0) {throw std::invalid_argument("invalid robot contact capacity");}
}

bool RobotContactBuffer::append(const msg::RobotContactEvidence & sample)
{
  if (!epoch_) {epoch_ = sample.reset_epoch;}
  const bool valid = sample.reset_epoch == *epoch_ && !sample.simulation_session_id.empty() &&
    std::isfinite(sample.simulation_time_s) && sample.simulation_time_s >= 0.0 &&
    (!last_ || (sample.simulation_session_id == last_->simulation_session_id &&
    sample.physics_step == last_->physics_step + 1 && sample.simulation_time_s > last_->simulation_time_s));
  if (!valid || sample.truncated || sample.evidence_loss) {loss_ = true;}
  if (!valid || samples_.size() >= capacity_) {
    loss_ = true;
    last_ = sample;
    return false;
  }
  samples_.push_back(sample);
  last_ = sample;
  return true;
}

bool RobotContactBuffer::empty() const {return samples_.empty();}

msg::RobotContactEvidence RobotContactBuffer::front() const
{
  if (samples_.empty()) {throw std::logic_error("empty robot contact buffer");}
  auto sample = samples_.front();
  sample.evidence_loss = sample.evidence_loss || loss_;
  return sample;
}

void RobotContactBuffer::pop_published()
{
  if (samples_.empty()) {throw std::logic_error("empty robot contact buffer");}
  samples_.pop_front();
}

void RobotContactBuffer::reset(uint64_t epoch)
{
  samples_.clear();last_.reset();epoch_ = epoch;loss_ = false;
}

bool SimulationEvidencePlugin::init(
  rclcpp::Node::SharedPtr node, const mjModel * model,
  mjData * data)
{
  cleanup();
  if (!node || model == nullptr || data == nullptr) {
    return false;
  }
  try {
    const auto object = parameter<std::string>(node, "object_body", "task_object");
    auto left = parameter<std::vector<std::string>>(node, "left_fingertip_geoms", {});
    auto right = parameter<std::vector<std::string>>(node, "right_fingertip_geoms", {});
    if (left.empty()) {
      left = {parameter<std::string>(node, "left_fingertip_geom", "left_fingertip")};
    }
    if (right.empty()) {
      right = {parameter<std::string>(node, "right_fingertip_geom", "right_fingertip")};
    }
    const auto other = parameter<std::vector<std::string>>(node, "other_contact_geoms", {});
    const auto max_contacts = parameter<int64_t>(node, "max_contacts", 128);
    const auto rate = parameter<double>(node, "publish_rate", 100.0);
    const auto physics_step_buffer_capacity =
      parameter<int64_t>(node, "physics_step_buffer_capacity", 5000);
    const auto physics_step_chunk_size = parameter<int64_t>(node, "physics_step_chunk_size", 5);
    static_shadow_force_n_ =
      parameter<double>(node, "static_shadow_force_n", 1.1579004532160448);
    diagnostic_hard_stop_force_n_ =
      parameter<double>(node, "diagnostic_hard_stop_force_n", 11.60);
    state_.simulation_session_id =
      parameter<std::string>(node, "simulation_session_id", "unconfigured-session");
    physics_state_.simulation_session_id = state_.simulation_session_id;
    physics_state_.previous_time = data->time;
    physics_state_.initialized = true;
    const auto topic = parameter<std::string>(node, "topic", "/so101/simulation/evidence");
    const auto chunk_topic = parameter<std::string>(
      node, "physics_step_topic", "/so101/simulation/physics_step_chunks");
    const auto hazard_topic =
      parameter<std::string>(node, "physics_hazard_topic", "/so101/simulation/physics_hazard");
    const auto cancellation_request_topic = parameter<std::string>(
      node, "physics_cancellation_request_topic",
      "/so101/simulation/physics_cancellation_request");
    const auto cancellation_ack_topic = parameter<std::string>(
      node, "physics_cancellation_ack_topic", "/so101/simulation/physics_cancellation_ack");
    if (max_contacts < 0 || physics_step_buffer_capacity <= 0 || physics_step_chunk_size <= 0 ||
      physics_step_chunk_size > physics_step_buffer_capacity || !std::isfinite(rate) ||
      rate <= 0.0 || !std::isfinite(model->opt.timestep) || model->opt.timestep <= 0.0 ||
      !std::isfinite(static_shadow_force_n_) || static_shadow_force_n_ <= 0.0 ||
      !std::isfinite(diagnostic_hard_stop_force_n_) ||
      diagnostic_hard_stop_force_n_ <= static_shadow_force_n_ || topic.empty() ||
      chunk_topic.empty() || hazard_topic.empty() || cancellation_request_topic.empty() ||
      cancellation_ack_topic.empty() ||
      state_.simulation_session_id.empty() ||
      !builder_.configure(model, object, left, right, other,
        static_cast<std::size_t>(max_contacts)))
    {
      return false;
    }
    node_ = std::move(node);
    const auto evidence_qos =
      rclcpp::QoS(rclcpp::KeepLast(1)).reliable().transient_local();
    scalar_joint_names_ = parameter<std::vector<std::string>>(node_, "scalar_joint_audit_names", {});
    if (!scalar_joint_names_.empty()) {
      make_scalar_joint_evidence(model, data, scalar_joint_names_,
        state_.simulation_session_id, 0, 0, false);
      scalar_joint_publisher_ = node_->create_publisher<msg::ScalarJointEvidence>(
        "/so101/simulation/joints", evidence_qos);
    }
    const auto robot_roots = parameter<std::vector<std::string>>(node_, "robot_contact_roots", {});
    if (!robot_roots.empty()) {
      const auto capacity = parameter<int64_t>(node_, "robot_contact_buffer_capacity", 5000);
      if (capacity <= 0 || !robot_builder_.configure(model, robot_roots, max_contacts)) {return false;}
      robot_buffer_ = std::make_unique<RobotContactBuffer>(static_cast<std::size_t>(capacity));
      robot_buffer_->reset(0);
      robot_publisher_ = node_->create_publisher<msg::RobotContactEvidence>(
        "/so101/simulation/robot_contacts", rclcpp::QoS(rclcpp::KeepLast(10000)).reliable());
      realtime_robot_publisher_ = std::make_unique<realtime_tools::RealtimePublisher<msg::RobotContactEvidence>>(robot_publisher_);
      if (!scene_builder_.configure(model)) {return false;}
      scene_publisher_ = node_->create_publisher<msg::SceneStateEvidence>(
        "/so101/simulation/scene_state", evidence_qos);
      realtime_scene_publisher_ = std::make_unique<realtime_tools::RealtimePublisher<msg::SceneStateEvidence>>(scene_publisher_);
    }
    publisher_ = node_->create_publisher<Evidence>(topic, evidence_qos);
    realtime_publisher_ = std::make_unique<realtime_tools::RealtimePublisher<Evidence>>(publisher_);
    const auto chunk_qos = rclcpp::QoS(rclcpp::KeepLast(100)).reliable();
    chunk_publisher_ = node_->create_publisher<EvidenceChunk>(chunk_topic, chunk_qos);
    realtime_chunk_publisher_ =
      std::make_unique<realtime_tools::RealtimePublisher<EvidenceChunk>>(chunk_publisher_);
    hazard_publisher_ = node_->create_publisher<msg::PhysicsHazardLatch>(
      hazard_topic, rclcpp::QoS(rclcpp::KeepLast(1)).reliable().transient_local());
    const auto cancellation_qos = rclcpp::QoS(rclcpp::KeepLast(5)).reliable();
    cancellation_ack_publisher_ =
      node_->create_publisher<msg::PhysicsCancellationAck>(cancellation_ack_topic,
        cancellation_qos);
    cancellation_request_subscription_ =
      node_->create_subscription<msg::PhysicsCancellationRequest>(
      cancellation_request_topic, cancellation_qos,
      [this](const msg::PhysicsCancellationRequest & request) {
        acknowledge_cancellation_request(request);
        });
    physics_step_buffer_ = std::make_unique<PhysicsStepEvidenceBuffer>(
      static_cast<std::size_t>(physics_step_buffer_capacity),
      static_cast<std::size_t>(physics_step_chunk_size), diagnostic_hard_stop_force_n_);
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
  if (!realtime_publisher_ || model == nullptr || data == nullptr || !std::isfinite(data->time)) {
    return;
  }
  const auto reset_generation = reset_generation_.load(std::memory_order_acquire);
  const bool reset_pending = reset_generation != state_.consumed_reset_generation;
  if (reset_pending) {
    return;
  }
  const bool paused = authoritative_paused_.load(std::memory_order_acquire);
  if (state_.initialized && data->time == state_.previous_time) {
    if (!published_) {
      try_publish_snapshot(model, data, paused, reset_generation, false);
    }
    return;
  }
  if (!published_ || data->time < last_publish_time_s_ ||
    data->time - last_publish_time_s_ >= publish_period_s_)
  {
    try_publish_snapshot(model, data, paused, reset_generation, true);
  }
}

void SimulationEvidencePlugin::on_physics_step(const mjModel * model, const mjData * data)
{
  if (!realtime_chunk_publisher_ || !physics_step_buffer_ || model == nullptr || data == nullptr ||
    !std::isfinite(data->time))
  {
    return;
  }
  const auto reset_generation = reset_generation_.load(std::memory_order_acquire);
  if (reset_generation != physics_state_.consumed_reset_generation) {
    return;
  }
  if (physics_state_.initialized && data->time == physics_state_.previous_time) {
    return;
  }
  const bool paused = authoritative_paused_.load(std::memory_order_acquire);
  const auto step = builder_.build_step(model, data, paused, physics_state_, reset_generation,
                                        static_shadow_force_n_, diagnostic_hard_stop_force_n_);
  current_reset_epoch_.store(step.reset_epoch, std::memory_order_release);
  current_physics_step_.store(step.physics_step, std::memory_order_release);
  current_simulation_time_s_.store(step.simulation_time_s, std::memory_order_release);
  physics_step_buffer_->append(step);
  if (robot_buffer_) {
    robot_buffer_->append(robot_builder_.build(model, data, step.simulation_session_id,
      step.reset_epoch, step.physics_step));
    try_publish_robot_contacts();
  }
  publish_hazard_if_needed();
  if (physics_step_buffer_->ready()) {
    try_publish_chunk();
  }
}

void SimulationEvidencePlugin::try_publish_snapshot(
  const mjModel * model, const mjData * data,
  bool paused, uint64_t reset_generation,
  bool advance_physics_step)
{
  if (!realtime_publisher_->trylock()) {
    return;
  }
  try {
    realtime_publisher_->msg_ =
      builder_.build(model, data, paused, state_, reset_generation, advance_physics_step);
    realtime_publisher_->unlockAndPublish();
    if (realtime_scene_publisher_ && realtime_scene_publisher_->trylock()) {
      try {
        realtime_scene_publisher_->msg_ = scene_builder_.build(model, data,
          state_.simulation_session_id, state_.reset_epoch, state_.simulation_step, paused);
        realtime_scene_publisher_->unlockAndPublish();
      } catch (...) {
        realtime_scene_publisher_->unlock();
      }
    }
    last_publish_time_s_ = data->time;
    published_ = true;
  } catch (...) {
    realtime_publisher_->unlock();
  }
}

void SimulationEvidencePlugin::try_publish_robot_contacts()
{
  if (!robot_buffer_ || !realtime_robot_publisher_) {return;}
  while (!robot_buffer_->empty()) {
    if (!realtime_robot_publisher_->trylock()) {return;}
    try {
      realtime_robot_publisher_->msg_ = robot_buffer_->front();
      realtime_robot_publisher_->unlockAndPublish();
      robot_buffer_->pop_published();
    } catch (...) {
      realtime_robot_publisher_->unlock();
      return;
    }
  }
}

void SimulationEvidencePlugin::try_publish_chunk()
{
  if (!physics_step_buffer_ || !realtime_chunk_publisher_) {
    return;
  }
  if (!realtime_chunk_publisher_->trylock()) {
    physics_step_buffer_->mark_publish_failed();
    return;
  }
  try {
    realtime_chunk_publisher_->msg_ = physics_step_buffer_->prepare_chunk();
    realtime_chunk_publisher_->unlockAndPublish();
    physics_step_buffer_->mark_published();
  } catch (...) {
    realtime_chunk_publisher_->unlock();
    physics_step_buffer_->mark_publish_failed();
  }
}

void SimulationEvidencePlugin::publish_hazard_if_needed()
{
  if (hazard_published_ || !physics_step_buffer_ || !hazard_publisher_) {
    return;
  }
  const auto hazard = physics_step_buffer_->hazard_latch();
  if (!hazard.has_value()) {
    return;
  }
  hazard_publisher_->publish(*hazard);
  hazard_published_ = true;
}

void SimulationEvidencePlugin::acknowledge_cancellation_request(
  const msg::PhysicsCancellationRequest & request)
{
  if (!cancellation_ack_publisher_ ||
    request.simulation_session_id != state_.simulation_session_id)
  {
    return;
  }
  const auto reset_epoch = current_reset_epoch_.load(std::memory_order_acquire);
  const auto physics_step = current_physics_step_.load(std::memory_order_acquire);
  if (request.reset_epoch != reset_epoch || request.hazard_physics_step > physics_step) {
    return;
  }
  cancellation_ack_publisher_->publish(make_cancellation_ack(
    request, reset_epoch, physics_step,
    current_simulation_time_s_.load(std::memory_order_acquire)));
}

void SimulationEvidencePlugin::on_reset()
{
  reset_generation_.fetch_add(1, std::memory_order_release);
}

void SimulationEvidencePlugin::on_pause(bool paused)
{
  authoritative_paused_.store(paused, std::memory_order_release);
}

void SimulationEvidencePlugin::on_state_snapshot(
  const mjModel * model, const mjData * data,
  bool paused)
{
  authoritative_paused_.store(paused, std::memory_order_release);
  if (!paused || model == nullptr || data == nullptr || !std::isfinite(data->time)) {
    return;
  }
  const auto generation = reset_generation_.load(std::memory_order_acquire);
  const bool reset_pending = generation != state_.consumed_reset_generation;
  try_publish_snapshot(model, data, true, generation, true);
  if (scalar_joint_publisher_) {
    scalar_joint_publisher_->publish(make_scalar_joint_evidence(
        model, data, scalar_joint_names_, state_.simulation_session_id, generation,
        reset_pending ? 0 : state_.simulation_step, true));
  }
  if (reset_pending && generation == state_.consumed_reset_generation) {
    physics_state_.publisher_sequence = 0;
    physics_state_.simulation_step = 0;
    physics_state_.reset_epoch = generation;
    physics_state_.consumed_reset_generation = generation;
    physics_state_.previous_time = data->time;
    physics_state_.initialized = true;
    if (physics_step_buffer_) {
      physics_step_buffer_->reset();
    }
    if (robot_buffer_) {robot_buffer_->reset(generation);}
    current_reset_epoch_.store(generation, std::memory_order_release);
    current_physics_step_.store(0, std::memory_order_release);
    current_simulation_time_s_.store(data->time, std::memory_order_release);
    hazard_published_ = false;
  }
}

void SimulationEvidencePlugin::cleanup()
{
  realtime_scene_publisher_.reset();
  scene_publisher_.reset();
  scene_builder_ = SceneStateBuilder{};
  robot_buffer_.reset();
  realtime_robot_publisher_.reset();
  robot_publisher_.reset();
  scalar_joint_publisher_.reset();
  scalar_joint_names_.clear();
  physics_step_buffer_.reset();
  cancellation_request_subscription_.reset();
  cancellation_ack_publisher_.reset();
  realtime_chunk_publisher_.reset();
  chunk_publisher_.reset();
  hazard_publisher_.reset();
  realtime_publisher_.reset();
  publisher_.reset();
  node_.reset();
  state_ = EvidenceState{};
  physics_state_ = EvidenceState{};
  publish_period_s_ = 0.01;
  last_publish_time_s_ = 0.0;
  static_shadow_force_n_ = 1.1579004532160448;
  diagnostic_hard_stop_force_n_ = 11.60;
  current_reset_epoch_.store(0, std::memory_order_release);
  current_physics_step_.store(0, std::memory_order_release);
  current_simulation_time_s_.store(0.0, std::memory_order_release);
  published_ = false;
  hazard_published_ = false;
  reset_generation_.store(0, std::memory_order_release);
  authoritative_paused_.store(false, std::memory_order_release);
}
}  // namespace so101_mujoco_support

PLUGINLIB_EXPORT_CLASS(so101_mujoco_support::SimulationEvidencePlugin,
                       mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase)

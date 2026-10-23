// Copyright 2026 SO-101 maintainers

#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <exception>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <rcutils/sha256.h>

#include "evidence_internal.hpp"

namespace so101_mujoco_support
{
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
  const int object_joint = model->body_jntadr[object_body_id_];
  if (model->body_jntnum[object_body_id_] == 1 && object_joint >= 0 &&
    model->jnt_type[object_joint] == mjJNT_FREE)
  {
    // mj_step updates qpos after xpos/xquat. The free body's world pose must
    // describe the same current configuration as SceneState and raw steps.
    const int address = model->jnt_qposadr[object_joint];
    position = data->qpos + address;
    quaternion = data->qpos + address + 3;
  }
  if (!std::all_of(position, position + 3, [](double value) {return std::isfinite(value);}) ||
    !std::all_of(quaternion, quaternion + 4, [](double value) {return std::isfinite(value);}))
  {
    output.truncated = true;
    return output;
  }
  output.object_pose_world.position.x = position[0];
  output.object_pose_world.position.y = position[1];
  output.object_pose_world.position.z = position[2];
  output.object_pose_world.orientation.x = quaternion[1];
  output.object_pose_world.orientation.y = quaternion[2];
  output.object_pose_world.orientation.z = quaternion[3];
  output.object_pose_world.orientation.w = quaternion[0];
  mjtNum velocity[6]{};
  if (model->body_jntnum[object_body_id_] == 1 && object_joint >= 0 &&
    model->jnt_type[object_joint] == mjJNT_FREE)
  {
    const mjtNum * joint_velocity = data->qvel + model->jnt_dofadr[object_joint];
    // Free-joint translation is world-oriented; angular velocity is local.
    // Preserve mjOBJ_BODY's inertial-origin semantics without reading cvel
    // from the previous integration configuration or modifying live mjData.
    mju_rotVecQuat(velocity, joint_velocity + 3, quaternion);
    mjtNum inertial_offset[3]{};
    mjtNum rotational_velocity[3]{};
    mju_rotVecQuat(inertial_offset, model->body_ipos + 3 * object_body_id_, quaternion);
    mju_cross(rotational_velocity, velocity, inertial_offset);
    mju_add3(velocity + 3, joint_velocity, rotational_velocity);
  } else {
    mj_objectVelocity(model, data, mjOBJ_BODY, object_body_id_, velocity, 0);
  }
  if (!std::all_of(velocity, velocity + 6, [](double value) {return std::isfinite(value);})) {
    output.truncated = true;
    return output;
  }
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
  output.total_normal_force_n = output.left_fingertip_total_normal_force_n +
    output.right_fingertip_total_normal_force_n + ignored_total;
  output.static_shadow_crossed = output.maximum_normal_force_n > static_shadow_force_n;
  output.diagnostic_hazard_breached =
    output.total_normal_force_n >= diagnostic_hard_stop_force_n;
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
  auto output = make_physics_step_evidence(snapshot, data == nullptr ? 0.0 : data->time,
                                          static_shadow_force_n, diagnostic_hard_stop_force_n);
  if (!model || !data) {
    throw std::invalid_argument("physics step has no MuJoCo state");
  }
  output.model_qpos.assign(data->qpos, data->qpos + model->nq);
  output.model_qvel.assign(data->qvel, data->qvel + model->nv);
  if (!std::all_of(output.model_qpos.begin(), output.model_qpos.end(),
    [](double value) {return std::isfinite(value);}) ||
    !std::all_of(output.model_qvel.begin(), output.model_qvel.end(),
    [](double value) {return std::isfinite(value);}))
  {
    throw std::invalid_argument("physics step has non-finite MuJoCo state");
  }
  const int joint = model->body_jntadr[object_body_id_];
  if (model->body_jntnum[object_body_id_] != 1 || joint < 0 ||
    model->jnt_type[joint] != mjJNT_FREE)
  {
    throw std::invalid_argument("physics-step object must have a free joint");
  }
  return output;
}
}  // namespace so101_mujoco_support

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
bool SceneStateBuilder::configure(const mjModel * model, const std::string & declared_sha256)
{
  model_ = nullptr;
  model_sha256_.clear();
  computed_model_sha256_.clear();
  if (!model || mj_version() != mjVERSION_HEADER) {return false;}
  if (!declared_sha256.empty() &&
    (declared_sha256.size() != 64 ||
    !std::all_of(
      declared_sha256.begin(), declared_sha256.end(),
      [](const char c) {return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');})))
  {
    return false;
  }
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
  computed_model_sha256_ = model_sha256_;
  if (!declared_sha256.empty()) {model_sha256_ = declared_sha256;}
  model_ = model;
  return true;
}

msg::SceneStateEvidence SceneStateBuilder::build(
  const mjModel * model, const mjData * data, const std::string & session,
  uint64_t epoch, uint64_t step, bool paused, int64_t clock_begin_ns) const
{
  if (!model_ || model != model_ || !data || session.empty() ||
    !std::isfinite(data->time) || data->time < 0.0 || clock_begin_ns <= 0)
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
  output.clock_interval_begin_monotonic_ns = clock_begin_ns;
  output.clock_interval_end_monotonic_ns = steady_nanoseconds();
  if (output.clock_interval_end_monotonic_ns < clock_begin_ns) {
    throw std::invalid_argument("invalid full-scene clock interval");
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
}  // namespace so101_mujoco_support

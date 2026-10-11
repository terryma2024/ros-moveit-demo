// Copyright 2026 SO-101 maintainers

#ifndef EVIDENCE_INTERNAL_HPP_
#define EVIDENCE_INTERNAL_HPP_

// Helpers shared by the evidence translation units of the plugin library; each unit keeps its own copy.

#include <chrono>
#include <cmath>
#include <string>

#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

namespace so101_mujoco_support
{
namespace
{
inline int64_t steady_nanoseconds()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}

inline std::string name(const mjModel * model, mjtObj type, int id)
{
  const char * value = mj_id2name(model, type, id);
  return value == nullptr ? "" : value;
}

inline bool finite_contact(const mjContact & contact)
{
  return std::isfinite(contact.pos[0]) && std::isfinite(contact.pos[1]) &&
         std::isfinite(contact.pos[2]) && std::isfinite(contact.frame[0]) &&
         std::isfinite(contact.frame[1]) && std::isfinite(contact.frame[2]) &&
         std::isfinite(contact.dist);
}
}  // namespace
}  // namespace so101_mujoco_support

#endif  // EVIDENCE_INTERNAL_HPP_

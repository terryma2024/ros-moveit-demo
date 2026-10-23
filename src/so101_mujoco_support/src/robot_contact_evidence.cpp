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

std::size_t RobotContactBuffer::size() const {return samples_.size();}

void RobotContactBuffer::note_loss() {loss_ = true;}

RobotContactPublisher::RobotContactPublisher(
  std::size_t capacity, Sink sink, Log log, std::chrono::milliseconds stats_period)
: buffer_(capacity), sink_(std::move(sink)), log_(std::move(log)), stats_period_(stats_period)
{
  if (!sink_) {throw std::invalid_argument("invalid robot contact sink");}
  thread_ = std::thread([this]() {run();});
}

RobotContactPublisher::~RobotContactPublisher() {stop();}

bool RobotContactPublisher::push(const msg::RobotContactEvidence & sample)
{
  bool accepted;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    accepted = buffer_.append(sample);
    ++stats_.pushed;
    if (!accepted) {++stats_.dropped;}
    stats_.depth = buffer_.size();
    stats_.high_water = std::max(stats_.high_water, stats_.depth);
  }
  wake_.notify_one();
  return accepted;
}

void RobotContactPublisher::reset(uint64_t epoch)
{
  std::unique_lock<std::mutex> lock(mutex_);
  ++generation_;  // a batch the thread already took is dropped before its next message
  buffer_.reset(epoch);
  stats_.depth = 0;
  // At most one sink call can still be in flight; wait for it (bounded) so it cannot follow the new epoch.
  idle_.wait_for(lock, std::chrono::milliseconds(50), [this]() {return !inflight_;});
}

void RobotContactPublisher::stop()
{
  {
    std::lock_guard<std::mutex> lock(mutex_);
    stop_ = true;
  }
  wake_.notify_all();
  if (thread_.joinable() && thread_.get_id() != std::this_thread::get_id()) {thread_.join();}
}

RobotContactPublisher::Stats RobotContactPublisher::stats() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return stats_;
}

void RobotContactPublisher::run()
{
  std::vector<msg::RobotContactEvidence> batch;
  batch.reserve(kBatch);
  auto window_begin = std::chrono::steady_clock::now();
  uint64_t window_published = 0, window_dropped = 0;
  std::size_t window_high_water = 0;
  while (true) {
    uint64_t generation;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      wake_.wait(lock, [this]() {return stop_ || !buffer_.empty();});
      if (stop_) {break;}
      generation = generation_;
      window_high_water = std::max(window_high_water, buffer_.size());
      while (!buffer_.empty() && batch.size() < kBatch) {
        batch.push_back(buffer_.front());  // carries the persistent loss flag, as before
        buffer_.pop_published();
      }
      stats_.depth = buffer_.size();
      inflight_ = true;
    }
    uint64_t sent = 0, failed = 0;
    for (const auto & sample : batch) {
      {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stop_ || generation != generation_) {break;}
      }
      try {
        sink_(sample);
        ++sent;
      } catch (...) {
        ++failed;
        std::lock_guard<std::mutex> lock(mutex_);
        buffer_.note_loss();  // a message that never left is lost evidence: later messages say so
      }
    }
    batch.clear();
    {
      std::lock_guard<std::mutex> lock(mutex_);
      inflight_ = false;
      stats_.published += sent;
      stats_.sink_errors += failed;
      window_dropped = stats_.dropped;
    }
    idle_.notify_all();
    window_published += sent;
    const auto now = std::chrono::steady_clock::now();
    if (log_ && now - window_begin >= stats_period_) {
      const double seconds = std::chrono::duration<double>(now - window_begin).count();
      const auto snapshot = stats();
      log_("robot_contacts publisher: " + std::to_string(window_published / seconds) + " msg/s, queue high-water " +
        std::to_string(window_high_water) + ", dropped(total) " + std::to_string(window_dropped) +
        ", sink_errors(total) " + std::to_string(snapshot.sink_errors) + ", published(total) " +
        std::to_string(snapshot.published));
      window_begin = now;
      window_published = 0;
      window_high_water = 0;
    }
  }
}
}  // namespace so101_mujoco_support

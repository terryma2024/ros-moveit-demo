// Copyright 2026 SO-101 maintainers

#include "so101_mujoco_support/simulation_evidence_plugin.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <exception>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include <pluginlib/class_list_macros.hpp>
#include <rcutils/sha256.h>

#include "evidence_internal.hpp"

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
}  // namespace

int64_t publish_grid_index(double time_s, int64_t period_ns)
{
  // llround(time * 1e9) is exact for every multiple of 1 ns the accumulated step sum can drift to (one ulp at 128 s is 1.4e-5 ns)
  const int64_t time_ns = static_cast<int64_t>(std::llround(time_s * 1.0e9));
  int64_t index = time_ns / period_ns;
  if (time_ns % period_ns < 0) {--index;}        // floor for a (never expected) negative time
  return index;
}

bool publish_grid_valid(int64_t period_ns, int64_t step_ns)
{
  return period_ns > 0 && step_ns > 0 && period_ns % step_ns == 0;
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
    const auto step_fence_request_topic = parameter<std::string>(
      node, "physics_step_fence_request_topic", "/so101/simulation/physics_step_fence_request");
    const auto step_fence_ack_topic = parameter<std::string>(
      node, "physics_step_fence_ack_topic", "/so101/simulation/physics_step_fence_ack");
    if (max_contacts < 0 || physics_step_buffer_capacity <= 0 || physics_step_chunk_size <= 0 ||
      physics_step_chunk_size > physics_step_buffer_capacity || !std::isfinite(rate) ||
      rate <= 0.0 || !std::isfinite(model->opt.timestep) || model->opt.timestep <= 0.0 ||
      !std::isfinite(static_shadow_force_n_) || static_shadow_force_n_ <= 0.0 ||
      !std::isfinite(diagnostic_hard_stop_force_n_) ||
      diagnostic_hard_stop_force_n_ <= static_shadow_force_n_ || topic.empty() ||
      chunk_topic.empty() || hazard_topic.empty() || cancellation_request_topic.empty() ||
      cancellation_ack_topic.empty() || step_fence_request_topic.empty() ||
      step_fence_ack_topic.empty() ||
      state_.simulation_session_id.empty() ||
      !builder_.configure(model, object, left, right, other,
        static_cast<std::size_t>(max_contacts)))
    {
      return false;
    }
    node_ = std::move(node);
    step_fence_.configure_session(state_.simulation_session_id);
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
      robot_publisher_ = node_->create_publisher<msg::RobotContactEvidence>(
        "/so101/simulation/robot_contacts", rclcpp::QoS(rclcpp::KeepLast(10000)).reliable());
      // Plan A21: a dedicated non-real-time thread publishes every queued message per wake, in order, so the
      // contact stream is never capped to one message per realtime-publisher cycle. Same type, topic and QoS.
      const auto publisher = robot_publisher_;
      const auto logger = node_->get_logger();
      robot_contacts_ = std::make_unique<RobotContactPublisher>(
        static_cast<std::size_t>(capacity),
        [publisher](const msg::RobotContactEvidence & sample) {publisher->publish(sample);},
        [logger](const std::string & text) {RCLCPP_INFO(logger, "%s", text.c_str());});
      robot_contacts_->reset(0);
      // A scene-variant stack (indoor P3) is launched with the identity of its nominal scene; no variable: the model's own hash.
      const char * declared = std::getenv("SO101_DECLARED_MODEL_SHA256");
      const char * proof = std::getenv("SO101_MODEL_EQUIVALENCE_PROOF_SHA256");
      if (!scene_builder_.configure(
          model, declared ? std::string(declared) : std::string(), proof ? std::string(proof) : std::string()))
      {
        return false;
      }
      if (declared) {
        RCLCPP_INFO(
          node_->get_logger(), "scene state declares the model identity %s (proof %s); the loaded model hashes to %s",
          declared, proof, scene_builder_.computed_model_sha256().c_str());
      }
      scene_publisher_ = node_->create_publisher<msg::SceneStateEvidence>(
        "/so101/simulation/scene_state", evidence_qos);
      realtime_scene_publisher_ = std::make_unique<realtime_tools::RealtimePublisher<msg::SceneStateEvidence>>(scene_publisher_);
    }
    // The strict capture consumes every atomic sequence, even while it
    // fsyncs paired RGB frames. Keep its offered history as deep as its queue.
    const auto capture_evidence_qos =
      rclcpp::QoS(rclcpp::KeepLast(256)).reliable().transient_local();
    publisher_ = node_->create_publisher<Evidence>(topic, capture_evidence_qos);
    realtime_publisher_ = std::make_unique<realtime_tools::RealtimePublisher<Evidence>>(publisher_);
    const auto chunk_qos = rclcpp::QoS(rclcpp::KeepLast(100)).reliable();
    chunk_publisher_ = node_->create_publisher<EvidenceChunk>(chunk_topic, chunk_qos);
    chunk_stamping_publisher_ = std::make_unique<StampingChunkPublisher>(chunk_publisher_);
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
    step_fence_ack_publisher_ = node_->create_publisher<msg::PhysicsStepFenceAck>(
      step_fence_ack_topic, cancellation_qos);
    realtime_step_fence_ack_publisher_ =
      std::make_unique<realtime_tools::RealtimePublisher<msg::PhysicsStepFenceAck>>(
      step_fence_ack_publisher_);
    step_fence_request_subscription_ =
      node_->create_subscription<msg::PhysicsStepFenceRequest>(
      step_fence_request_topic, cancellation_qos,
      [this](const msg::PhysicsStepFenceRequest & request) {
        step_fence_.request(request);
      });
    physics_step_buffer_ = std::make_unique<PhysicsStepEvidenceBuffer>(
      static_cast<std::size_t>(physics_step_buffer_capacity),
      static_cast<std::size_t>(physics_step_chunk_size), diagnostic_hard_stop_force_n_);
    // The integer grid: refuse a rate whose period is not a whole number of physics steps.
    if (!std::isfinite(rate) || rate <= 0.0 || !std::isfinite(model->opt.timestep) || model->opt.timestep <= 0.0) {
      cleanup();
      return false;
    }
    const int64_t period_ns = static_cast<int64_t>(std::llround(1.0e9 / rate));
    const int64_t step_ns = static_cast<int64_t>(std::llround(model->opt.timestep * 1.0e9));
    if (!publish_grid_valid(period_ns, step_ns)) {
      cleanup();
      return false;
    }
    publish_period_ns_ = period_ns;
    last_publish_grid_ = publish_grid_index(data->time, publish_period_ns_);
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
  if (evidence_snapshot_retry_.load(std::memory_order_acquire) ||
    scene_snapshot_retry_.load(std::memory_order_acquire))
  {
    retry_paused_snapshot(model, data);
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
  if (!published_ || publish_grid_index(data->time, publish_period_ns_) != last_publish_grid_) {
    try_publish_snapshot(model, data, paused, reset_generation, true);
  }
}

void SimulationEvidencePlugin::on_physics_step(const mjModel * model, const mjData * data)
{
  if (!chunk_stamping_publisher_ || !physics_step_buffer_ || model == nullptr || data == nullptr ||
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
  const auto clock_begin_ns = steady_nanoseconds();
  auto step = builder_.build_step(model, data, paused, physics_state_, reset_generation,
                                  static_shadow_force_n_, diagnostic_hard_stop_force_n_);
  step.clock_interval_begin_monotonic_ns = clock_begin_ns;
  step.clock_interval_end_monotonic_ns = steady_nanoseconds();
  current_reset_epoch_.store(step.reset_epoch, std::memory_order_release);
  current_physics_step_.store(step.physics_step, std::memory_order_release);
  current_simulation_time_s_.store(step.simulation_time_s, std::memory_order_release);
  const bool recorded = physics_step_buffer_->append(step);
  const auto clock_end_ns = steady_nanoseconds();
  if (robot_contacts_) {
    robot_contacts_->push(robot_builder_.build(model, data, step.simulation_session_id,
      step.reset_epoch, step.physics_step));
  }
  publish_hazard_if_needed();
  if (recorded && !physics_step_buffer_->evidence_loss_latched() &&
    realtime_step_fence_ack_publisher_ && realtime_step_fence_ack_publisher_->trylock())
  {
    const auto ack = step_fence_.observe(
      step, paused, clock_begin_ns, clock_end_ns);
    if (ack) {
      realtime_step_fence_ack_publisher_->msg_ = *ack;
      realtime_step_fence_ack_publisher_->unlockAndPublish();
    } else {
      realtime_step_fence_ack_publisher_->unlock();
    }
  }
  if (physics_step_buffer_->ready()) {
    try_publish_chunk();
  }
}

bool SimulationEvidencePlugin::try_publish_snapshot(
  const mjModel * model, const mjData * data,
  bool paused, uint64_t reset_generation,
  bool advance_physics_step)
{
  if (!realtime_publisher_->trylock()) {
    return false;
  }
  const auto clock_begin_ns = steady_nanoseconds();
  try {
    realtime_publisher_->msg_ =
      builder_.build(model, data, paused, state_, reset_generation, advance_physics_step);
    realtime_publisher_->unlockAndPublish();
    publish_scene_snapshot(model, data, paused, clock_begin_ns);
    last_publish_grid_ = publish_grid_index(data->time, publish_period_ns_);
    published_ = true;
    return true;
  } catch (...) {
    realtime_publisher_->unlock();
    return false;
  }
}

bool SimulationEvidencePlugin::publish_scene_snapshot(
  const mjModel * model, const mjData * data, bool paused, int64_t clock_begin_ns)
{
  if (!realtime_scene_publisher_) {
    return true;
  }
  bool published = false;
  if (realtime_scene_publisher_->trylock()) {
    try {
      realtime_scene_publisher_->msg_ = scene_builder_.build(model, data,
        state_.simulation_session_id, state_.reset_epoch, state_.simulation_step,
        paused, clock_begin_ns);
      realtime_scene_publisher_->unlockAndPublish();
      published = true;
    } catch (...) {
      realtime_scene_publisher_->unlock();
    }
  }
  if (paused) {
    // The paused frame is the last one before the simulation stops; it is published once, so it must not be lost.
    scene_snapshot_retry_.store(!published, std::memory_order_release);
  }
  return published;
}

void SimulationEvidencePlugin::retry_paused_snapshot(const mjModel * model, const mjData * data)
{
  if (!authoritative_paused_.load(std::memory_order_acquire)) {
    // The simulation resumed: the paused frame is stale and the running stream carries on.
    evidence_snapshot_retry_.store(false, std::memory_order_release);
    scene_snapshot_retry_.store(false, std::memory_order_release);
    return;
  }
  const auto generation = reset_generation_.load(std::memory_order_acquire);
  if (evidence_snapshot_retry_.load(std::memory_order_acquire)) {
    const bool reset_pending = generation != state_.consumed_reset_generation;
    // The same call the hook made, so the frame is exactly the one the hook would have published.
    if (!try_publish_snapshot(model, data, true, generation, true)) {
      return;
    }
    evidence_snapshot_retry_.store(false, std::memory_order_release);
    complete_reset_snapshot(data, generation, reset_pending);
    return;
  }
  // Only the scene frame is missing; the evidence frame it belongs to was published and is not repeated.
  publish_scene_snapshot(model, data, true, steady_nanoseconds());
}

void SimulationEvidencePlugin::try_publish_chunk()
{
  if (!physics_step_buffer_ || !chunk_stamping_publisher_) {
    return;
  }
  try {
    auto chunk = physics_step_buffer_->prepare_chunk();
    chunk.handoff_monotonic_ns = static_cast<uint64_t>(steady_nanoseconds());
    if (!chunk_stamping_publisher_->try_post(chunk)) {
      physics_step_buffer_->mark_publish_failed();
      return;
    }
    physics_step_buffer_->mark_published();
  } catch (...) {
    physics_step_buffer_->mark_publish_failed();
  }
}

StampingChunkPublisher::StampingChunkPublisher(rclcpp::Publisher<Chunk>::SharedPtr publisher)
: publisher_(std::move(publisher))
{
  thread_ = std::thread(&StampingChunkPublisher::loop, this);
}

StampingChunkPublisher::~StampingChunkPublisher()
{
  {
    std::lock_guard<std::mutex> lock(mutex_);
    stop_ = true;
  }
  condition_.notify_one();
  if (thread_.joinable()) {
    thread_.join();
  }
}

bool StampingChunkPublisher::try_post(const Chunk & chunk)
{
  {
    std::unique_lock<std::mutex> lock(mutex_, std::try_to_lock);
    if (!lock.owns_lock() || full_) {
      return false;
    }
    slot_ = chunk;
    full_ = true;
  }
  condition_.notify_one();
  return true;
}

void StampingChunkPublisher::loop()
{
  for (;;) {
    Chunk chunk;
    {
      std::unique_lock<std::mutex> lock(mutex_);
      condition_.wait(lock, [this] {return full_ || stop_;});
      if (!full_) {
        return;          // stopped with nothing pending
      }
      chunk = std::move(slot_);
      full_ = false;
    }
    chunk.publish_monotonic_ns = static_cast<uint64_t>(steady_nanoseconds());
    try {
      publisher_->publish(chunk);
    } catch (...) {
      // A failed publish is visible to the consumer as a sequence gap (continuity), never hidden here.
    }
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
  const bool published = try_publish_snapshot(model, data, true, generation, true);
  // A paused frame that could not be published is retried by the controller cycle (`update`) until it is.
  evidence_snapshot_retry_.store(!published, std::memory_order_release);
  if (scalar_joint_publisher_) {
    scalar_joint_publisher_->publish(make_scalar_joint_evidence(
        model, data, scalar_joint_names_, state_.simulation_session_id, generation,
        reset_pending ? 0 : state_.simulation_step, true));
  }
  complete_reset_snapshot(data, generation, reset_pending);
}

void SimulationEvidencePlugin::complete_reset_snapshot(
  const mjData * data, uint64_t generation, bool reset_pending)
{
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
    if (robot_contacts_) {robot_contacts_->reset(generation);}
    current_reset_epoch_.store(generation, std::memory_order_release);
    current_physics_step_.store(0, std::memory_order_release);
    current_simulation_time_s_.store(data->time, std::memory_order_release);
    step_fence_.reset(generation);
    hazard_published_ = false;
  }
}

void SimulationEvidencePlugin::cleanup()
{
  evidence_snapshot_retry_.store(false);
  scene_snapshot_retry_.store(false);
  realtime_scene_publisher_.reset();
  scene_publisher_.reset();
  scene_builder_ = SceneStateBuilder{};
  robot_contacts_.reset();  // joins the publishing thread before the publisher goes away
  robot_publisher_.reset();
  scalar_joint_publisher_.reset();
  scalar_joint_names_.clear();
  physics_step_buffer_.reset();
  step_fence_request_subscription_.reset();
  realtime_step_fence_ack_publisher_.reset();
  step_fence_ack_publisher_.reset();
  step_fence_.configure_session("");
  cancellation_request_subscription_.reset();
  cancellation_ack_publisher_.reset();
  chunk_stamping_publisher_.reset();
  chunk_publisher_.reset();
  hazard_publisher_.reset();
  realtime_publisher_.reset();
  publisher_.reset();
  node_.reset();
  state_ = EvidenceState{};
  physics_state_ = EvidenceState{};
  publish_period_ns_ = 10000000;
  last_publish_grid_ = 0;
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

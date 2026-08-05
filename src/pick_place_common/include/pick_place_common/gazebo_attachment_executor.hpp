#pragma once

#include <memory>
#include <string>

#include "pick_place_common/state_action.hpp"

namespace pick_place_common::ros_adapters
{

struct GazeboAttachmentConfig
{
  State allowed_state;
  bool desired_attached;
  std::string attach_topic;
  std::string detach_topic;
  std::string state_topic;
  double timeout_seconds;
  double poll_interval_seconds;
  bool idempotent{false};
};

class IAttachmentConvergencePolicy
{
public:
  virtual ~IAttachmentConvergencePolicy() = default;
  [[nodiscard]] virtual bool canTreatAsConverged(const ExecutionContext & context,
                                                 bool desired_attached) const = 0;
};

class DefaultAttachmentConvergencePolicy final : public IAttachmentConvergencePolicy
{
public:
  [[nodiscard]] bool canTreatAsConverged(const ExecutionContext & context,
                                         bool desired_attached) const override;
};

class GazeboAttachmentExecutor final : public IStateExecutor
{
public:
  explicit GazeboAttachmentExecutor(
    GazeboAttachmentConfig config,
    std::shared_ptr<const IAttachmentConvergencePolicy> convergence_policy =
      std::make_shared<DefaultAttachmentConvergencePolicy>());
  GazeboAttachmentExecutor(State allowed_state, bool desired_attached,
                           const std::string & attach_topic, const std::string & detach_topic,
                           const std::string & state_topic, double timeout_seconds,
                           double poll_interval_seconds, bool idempotent,
                           std::shared_ptr<const IAttachmentConvergencePolicy> convergence_policy =
                             std::make_shared<DefaultAttachmentConvergencePolicy>());
  ~GazeboAttachmentExecutor() override;

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  class Impl;
  GazeboAttachmentConfig config_;
  std::shared_ptr<const IAttachmentConvergencePolicy> convergence_policy_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace pick_place_common::ros_adapters

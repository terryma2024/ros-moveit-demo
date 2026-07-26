#pragma once

#include <memory>
#include <string>

#include "so101_gazebo_demo/pick_place/state_action.hpp"

namespace so101_gazebo_demo::pick_place
{

class GazeboAttachmentExecutor final : public IStateExecutor
{
public:
  GazeboAttachmentExecutor(State allowed_state, bool desired_attached,
                           const std::string & attach_topic, const std::string & detach_topic,
                           const std::string & output_topic, double timeout_seconds,
                           double poll_interval_seconds, bool idempotent);
  ~GazeboAttachmentExecutor() override;

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  class Impl;
  State allowed_state_;
  bool desired_attached_;
  double timeout_seconds_;
  double poll_interval_seconds_;
  bool idempotent_;
  std::unique_ptr<Impl> impl_;
};

}  // namespace so101_gazebo_demo::pick_place

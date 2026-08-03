#pragma once
#include <pick_place_common/gazebo_attachment_executor.hpp>
namespace so101_gazebo_demo::pick_place
{
using pick_place_common::ExecutionContext;
using pick_place_common::ros_adapters::DefaultAttachmentConvergencePolicy;
using pick_place_common::ros_adapters::GazeboAttachmentConfig;
using pick_place_common::ros_adapters::GazeboAttachmentExecutor;
using pick_place_common::ros_adapters::IAttachmentConvergencePolicy;
}  // namespace so101_gazebo_demo::pick_place

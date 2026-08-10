#include "so101_gazebo_demo/pick_place/attachment_state_reducer.hpp"

namespace so101_gazebo_demo::pick_place
{

bool AttachmentStateReducer::consume(const std::string & raw_event)
{
  std::lock_guard<std::mutex> lock(mutex_);
  if (raw_event == "attached") {
    attached_ = true;
    return true;
  }
  if (raw_event == "detached") {
    attached_ = false;
    return true;
  }
  return false;
}

std::optional<bool> AttachmentStateReducer::state() const
{
  std::lock_guard<std::mutex> lock(mutex_);
  return attached_;
}

}  // namespace so101_gazebo_demo::pick_place

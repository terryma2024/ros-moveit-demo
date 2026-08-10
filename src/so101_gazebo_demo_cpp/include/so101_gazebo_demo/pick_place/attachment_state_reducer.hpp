#pragma once

#include <mutex>
#include <optional>
#include <string>

namespace so101_gazebo_demo::pick_place
{

class AttachmentStateReducer
{
public:
  [[nodiscard]] bool consume(const std::string & raw_event);
  [[nodiscard]] std::optional<bool> state() const;

private:
  mutable std::mutex mutex_;
  std::optional<bool> attached_;
};

}  // namespace so101_gazebo_demo::pick_place

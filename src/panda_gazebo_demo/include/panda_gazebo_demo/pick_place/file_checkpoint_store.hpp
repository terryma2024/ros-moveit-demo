#pragma once

#include <filesystem>

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"

namespace panda_gazebo_demo::pick_place
{

class FileCheckpointStore final : public ICheckpointStore
{
public:
  explicit FileCheckpointStore(std::filesystem::path path);
  [[nodiscard]] std::optional<Failure> commit(const Checkpoint & checkpoint) override;

private:
  std::filesystem::path path_;
};

}  // namespace panda_gazebo_demo::pick_place

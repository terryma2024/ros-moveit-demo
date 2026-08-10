#pragma once
#include <filesystem>
#include "so101_gazebo_demo/pick_place/checkpoint.hpp"
namespace so101_gazebo_demo::pick_place
{
class FileCheckpointStore final : public ICheckpointStore
{
public:
  explicit FileCheckpointStore(std::filesystem::path path) : path_(std::move(path)) {}
  [[nodiscard]] std::optional<Failure> commit(const Checkpoint &) override;
  [[nodiscard]] CheckpointLoadResult loadLatestCompatible() override;

private:
  std::filesystem::path path_;
};
}  // namespace so101_gazebo_demo::pick_place

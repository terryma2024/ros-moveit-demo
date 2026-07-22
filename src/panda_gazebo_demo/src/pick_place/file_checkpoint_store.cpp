#include "panda_gazebo_demo/pick_place/file_checkpoint_store.hpp"

#include <fstream>
#include <system_error>

namespace panda_gazebo_demo::pick_place
{

FileCheckpointStore::FileCheckpointStore(std::filesystem::path path)
: path_(std::move(path))
{
}

std::optional<Failure> FileCheckpointStore::commit(const Checkpoint & checkpoint)
{
  std::error_code error;
  std::filesystem::create_directories(path_.parent_path(), error);
  if (error) {
    return Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_DIRECTORY_CREATE_FAILED",
      "Unable to create checkpoint directory: " + error.message(), {}};
  }
  const auto temporary_path = path_.string() + ".tmp";
  {
    std::ofstream output(temporary_path, std::ios::out | std::ios::trunc);
    if (!output) {
      return Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_WRITE_OPEN_FAILED",
        "Unable to open temporary checkpoint file", {}};
    }
    output << "schema_version: " << checkpoint.schema_version << '\n';
    output << "run_id: " << checkpoint.run_id << '\n';
    output << "sequence: " << checkpoint.sequence << '\n';
    output << "source_mode: " << toString(checkpoint.source_mode) << '\n';
    output << "last_completed_state: " << toString(checkpoint.last_completed_state) << '\n';
    output << "next_state: " << toString(checkpoint.next_state) << '\n';
    output << "tcp_position: [" << checkpoint.expected.tcp_pose_world.x << ", "
           << checkpoint.expected.tcp_pose_world.y << ", " << checkpoint.expected.tcp_pose_world.z
           << "]\n";
    output << "coke_attached: " << (checkpoint.expected.coke_attached ? "true" : "false") << '\n';
    output << "resumable: " << (checkpoint.resumable ? "true" : "false") << '\n';
    if (!output) {
      return Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_WRITE_FAILED",
        "Failed while writing temporary checkpoint file", {}};
    }
  }
  std::filesystem::rename(temporary_path, path_, error);
  if (error) {
    std::filesystem::remove(temporary_path);
    return Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_ATOMIC_RENAME_FAILED",
      "Unable to atomically commit checkpoint: " + error.message(), {}};
  }
  return std::nullopt;
}

}  // namespace panda_gazebo_demo::pick_place

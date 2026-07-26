#include "so101_gazebo_demo/pick_place/file_checkpoint_store.hpp"

#include <fstream>

namespace so101_gazebo_demo::pick_place
{

std::optional<Failure> FileCheckpointStore::commit(const Checkpoint & checkpoint)
{
  std::ofstream output(path_, std::ios::trunc);
  if (!output) {
    return Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_WRITE_FAILED",
                   "could not open checkpoint file", {}};
  }
  output << checkpoint.schema_version << '\n' << checkpoint.run_id << '\n'
         << checkpoint.sequence << '\n' << static_cast<int>(checkpoint.next_state) << '\n'
         << checkpoint.configuration_hash << '\n' << checkpoint.simulation_session_id << '\n';
  if (!output) {
    return Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_WRITE_FAILED",
                   "could not write checkpoint file", {}};
  }
  return std::nullopt;
}

CheckpointLoadResult FileCheckpointStore::loadLatestCompatible()
{
  std::ifstream input(path_);
  Checkpoint checkpoint;
  int next_state = 0;
  if (!(input >> checkpoint.schema_version)) {
    return {{}, Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_NOT_FOUND",
                        "no checkpoint is available", {}}};
  }
  if (checkpoint.schema_version != 3) {
    return {{}, Failure{FailureCategory::CHECKPOINT, "CHECKPOINT_INCOMPATIBLE",
                        "checkpoint schema v3 is required", {}}};
  }
  input.ignore();
  std::getline(input, checkpoint.run_id);
  input >> checkpoint.sequence >> next_state;
  checkpoint.next_state = static_cast<State>(next_state);
  input.ignore();
  std::getline(input, checkpoint.configuration_hash);
  std::getline(input, checkpoint.simulation_session_id);
  return {checkpoint, {}};
}

}  // namespace so101_gazebo_demo::pick_place

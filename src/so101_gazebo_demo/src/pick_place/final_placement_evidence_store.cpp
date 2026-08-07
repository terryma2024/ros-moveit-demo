#include "so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp"

#include <mutex>

namespace so101_gazebo_demo::pick_place
{

std::optional<Failure> InMemoryFinalPlacementEvidenceStore::beginEpoch(const ReleaseEpoch & epoch)
{
  const std::scoped_lock lock(mutex_);
  epoch_ = epoch;
  frozen_.reset();
  return std::nullopt;
}

std::optional<Failure>
InMemoryFinalPlacementEvidenceStore::recordEvaluation(const FinalPlacementEvaluation & evaluation)
{
  const std::scoped_lock lock(mutex_);
  if (!epoch_) {
    return Failure{FailureCategory::CONFIGURATION,
                   "FINAL_PLACEMENT_EPOCH_NOT_STARTED",
                   "Final placement evidence cannot be recorded before its release epoch",
                   {}};
  }
  frozen_ = FinalPlacementOutcomeRecord{*epoch_, evaluation};
  return std::nullopt;
}

std::optional<FinalPlacementOutcomeRecord> InMemoryFinalPlacementEvidenceStore::frozen() const
{
  const std::scoped_lock lock(mutex_);
  return frozen_;
}

}  // namespace so101_gazebo_demo::pick_place

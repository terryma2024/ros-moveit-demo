#pragma once

#include <mutex>
#include <optional>

#include "so101_gazebo_demo/pick_place/final_placement_evaluator.hpp"

namespace so101_gazebo_demo::pick_place
{

struct FinalPlacementOutcomeRecord
{
  ReleaseEpoch epoch;
  FinalPlacementEvaluation evaluation;
};

class IFinalPlacementEvidenceStore
{
public:
  virtual ~IFinalPlacementEvidenceStore() = default;
  virtual std::optional<Failure> beginEpoch(const ReleaseEpoch & epoch) = 0;
  virtual std::optional<Failure> recordEvaluation(const FinalPlacementEvaluation & evaluation) = 0;
  [[nodiscard]] virtual std::optional<FinalPlacementOutcomeRecord> frozen() const = 0;
};

class InMemoryFinalPlacementEvidenceStore final : public IFinalPlacementEvidenceStore
{
public:
  std::optional<Failure> beginEpoch(const ReleaseEpoch & epoch) override;
  std::optional<Failure> recordEvaluation(const FinalPlacementEvaluation & evaluation) override;
  [[nodiscard]] std::optional<FinalPlacementOutcomeRecord> frozen() const override;

private:
  mutable std::mutex mutex_;
  std::optional<ReleaseEpoch> epoch_;
  std::optional<FinalPlacementOutcomeRecord> frozen_;
};

}  // namespace so101_gazebo_demo::pick_place

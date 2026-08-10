#pragma once

#include <atomic>
#include <chrono>
#include <vector>

#include "so101_gazebo_demo/pick_place/final_placement_evidence_store.hpp"
#include "so101_gazebo_demo/pick_place/state_action.hpp"

namespace so101_gazebo_demo::pick_place
{

class ISettleWaiter
{
public:
  virtual ~ISettleWaiter() = default;
  virtual void waitFor(std::chrono::steady_clock::duration duration) = 0;
};

class ThreadSettleWaiter final : public ISettleWaiter
{
public:
  void waitFor(std::chrono::steady_clock::duration duration) override;
};

class ReleaseSettleExecutor final : public IStateExecutor
{
public:
  ReleaseSettleExecutor(IWorldObserver & observer, FinalPlacementEvaluator evaluator,
                        IFinalPlacementEvidenceStore & evidence, PhysicalOutcomePolicyConfig policy,
                        ISettleWaiter & waiter);

  [[nodiscard]] ActionResult execute(const ExecutionContext & context) override;
  [[nodiscard]] ActionResult cancel() override;

private:
  [[nodiscard]] ActionResult freezeFailure(FinalPlacementEvaluation evaluation, Failure failure);

  IWorldObserver & observer_;
  FinalPlacementEvaluator evaluator_;
  IFinalPlacementEvidenceStore & evidence_;
  PhysicalOutcomePolicyConfig policy_;
  ISettleWaiter & waiter_;
  std::atomic_bool cancelled_{false};
};

}  // namespace so101_gazebo_demo::pick_place

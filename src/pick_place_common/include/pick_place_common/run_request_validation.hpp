#pragma once

#include <optional>

#include "pick_place_common/domain_types.hpp"
#include "pick_place_common/workflow_definition.hpp"

namespace pick_place_common
{
enum class ForwardPathRelation
{
  UPSTREAM,
  SAME,
  DOWNSTREAM,
  UNREACHABLE
};

[[nodiscard]] ForwardPathRelation compareForwardPathPosition(const WorkflowDefinition & workflow,
                                                             State cursor, State target) noexcept;

[[nodiscard]] std::optional<Failure> validateRunRequest(const WorkflowDefinition & workflow,
                                                        const RunRequest & request);
}  // namespace pick_place_common

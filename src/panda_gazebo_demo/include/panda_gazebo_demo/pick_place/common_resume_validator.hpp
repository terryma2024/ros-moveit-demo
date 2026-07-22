#pragma once

#include <string>

#include "panda_gazebo_demo/pick_place/checkpoint.hpp"
#include "panda_gazebo_demo/pick_place/transition_contract.hpp"

namespace panda_gazebo_demo::pick_place
{

class CommonResumeValidator
{
public:
  CommonResumeValidator(
    std::string configuration_hash, std::string simulation_session_id,
    double joint_position_tolerance = 0.01);

  [[nodiscard]] ValidationResult validate(
    const Checkpoint & checkpoint, const WorldSnapshot & current) const;
  [[nodiscard]] const std::string & configurationHash() const noexcept;
  [[nodiscard]] const std::string & simulationSessionId() const noexcept;

private:
  std::string configuration_hash_;
  std::string simulation_session_id_;
  double joint_position_tolerance_;
};

}  // namespace panda_gazebo_demo::pick_place

#pragma once

#include <memory>
#include <limits>
#include <string>
#include <vector>

#include "so101_gazebo_demo/pick_place/domain_types.hpp"

namespace rclcpp
{
class Node;
}

namespace so101_gazebo_demo::pick_place
{

struct SingleJointTrajectoryGoal
{
  std::vector<std::string> joint_names;
  std::vector<double> positions;
  double duration_seconds{0.0};
};

class ITrajectoryActionClient
{
public:
  virtual ~ITrajectoryActionClient() = default;
  [[nodiscard]] virtual ActionResult send(const SingleJointTrajectoryGoal & goal,
                                          double timeout_seconds) = 0;
  [[nodiscard]] virtual ActionResult cancelAndWait(double timeout_seconds) = 0;
};

class RosTrajectoryActionClient final : public ITrajectoryActionClient
{
public:
  RosTrajectoryActionClient(std::shared_ptr<rclcpp::Node> node, std::string action_name);
  ~RosTrajectoryActionClient() override;
  [[nodiscard]] ActionResult send(const SingleJointTrajectoryGoal & goal,
                                  double timeout_seconds) override;
  [[nodiscard]] ActionResult cancelAndWait(double timeout_seconds) override;

private:
  class Impl;
  std::shared_ptr<rclcpp::Node> node_;
  std::string action_name_;
  std::unique_ptr<Impl> impl_;
};

class ISO101GripperCommand
{
public:
  virtual ~ISO101GripperCommand() = default;
  [[nodiscard]] virtual ActionResult command(double q6) = 0;
  [[nodiscard]] virtual ActionResult cancelAndWait() = 0;
};

class FollowJointTrajectoryGripperAdapter final : public ISO101GripperCommand
{
public:
  FollowJointTrajectoryGripperAdapter(
    std::shared_ptr<ITrajectoryActionClient> client, double trajectory_duration_seconds,
    double action_timeout_seconds,
    double contact_stop_q6 = std::numeric_limits<double>::quiet_NaN());
  [[nodiscard]] ActionResult command(double q6) override;
  [[nodiscard]] ActionResult cancelAndWait() override;

private:
  std::shared_ptr<ITrajectoryActionClient> client_;
  double trajectory_duration_seconds_;
  double action_timeout_seconds_;
  double contact_stop_q6_;
};

}  // namespace so101_gazebo_demo::pick_place

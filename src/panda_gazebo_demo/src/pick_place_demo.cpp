#include <cstdlib>
#include <memory>

#include <geometry_msgs/msg/pose.hpp>
#include <moveit/move_group_interface/move_group_interface.hpp>
#include <rclcpp/rclcpp.hpp>

int main(int argc, char *argv[])
{
    rclcpp::init(argc, argv);

    auto node = std::make_shared<rclcpp::Node>(
        "pre_grasp_plan",
        rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true));

    const auto logger = node->get_logger();
    int exit_code = EXIT_FAILURE;

    bool execute_requested = false;

    if (node->has_parameter("execute"))
    {
        execute_requested =
            node->get_parameter("execute").as_bool();
    }
    else
    {
        execute_requested =
            node->declare_parameter<bool>("execute", false);
    }

    {
        using MoveGroupInterface =
            moveit::planning_interface::MoveGroupInterface;

        MoveGroupInterface move_group(node, "panda_arm");

        move_group.setPoseReferenceFrame("world");

        if (!move_group.setEndEffectorLink("panda_tcp"))
        {
            RCLCPP_ERROR(logger, "MoveIt RobotModel does not accept panda_tcp");
        }
        else
        {
            RCLCPP_INFO(
                logger,
                "Planning frame: %s",
                move_group.getPlanningFrame().c_str());

            RCLCPP_INFO(
                logger,
                "Target link: %s",
                move_group.getEndEffectorLink().c_str());

            // 第一阶段只规划到 Coke 上方 0.12 m 的 pre-grasp。
            geometry_msgs::msg::Pose target_pose;
            target_pose.position.x = 0.3;
            target_pose.position.y = 0.0;
            target_pose.position.z = 0.987;

            // RPY = (pi, 0, 0)
            // TCP local +Z points toward world -Z.
            target_pose.orientation.x = 1.0;
            target_pose.orientation.y = 0.0;
            target_pose.orientation.z = 0.0;
            target_pose.orientation.w = 0.0;

            move_group.setStartStateToCurrentState();
            move_group.setPlanningTime(10.0);
            move_group.setGoalPositionTolerance(0.005);
            move_group.setGoalOrientationTolerance(0.02);
            move_group.setMaxVelocityScalingFactor(0.1);
            move_group.setMaxAccelerationScalingFactor(0.1);

            if (!move_group.setPoseTarget(target_pose, "panda_tcp"))
            {
                RCLCPP_ERROR(logger, "Failed to set panda_tcp pose target");
            }
            else
            {
                MoveGroupInterface::Plan plan;
                const bool success = static_cast<bool>(move_group.plan(plan));
                if (!success)
                {
                    RCLCPP_ERROR(logger, "Planning to pre-grasp failed");
                }
                else
                {
                    RCLCPP_INFO(
                        logger,
                        "Planning succeeded: %zu trajectory points",
                        plan.trajectory.joint_trajectory.points.size());

                    if (!execute_requested)
                    {
                        RCLCPP_INFO(
                            logger,
                            "Plan-only mode; pass --execute to move the robot");

                        exit_code = EXIT_SUCCESS;
                    }
                    else
                    {
                        RCLCPP_WARN(
                            logger,
                            "Executing pre-grasp trajectory at 10%% scaling");

                        const bool executed =
                            static_cast<bool>(move_group.execute(plan));

                        if (executed)
                        {
                            RCLCPP_INFO(logger, "Pre-grasp execution succeeded");
                            exit_code = EXIT_SUCCESS;
                        }
                        else
                        {
                            RCLCPP_ERROR(logger, "Pre-grasp execution failed");
                        }
                    }
                }

                move_group.clearPoseTargets();
            }
        }
    }

    rclcpp::shutdown();
    return exit_code;
}
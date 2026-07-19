#include <cstdlib>
#include <memory>
#include <vector>

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

    bool execute_requested = node->get_parameter_or("execute", false);
    bool plan_approach_requested = node->get_parameter_or("plan_approach", false);
    bool execute_approach_requested = node->get_parameter_or("execute_approach", false);
    double approach_target_z = node->get_parameter_or("approach_target_z", 0.947);
    double target_y = node->get_parameter_or("target_y", 0.0);

    if (approach_target_z < 0.867 || approach_target_z >= 0.987)
    {
        RCLCPP_ERROR(
            logger,
            "approach_target_z must be in [0.867, 0.987)");

        rclcpp::shutdown();
        return EXIT_FAILURE;
    }

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
        target_pose.position.y = target_y;
        target_pose.position.z = 0.987;

        RCLCPP_INFO(logger, "Target center: x=0.300, y=%.4f", target_y);

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
                    RCLCPP_INFO(
                        logger,
                        "Executing pre-grasp trajectory at 10%% scaling");

                    const bool executed =
                        static_cast<bool>(move_group.execute(plan));

                    if (!executed)
                    {
                        RCLCPP_ERROR(logger, "Pre-grasp execution failed");
                        exit_code = EXIT_FAILURE;
                    }
                    else
                    {
                        if (!plan_approach_requested)
                        {
                            exit_code = EXIT_SUCCESS;
                        }
                        else
                        {
                            // plan() 留下的 Pose target 不再需要。
                            move_group.clearPoseTargets();
                            move_group.setStartStateToCurrentState();

                            geometry_msgs::msg::Pose grasp_pose = target_pose;
                            grasp_pose.position.z = approach_target_z;
                            RCLCPP_INFO(logger, "Cartesian target z: %.3f", approach_target_z);

                            std::vector<geometry_msgs::msg::Pose> waypoints;
                            waypoints.push_back(grasp_pose);

                            moveit_msgs::msg::RobotTrajectory approach_trajectory;
                            moveit_msgs::msg::MoveItErrorCodes cartesian_error;

                            constexpr double eef_step = 0.005;

                            const double fraction =
                                move_group.computeCartesianPath(
                                    waypoints,
                                    eef_step,
                                    approach_trajectory,
                                    true,
                                    &cartesian_error);

                            RCLCPP_INFO(
                                logger,
                                "Cartesian approach: %.1f%%, %zu trajectory points, error=%d",
                                fraction * 100.0,
                                approach_trajectory.joint_trajectory.points.size(),
                                cartesian_error.val);
                            if (fraction >= 0.999)
                            {
                                const auto &points =
                                    approach_trajectory.joint_trajectory.points;

                                if (points.empty())
                                {
                                    RCLCPP_ERROR(
                                        logger,
                                        "Cartesian trajectory is empty");
                                }
                                else
                                {
                                    const auto &time_from_start =
                                        points.back().time_from_start;

                                    const double trajectory_duration =
                                        static_cast<double>(time_from_start.sec) +
                                        static_cast<double>(time_from_start.nanosec) * 1e-9;

                                    RCLCPP_INFO(
                                        logger,
                                        "Cartesian trajectory duration: %.3f seconds",
                                        trajectory_duration);

                                    if (trajectory_duration <= 0.0)
                                    {
                                        RCLCPP_ERROR(
                                            logger,
                                            "Cartesian trajectory has no valid timing; refusing execution");
                                        exit_code = EXIT_FAILURE;
                                    }
                                    else if (!execute_approach_requested)
                                    {
                                        RCLCPP_INFO(
                                            logger,
                                            "Cartesian approach fully planned; not executing");

                                        exit_code = EXIT_SUCCESS;
                                    }
                                    else
                                    {
                                        RCLCPP_WARN(
                                            logger,
                                            "Executing Cartesian approach to grasp pose");

                                        const bool approach_executed =
                                            static_cast<bool>(
                                                move_group.execute(approach_trajectory));

                                        if (approach_executed)
                                        {
                                            RCLCPP_INFO(
                                                logger,
                                                "Cartesian approach execution succeeded");

                                            exit_code = EXIT_SUCCESS;
                                        }
                                        else
                                        {
                                            RCLCPP_ERROR(
                                                logger,
                                                "Cartesian approach execution failed");
                                            exit_code = EXIT_FAILURE;
                                        }
                                    }
                                }
                            }
                            else
                            {
                                RCLCPP_ERROR(
                                    logger,
                                    "Cartesian approach incomplete; refusing to execute");
                                exit_code = EXIT_FAILURE;
                            }
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
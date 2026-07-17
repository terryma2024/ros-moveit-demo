#include <geometry_msgs/msg/pose.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <rclcpp/rclcpp.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>

int main(int argc, char *argv[])
{
    rclcpp::init(argc, argv);

    auto node = std::make_shared<rclcpp::Node>("planning_scene_setup");

    moveit_msgs::msg::CollisionObject table;
    table.header.frame_id = "world";
    table.id = "table";

    shape_msgs::msg::SolidPrimitive primitive;
    primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
    primitive.dimensions = {
        1.2, // x
        0.8, // y
        0.05 // z
    };

    geometry_msgs::msg::Pose pose;
    pose.orientation.w = 1.0;
    pose.position.x = 0.0;
    pose.position.y = 0.0;
    pose.position.z = 0.75;

    table.primitives.push_back(primitive);
    table.primitive_poses.push_back(pose);
    table.operation = moveit_msgs::msg::CollisionObject::ADD;

    RCLCPP_INFO(node->get_logger(), "Waiting for MoveGroup planning scene service...");

    // 默认会等待 MoveGroup 的 Planning Scene 服务出现。
    moveit::planning_interface::PlanningSceneInterface planning_scene_interface;

    if (!planning_scene_interface.applyCollisionObject(table))
    {
        RCLCPP_ERROR(node->get_logger(), "Failed to add table to Planning Scene");
        rclcpp::shutdown();
        return 1;
    }

    RCLCPP_INFO(
        node->get_logger(),
        "Added table: frame=world center=(0, 0, 0.75) size=(1.2, 0.8, 0.05)");

    rclcpp::shutdown();
    return 0;
}
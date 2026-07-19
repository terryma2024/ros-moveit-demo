#include <geometry_msgs/msg/pose.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <rclcpp/rclcpp.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <vector>

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

    moveit_msgs::msg::CollisionObject coke;
    coke.header.frame_id = "world";
    coke.id = "coke";

    shape_msgs::msg::SolidPrimitive coke_primitive;
    coke_primitive.type = shape_msgs::msg::SolidPrimitive::CYLINDER;
    coke_primitive.dimensions.resize(2);

    // SolidPrimitive 对 Cylinder 的维度顺序：高度、半径
    coke_primitive.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_HEIGHT] = 0.122;
    coke_primitive.dimensions[shape_msgs::msg::SolidPrimitive::CYLINDER_RADIUS] = 0.033;

    geometry_msgs::msg::Pose coke_pose;
    coke_pose.orientation.w = 1.0;
    coke_pose.position.x = 0.3;
    coke_pose.position.y = 0.0;
    coke_pose.position.z = 0.836;

    coke.primitives.push_back(coke_primitive);
    coke.primitive_poses.push_back(coke_pose);
    coke.operation = moveit_msgs::msg::CollisionObject::ADD;

    RCLCPP_INFO(node->get_logger(), "Waiting for MoveGroup planning scene service...");

    // 默认会等待 MoveGroup 的 Planning Scene 服务出现。
    moveit::planning_interface::PlanningSceneInterface planning_scene_interface;

    const std::vector<moveit_msgs::msg::CollisionObject> objects{table, coke};

    if (!planning_scene_interface.applyCollisionObjects(objects))
    {
        RCLCPP_INFO(
            node->get_logger(),
            "Added table and coke to Planning Scene");
        rclcpp::shutdown();
        return 1;
    }

    RCLCPP_INFO(
        node->get_logger(),
        "Added table: frame=world center=(0, 0, 0.75) size=(1.2, 0.8, 0.05); coke: frame=world center=(0.3, 0, 0.836) size=(0.066, 0.122)");

    rclcpp::shutdown();
    return 0;
}
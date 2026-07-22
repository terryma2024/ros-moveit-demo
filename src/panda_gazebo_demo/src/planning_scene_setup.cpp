#include <geometry_msgs/msg/pose.hpp>
#include <moveit/planning_scene_interface/planning_scene_interface.hpp>
#include <moveit_msgs/msg/collision_object.hpp>
#include <rclcpp/rclcpp.hpp>
#include <shape_msgs/msg/solid_primitive.hpp>
#include <vector>
#include <cmath>

int main(int argc, char *argv[])
{
  rclcpp::init(argc, argv);

  auto node = std::make_shared<rclcpp::Node>("planning_scene_setup");

  const double coke_x =
    node->declare_parameter<double>("coke_x", 0.3);
  const double coke_y =
    node->declare_parameter<double>("coke_y", 0.0);
  const double coke_z =
    node->declare_parameter<double>("coke_z", 0.836);
  const double coke_yaw =
    node->declare_parameter<double>("coke_yaw", 0.0);

  moveit_msgs::msg::CollisionObject table;
  table.header.frame_id = "world";
  table.id = "table";

  shape_msgs::msg::SolidPrimitive primitive;
  primitive.type = shape_msgs::msg::SolidPrimitive::BOX;
  primitive.dimensions = {
    1.2,     // x
    0.8,     // y
    0.05     // z
  };

  geometry_msgs::msg::Pose pose;
  pose.orientation.w = 1.0;
  pose.position.x = 0.0;
  pose.position.y = 0.0;
  pose.position.z = 0.75;

  table.pose = pose;
  table.primitives.push_back(primitive);
  geometry_msgs::msg::Pose table_primitive_pose;
  table_primitive_pose.orientation.w = 1.0;
  table.primitive_poses.push_back(table_primitive_pose);
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
  coke_pose.position.x = coke_x;
  coke_pose.position.y = coke_y;
  coke_pose.position.z = coke_z;

  coke_pose.orientation.x = 0.0;
  coke_pose.orientation.y = 0.0;
  coke_pose.orientation.z = std::sin(coke_yaw / 2.0);
  coke_pose.orientation.w = std::cos(coke_yaw / 2.0);

  coke.pose = coke_pose;
  coke.primitives.push_back(coke_primitive);
  geometry_msgs::msg::Pose coke_primitive_pose;
  coke_primitive_pose.orientation.w = 1.0;
  coke.primitive_poses.push_back(coke_primitive_pose);
  coke.operation = moveit_msgs::msg::CollisionObject::ADD;

  RCLCPP_INFO(node->get_logger(), "Waiting for MoveGroup planning scene service...");

    // 默认会等待 MoveGroup 的 Planning Scene 服务出现。
  moveit::planning_interface::PlanningSceneInterface planning_scene_interface;

  const std::vector<moveit_msgs::msg::CollisionObject> objects{table, coke};

  if (!planning_scene_interface.applyCollisionObjects(objects)) {
    RCLCPP_ERROR(
            node->get_logger(),
            "Failed to add table and coke to Planning Scene");
    rclcpp::shutdown();
    return EXIT_FAILURE;
  }

  RCLCPP_INFO(
        node->get_logger(),
        "Synced coke world pose: x=%.6f y=%.6f z=%.6f yaw=%.6f",
        coke_x,
        coke_y,
        coke_z,
        coke_yaw);

  rclcpp::shutdown();
  return EXIT_SUCCESS;
}

#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <stdexcept>
#include <vector>

#include <moveit/planning_scene/planning_scene.hpp>
#include <moveit_msgs/srv/apply_planning_scene.hpp>
#include <moveit_msgs/srv/get_planning_scene.hpp>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <srdfdom/model.h>
#include <urdf_parser/urdf_parser.h>

template<typename Message>
Message read_cdr(const char * path)
{
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {throw std::runtime_error("CDR_INPUT_ABSENT");}
  std::vector<char> bytes{std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
  rclcpp::SerializedMessage serialized(bytes.size());
  auto & raw = serialized.get_rcl_serialized_message();
  std::copy(bytes.begin(), bytes.end(), raw.buffer);
  raw.buffer_length = bytes.size();
  Message message;
  rclcpp::Serialization<Message>().deserialize_message(&serialized, &message);
  return message;
}

int main(int argc, char ** argv)
{
  if (argc != 4) {return 90;}
  try {
    // An in-memory robot isolates MoveIt's actual scene-apply semantics. No ROS
    // node, executor, controller, transport, simulator or hardware is created.
    const std::string description = R"(<robot name="probe"><link name="world"/>
      <link name="gripper"/><link name="jaw"/>
      <joint name="root" type="fixed"><parent link="world"/><child link="gripper"/></joint>
      <joint name="jaw_fixed" type="fixed"><parent link="gripper"/><child link="jaw"/></joint></robot>)";
    auto urdf = urdf::parseURDF(description);
    auto srdf = std::make_shared<srdf::Model>();
    if (!urdf || !srdf->initString(*urdf, "<robot name=\"probe\"/>")) {return 91;}
    planning_scene::PlanningScene scene(urdf, srdf);
    const auto initial = read_cdr<moveit_msgs::srv::ApplyPlanningScene::Request>(argv[1]);
    const auto request = read_cdr<moveit_msgs::srv::ApplyPlanningScene::Request>(argv[2]);
    if (!scene.setPlanningSceneDiffMsg(initial.scene)) {return 92;}
    const bool accepted = scene.setPlanningSceneDiffMsg(request.scene);
    moveit_msgs::srv::GetPlanningScene::Response response;
    moveit_msgs::msg::PlanningSceneComponents components;
    components.components = components.WORLD_OBJECT_NAMES | components.WORLD_OBJECT_GEOMETRY |
      components.ROBOT_STATE_ATTACHED_OBJECTS | components.OBJECT_COLORS;
    scene.getPlanningSceneMsg(response.scene, components);
    rclcpp::SerializedMessage serialized;
    rclcpp::Serialization<moveit_msgs::srv::GetPlanningScene::Response>().serialize_message(&response, &serialized);
    std::ofstream output(argv[3], std::ios::binary);
    const auto & raw = serialized.get_rcl_serialized_message();
    output.write(reinterpret_cast<const char *>(raw.buffer), raw.buffer_length);
    output.close();
    if (!output) {return 93;}
    std::cout << "native_apply_accepted=" << accepted << '\n';
    return accepted ? 0 : 1;
  } catch (const std::exception & error) {
    std::cerr << error.what() << '\n';
    return 94;
  }
}

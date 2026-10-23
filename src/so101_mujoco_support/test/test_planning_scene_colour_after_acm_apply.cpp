// Pilot 8d9ed9d3: after the Teacher's ACM-only apply at 61.496 s the planning-scene reads carried no colour for the attached
// plastic_cup (reads at 61.416 s had it), although the apply already set robot_state.is_diff. This test replays the Teacher's own
// three apply requests (recorded in the pilot bag) through MoveIt's PlanningScene exactly as move_group's apply service does and
// reads the colours back the way the Recorder's scene reads do.

#include <gtest/gtest.h>

#include <algorithm>
#include <fstream>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#include <moveit/planning_scene/planning_scene.h>
#include <moveit/robot_model/robot_model.h>
#include <moveit_msgs/msg/planning_scene.hpp>
#include <moveit_msgs/srv/apply_planning_scene.hpp>
#include <moveit/planning_scene_monitor/planning_scene_monitor.hpp>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <rclcpp/serialization.hpp>
#include <rclcpp/serialized_message.hpp>
#include <srdfdom/model.h>
#include <urdf/model.h>

#ifndef SO101_TEST_FIXTURES
#error "SO101_TEST_FIXTURES must name the fixtures directory"
#endif

namespace
{
std::string slurp(const std::string& name)
{
  std::ifstream file(std::string(SO101_TEST_FIXTURES) + "/" + name);
  EXPECT_TRUE(file.good()) << name;
  std::stringstream buffer;
  buffer << file.rdbuf();
  return buffer.str();
}

moveit_msgs::srv::ApplyPlanningScene::Request request_from_fixture(const std::string& name)
{
  std::string hex = slurp(name);
  hex.erase(std::remove_if(hex.begin(), hex.end(), [](char c) { return c == '\n' || c == ' '; }), hex.end());
  rclcpp::SerializedMessage serialized(hex.size() / 2);
  auto& raw = serialized.get_rcl_serialized_message();
  for (size_t index = 0; index < hex.size() / 2; ++index)
  {
    raw.buffer[index] = static_cast<uint8_t>(std::stoi(hex.substr(2 * index, 2), nullptr, 16));
  }
  raw.buffer_length = hex.size() / 2;
  moveit_msgs::srv::ApplyPlanningScene::Request request;
  rclcpp::Serialization<moveit_msgs::srv::ApplyPlanningScene::Request>().deserialize_message(&serialized, &request);
  return request;
}

planning_scene::PlanningScenePtr make_scene()
{
  auto urdf_model = std::make_shared<urdf::Model>();
  EXPECT_TRUE(urdf_model->initFile(std::string(SO101_TEST_FIXTURES) + "/so101_kinematic_stand_in.urdf"));
  auto srdf_model = std::make_shared<srdf::Model>();
  EXPECT_TRUE(srdf_model->initString(*urdf_model, "<robot name=\"so101\"></robot>"));
  auto model = std::make_shared<moveit::core::RobotModel>(urdf_model, srdf_model);
  EXPECT_EQ(model->getModelFrame(), "world");
  return std::make_shared<planning_scene::PlanningScene>(model);
}

std::vector<std::string> colour_ids(const planning_scene::PlanningScene& scene)
{
  moveit_msgs::msg::PlanningScene message;
  moveit_msgs::msg::PlanningSceneComponents components;
  components.components = moveit_msgs::msg::PlanningSceneComponents::OBJECT_COLORS;
  scene.getPlanningSceneMsg(message, components);
  std::vector<std::string> ids;
  for (const auto& colour : message.object_colors)
  {
    ids.push_back(colour.id);
  }
  std::sort(ids.begin(), ids.end());
  return ids;
}

// move_group's apply service: PlanningSceneMonitor::newPlanningSceneMessage -> setPlanningSceneDiffMsg for a diff.
void apply_scene(planning_scene::PlanningScene& scene, const moveit_msgs::msg::PlanningScene& message)
{
  if (message.is_diff)
  {
    scene.setPlanningSceneDiffMsg(message);
  }
  else
  {
    scene.usePlanningSceneMsg(message);
  }
}

TEST(PlanningSceneColour, TheAttachedCupKeepsItsColourThroughTheTeachersAcmOnlyApply)
{
  auto scene = make_scene();
  apply_scene(*scene, request_from_fixture("pilot_8d9ed9d3_setup_apply.cdr.hex").scene);
  const std::vector<std::string> expected{ "pedestal", "plastic_cup", "table" };
  ASSERT_EQ(colour_ids(*scene), expected) << "after SETUP";

  apply_scene(*scene, request_from_fixture("pilot_8d9ed9d3_attach_apply.cdr.hex").scene);
  ASSERT_EQ(colour_ids(*scene), expected) << "after the attach (the Teacher's own read-back at 61.428 s saw the colour)";

  apply_scene(*scene, request_from_fixture("pilot_8d9ed9d3_acm_apply_after_attach.cdr.hex").scene);
  EXPECT_EQ(colour_ids(*scene), expected) << "after the ACM-only apply (the read at 61.668 s had lost plastic_cup)";
}

// The Teacher's request-local, plan-only MoveGroup goal for every segment after the first: planning_scene_diff removes the cup from
// the world (task_reachability.make_move_group_goal). move_group's plan-only branch plans on scene->diff(planning_scene_diff).
TEST(PlanningSceneColour, ThePlanOnlyGoalsRequestLocalRemoveOfTheCupLeavesTheLiveSceneColoursAlone)
{
  auto scene = make_scene();
  apply_scene(*scene, request_from_fixture("pilot_8d9ed9d3_setup_apply.cdr.hex").scene);
  apply_scene(*scene, request_from_fixture("pilot_8d9ed9d3_attach_apply.cdr.hex").scene);
  apply_scene(*scene, request_from_fixture("pilot_8d9ed9d3_acm_apply_after_attach.cdr.hex").scene);
  const std::vector<std::string> expected{ "pedestal", "plastic_cup", "table" };
  ASSERT_EQ(colour_ids(*scene), expected);

  moveit_msgs::msg::PlanningScene diff;
  diff.is_diff = true;
  moveit_msgs::msg::CollisionObject remove;
  remove.header.frame_id = "world";
  remove.id = "plastic_cup";
  remove.operation = moveit_msgs::msg::CollisionObject::REMOVE;
  diff.world.collision_objects.push_back(remove);
  const planning_scene::PlanningScenePtr request_scene = scene->diff(diff);
  EXPECT_EQ(colour_ids(*scene), expected) << "the live scene lost the cup colour to a request-local diff";
  (void)request_scene;
}

TEST(PlanningSceneColour, TheMonitorKeepsTheAttachedCupColourWhileJointStatesArrive)
{
  if (!rclcpp::ok())
  {
    rclcpp::init(0, nullptr);
  }
  rclcpp::NodeOptions options;
  options.parameter_overrides({ rclcpp::Parameter("robot_description", slurp("so101_kinematic_stand_in.urdf")),
                                rclcpp::Parameter("robot_description_semantic", "<robot name=\"so101\"/>") });
  auto node = std::make_shared<rclcpp::Node>("colour_probe", options);
  auto scene = make_scene();
  auto monitor = std::make_shared<planning_scene_monitor::PlanningSceneMonitor>(node, scene, "robot_description");
  monitor->startStateMonitor("/joint_states");
  EXPECT_TRUE(monitor->newPlanningSceneMessage(request_from_fixture("pilot_8d9ed9d3_setup_apply.cdr.hex").scene));
  EXPECT_TRUE(monitor->newPlanningSceneMessage(request_from_fixture("pilot_8d9ed9d3_attach_apply.cdr.hex").scene));
  EXPECT_TRUE(monitor->newPlanningSceneMessage(request_from_fixture("pilot_8d9ed9d3_acm_apply_after_attach.cdr.hex").scene));
  const std::vector<std::string> expected{ "pedestal", "plastic_cup", "table" };
  {
    planning_scene_monitor::LockedPlanningSceneRO locked(monitor);
    ASSERT_EQ(colour_ids(static_cast<const planning_scene::PlanningScene&>(*monitor->getPlanningScene())), expected);
  }
  auto publisher = node->create_publisher<sensor_msgs::msg::JointState>("/joint_states", 10);
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  for (int index = 0; index < 100; ++index)
  {
    sensor_msgs::msg::JointState state;
    state.header.stamp = node->now();
    state.name = { "1", "2", "3", "4", "5", "6" };
    state.position = { 0.0, 0.1 * index * 0.001, 0.0, 0.0, 0.0, 0.0 };
    publisher->publish(state);
    executor.spin_some(std::chrono::milliseconds(5));
  }
  monitor->updateSceneWithCurrentState();
  planning_scene_monitor::LockedPlanningSceneRO locked(monitor);
  EXPECT_EQ(colour_ids(static_cast<const planning_scene::PlanningScene&>(*monitor->getPlanningScene())), expected) << "joint states removed the colour";
}

// move_group's planning scene monitor, with or without publishing /monitored_planning_scene. With publishing the monitor's scene is a diff
// of a parent scene and the publishing thread pushes and clears that diff after every update (scenePublishingThread); MoveIt then loses
// the colour of an attached object. Without publishing there is no diff to push and the colour stays.
void run_attach_acm_sequence_through_a_monitor(bool publishing, const char* node_name, bool stop_publishing_again = false)
{
  if (!rclcpp::ok())
  {
    rclcpp::init(0, nullptr);
  }
  rclcpp::NodeOptions options;
  options.parameter_overrides({ rclcpp::Parameter("robot_description", slurp("so101_kinematic_stand_in.urdf")),
                                rclcpp::Parameter("robot_description_semantic", "<robot name=\"so101\"/>") });
  auto node = std::make_shared<rclcpp::Node>(node_name, options);
  auto scene = make_scene();
  auto monitor = std::make_shared<planning_scene_monitor::PlanningSceneMonitor>(node, scene, "robot_description");
  if (publishing)
  {
    monitor->setPlanningScenePublishingFrequency(4.0);
    monitor->startPublishingPlanningScene(planning_scene_monitor::PlanningSceneMonitor::UPDATE_SCENE,
                                          "monitored_planning_scene");
    if (stop_publishing_again)
    {
      monitor->stopPublishingPlanningScene();
    }
  }
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(node);
  const std::vector<std::string> expected{ "pedestal", "plastic_cup", "table" };
  auto colours = [&]() {
    planning_scene_monitor::LockedPlanningSceneRO locked(monitor);
    return colour_ids(static_cast<const planning_scene::PlanningScene&>(*monitor->getPlanningScene()));
  };
  auto settle = [&](int milliseconds) {
    const auto end = std::chrono::steady_clock::now() + std::chrono::milliseconds(milliseconds);
    while (std::chrono::steady_clock::now() < end)
    {
      executor.spin_some(std::chrono::milliseconds(5));
    }
  };
  EXPECT_TRUE(monitor->newPlanningSceneMessage(request_from_fixture("pilot_8d9ed9d3_setup_apply.cdr.hex").scene));
  settle(600);
  EXPECT_EQ(colours(), expected) << "after SETUP and one publishing period";
  EXPECT_TRUE(monitor->newPlanningSceneMessage(request_from_fixture("pilot_8d9ed9d3_attach_apply.cdr.hex").scene));
  settle(600);
  EXPECT_EQ(colours(), expected) << "after the attach and one publishing period";
  EXPECT_TRUE(monitor->newPlanningSceneMessage(request_from_fixture("pilot_8d9ed9d3_acm_apply_after_attach.cdr.hex").scene));
  settle(600);
  EXPECT_EQ(colours(), expected) << "after the ACM apply and one publishing period";
  settle(600);
  EXPECT_EQ(colours(), expected) << "a second publishing period later";
}

// The configuration of the ACT stack (launch_composition: publish_planning_scene false): the colour stays.
TEST(PlanningSceneColour, AMonitorThatDoesNotPublishKeepsTheAttachedCupColour)
{
  run_attach_acm_sequence_through_a_monitor(false, "colour_probe_quiet");
}

// What graceful_shutdown_move_group does when publish_planning_scene is false: MoveItCpp starts the publishing unconditionally, so the
// executable stops it again before MoveGroupExe takes over. Pilot 429dbf50 (flat launch flags only) still lost the colour.
TEST(PlanningSceneColour, AMonitorWhosePublishingWasStoppedAgainKeepsTheAttachedCupColour)
{
  run_attach_acm_sequence_through_a_monitor(true, "colour_probe_stopped", true);
}

// The reproduction of the pilot's defect (move_group with publish_planning_scene true): disabled because it documents MoveIt's behaviour,
// it is not ours to fix. Run with --gtest_also_run_disabled_tests.
TEST(PlanningSceneColour, DISABLED_APublishingMonitorLosesTheAttachedCupColour)
{
  run_attach_acm_sequence_through_a_monitor(true, "colour_probe_publishing");
}

}  // namespace

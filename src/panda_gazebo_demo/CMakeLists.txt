cmake_minimum_required(VERSION 3.8)
project(panda_gazebo_demo)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(xacro REQUIRED)
find_package(robot_state_publisher REQUIRED)
find_package(ros_gz_sim REQUIRED)
find_package(gz_ros2_control REQUIRED)
find_package(controller_manager REQUIRED)
find_package(joint_state_broadcaster REQUIRED)
find_package(joint_trajectory_controller REQUIRED)
find_package(moveit_resources_panda_description REQUIRED)
find_package(moveit_resources_panda_moveit_config REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(control_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(gz-msgs10 REQUIRED)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

add_library(
  pick_place_core
  src/pick_place/domain_types.cpp
  src/pick_place/state_action.cpp
  src/pick_place/transition_contract.cpp
  src/pick_place/transition_table.cpp
  src/pick_place/runner.cpp
  src/pick_place/common_resume_validator.cpp
  src/pick_place/moveit_world_object_pose.cpp
  src/pick_place/pick_place_target_policy.cpp
  src/pick_place/world_observer.cpp
)
target_compile_features(pick_place_core PUBLIC cxx_std_17)
target_include_directories(
  pick_place_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(pick_place_core moveit_msgs)

add_library(
  pick_place_ros_adapters
  src/pick_place/file_checkpoint_store.cpp
  src/pick_place/gazebo_world_observer.cpp
  src/pick_place/move_above_object_planner.cpp
  src/pick_place/open_gripper_executor.cpp
)
target_link_libraries(
  pick_place_ros_adapters
  pick_place_core
  nlohmann_json::nlohmann_json
  gz-transport13::core
  gz-msgs10::core
)
target_include_directories(
  pick_place_ros_adapters
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(
  pick_place_ros_adapters
  rclcpp
  rclcpp_action
  control_msgs
  geometry_msgs
  moveit_msgs
  moveit_ros_planning_interface
)

add_executable(
  planning_scene_setup
  src/planning_scene_setup.cpp
)

add_executable(
  pre_grasp_plan
  src/pick_place_demo.cpp
)

add_executable(
  attach_and_lift_demo
  src/attach_and_lift_demo.cpp
)

add_executable(
  pick_place_state_machine
  src/nodes/pick_place_state_machine_node.cpp
)

ament_target_dependencies(
  planning_scene_setup
  rclcpp
  geometry_msgs
  shape_msgs
  moveit_msgs
  moveit_ros_planning_interface
)

ament_target_dependencies(
  pre_grasp_plan
  rclcpp
  geometry_msgs
  shape_msgs
  moveit_msgs
  moveit_ros_planning_interface
)

ament_target_dependencies(
  attach_and_lift_demo
  rclcpp
  geometry_msgs
  moveit_msgs
  moveit_ros_planning_interface
)

ament_target_dependencies(
  pick_place_state_machine
  rclcpp
)
target_link_libraries(pick_place_state_machine pick_place_core pick_place_ros_adapters)

if(BUILD_TESTING)
  ament_add_gtest(test_pick_place_core test/pick_place/test_pick_place_core.cpp)
  if(TARGET test_pick_place_core)
    target_link_libraries(test_pick_place_core pick_place_core)
  endif()

  add_test(
    NAME test_reset_coke
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_reset_coke.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reset_coke.sh
  )
endif()

install(
  TARGETS
    pick_place_core
    pick_place_ros_adapters
    planning_scene_setup
    pre_grasp_plan
    attach_and_lift_demo
    pick_place_state_machine
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/ DESTINATION include)

install(
  DIRECTORY
    config
    launch
    urdf
    worlds
  DESTINATION share/${PROJECT_NAME}
)

ament_package()

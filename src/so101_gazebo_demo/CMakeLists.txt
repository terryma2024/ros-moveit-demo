cmake_minimum_required(VERSION 3.22)
project(so101_gazebo_demo)

find_package(ament_cmake REQUIRED)
find_package(control_msgs REQUIRED)
find_package(gz-msgs10 REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(shape_msgs REQUIRED)

add_library(pick_place_core
  src/pick_place/domain_types.cpp
  src/pick_place/file_checkpoint_store.cpp
  src/pick_place/common_resume_validator.cpp
  src/pick_place/plan_validation.cpp
  src/pick_place/state_action.cpp
  src/pick_place/transition_contract.cpp
  src/pick_place/transition_table.cpp
  src/pick_place/runner.cpp
  src/pick_place/simulation_session_id.cpp
  src/pick_place/so101_profile.cpp
  src/pick_place/so101_gripper_validation.cpp
  src/pick_place/follow_joint_trajectory_gripper_adapter.cpp
  src/pick_place/gazebo_attachment_executor.cpp
  src/pick_place/gazebo_world_observer.cpp
  src/pick_place/moveit_scene_adapter.cpp
  src/pick_place/moveit_scene_executor.cpp
  src/pick_place/world_reset_coordinator.cpp
)
target_compile_features(pick_place_core PUBLIC cxx_std_17)
target_include_directories(pick_place_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(pick_place_core PUBLIC nlohmann_json::nlohmann_json gz-msgs10::core gz-transport13::core)
ament_target_dependencies(pick_place_core PUBLIC control_msgs geometry_msgs moveit_msgs
  moveit_ros_planning_interface rclcpp rclcpp_action shape_msgs trajectory_msgs)

add_executable(pick_place_state_machine src/pick_place/pick_place_state_machine.cpp)
target_link_libraries(pick_place_state_machine pick_place_core)

add_executable(gazebo_attachment_state_relay src/nodes/gazebo_attachment_state_relay.cpp)
target_link_libraries(gazebo_attachment_state_relay pick_place_core gz-msgs10::core gz-transport13::core)
ament_target_dependencies(gazebo_attachment_state_relay rclcpp)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_pick_place_dry_run test/pick_place/test_dry_run.cpp)
  target_link_libraries(test_pick_place_dry_run pick_place_core)
  ament_add_gtest(test_pick_place_checkpoint test/pick_place/test_checkpoint.cpp)
  target_link_libraries(test_pick_place_checkpoint pick_place_core)
  ament_add_gtest(test_pick_place_transition_table test/pick_place/test_transition_table.cpp)
  target_link_libraries(test_pick_place_transition_table pick_place_core)
  ament_add_gtest(test_pick_place_runner test/pick_place/test_pick_place_runner.cpp)
  target_link_libraries(test_pick_place_runner pick_place_core)
  ament_add_gtest(test_so101_gripper_adapter test/pick_place/test_so101_gripper_adapter.cpp)
  target_link_libraries(test_so101_gripper_adapter pick_place_core)
  ament_add_gtest(test_so101_gazebo_attachment test/pick_place/test_so101_gazebo_attachment.cpp)
  target_link_libraries(test_so101_gazebo_attachment pick_place_core gz-msgs10::core gz-transport13::core)
  ament_add_gtest(test_so101_moveit_scene test/pick_place/test_so101_moveit_scene.cpp)
  target_link_libraries(test_so101_moveit_scene pick_place_core)
  ament_target_dependencies(test_so101_moveit_scene moveit_msgs shape_msgs)
  ament_add_gtest(test_so101_world_reset test/pick_place/test_so101_world_reset.cpp)
  target_link_libraries(test_so101_world_reset pick_place_core)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_package_layout test/test_package_layout.py)
  ament_add_pytest_test(
    test_gripper_preopen_calc
    test/test_gripper_preopen_calc.py
  )
  ament_add_pytest_test(
    test_so101_pick_place_world
    test/test_so101_pick_place_world.py
  )
  ament_add_pytest_test(
    test_so101_launch_contract
    test/test_so101_launch_contract.py
  )
  ament_add_pytest_test(test_so101_srdf test/test_so101_srdf.py)
  ament_add_pytest_test(
    test_tile_ai_station_guis
    test/test_tile_ai_station_guis.py
  )
  ament_add_pytest_test(
    test_self_containment
    test/test_self_containment.py
  )
  ament_add_pytest_test(
    test_configuration_contract
    test/test_configuration_contract.py
  )
endif()

install(
  TARGETS pick_place_core pick_place_state_machine gazebo_attachment_state_relay
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY include/
  DESTINATION include
)

install(
  DIRECTORY config launch meshes rviz urdf worlds
  DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)

install(
  PROGRAMS
    scripts/gripper_preopen_calc.py
    scripts/tile_ai_station_guis.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()

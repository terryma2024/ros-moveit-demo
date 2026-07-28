cmake_minimum_required(VERSION 3.22)
project(so101_gazebo_demo)

find_package(ament_cmake REQUIRED)
find_package(control_msgs REQUIRED)
find_package(gz-msgs10 REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(std_msgs REQUIRED)

add_library(pick_place_core
  src/pick_place/attachment_state_reducer.cpp
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
  src/pick_place/so101_gripper_state.cpp
  src/pick_place/so101_attachment_contracts.cpp
  src/pick_place/so101_recovery_policy.cpp
  src/pick_place/so101_task3_runtime.cpp
  src/pick_place/pick_place_runtime.cpp
  src/pick_place/so101_motion_validation.cpp
  src/pick_place/so101_motion_evidence_builder.cpp
  src/pick_place/so101_motion_planner.cpp
  src/pick_place/so101_fixed_motion_targets.cpp
  src/pick_place/so101_joint_motion_adapter.cpp
  src/pick_place/moveit_joint_planning_boundary.cpp
  src/pick_place/calibration_cli_options.cpp
  src/pick_place/follow_joint_trajectory_gripper_adapter.cpp
  src/pick_place/gazebo_attachment_executor.cpp
  src/pick_place/gazebo_reset_adapter.cpp
  src/pick_place/gazebo_world_observer.cpp
  src/pick_place/moveit_scene_adapter.cpp
  src/pick_place/moveit_scene_executor.cpp
  src/pick_place/world_reset_coordinator.cpp
  src/pick_place/robot_home_reset_adapter.cpp
)
target_compile_features(pick_place_core PUBLIC cxx_std_17)
target_include_directories(pick_place_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(pick_place_core PUBLIC nlohmann_json::nlohmann_json gz-msgs10::core gz-transport13::core)
ament_target_dependencies(pick_place_core PUBLIC control_msgs geometry_msgs moveit_msgs
  moveit_core moveit_ros_planning_interface rclcpp rclcpp_action sensor_msgs shape_msgs
  trajectory_msgs)

add_executable(pick_place_state_machine src/pick_place/pick_place_state_machine.cpp)
target_link_libraries(pick_place_state_machine pick_place_core)

add_executable(gazebo_attachment_state_relay src/nodes/gazebo_attachment_state_relay.cpp)
target_link_libraries(gazebo_attachment_state_relay pick_place_core gz-msgs10::core gz-transport13::core)
ament_target_dependencies(gazebo_attachment_state_relay rclcpp)

add_executable(reset_so101_world src/nodes/reset_so101_world.cpp)
target_link_libraries(reset_so101_world pick_place_core)
ament_target_dependencies(reset_so101_world rclcpp)

add_executable(so101_moveit_scene src/nodes/so101_moveit_scene.cpp)
target_link_libraries(so101_moveit_scene pick_place_core)
ament_target_dependencies(so101_moveit_scene rclcpp)

add_executable(calibrate_so101_motion src/nodes/calibrate_so101_motion.cpp)
target_link_libraries(calibrate_so101_motion pick_place_core)
ament_target_dependencies(calibrate_so101_motion rclcpp)

add_executable(validate_so101_motion_matrix src/nodes/validate_so101_motion_matrix.cpp)
target_link_libraries(validate_so101_motion_matrix pick_place_core)
ament_target_dependencies(validate_so101_motion_matrix rclcpp)

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
  ament_add_gtest(test_ros_trajectory_action_client
    test/pick_place/test_ros_trajectory_action_client.cpp)
  target_link_libraries(test_ros_trajectory_action_client pick_place_core)
  ament_add_gtest(test_so101_gripper_state test/pick_place/test_so101_gripper_state.cpp)
  target_link_libraries(test_so101_gripper_state pick_place_core)
  ament_add_gtest(test_so101_gazebo_attachment test/pick_place/test_so101_gazebo_attachment.cpp)
  target_link_libraries(test_so101_gazebo_attachment pick_place_core gz-msgs10::core gz-transport13::core)
  ament_add_gtest(test_attachment_state_reducer
    test/pick_place/test_attachment_state_reducer.cpp)
  target_link_libraries(test_attachment_state_reducer pick_place_core)
  ament_add_gtest(test_so101_attachment_contracts
    test/pick_place/test_so101_attachment_contracts.cpp)
  target_link_libraries(test_so101_attachment_contracts pick_place_core)
  ament_add_gtest(test_so101_recovery_policy test/pick_place/test_so101_recovery_policy.cpp)
  target_link_libraries(test_so101_recovery_policy pick_place_core)
  ament_add_gtest(test_so101_pick_place_runtime test/pick_place/test_so101_pick_place_runtime.cpp)
  target_link_libraries(test_so101_pick_place_runtime pick_place_core)
  ament_add_gtest(test_so101_task3_runtime test/pick_place/test_so101_task3_runtime.cpp)
  target_link_libraries(test_so101_task3_runtime pick_place_core)
  ament_add_gtest(test_so101_motion_validation
    test/pick_place/test_so101_motion_validation.cpp)
  target_link_libraries(test_so101_motion_validation pick_place_core)
  ament_add_gtest(test_so101_motion_evidence_builder
    test/pick_place/test_so101_motion_evidence_builder.cpp)
  target_link_libraries(test_so101_motion_evidence_builder pick_place_core)
  ament_add_gtest(test_so101_motion_planner test/pick_place/test_so101_motion_planner.cpp)
  target_link_libraries(test_so101_motion_planner pick_place_core)
  ament_add_gtest(test_so101_fixed_motion_targets
    test/pick_place/test_so101_fixed_motion_targets.cpp)
  target_link_libraries(test_so101_fixed_motion_targets pick_place_core)
  find_program(XACRO_EXECUTABLE xacro REQUIRED)
  set(SO101_TEST_URDF ${CMAKE_CURRENT_BINARY_DIR}/so101_fixed_target_test.urdf)
  add_custom_command(
    OUTPUT ${SO101_TEST_URDF}
    COMMAND ${XACRO_EXECUTABLE} -o ${SO101_TEST_URDF}
      ${CMAKE_CURRENT_SOURCE_DIR}/test/fixtures/so101_robot_model.xacro
      base_height:=0.1899186
    DEPENDS
      ${CMAKE_CURRENT_SOURCE_DIR}/test/fixtures/so101_robot_model.xacro
      ${CMAKE_CURRENT_SOURCE_DIR}/urdf/so101_base.xacro)
  add_custom_target(so101_fixed_target_test_urdf DEPENDS ${SO101_TEST_URDF})
  add_dependencies(test_so101_fixed_motion_targets so101_fixed_target_test_urdf)
  target_compile_definitions(test_so101_fixed_motion_targets PRIVATE
    SO101_TEST_URDF="${SO101_TEST_URDF}"
    SO101_TEST_SRDF="${CMAKE_CURRENT_SOURCE_DIR}/config/so101.srdf")
  ament_add_gtest(test_request_scoped_goal_cancellation
    test/pick_place/test_request_scoped_goal_cancellation.cpp)
  target_link_libraries(test_request_scoped_goal_cancellation pick_place_core)
  ament_add_gtest(test_so101_joint_motion_adapter
    test/pick_place/test_so101_joint_motion_adapter.cpp)
  target_link_libraries(test_so101_joint_motion_adapter pick_place_core)
  ament_add_gtest(test_so101_node_spinner test/pick_place/test_node_spinner.cpp)
  target_link_libraries(test_so101_node_spinner pick_place_core)
  ament_target_dependencies(test_so101_node_spinner rclcpp std_msgs)
  ament_add_gtest(test_so101_calibration_cli_options
    test/pick_place/test_calibration_cli_options.cpp)
  target_link_libraries(test_so101_calibration_cli_options pick_place_core)
  ament_add_gtest(test_so101_moveit_scene test/pick_place/test_so101_moveit_scene.cpp)
  target_link_libraries(test_so101_moveit_scene pick_place_core)
  ament_target_dependencies(test_so101_moveit_scene moveit_msgs shape_msgs)
  ament_add_gtest(test_so101_world_reset test/pick_place/test_so101_world_reset.cpp)
  target_link_libraries(test_so101_world_reset pick_place_core)
  ament_add_gtest(test_robot_home_reset_adapter
    test/pick_place/test_robot_home_reset_adapter.cpp)
  target_link_libraries(test_robot_home_reset_adapter pick_place_core)
  ament_add_gtest(test_so101_gazebo_reset_adapter
    test/pick_place/test_so101_gazebo_reset_adapter.cpp)
  target_link_libraries(test_so101_gazebo_reset_adapter pick_place_core
    gz-msgs10::core gz-transport13::core)
  add_test(NAME test_so101_reset_cli
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_so101_reset_cli.sh
      $<TARGET_FILE:reset_so101_world> $<TARGET_FILE:so101_moveit_scene>)
  add_test(NAME test_so101_calibration_cli
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_so101_calibration_cli.sh
      $<TARGET_FILE:calibrate_so101_motion>)
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
  ament_add_pytest_test(
    test_prepare_simulation_model
    test/test_prepare_simulation_model.py
  )
endif()

install(
  TARGETS pick_place_core pick_place_state_machine gazebo_attachment_state_relay
    reset_so101_world so101_moveit_scene
    calibrate_so101_motion validate_so101_motion_matrix
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY include/
  DESTINATION include
)

install(
  DIRECTORY config launch meshes rviz scripts urdf worlds
  DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)

install(
  PROGRAMS
    scripts/gripper_preopen_calc.py
    scripts/prepare_simulation_model.py
    scripts/tile_ai_station_guis.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()

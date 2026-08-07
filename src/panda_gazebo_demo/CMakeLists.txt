cmake_minimum_required(VERSION 3.8)
project(panda_gazebo_demo)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

get_filename_component(
  PANDA_GAZEBO_DEMO_WORKSPACE_ROOT
  "${CMAKE_CURRENT_SOURCE_DIR}/../.."
  REALPATH
)
find_program(
  RUN_CLANG_TIDY_EXECUTABLE
  NAMES run-clang-tidy run-clang-tidy-18 run-clang-tidy-17 run-clang-tidy-16
  DOC "Path to run-clang-tidy for the required C++ quality gate"
)
if(NOT RUN_CLANG_TIDY_EXECUTABLE)
  message(FATAL_ERROR
          "RUN_CLANG_TIDY_EXECUTABLE is required for the C++ quality gate. "
          "Install run-clang-tidy or set -DRUN_CLANG_TIDY_EXECUTABLE=/path/to/run-clang-tidy.")
endif()
find_program(
  CLANG_FORMAT_EXECUTABLE
  NAMES clang-format clang-format-18 clang-format-17 clang-format-16
  DOC "Path to clang-format for the required C++ quality gate"
)
if(NOT CLANG_FORMAT_EXECUTABLE)
  message(FATAL_ERROR
          "CLANG_FORMAT_EXECUTABLE is required for the C++ quality gate. "
          "Install clang-format or set -DCLANG_FORMAT_EXECUTABLE=/path/to/clang-format.")
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(pick_place_common REQUIRED)
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
find_package(moveit_core REQUIRED)
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
  # Register cppcheck explicitly below so its bundled GoogleTest model is loaded.
  # Without it cppcheck 2.13 reports TEST(...) declarations as syntax errors.
  # clang-format is enforced by pick_place_common_add_cpp_quality_gate; avoid the
  # incompatible ament_uncrustify formatter running over the same C++ sources.
  list(APPEND AMENT_LINT_AUTO_EXCLUDE ament_cmake_cppcheck ament_cmake_uncrustify)
  ament_lint_auto_find_test_dependencies()
endif()

add_library(
  panda_pick_place_runtime
  src/pick_place/motion_plan_evidence.cpp
  src/pick_place/gripper_state_executor.cpp
  src/pick_place/motion_state_action.cpp
  src/pick_place/named_target_validation.cpp
  src/pick_place/panda_workflow.cpp
  src/pick_place/pick_place_contracts.cpp
  src/pick_place/pick_place_runtime.cpp
  src/pick_place/recovery_contracts.cpp
  src/pick_place/recovery_policy.cpp
  src/pick_place/ready_retreat_action.cpp
  src/pick_place/state_validation.cpp
  src/pick_place/transition_contract.cpp
  src/pick_place/transition_table.cpp
  src/pick_place/runtime_parameters.cpp
  src/pick_place/common_resume_validator.cpp
  src/pick_place/panda_resume_validation_policy.cpp
  src/pick_place/panda_moveit_scene_policy.cpp
  src/pick_place/moveit_world_object_pose.cpp
  src/pick_place/moveit_world_resetter.cpp
  src/pick_place/pick_place_target_policy.cpp
)
target_compile_features(panda_pick_place_runtime PUBLIC cxx_std_17)
target_link_libraries(panda_pick_place_runtime pick_place_common::core
  pick_place_common::ros_adapters)
target_include_directories(
  panda_pick_place_runtime
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(panda_pick_place_runtime moveit_msgs)

add_library(
  panda_pick_place_ros_adapters
  src/pick_place/file_checkpoint_store.cpp
  src/pick_place/gazebo_world_observer.cpp
  src/pick_place/gripper_command_adapter.cpp
  src/pick_place/moveit_scene_adapter.cpp
  src/pick_place/moveit_motion_adapter.cpp
)
target_link_libraries(
  panda_pick_place_ros_adapters
  panda_pick_place_runtime
  pick_place_common::ros_adapters
  nlohmann_json::nlohmann_json
  gz-transport13::core
  gz-msgs10::core
)
target_include_directories(
  panda_pick_place_ros_adapters
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(
  panda_pick_place_ros_adapters
  rclcpp
  rclcpp_action
  control_msgs
  geometry_msgs
  moveit_core
  moveit_msgs
  moveit_ros_planning_interface
  shape_msgs
)

add_executable(
  pick_place_state_machine
  src/nodes/pick_place_state_machine_node.cpp
)

add_executable(
  gazebo_attachment_state_relay
  src/nodes/gazebo_attachment_state_relay.cpp
)

add_executable(
  reset_moveit_world
  src/nodes/reset_moveit_world.cpp
)


ament_target_dependencies(
  pick_place_state_machine
  rclcpp
)
target_link_libraries(pick_place_state_machine panda_pick_place_runtime panda_pick_place_ros_adapters)

ament_target_dependencies(gazebo_attachment_state_relay rclcpp)
target_link_libraries(
  gazebo_attachment_state_relay
  gz-transport13::core
  gz-msgs10::core
)

ament_target_dependencies(reset_moveit_world rclcpp)
target_link_libraries(reset_moveit_world panda_pick_place_runtime panda_pick_place_ros_adapters)

pick_place_common_add_cpp_quality_gate(
  WORKSPACE_ROOT ${PANDA_GAZEBO_DEMO_WORKSPACE_ROOT}
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}
  RUN_CLANG_TIDY_EXECUTABLE ${RUN_CLANG_TIDY_EXECUTABLE}
  CLANG_FORMAT_EXECUTABLE ${CLANG_FORMAT_EXECUTABLE}
  TARGETS
    panda_pick_place_runtime
    panda_pick_place_ros_adapters
    pick_place_state_machine
    gazebo_attachment_state_relay
    reset_moveit_world
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_source_manifest test/test_source_manifest.py)
  ament_add_pytest_test(test_panda_launch_contract test/test_panda_launch_contract.py)

  ament_add_gtest(
    test_workflow_characterization
    test/pick_place/test_workflow_characterization.cpp
  )
  if(TARGET test_workflow_characterization)
    target_link_libraries(test_workflow_characterization panda_pick_place_runtime)
  endif()

  ament_add_gtest(test_pick_place_core test/pick_place/test_pick_place_core.cpp)
  if(TARGET test_pick_place_core)
    target_link_libraries(test_pick_place_core panda_pick_place_runtime panda_pick_place_ros_adapters)
  endif()

  ament_add_gtest(
    test_simulation_session_id
    test/pick_place/test_simulation_session_id.cpp
  )
  if(TARGET test_simulation_session_id)
    target_link_libraries(test_simulation_session_id panda_pick_place_runtime)
  endif()

  ament_add_gtest(test_pick_place_targets test/pick_place/test_pick_place_targets.cpp)
  if(TARGET test_pick_place_targets)
    target_link_libraries(test_pick_place_targets panda_pick_place_runtime)
  endif()

  ament_add_gtest(test_recovery_policy test/pick_place/test_recovery_policy.cpp)
  if(TARGET test_recovery_policy)
    target_link_libraries(test_recovery_policy panda_pick_place_runtime)
  endif()

  ament_add_gtest(test_checkpoint_v3 test/pick_place/test_checkpoint_v3.cpp)
  if(TARGET test_checkpoint_v3)
    target_link_libraries(test_checkpoint_v3 panda_pick_place_runtime panda_pick_place_ros_adapters)
  endif()

  ament_add_gtest(test_state_validation test/pick_place/test_state_validation.cpp)
  if(TARGET test_state_validation)
    target_link_libraries(test_state_validation panda_pick_place_runtime)
  endif()

  ament_add_gtest(test_gripper_state_executor test/pick_place/test_gripper_state_executor.cpp)
  if(TARGET test_gripper_state_executor)
    target_link_libraries(test_gripper_state_executor panda_pick_place_runtime)
  endif()

  ament_add_gtest(
    test_gripper_command_adapter
    test/pick_place/test_gripper_command_adapter.cpp
  )
  if(TARGET test_gripper_command_adapter)
    target_link_libraries(
      test_gripper_command_adapter
      panda_pick_place_runtime
      panda_pick_place_ros_adapters
    )
    ament_target_dependencies(
      test_gripper_command_adapter
      rclcpp
      rclcpp_action
      control_msgs
    )
  endif()

  ament_add_gtest(
    test_gazebo_attachment_executor
    test/pick_place/test_gazebo_attachment_executor.cpp
  )
  if(TARGET test_gazebo_attachment_executor)
    target_link_libraries(
      test_gazebo_attachment_executor
      panda_pick_place_runtime
      panda_pick_place_ros_adapters
    )
  endif()

  ament_add_gtest(
    test_gazebo_world_observer
    test/pick_place/test_gazebo_world_observer.cpp
  )
  if(TARGET test_gazebo_world_observer)
    target_link_libraries(
      test_gazebo_world_observer
      panda_pick_place_runtime
      panda_pick_place_ros_adapters
    )
  endif()

  ament_add_gtest(
    test_moveit_scene_executor
    test/pick_place/test_moveit_scene_executor.cpp
  )
  if(TARGET test_moveit_scene_executor)
    target_link_libraries(test_moveit_scene_executor panda_pick_place_runtime)
  endif()

  ament_add_gtest(
    test_moveit_world_resetter
    test/pick_place/test_moveit_world_resetter.cpp
  )
  if(TARGET test_moveit_world_resetter)
    target_link_libraries(test_moveit_world_resetter panda_pick_place_runtime)
  endif()

  ament_add_gtest(
    test_motion_plan_validation
    test/pick_place/test_motion_plan_validation.cpp
  )
  if(TARGET test_motion_plan_validation)
    target_link_libraries(
      test_motion_plan_validation
      panda_pick_place_runtime
      panda_pick_place_ros_adapters
    )
  endif()

  ament_add_gtest(
    test_motion_state_action
    test/pick_place/test_motion_state_action.cpp
  )
  if(TARGET test_motion_state_action)
    target_link_libraries(test_motion_state_action panda_pick_place_runtime)
  endif()
  ament_add_gtest(
    test_ready_retreat_action
    test/pick_place/test_ready_retreat_action.cpp
  )
  if(TARGET test_ready_retreat_action)
    target_link_libraries(test_ready_retreat_action panda_pick_place_runtime)
  endif()

  ament_add_gtest(
    test_forward_contracts
    test/pick_place/test_forward_contracts.cpp
  )
  if(TARGET test_forward_contracts)
    target_link_libraries(test_forward_contracts panda_pick_place_runtime)
  endif()

  ament_add_gtest(
    test_recovery_workflow
    test/pick_place/test_recovery_workflow.cpp
  )
  if(TARGET test_recovery_workflow)
    target_link_libraries(
      test_recovery_workflow
      panda_pick_place_runtime
      panda_pick_place_ros_adapters
    )
  endif()

  ament_add_gtest(
    test_registration_coverage
    test/pick_place/test_registration_coverage.cpp
  )
  if(TARGET test_registration_coverage)
    target_link_libraries(test_registration_coverage panda_pick_place_runtime)
  endif()

  add_test(
    NAME test_reset_world
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_reset_world.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/scripts/reset_world.sh
  )

  add_test(
    NAME test_world_reset_caller_migration
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_world_reset_caller_migration.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/launch/panda_gazebo.launch.py
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/run_pick_place_e2e.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/run_recovery_scenarios.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/run_plan_only_resume_matrix.sh
  )

  add_test(
    NAME test_cpp_quality_gate
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_cpp_quality_gate.sh
      ${pick_place_common_DIR}/run_cpp_quality_gate.cmake
      ${pick_place_common_DIR}/cpp_quality_gate.cmake
  )

  add_test(
    NAME test_assert_reset_moveit_scene
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/test_assert_reset_moveit_scene.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/assert_reset_moveit_scene.py
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/fixtures/snapshot_planning_scene.txt
  )

  add_test(
    NAME test_reset_moveit_world_cli
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_reset_moveit_world_cli.sh
      $<TARGET_FILE:reset_moveit_world>
  )

  add_test(
    NAME test_attachment_state_relay
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/test_attachment_state_relay.sh
      $<TARGET_FILE:gazebo_attachment_state_relay>
  )

  add_test(
    NAME test_assert_pick_place_log
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/test_assert_pick_place_log.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/assert_pick_place_log.py
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/fixtures
  )

  add_test(
    NAME test_assert_pick_place_snapshot
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/test_assert_pick_place_snapshot.sh
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/assert_pick_place_snapshot.py
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/fixtures
  )

  add_test(
    NAME test_plan_only_resume_helpers
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/headless/test_plan_only_resume_helpers.sh
  )

  ament_cppcheck(
    LIBRARIES googletest
    INCLUDE_DIRS ${CMAKE_CURRENT_SOURCE_DIR}/include
  )
endif()

install(
  TARGETS
    panda_pick_place_runtime
    panda_pick_place_ros_adapters
    pick_place_state_machine
    gazebo_attachment_state_relay
    reset_moveit_world
  DESTINATION lib/${PROJECT_NAME}
)

install(DIRECTORY include/ DESTINATION include)

install(
  PROGRAMS scripts/reset_world.sh
  DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY
    config
    launch
    urdf
    worlds
  DESTINATION share/${PROJECT_NAME}
)

ament_package()

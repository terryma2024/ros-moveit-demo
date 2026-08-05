cmake_minimum_required(VERSION 3.22)
project(so101_gazebo_demo)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

get_filename_component(
  SO101_GAZEBO_DEMO_WORKSPACE_ROOT
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

find_package(ament_cmake REQUIRED)
find_package(pick_place_common REQUIRED)
find_package(ament_cmake_python REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(OpenSSL REQUIRED)
find_package(control_msgs REQUIRED)
find_package(gz-msgs10 REQUIRED)
find_package(gz-plugin2 REQUIRED)
find_package(gz-sim8 REQUIRED)
find_package(gz-transport13 REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_msgs REQUIRED)
find_package(moveit_core REQUIRED)
find_package(moveit_ros_planning REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(nlohmann_json REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(sensor_msgs REQUIRED)
find_package(trajectory_msgs REQUIRED)
find_package(shape_msgs REQUIRED)
find_package(std_msgs REQUIRED)
find_package(yaml-cpp REQUIRED)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# The Teleop frontend uses Bun consistently for dependency resolution and scripts.
if(DEFINED ENV{SO101_TELEOP_BUN})
  set(BUN_EXECUTABLE "$ENV{SO101_TELEOP_BUN}")
elseif(EXISTS "/home/lenovo/.bun/bin/bun")
  set(BUN_EXECUTABLE "/home/lenovo/.bun/bin/bun")
else()
  find_program(BUN_EXECUTABLE bun REQUIRED)
endif()
if(NOT EXISTS "${BUN_EXECUTABLE}")
  message(FATAL_ERROR "Bun is required; set SO101_TELEOP_BUN to its executable")
endif()
get_filename_component(SO101_TELEOP_BUN_BIN "${BUN_EXECUTABLE}" DIRECTORY)

# The production FastAPI server serves this Vite bundle from the installed
# package. Keep it generated (never committed) while making a clean colcon
# build reproduce it under the project Bun toolchain.
set(SO101_TELEOP_WEB_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/web)
set(SO101_TELEOP_WEB_INDEX ${SO101_TELEOP_WEB_ROOT}/dist/index.html)
file(GLOB_RECURSE SO101_TELEOP_WEB_SOURCES CONFIGURE_DEPENDS
  ${SO101_TELEOP_WEB_ROOT}/src/*.ts
  ${SO101_TELEOP_WEB_ROOT}/src/*.tsx
  ${SO101_TELEOP_WEB_ROOT}/e2e/*.ts
)
add_custom_command(
  OUTPUT ${SO101_TELEOP_WEB_INDEX}
  COMMAND ${CMAKE_COMMAND} -E env "PATH=${SO101_TELEOP_BUN_BIN}:$ENV{PATH}" ${BUN_EXECUTABLE} install --frozen-lockfile
  COMMAND ${CMAKE_COMMAND} -E env "PATH=${SO101_TELEOP_BUN_BIN}:$ENV{PATH}" ${BUN_EXECUTABLE} run build
  WORKING_DIRECTORY ${SO101_TELEOP_WEB_ROOT}
  DEPENDS ${SO101_TELEOP_WEB_ROOT}/package.json ${SO101_TELEOP_WEB_ROOT}/bun.lock
    ${SO101_TELEOP_WEB_ROOT}/vite.config.ts ${SO101_TELEOP_WEB_ROOT}/tailwind.config.ts
    ${SO101_TELEOP_WEB_ROOT}/postcss.config.cjs ${SO101_TELEOP_WEB_SOURCES}
  VERBATIM)
add_custom_target(so101_teleop_web ALL DEPENDS ${SO101_TELEOP_WEB_INDEX})

set(SO101_FINGERTIP_PAD_ASSET_DIR ${CMAKE_CURRENT_BINARY_DIR}/fingertip_pad_assets)
set(SO101_FINGERTIP_PAD_MANIFEST ${SO101_FINGERTIP_PAD_ASSET_DIR}/fixed/manifest.yaml)
add_custom_command(
  OUTPUT ${SO101_FINGERTIP_PAD_MANIFEST}
  COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate_fingertip_pad_meshes.py
    --config ${CMAKE_CURRENT_SOURCE_DIR}/config/task_objects/light_plastic_cup.yaml
    --output-root ${SO101_FINGERTIP_PAD_ASSET_DIR}
  DEPENDS
    ${CMAKE_CURRENT_SOURCE_DIR}/scripts/generate_fingertip_pad_meshes.py
    ${CMAKE_CURRENT_SOURCE_DIR}/config/task_objects/light_plastic_cup.yaml
  VERBATIM)
add_custom_target(so101_fingertip_pad_assets ALL DEPENDS ${SO101_FINGERTIP_PAD_MANIFEST})

add_library(so101_pick_place_runtime
  src/pick_place/attachment_state_reducer.cpp
  src/pick_place/file_checkpoint_store.cpp
  src/pick_place/common_resume_validator.cpp
  src/pick_place/so101_resume_validation_policy.cpp
  src/pick_place/so101_runner_behavior_policy.cpp
  src/pick_place/so101_moveit_scene_policy.cpp
  src/pick_place/so101_workflow.cpp
  src/pick_place/policy_config.cpp
  src/pick_place/physical_grasp_validator.cpp
  src/pick_place/physical_grasp_evidence_store.cpp
  src/pick_place/planning_failure_diagnostics.cpp
  src/pick_place/transition_table.cpp
  src/pick_place/so101_profile.cpp
  src/pick_place/so101_gripper_validation.cpp
  src/pick_place/so101_gripper_state.cpp
  src/pick_place/support_pose.cpp
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
  src/pick_place/gazebo_reset_adapter.cpp
  src/pick_place/gazebo_world_observer.cpp
  src/pick_place/world_readiness_gate.cpp
  src/pick_place/moveit_scene_adapter.cpp
  src/pick_place/moveit_scene_initializer.cpp
  src/pick_place/world_reset_coordinator.cpp
  src/pick_place/robot_home_reset_adapter.cpp
)
target_compile_features(so101_pick_place_runtime PUBLIC cxx_std_17)
target_include_directories(so101_pick_place_runtime PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(so101_pick_place_runtime PUBLIC pick_place_common::core pick_place_common::ros_adapters
  nlohmann_json::nlohmann_json OpenSSL::Crypto yaml-cpp gz-msgs10::core gz-transport13::core)
ament_target_dependencies(so101_pick_place_runtime PUBLIC control_msgs geometry_msgs moveit_msgs
  moveit_core moveit_ros_planning_interface rclcpp rclcpp_action sensor_msgs shape_msgs
  trajectory_msgs)

add_library(so101_workspace_sampling
  src/workspace/joint_sample_generator.cpp
  src/workspace/pose_coverage_index.cpp
  src/workspace/workspace_state_evaluator.cpp
  src/workspace/workspace_artifact_writer.cpp
  src/workspace/workspace_checkpoint_store.cpp
  src/workspace/workspace_sampler.cpp
  src/workspace/workspace_types.cpp
)
target_compile_features(so101_workspace_sampling PUBLIC cxx_std_17)
target_include_directories(so101_workspace_sampling PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(so101_workspace_sampling PUBLIC so101_pick_place_runtime)

add_executable(pick_place_state_machine src/pick_place/pick_place_state_machine.cpp)
target_link_libraries(pick_place_state_machine so101_pick_place_runtime)
ament_target_dependencies(pick_place_state_machine ament_index_cpp)

add_executable(gazebo_attachment_state_relay src/nodes/gazebo_attachment_state_relay.cpp)
target_link_libraries(gazebo_attachment_state_relay so101_pick_place_runtime gz-msgs10::core gz-transport13::core)
ament_target_dependencies(gazebo_attachment_state_relay rclcpp std_msgs)

add_executable(reset_so101_world src/nodes/reset_so101_world.cpp)
target_link_libraries(reset_so101_world so101_pick_place_runtime)
ament_target_dependencies(reset_so101_world ament_index_cpp rclcpp)

add_executable(so101_moveit_scene src/nodes/so101_moveit_scene.cpp)
target_link_libraries(so101_moveit_scene so101_pick_place_runtime)
ament_target_dependencies(so101_moveit_scene rclcpp)

add_executable(calibrate_so101_motion src/nodes/calibrate_so101_motion.cpp)
target_link_libraries(calibrate_so101_motion so101_pick_place_runtime)
ament_target_dependencies(calibrate_so101_motion rclcpp)

add_executable(validate_so101_motion_matrix src/nodes/validate_so101_motion_matrix.cpp)
target_link_libraries(validate_so101_motion_matrix so101_pick_place_runtime)
ament_target_dependencies(validate_so101_motion_matrix ament_index_cpp rclcpp)

add_executable(sample_so101_workspace src/nodes/sample_so101_workspace.cpp)
target_link_libraries(sample_so101_workspace so101_workspace_sampling so101_pick_place_runtime)
ament_target_dependencies(sample_so101_workspace ament_index_cpp moveit_core moveit_ros_planning rclcpp)

add_library(so101_attachment_collision_system SHARED
  src/gazebo/attachment_collision_system.cpp)
target_compile_features(so101_attachment_collision_system PUBLIC cxx_std_17)
target_link_libraries(so101_attachment_collision_system
  gz-msgs10::core gz-plugin2::gz-plugin2 gz-sim8::gz-sim8 gz-transport13::core)

pick_place_common_add_cpp_quality_gate(
  WORKSPACE_ROOT ${SO101_GAZEBO_DEMO_WORKSPACE_ROOT}
  SOURCE_ROOT ${CMAKE_CURRENT_SOURCE_DIR}
  RUN_CLANG_TIDY_EXECUTABLE ${RUN_CLANG_TIDY_EXECUTABLE}
  CLANG_FORMAT_EXECUTABLE ${CLANG_FORMAT_EXECUTABLE}
  # These tracked headers are byte-for-byte outputs of gripper_preopen_calc.py.
  # Their regeneration tests, rather than clang-format, define canonical form.
  EXCLUDE_FILES
    include/so101_gazebo_demo/pick_place/fingertip_pad_gap_calibration_data.hpp
    include/so101_gazebo_demo/pick_place/gripper_width_calibration_data.hpp
  TARGETS
    so101_workspace_sampling
    so101_pick_place_runtime
    pick_place_state_machine
    gazebo_attachment_state_relay
    reset_so101_world
    so101_moveit_scene
    calibrate_so101_motion
    validate_so101_motion_matrix
    sample_so101_workspace
    so101_attachment_collision_system
)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_workspace_types test/workspace/test_workspace_types.cpp)
  target_link_libraries(test_workspace_types so101_workspace_sampling)
  ament_add_gtest(test_joint_sample_generator test/workspace/test_joint_sample_generator.cpp)
  target_link_libraries(test_joint_sample_generator so101_workspace_sampling)
  ament_add_gtest(test_pose_coverage_index test/workspace/test_pose_coverage_index.cpp)
  target_link_libraries(test_pose_coverage_index so101_workspace_sampling)
  ament_add_gtest(test_workflow_characterization test/pick_place/test_workflow_characterization.cpp)
  target_link_libraries(test_workflow_characterization so101_pick_place_runtime)
  ament_add_gtest(test_pick_place_dry_run test/pick_place/test_dry_run.cpp)
  target_link_libraries(test_pick_place_dry_run so101_pick_place_runtime)
  ament_add_gtest(test_pick_place_checkpoint test/pick_place/test_checkpoint.cpp)
  target_link_libraries(test_pick_place_checkpoint so101_pick_place_runtime)
  ament_add_gtest(test_pick_place_transition_table test/pick_place/test_transition_table.cpp)
  target_link_libraries(test_pick_place_transition_table so101_pick_place_runtime)
  ament_add_gtest(test_pick_place_runner test/pick_place/test_pick_place_runner.cpp)
  target_link_libraries(test_pick_place_runner so101_pick_place_runtime)
  ament_add_gtest(test_physical_grasp_validator test/pick_place/test_physical_grasp_validator.cpp)
  target_link_libraries(test_physical_grasp_validator so101_pick_place_runtime)
  ament_add_gtest(test_physical_grasp_evidence_store test/pick_place/test_physical_grasp_evidence_store.cpp)
  target_link_libraries(test_physical_grasp_evidence_store so101_pick_place_runtime)
  ament_add_gtest(test_so101_gripper_adapter test/pick_place/test_so101_gripper_adapter.cpp)
  target_link_libraries(test_so101_gripper_adapter so101_pick_place_runtime)
  ament_add_gtest(test_ros_trajectory_action_client
    test/pick_place/test_ros_trajectory_action_client.cpp)
  target_link_libraries(test_ros_trajectory_action_client so101_pick_place_runtime)
  ament_add_gtest(test_so101_gripper_state test/pick_place/test_so101_gripper_state.cpp)
  target_link_libraries(test_so101_gripper_state so101_pick_place_runtime)
  ament_add_gtest(test_support_pose test/pick_place/test_support_pose.cpp)
  target_link_libraries(test_support_pose so101_pick_place_runtime)
  ament_add_gtest(test_so101_gazebo_attachment test/pick_place/test_so101_gazebo_attachment.cpp)
  target_link_libraries(test_so101_gazebo_attachment so101_pick_place_runtime gz-msgs10::core gz-transport13::core)
  ament_add_gtest(test_attachment_state_reducer
    test/pick_place/test_attachment_state_reducer.cpp)
  target_link_libraries(test_attachment_state_reducer so101_pick_place_runtime)
  ament_add_gtest(test_so101_attachment_contracts
    test/pick_place/test_so101_attachment_contracts.cpp)
  target_link_libraries(test_so101_attachment_contracts so101_pick_place_runtime)
  ament_add_gtest(test_so101_recovery_policy test/pick_place/test_so101_recovery_policy.cpp)
  target_link_libraries(test_so101_recovery_policy so101_pick_place_runtime)
  ament_add_gtest(test_so101_pick_place_runtime test/pick_place/test_so101_pick_place_runtime.cpp)
  target_link_libraries(test_so101_pick_place_runtime so101_pick_place_runtime)
  target_compile_definitions(test_so101_pick_place_runtime PRIVATE
    SO101_TEST_POLICY_CONFIG_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/config")
  ament_add_gtest(test_so101_task3_runtime test/pick_place/test_so101_task3_runtime.cpp)
  target_link_libraries(test_so101_task3_runtime so101_pick_place_runtime)
  ament_add_gtest(test_so101_motion_validation
    test/pick_place/test_so101_motion_validation.cpp)
  target_link_libraries(test_so101_motion_validation so101_pick_place_runtime)
  ament_add_gtest(test_so101_motion_evidence_builder
    test/pick_place/test_so101_motion_evidence_builder.cpp)
  target_link_libraries(test_so101_motion_evidence_builder so101_pick_place_runtime)
  ament_add_gtest(test_so101_motion_planner test/pick_place/test_so101_motion_planner.cpp)
  target_link_libraries(test_so101_motion_planner so101_pick_place_runtime)
  ament_add_gtest(test_so101_fixed_motion_targets
    test/pick_place/test_so101_fixed_motion_targets.cpp)
  target_link_libraries(test_so101_fixed_motion_targets so101_pick_place_runtime)
  ament_add_gtest(test_policy_config test/pick_place/test_policy_config.cpp)
  target_link_libraries(test_policy_config so101_pick_place_runtime)
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
    SO101_TEST_SRDF="${CMAKE_CURRENT_SOURCE_DIR}/config/so101.srdf"
    SO101_TEST_POLICY_CONFIG_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/config")
  ament_add_gtest(test_workspace_state_evaluator
    test/workspace/test_workspace_state_evaluator.cpp)
  target_link_libraries(test_workspace_state_evaluator so101_workspace_sampling)
  add_dependencies(test_workspace_state_evaluator so101_fixed_target_test_urdf)
  target_compile_definitions(test_workspace_state_evaluator PRIVATE
    SO101_TEST_URDF="${SO101_TEST_URDF}"
    SO101_TEST_SRDF="${CMAKE_CURRENT_SOURCE_DIR}/config/so101.srdf")
  ament_add_gtest(test_workspace_artifact_writer
    test/workspace/test_workspace_artifact_writer.cpp)
  target_link_libraries(test_workspace_artifact_writer so101_workspace_sampling)
  ament_add_gtest(test_workspace_checkpoint_store
    test/workspace/test_workspace_checkpoint_store.cpp)
  target_link_libraries(test_workspace_checkpoint_store so101_workspace_sampling)
  ament_add_gtest(test_workspace_sampler test/workspace/test_workspace_sampler.cpp)
  target_link_libraries(test_workspace_sampler so101_workspace_sampling)
  add_dependencies(test_workspace_sampler so101_fixed_target_test_urdf)
  target_compile_definitions(test_workspace_sampler PRIVATE
    SO101_TEST_URDF="${SO101_TEST_URDF}"
    SO101_TEST_SRDF="${CMAKE_CURRENT_SOURCE_DIR}/config/so101.srdf")
  ament_add_gtest(test_workspace_sampler_integration
    test/workspace/test_workspace_sampler_integration.cpp)
  target_link_libraries(test_workspace_sampler_integration so101_workspace_sampling)
  add_dependencies(test_workspace_sampler_integration so101_fixed_target_test_urdf)
  target_compile_definitions(test_workspace_sampler_integration PRIVATE
    SO101_TEST_URDF="${SO101_TEST_URDF}"
    SO101_TEST_SRDF="${CMAKE_CURRENT_SOURCE_DIR}/config/so101.srdf")
  set_tests_properties(test_workspace_sampler_integration PROPERTIES TIMEOUT 300)
  ament_add_gtest(test_request_scoped_goal_cancellation
    test/pick_place/test_request_scoped_goal_cancellation.cpp)
  target_link_libraries(test_request_scoped_goal_cancellation so101_pick_place_runtime)
  ament_add_gtest(test_planning_failure_diagnostics
    test/pick_place/test_planning_failure_diagnostics.cpp)
  target_link_libraries(test_planning_failure_diagnostics so101_pick_place_runtime)
  ament_add_gtest(test_so101_joint_motion_adapter
    test/pick_place/test_so101_joint_motion_adapter.cpp)
  target_link_libraries(test_so101_joint_motion_adapter so101_pick_place_runtime)
  ament_add_gtest(test_so101_node_spinner test/pick_place/test_node_spinner.cpp)
  target_link_libraries(test_so101_node_spinner so101_pick_place_runtime)
  ament_target_dependencies(test_so101_node_spinner rclcpp std_msgs)
  ament_add_gtest(test_so101_calibration_cli_options
    test/pick_place/test_calibration_cli_options.cpp)
  target_link_libraries(test_so101_calibration_cli_options so101_pick_place_runtime)
  ament_add_gtest(test_so101_moveit_scene test/pick_place/test_so101_moveit_scene.cpp)
  target_link_libraries(test_so101_moveit_scene so101_pick_place_runtime)
  ament_target_dependencies(test_so101_moveit_scene moveit_msgs shape_msgs)
  ament_add_gtest(test_moveit_scene_initializer test/pick_place/test_moveit_scene_initializer.cpp)
  target_link_libraries(test_moveit_scene_initializer so101_pick_place_runtime)
  ament_target_dependencies(test_moveit_scene_initializer moveit_msgs shape_msgs)
  ament_add_gtest(test_world_readiness_gate test/pick_place/test_world_readiness_gate.cpp)
  target_link_libraries(test_world_readiness_gate so101_pick_place_runtime)
  ament_add_gtest(test_so101_world_reset test/pick_place/test_so101_world_reset.cpp)
  target_link_libraries(test_so101_world_reset so101_pick_place_runtime)
  ament_add_gtest(test_robot_home_reset_adapter
    test/pick_place/test_robot_home_reset_adapter.cpp)
  target_link_libraries(test_robot_home_reset_adapter so101_pick_place_runtime)
  ament_add_gtest(test_so101_gazebo_reset_adapter
    test/pick_place/test_so101_gazebo_reset_adapter.cpp)
  target_link_libraries(test_so101_gazebo_reset_adapter so101_pick_place_runtime
    gz-msgs10::core gz-transport13::core)
  add_test(NAME test_so101_reset_cli
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_so101_reset_cli.sh
      $<TARGET_FILE:reset_so101_world> $<TARGET_FILE:so101_moveit_scene>)
  add_test(NAME test_so101_calibration_cli
    COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_so101_calibration_cli.sh
      $<TARGET_FILE:calibrate_so101_motion>)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_package_layout test/test_package_layout.py)
  ament_add_pytest_test(test_workspace_launch_contract test/test_workspace_launch_contract.py)
  ament_add_pytest_test(test_source_manifest test/test_source_manifest.py)
  ament_add_pytest_test(
    test_gripper_preopen_calc
    test/test_gripper_preopen_calc.py
  )
  ament_add_pytest_test(
    test_so101_pick_place_world
    test/test_so101_pick_place_world.py
    TIMEOUT 300
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
    test_ai_station_x11
    test/test_ai_station_x11.py
  )
  ament_add_pytest_test(
    test_gazebo_camera_pose
    test/test_gazebo_camera_pose.py
  )
  ament_add_pytest_test(
    test_so101_stack_inventory
    test/test_so101_stack_inventory.py
  )
  ament_add_pytest_test(
    test_gazebo_window_recorder
    test/test_gazebo_window_recorder.py
  )
  ament_add_pytest_test(
    test_video_extract_frame
    test/test_video_extract_frame.py
  )
  ament_add_pytest_test(
    test_video_sample_frames
    test/test_video_sample_frames.py
  )
  ament_add_pytest_test(
    test_video_mosaic
    test/test_video_mosaic.py
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
  ament_add_pytest_test(
    test_benchmark_gazebo_startup
    test/test_benchmark_gazebo_startup.py
  )
  ament_add_pytest_test(
    test_generate_fingertip_convex_collision
    test/test_generate_fingertip_convex_collision.py
  )
  ament_add_pytest_test(
    test_audit_contact_depth_evidence
    test/test_audit_contact_depth_evidence.py
  )
  ament_add_pytest_test(
    test_fingertip_pad_geometry
    test/test_fingertip_pad_geometry.py
  )
  # Direct installed-overlay run is 58.753 s under the live GUI stack and the
  # 60 s CTest wrapper expired at 60.03 s; retain assertion coverage while
  # allowing bounded wrapper/scheduler headroom.
  set_tests_properties(test_fingertip_pad_geometry PROPERTIES TIMEOUT 90)
  ament_add_pytest_test(test_teleop_api test/teleop/test_api.py)
  ament_add_pytest_test(test_teleop_camera test/teleop/test_camera.py)
  ament_add_pytest_test(test_teleop_control test/teleop/test_control.py)
  ament_add_pytest_test(test_teleop_geometry test/teleop/test_geometry.py)
  ament_add_pytest_test(test_teleop_models test/teleop/test_models.py)
  ament_add_pytest_test(test_teleop_openapi_export test/teleop/test_openapi_export.py)
  ament_add_pytest_test(test_teleop_moveit_gateway test/teleop/test_moveit_gateway.py)
  ament_add_pytest_test(test_teleop_scene_gateway test/teleop/test_scene_gateway.py)
  ament_add_pytest_test(test_teleop_screenshot test/teleop/test_screenshot.py)
  ament_add_pytest_test(test_teleop_telemetry test/teleop/test_telemetry.py)
  ament_add_pytest_test(test_teleop_workflow_gateway test/teleop/test_workflow_gateway.py)
  ament_add_pytest_test(test_teleop_server_safety test/teleop/test_server_safety.py)
  add_test(
    NAME test_cpp_quality_gate
    COMMAND
      bash
      ${CMAKE_CURRENT_SOURCE_DIR}/test/scripts/test_cpp_quality_gate.sh
      ${pick_place_common_DIR}/run_cpp_quality_gate.cmake
      ${pick_place_common_DIR}/cpp_quality_gate.cmake
  )
endif()

install(
  TARGETS so101_pick_place_runtime pick_place_state_machine gazebo_attachment_state_relay
    so101_attachment_collision_system
    reset_so101_world so101_moveit_scene
    calibrate_so101_motion validate_so101_motion_matrix
    sample_so101_workspace so101_workspace_sampling
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION lib/${PROJECT_NAME}
)

install(
  DIRECTORY include/
  DESTINATION include
)

ament_python_install_package(so101_teleop)

install(DIRECTORY web/dist/
  DESTINATION share/${PROJECT_NAME}/web
)

install(
  DIRECTORY config docs launch meshes rviz scripts urdf worlds
  DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)

install(
  DIRECTORY ${SO101_FINGERTIP_PAD_ASSET_DIR}/
  DESTINATION share/${PROJECT_NAME}/meshes/so101/generated
)

install(
  PROGRAMS
    scripts/benchmark_gazebo_startup.py
    scripts/audit_contact_depth_evidence.py
    scripts/generate_fingertip_convex_collision.py
    scripts/generate_fingertip_pad_meshes.py
    scripts/gripper_preopen_calc.py
    scripts/prepare_simulation_model.py
    scripts/tile_ai_station_guis.py
    scripts/so101_teleop_server.py
    scripts/gazebo_camera_pose.py
    scripts/so101_stack_inventory.py
    scripts/gazebo_window_recorder.py
    scripts/video_extract_frame.py
    scripts/video_sample_frames.py
    scripts/video_mosaic.py
  DESTINATION lib/${PROJECT_NAME}
)

install(
  FILES scripts/ai_station_x11.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()

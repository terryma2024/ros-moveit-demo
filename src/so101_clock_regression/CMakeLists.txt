cmake_minimum_required(VERSION 3.22)
project(so101_clock_regression)

find_package(ament_cmake REQUIRED)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(controller_manager REQUIRED)
  find_package(mujoco_ros2_control REQUIRED)
  find_package(mujoco_vendor REQUIRED)
  find_package(joint_trajectory_controller REQUIRED)
  find_package(rclcpp REQUIRED)
  find_package(rosgraph_msgs REQUIRED)
  find_package(realtime_tools REQUIRED)
  find_package(nlohmann_json REQUIRED)
  find_package(Threads REQUIRED)
  find_package(Python3 REQUIRED COMPONENTS Interpreter)

  ament_add_gtest(actual_cm_cycle test/test_actual_cm_cycle.cpp TIMEOUT 120)
  target_compile_features(actual_cm_cycle PRIVATE cxx_std_17)
  target_link_libraries(actual_cm_cycle
    controller_manager::controller_manager
    joint_trajectory_controller::joint_trajectory_controller
    mujoco_ros2_control::mujoco_clock_trace
    ${rosgraph_msgs_TARGETS} ${CMAKE_DL_LIBS})
  target_compile_definitions(actual_cm_cycle PRIVATE
    EXPECTED_CM_LIBRARY="$<TARGET_FILE:controller_manager::controller_manager>"
    EXPECTED_NATIVE_LIBRARY="$<TARGET_FILE:joint_trajectory_controller::joint_trajectory_controller>")

  # Compile the current production method verbatim against real ROS/MuJoCo APIs.
  # The reduced fixture class does not prove the whole simulation class ABI.
  get_filename_component(workspace_root "${CMAKE_CURRENT_SOURCE_DIR}/../.." ABSOLUTE)
  set(publication_source "${workspace_root}/third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_simulation.cpp")
  set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    "${publication_source}" "${CMAKE_CURRENT_SOURCE_DIR}/test/extract_publish_clock.py")
  execute_process(COMMAND "${Python3_EXECUTABLE}"
    "${CMAKE_CURRENT_SOURCE_DIR}/test/extract_publish_clock.py"
    "${publication_source}" "${CMAKE_CURRENT_BINARY_DIR}/publish_clock_body.inc"
    COMMAND_ERROR_IS_FATAL ANY)
  ament_add_gtest(clock_publication_boundary test/clock_publication_boundary.cpp
    TIMEOUT 120
    ENV "CLOCK_EXPECTED_TRACE_LIBRARY=$<TARGET_FILE:mujoco_ros2_control::mujoco_clock_trace>")
  target_compile_features(clock_publication_boundary PRIVATE cxx_std_17)
  target_include_directories(clock_publication_boundary PRIVATE "${CMAKE_CURRENT_BINARY_DIR}")
  ament_target_dependencies(clock_publication_boundary rclcpp rosgraph_msgs realtime_tools)
  target_link_libraries(clock_publication_boundary
    mujoco_ros2_control::mujoco_clock_trace mujoco::mujoco
    Threads::Threads nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})
endif()

ament_package()

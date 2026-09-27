cmake_minimum_required(VERSION 3.22)
project(so101_mujoco_support)

find_package(Boost REQUIRED)
find_package(ament_cmake REQUIRED)
find_package(control_msgs REQUIRED)
find_package(controller_interface REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(hardware_interface REQUIRED)
find_package(joint_trajectory_controller REQUIRED)
find_package(lifecycle_msgs REQUIRED)
find_package(moveit_ros_move_group REQUIRED)
if(NOT APPLE)
  find_package(OpenGL REQUIRED COMPONENTS EGL)
endif()
find_package(mujoco_ros2_control_plugins REQUIRED)
find_package(mujoco_vendor REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rclcpp_action REQUIRED)
find_package(rcutils REQUIRED)
find_package(realtime_tools REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(Threads REQUIRED)
find_package(trajectory_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ContactSample.msg"
  "msg/PhysicsCancellationAck.msg"
  "msg/PhysicsCancellationRequest.msg"
  "msg/PhysicsStepFenceAck.msg"
  "msg/PhysicsStepFenceRequest.msg"
  "msg/PhysicsHazardLatch.msg"
  "msg/PhysicsStepEvidence.msg"
  "msg/PhysicsStepEvidenceChunk.msg"
  "msg/SimulationEvidence.msg"
  "msg/ScalarJointEvidence.msg"
  "msg/RobotContactEvidence.msg"
  "msg/SceneStateEvidence.msg"
  DEPENDENCIES geometry_msgs std_msgs)
rosidl_get_typesupport_target(cpp_typesupport_target ${PROJECT_NAME} rosidl_typesupport_cpp)

add_library(so101_simulation_evidence_plugin SHARED src/simulation_evidence_plugin.cpp)
target_compile_features(so101_simulation_evidence_plugin PUBLIC cxx_std_17)
target_include_directories(so101_simulation_evidence_plugin PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(so101_simulation_evidence_plugin PUBLIC
  mujoco::mujoco
  mujoco_ros2_control_plugins::mujoco_ros2_control_plugins
  ${cpp_typesupport_target})
ament_target_dependencies(so101_simulation_evidence_plugin PUBLIC
  geometry_msgs pluginlib rclcpp rcutils realtime_tools std_msgs)
pluginlib_export_plugin_description_file(mujoco_ros2_control_plugins so101_mujoco_plugins.xml)

add_library(so101_broker_owned_trajectory_controller SHARED
  src/broker_owned_trajectory_controller.cpp)
target_compile_features(so101_broker_owned_trajectory_controller PUBLIC cxx_std_17)
target_include_directories(so101_broker_owned_trajectory_controller PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(so101_broker_owned_trajectory_controller PUBLIC
  joint_trajectory_controller::joint_trajectory_controller)
ament_target_dependencies(so101_broker_owned_trajectory_controller PUBLIC
  control_msgs controller_interface joint_trajectory_controller pluginlib rclcpp rclcpp_action)
pluginlib_export_plugin_description_file(controller_interface so101_trajectory_controllers.xml)

add_library(so101_controller_reservation_protocol STATIC
  src/controller_reservation_protocol.cpp
  src/controller_reservation_provision.cpp
  src/controller_reservation_socket.cpp)
set_target_properties(so101_controller_reservation_protocol PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_features(so101_controller_reservation_protocol PUBLIC cxx_std_17)
target_include_directories(so101_controller_reservation_protocol PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
ament_target_dependencies(so101_controller_reservation_protocol PUBLIC control_msgs rclcpp rcutils)
target_link_libraries(so101_controller_reservation_protocol PUBLIC Threads::Threads)
target_link_libraries(so101_broker_owned_trajectory_controller PRIVATE
  so101_controller_reservation_protocol)

add_executable(graceful_shutdown_move_group src/graceful_shutdown_move_group.cpp)
target_compile_features(graceful_shutdown_move_group PRIVATE cxx_std_17)
target_include_directories(graceful_shutdown_move_group PRIVATE ${Boost_INCLUDE_DIRS})
ament_target_dependencies(graceful_shutdown_move_group moveit_ros_move_group rclcpp)
target_link_libraries(graceful_shutdown_move_group
  moveit_ros_move_group::moveit_move_group_capabilities_base)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  set(so101_test_library_dirs)
  if(APPLE)
    find_package(rcl_logging_spdlog REQUIRED)
    find_package(rmw_dds_common REQUIRED)
    find_package(rmw_fastrtps_cpp REQUIRED)
    foreach(package_name rcl_logging_spdlog rmw_dds_common rmw_fastrtps_cpp)
      get_filename_component(package_prefix
        "${${package_name}_DIR}/../../.." ABSOLUTE)
      list(APPEND so101_test_library_dirs "${package_prefix}/lib")
    endforeach()
  endif()
  ament_add_gtest(test_simulation_evidence_plugin
    test/test_simulation_evidence_plugin.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_simulation_evidence_plugin PRIVATE cxx_std_17)
  target_include_directories(test_simulation_evidence_plugin PRIVATE include)
  target_link_libraries(test_simulation_evidence_plugin so101_simulation_evidence_plugin)

  ament_add_gtest(test_physics_step_fence
    test/test_physics_step_fence.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_physics_step_fence PRIVATE cxx_std_17)
  target_include_directories(test_physics_step_fence PRIVATE include)
  target_link_libraries(test_physics_step_fence so101_simulation_evidence_plugin)

  ament_add_gtest(test_controller_ingress_witness
    test/test_controller_ingress_witness.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_controller_ingress_witness PRIVATE cxx_std_17)
  target_include_directories(test_controller_ingress_witness PRIVATE include)

  ament_add_gtest(test_broker_owned_trajectory_controller
    test/test_broker_owned_trajectory_controller.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_broker_owned_trajectory_controller PRIVATE cxx_std_17)
  ament_target_dependencies(test_broker_owned_trajectory_controller
    control_msgs controller_interface hardware_interface lifecycle_msgs
    pluginlib rclcpp rclcpp_action)
  target_link_libraries(test_broker_owned_trajectory_controller
    so101_broker_owned_trajectory_controller)

  ament_add_gtest(test_controller_goal_admission
    test/test_controller_goal_admission.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_controller_goal_admission PRIVATE cxx_std_17)
  target_include_directories(test_controller_goal_admission PRIVATE include)
  ament_target_dependencies(test_controller_goal_admission
    control_msgs rclcpp trajectory_msgs)

  ament_add_gtest(test_controller_stop_witness
    test/test_controller_stop_witness.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_controller_stop_witness PRIVATE cxx_std_17)
  target_include_directories(test_controller_stop_witness PRIVATE include)

  ament_add_gtest(test_controller_reservation_protocol
    test/test_controller_reservation_protocol.cpp
    APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  target_compile_features(test_controller_reservation_protocol PRIVATE cxx_std_17)
  target_include_directories(test_controller_reservation_protocol PRIVATE include)
  ament_target_dependencies(test_controller_reservation_protocol control_msgs rclcpp)
  target_link_libraries(test_controller_reservation_protocol
    so101_controller_reservation_protocol)

  if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    ament_add_gtest(test_controller_reservation_provision
      test/test_controller_reservation_provision.cpp
      APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
    target_compile_features(test_controller_reservation_provision PRIVATE cxx_std_17)
    target_include_directories(test_controller_reservation_provision PRIVATE include)
    ament_target_dependencies(test_controller_reservation_provision control_msgs rclcpp)
    target_link_libraries(test_controller_reservation_provision
      so101_controller_reservation_protocol)

    ament_add_gtest(test_controller_reservation_socket
      test/test_controller_reservation_socket.cpp
      APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
    target_compile_features(test_controller_reservation_socket PRIVATE cxx_std_17)
    ament_target_dependencies(test_controller_reservation_socket control_msgs rclcpp)
    target_link_libraries(test_controller_reservation_socket
      so101_controller_reservation_protocol)
  endif()
endif()

install(TARGETS so101_simulation_evidence_plugin
  so101_broker_owned_trajectory_controller EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(TARGETS graceful_shutdown_move_group RUNTIME DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)
ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(control_msgs controller_interface geometry_msgs joint_trajectory_controller
  lifecycle_msgs mujoco_ros2_control_plugins mujoco_vendor pluginlib
  rclcpp rclcpp_action rcutils realtime_tools rosidl_default_runtime std_msgs trajectory_msgs)
ament_package()

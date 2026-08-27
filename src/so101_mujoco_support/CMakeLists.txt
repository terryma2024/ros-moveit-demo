cmake_minimum_required(VERSION 3.22)
project(so101_mujoco_support)

find_package(Boost REQUIRED)
find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_ros_move_group REQUIRED)
if(NOT APPLE)
  find_package(OpenGL REQUIRED COMPONENTS EGL)
endif()
find_package(mujoco_ros2_control_plugins REQUIRED)
find_package(mujoco_vendor REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(realtime_tools REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/ContactSample.msg"
  "msg/PhysicsCancellationAck.msg"
  "msg/PhysicsCancellationRequest.msg"
  "msg/PhysicsHazardLatch.msg"
  "msg/PhysicsStepEvidence.msg"
  "msg/PhysicsStepEvidenceChunk.msg"
  "msg/SimulationEvidence.msg"
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
  geometry_msgs pluginlib rclcpp realtime_tools std_msgs)
pluginlib_export_plugin_description_file(mujoco_ros2_control_plugins so101_mujoco_plugins.xml)

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
endif()

install(TARGETS so101_simulation_evidence_plugin EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(TARGETS graceful_shutdown_move_group RUNTIME DESTINATION lib/${PROJECT_NAME})
install(DIRECTORY include/ DESTINATION include)
ament_export_targets(export_${PROJECT_NAME} HAS_LIBRARY_TARGET)
ament_export_dependencies(geometry_msgs mujoco_ros2_control_plugins mujoco_vendor pluginlib
  rclcpp realtime_tools rosidl_default_runtime std_msgs)
ament_package()

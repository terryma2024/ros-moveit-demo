cmake_minimum_required(VERSION 3.16)
project(so101_clock_test_hardware LANGUAGES CXX)

find_package(ament_cmake REQUIRED)

if(BUILD_TESTING)
  find_package(hardware_interface REQUIRED)
  find_package(pluginlib REQUIRED)
  find_package(rclcpp REQUIRED)

  add_library(test_hardware_components SHARED
    upstream/test_single_joint_actuator.cpp
    upstream/test_force_torque_sensor.cpp
    upstream/test_imu_sensor.cpp
    upstream/test_two_joint_system.cpp
    upstream/test_system_with_command_modes.cpp)
  target_compile_features(test_hardware_components PRIVATE cxx_std_17)
  target_link_libraries(test_hardware_components PRIVATE
    hardware_interface::hardware_interface
    pluginlib::pluginlib
    rclcpp::rclcpp)
  pluginlib_export_plugin_description_file(
    hardware_interface upstream/test_hardware_components.xml)
  install(TARGETS test_hardware_components DESTINATION lib)
endif()

ament_package()

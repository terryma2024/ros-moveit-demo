cmake_minimum_required(VERSION 3.16)
project(so101_queued_state_publisher)

find_package(ament_cmake REQUIRED)
find_package(realtime_tools REQUIRED)
find_package(Threads REQUIRED)

add_library(so101_queued_state_publisher INTERFACE)
target_compile_features(so101_queued_state_publisher INTERFACE cxx_std_17)
target_include_directories(so101_queued_state_publisher INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/so101_queued_state_publisher>)
target_link_libraries(so101_queued_state_publisher INTERFACE
  realtime_tools::realtime_tools Threads::Threads)

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_queued_state_publisher test/test_queued_state_publisher.cpp)
  target_link_libraries(test_queued_state_publisher so101_queued_state_publisher)
endif()

install(DIRECTORY include/ DESTINATION include/so101_queued_state_publisher)
install(TARGETS so101_queued_state_publisher EXPORT export_so101_queued_state_publisher)
ament_export_targets(export_so101_queued_state_publisher HAS_LIBRARY_TARGET)
ament_export_dependencies(realtime_tools)
ament_package()

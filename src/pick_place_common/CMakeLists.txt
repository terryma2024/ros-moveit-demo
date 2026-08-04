cmake_minimum_required(VERSION 3.22)
project(pick_place_common)

find_package(ament_cmake REQUIRED)
find_package(gz-msgs10 REQUIRED)
find_package(gz-transport13 REQUIRED)

add_library(pick_place_common_core
  src/common_resume_validator.cpp
  src/domain_types.cpp
  src/plan_validation.cpp
  src/runner.cpp
  src/simulation_session_id.cpp
  src/state_action.cpp
  src/transition_contract.cpp
  src/workflow_definition.cpp
  src/world_observer.cpp
)
target_compile_features(pick_place_common_core PUBLIC cxx_std_17)
target_include_directories(pick_place_common_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
set_target_properties(pick_place_common_core PROPERTIES EXPORT_NAME core)
add_library(pick_place_common::core ALIAS pick_place_common_core)

add_library(pick_place_common_ros_adapters
  src/gazebo_attachment_executor.cpp
  src/moveit_scene_executor.cpp
)
target_compile_features(pick_place_common_ros_adapters PUBLIC cxx_std_17)
target_include_directories(pick_place_common_ros_adapters PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>)
target_link_libraries(pick_place_common_ros_adapters PUBLIC pick_place_common_core
  gz-msgs10::core gz-transport13::core)
set_target_properties(pick_place_common_ros_adapters PROPERTIES EXPORT_NAME ros_adapters)
add_library(pick_place_common::ros_adapters ALIAS pick_place_common_ros_adapters)

install(DIRECTORY include/ DESTINATION include)
install(TARGETS pick_place_common_core pick_place_common_ros_adapters EXPORT pick_place_common_targets
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin
  INCLUDES DESTINATION include)
ament_export_targets(pick_place_common_targets HAS_LIBRARY_TARGET NAMESPACE pick_place_common::)
ament_export_dependencies(gz-msgs10 gz-transport13)

install(FILES
  cmake/cpp_quality_gate.cmake
  cmake/run_cpp_quality_gate.cmake
  DESTINATION share/${PROJECT_NAME}/cmake
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_pytest_test(test_package_contract test/test_package_contract.py)
  ament_add_gtest(test_workflow_definition test/test_workflow_definition.cpp)
  target_link_libraries(test_workflow_definition pick_place_common_core)
  ament_add_gtest(test_common_runner test/test_common_runner.cpp)
  target_link_libraries(test_common_runner pick_place_common_core)
  ament_add_gtest(test_gazebo_attachment_executor test/test_gazebo_attachment_executor.cpp)
  target_link_libraries(test_gazebo_attachment_executor pick_place_common_ros_adapters)
  ament_add_gtest(test_moveit_scene_executor test/test_moveit_scene_executor.cpp)
  target_link_libraries(test_moveit_scene_executor pick_place_common_ros_adapters)
endif()

ament_package(CONFIG_EXTRAS "cmake/pick_place_common-extras.cmake")

cmake_minimum_required(VERSION 3.8)
project(fixed_pose_goal)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(moveit_ros_planning_interface REQUIRED)
find_package(visualization_msgs REQUIRED)

add_executable(fixed_pose_goal src/fixed_pose_goal.cpp)
target_include_directories(fixed_pose_goal PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
target_compile_features(fixed_pose_goal PUBLIC c_std_99 cxx_std_17)  # Require C99 and C++17
ament_target_dependencies(
  fixed_pose_goal
  "rclcpp"
  "geometry_msgs"
  "moveit_ros_planning_interface"
  "visualization_msgs"
)

add_executable(interactive_marker_pose_feedback
  src/interactive_marker_pose_feedback.cpp)
target_compile_features(interactive_marker_pose_feedback PUBLIC cxx_std_17)
ament_target_dependencies(
  interactive_marker_pose_feedback
  "rclcpp"
  "visualization_msgs"
)

install(TARGETS
  fixed_pose_goal
  interactive_marker_pose_feedback
  DESTINATION lib/${PROJECT_NAME})

install(DIRECTORY launch
  DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()

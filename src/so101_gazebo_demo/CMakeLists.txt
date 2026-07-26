cmake_minimum_required(VERSION 3.22)
project(so101_gazebo_demo)

find_package(ament_cmake REQUIRED)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_package_layout test/test_package_layout.py)
endif()

ament_package()

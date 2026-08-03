cmake_minimum_required(VERSION 3.22)
project(pick_place_common)

find_package(ament_cmake REQUIRED)

install(FILES
  cmake/cpp_quality_gate.cmake
  cmake/run_cpp_quality_gate.cmake
  DESTINATION share/${PROJECT_NAME}/cmake
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_package_contract test/test_package_contract.py)
endif()

ament_package(CONFIG_EXTRAS "cmake/pick_place_common-extras.cmake")

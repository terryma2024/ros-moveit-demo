cmake_minimum_required(VERSION 3.22)
project(so101_gazebo_demo)

find_package(ament_cmake REQUIRED)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_pytest_test(test_package_layout test/test_package_layout.py)
  ament_add_pytest_test(
    test_gripper_preopen_calc
    test/test_gripper_preopen_calc.py
  )
  ament_add_pytest_test(
    test_so101_pick_place_world
    test/test_so101_pick_place_world.py
  )
  ament_add_pytest_test(
    test_so101_launch_contract
    test/test_so101_launch_contract.py
  )
  ament_add_pytest_test(test_so101_srdf test/test_so101_srdf.py)
endif()

install(
  DIRECTORY config launch meshes rviz urdf worlds
  DESTINATION share/${PROJECT_NAME}
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)

install(
  PROGRAMS scripts/gripper_preopen_calc.py
  DESTINATION lib/${PROJECT_NAME}
)

ament_package()

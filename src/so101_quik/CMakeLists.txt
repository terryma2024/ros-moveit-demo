cmake_minimum_required(VERSION 3.22)
project(so101_quik VERSION 0.1.0 LANGUAGES CXX)

option(SO101_QUIK_STANDALONE "Build the same CPU library without a ROS underlay" OFF)
find_package(Eigen3 3.4.0 EXACT REQUIRED CONFIG)
find_package(Python3 REQUIRED COMPONENTS Interpreter)

# Both the ROS build and standalone wheel use this source/flags contract.
file(READ "${CMAKE_CURRENT_SOURCE_DIR}/config/quik.lock.json" quik_lock)
string(JSON source_count LENGTH "${quik_lock}" files)
math(EXPR source_last "${source_count} - 1")
foreach(index RANGE ${source_last})
  string(JSON relative MEMBER "${quik_lock}" files ${index})
  string(JSON expected GET "${quik_lock}" files "${relative}")
  file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/${relative}" actual)
  if(NOT actual STREQUAL expected)
    message(FATAL_ERROR "QUIK_SOURCE_SHA256_MISMATCH: ${relative}")
  endif()
endforeach()
string(JSON flag_count LENGTH "${quik_lock}" build_flags)
math(EXPR flag_last "${flag_count} - 1")
set(quik_flags)
foreach(index RANGE ${flag_last})
  string(JSON flag GET "${quik_lock}" build_flags ${index})
  list(APPEND quik_flags "${flag}")
endforeach()

add_library(so101_quik_core SHARED src/quik_c_api.cpp third_party/quik/src/geometry.cpp)
target_compile_features(so101_quik_core PUBLIC cxx_std_17)
target_compile_options(so101_quik_core PRIVATE ${quik_flags})
target_link_libraries(so101_quik_core PUBLIC Eigen3::Eigen)
target_include_directories(so101_quik_core PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/third_party/quik/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>)
set_target_properties(so101_quik_core PROPERTIES
  EXPORT_NAME core
  LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/lib"
  BUILD_WITH_INSTALL_RPATH TRUE
  INSTALL_RPATH "")
if(APPLE)
  set_target_properties(so101_quik_core PROPERTIES
    BUILD_WITH_INSTALL_NAME_DIR TRUE INSTALL_NAME_DIR "@rpath")
endif()
add_library(so101_quik::core ALIAS so101_quik_core)

if(SO101_QUIK_STANDALONE)
  set(python_install_dir "lib/python${Python3_VERSION_MAJOR}.${Python3_VERSION_MINOR}/site-packages")
  install(DIRECTORY so101_quik DESTINATION "${python_install_dir}"
    FILES_MATCHING PATTERN "*.py")
else()
  find_package(ament_cmake REQUIRED)
  find_package(ament_cmake_python REQUIRED)
  ament_get_python_install_dir(python_install_dir)
  ament_python_install_package(${PROJECT_NAME} VERSION ${PROJECT_VERSION})
endif()

install(TARGETS so101_quik_core EXPORT export_so101_quik
  ARCHIVE DESTINATION lib LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
install(FILES $<TARGET_FILE:so101_quik_core>
  DESTINATION "${python_install_dir}/${PROJECT_NAME}/lib")
install(DIRECTORY include/ third_party/quik/include/ DESTINATION include/${PROJECT_NAME})
install(FILES third_party/quik/LICENSE third_party/quik/NOTICE
  third_party/quik/upstream-package.xml DESTINATION share/${PROJECT_NAME}/third_party/quik)
install(FILES config/quik.lock.json DESTINATION share/${PROJECT_NAME}/config)

include(CTest)
if(BUILD_TESTING AND NOT SO101_QUIK_STANDALONE)
  find_package(ament_cmake_gtest REQUIRED)
  find_package(ament_cmake_pytest REQUIRED)
  ament_add_gtest(test_cpp_api test/test_cpp_api.cpp)
  target_link_libraries(test_cpp_api so101_quik_core)
  execute_process(COMMAND "${Python3_EXECUTABLE}" -c
    "import os; print(min(8, os.cpu_count() or 1))"
    OUTPUT_VARIABLE quik_test_workers OUTPUT_STRIP_TRAILING_WHITESPACE
    COMMAND_ERROR_IS_FATAL ANY)
  ament_add_pytest_test(test_native_library test
    PYTHON_EXECUTABLE "${Python3_EXECUTABLE}"
    WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}"
    ENV "PYTEST_ADDOPTS=-n ${quik_test_workers} --dist loadscope -p no:cacheprovider"
    TIMEOUT 120)
endif()

if(SO101_QUIK_STANDALONE)
  include(CMakePackageConfigHelpers)
  configure_package_config_file(cmake/so101_quikConfig.cmake.in
    "${CMAKE_CURRENT_BINARY_DIR}/so101_quikConfig.cmake"
    INSTALL_DESTINATION share/${PROJECT_NAME}/cmake)
  write_basic_package_version_file("${CMAKE_CURRENT_BINARY_DIR}/so101_quikConfigVersion.cmake"
    VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
  install(EXPORT export_so101_quik NAMESPACE so101_quik:: FILE so101_quikTargets.cmake
    DESTINATION share/${PROJECT_NAME}/cmake)
  install(FILES "${CMAKE_CURRENT_BINARY_DIR}/so101_quikConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/so101_quikConfigVersion.cmake"
    DESTINATION share/${PROJECT_NAME}/cmake)
else()
  ament_export_targets(export_so101_quik HAS_LIBRARY_TARGET NAMESPACE so101_quik::)
  ament_export_dependencies(Eigen3)
  ament_package(CONFIG_EXTRAS cmake/require_eigen.cmake)
endif()

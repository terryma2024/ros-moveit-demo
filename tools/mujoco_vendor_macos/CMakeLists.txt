cmake_minimum_required(VERSION 3.22)
project(mujoco_vendor)

find_package(ament_cmake REQUIRED)

set(MUJOCO_STAGE_ROOT "" CACHE PATH "Installed MuJoCo core prefix")
set(MUJOCO_SOURCE_ROOT "" CACHE PATH "MuJoCo source checkout used to build the core")
if(NOT MUJOCO_STAGE_ROOT AND DEFINED ENV{MUJOCO_STAGE_ROOT})
  set(MUJOCO_STAGE_ROOT "$ENV{MUJOCO_STAGE_ROOT}" CACHE PATH "Installed MuJoCo core prefix" FORCE)
endif()
if(NOT MUJOCO_SOURCE_ROOT AND DEFINED ENV{MUJOCO_SOURCE_ROOT})
  set(MUJOCO_SOURCE_ROOT "$ENV{MUJOCO_SOURCE_ROOT}" CACHE PATH "MuJoCo source checkout used to build the core" FORCE)
endif()

if(NOT EXISTS "${MUJOCO_STAGE_ROOT}/include/mujoco/mujoco.h")
  message(FATAL_ERROR "MUJOCO_STAGE_ROOT must contain include/mujoco/mujoco.h")
endif()
if(NOT EXISTS "${MUJOCO_STAGE_ROOT}/lib/libmujoco.dylib")
  message(FATAL_ERROR "MUJOCO_STAGE_ROOT must contain lib/libmujoco.dylib")
endif()
if(NOT EXISTS "${MUJOCO_SOURCE_ROOT}/simulate/simulate.h")
  message(FATAL_ERROR "MUJOCO_SOURCE_ROOT must contain simulate/simulate.h")
endif()

# Mirror the Linux Jazzy package layout so consumers use one package contract.
install(
  DIRECTORY "${MUJOCO_STAGE_ROOT}/"
  DESTINATION "opt/${PROJECT_NAME}"
  USE_SOURCE_PERMISSIONS
)
install(
  DIRECTORY "${MUJOCO_SOURCE_ROOT}/simulate/"
  DESTINATION "opt/${PROJECT_NAME}/include/simulate"
  FILES_MATCHING PATTERN "*.cc" PATTERN "*.h" PATTERN "*.mm"
)

ament_package(CONFIG_EXTRAS_POST "mujoco_vendor-extras.cmake")

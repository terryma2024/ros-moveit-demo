cmake_minimum_required(VERSION 3.22)
project(so101_teleop)

find_package(ament_cmake REQUIRED)
find_package(ament_cmake_python REQUIRED)

if(DEFINED ENV{SO101_TELEOP_BUN})
  set(BUN_EXECUTABLE "$ENV{SO101_TELEOP_BUN}")
elseif(EXISTS "/home/lenovo/.bun/bin/bun")
  set(BUN_EXECUTABLE "/home/lenovo/.bun/bin/bun")
else()
  find_program(BUN_EXECUTABLE bun REQUIRED)
endif()
if(NOT EXISTS "${BUN_EXECUTABLE}")
  message(FATAL_ERROR "Bun is required; set SO101_TELEOP_BUN to its executable")
endif()
get_filename_component(SO101_TELEOP_BUN_BIN "${BUN_EXECUTABLE}" DIRECTORY)

set(SO101_TELEOP_WEB_ROOT ${CMAKE_CURRENT_SOURCE_DIR}/web)
set(SO101_TELEOP_WEB_INDEX ${SO101_TELEOP_WEB_ROOT}/dist/index.html)
file(GLOB_RECURSE SO101_TELEOP_WEB_SOURCES CONFIGURE_DEPENDS
  ${SO101_TELEOP_WEB_ROOT}/src/*.ts
  ${SO101_TELEOP_WEB_ROOT}/src/*.tsx
  ${SO101_TELEOP_WEB_ROOT}/e2e/*.ts
)
add_custom_command(
  OUTPUT ${SO101_TELEOP_WEB_INDEX}
  COMMAND ${CMAKE_COMMAND} -E env "PATH=${SO101_TELEOP_BUN_BIN}:$ENV{PATH}" ${BUN_EXECUTABLE} install --frozen-lockfile
  COMMAND ${CMAKE_COMMAND} -E env "PATH=${SO101_TELEOP_BUN_BIN}:$ENV{PATH}" ${BUN_EXECUTABLE} run build
  WORKING_DIRECTORY ${SO101_TELEOP_WEB_ROOT}
  DEPENDS ${SO101_TELEOP_WEB_ROOT}/package.json ${SO101_TELEOP_WEB_ROOT}/bun.lock
    ${SO101_TELEOP_WEB_ROOT}/vite.config.ts ${SO101_TELEOP_WEB_ROOT}/tailwind.config.ts
    ${SO101_TELEOP_WEB_ROOT}/postcss.config.cjs ${SO101_TELEOP_WEB_SOURCES}
  VERBATIM
)
add_custom_target(so101_teleop_web ALL DEPENDS ${SO101_TELEOP_WEB_INDEX})

ament_python_install_package(so101_teleop)

install(DIRECTORY web/dist/
  DESTINATION share/${PROJECT_NAME}/web
)
install(DIRECTORY config docs launch
  DESTINATION share/${PROJECT_NAME}
)
install(
  PROGRAMS
    scripts/so101_teleop_server.py
    scripts/so101_expert_validation_server.py
    scripts/tile_ai_station_guis.py
    scripts/gazebo_window_recorder.py
    scripts/simulator_window_recorder.py
    scripts/so101_stack_inventory.py
  DESTINATION lib/${PROJECT_NAME}
)

if(BUILD_TESTING)
  find_package(ament_cmake_pytest REQUIRED)
  set(so101_test_library_dirs)
  if(APPLE)
    string(REPLACE ":" ";" so101_ament_prefixes "$ENV{AMENT_PREFIX_PATH}")
    foreach(prefix IN LISTS so101_ament_prefixes)
      if(IS_DIRECTORY "${prefix}/lib")
        list(APPEND so101_test_library_dirs "${prefix}/lib")
      endif()
    endforeach()
    list(REMOVE_DUPLICATES so101_test_library_dirs)
  endif()
  function(so101_add_pytest_test test_name test_path)
    ament_add_pytest_test(${test_name} ${test_path}
      APPEND_LIBRARY_DIRS ${so101_test_library_dirs})
  endfunction()

  so101_add_pytest_test(test_backend_profiles test/backends/test_profiles.py)
  so101_add_pytest_test(test_backend_cli_adapter test/backends/test_cli_adapter.py)
  so101_add_pytest_test(test_mujoco_profile test/backends/test_mujoco_profile.py)
  so101_add_pytest_test(test_package_layout test/test_package_layout.py)
  so101_add_pytest_test(test_expert_validation_package_layout test/test_expert_validation_package_layout.py)
  so101_add_pytest_test(test_launch_contract test/test_launch_contract.py)
  so101_add_pytest_test(test_tile_ai_station_guis test/test_tile_ai_station_guis.py)
  so101_add_pytest_test(test_ai_station_x11 test/test_ai_station_x11.py)
  so101_add_pytest_test(test_gazebo_window_recorder test/test_gazebo_window_recorder.py)
  so101_add_pytest_test(test_so101_stack_inventory test/test_so101_stack_inventory.py)
  so101_add_pytest_test(test_teleop_api test/teleop/test_api.py)
  so101_add_pytest_test(test_teleop_camera test/teleop/test_camera.py)
  so101_add_pytest_test(test_teleop_control test/teleop/test_control.py)
  so101_add_pytest_test(test_teleop_geometry test/teleop/test_geometry.py)
  so101_add_pytest_test(test_teleop_models test/teleop/test_models.py)
  so101_add_pytest_test(test_teleop_openapi_export test/teleop/test_openapi_export.py)
  so101_add_pytest_test(test_teleop_moveit_gateway test/teleop/test_moveit_gateway.py)
  so101_add_pytest_test(test_teleop_scene_gateway test/teleop/test_scene_gateway.py)
  so101_add_pytest_test(test_teleop_screenshot test/teleop/test_screenshot.py)
  so101_add_pytest_test(test_teleop_telemetry test/teleop/test_telemetry.py)
  so101_add_pytest_test(test_teleop_web_bundle test/teleop/test_web_bundle.py)
  so101_add_pytest_test(test_teleop_workflow_gateway test/teleop/test_workflow_gateway.py)
  so101_add_pytest_test(test_teleop_server_safety test/teleop/test_server_safety.py)
  so101_add_pytest_test(test_backend_capabilities test/teleop/test_backend_capabilities.py)
  so101_add_pytest_test(test_backend_result test/teleop/test_backend_result.py)
  so101_add_pytest_test(test_main_backend test/teleop/test_main_backend.py)
  so101_add_pytest_test(test_task_gateway test/teleop/test_task_gateway.py)
  so101_add_pytest_test(test_task_artifacts test/teleop/test_task_artifacts.py)
  so101_add_pytest_test(test_task_service test/teleop/test_task_service.py)
  so101_add_pytest_test(test_expert_validation_adaptive_events test/teleop/test_expert_validation_adaptive_events.py)
  so101_add_pytest_test(test_expert_validation_adaptive_owner test/teleop/test_expert_validation_adaptive_owner.py)
  so101_add_pytest_test(test_expert_validation_api test/teleop/test_expert_validation_api.py)
  so101_add_pytest_test(test_expert_validation_artifacts test/teleop/test_expert_validation_artifacts.py)
  so101_add_pytest_test(test_expert_validation_catalog test/teleop/test_expert_validation_catalog.py)
  so101_add_pytest_test(test_expert_validation_control test/teleop/test_expert_validation_control.py)
  so101_add_pytest_test(test_expert_validation_coordinator_events test/teleop/test_expert_validation_coordinator_events.py)
  so101_add_pytest_test(test_expert_validation_e2e_fixtures test/teleop/test_expert_validation_e2e_fixtures.py)
  so101_add_pytest_test(test_expert_validation_e2e_installed_port test/teleop/test_expert_validation_e2e_installed_port.py)
  so101_add_pytest_test(test_expert_validation_executor_registry test/teleop/test_expert_validation_executor_registry.py)
  so101_add_pytest_test(test_expert_validation_frozen_manifest test/teleop/test_expert_validation_frozen_manifest.py)
  so101_add_pytest_test(test_expert_validation_lease test/teleop/test_expert_validation_lease.py)
  so101_add_pytest_test(test_expert_validation_main test/teleop/test_expert_validation_main.py)
  so101_add_pytest_test(test_expert_validation_preflight test/teleop/test_expert_validation_preflight.py)
  so101_add_pytest_test(test_expert_validation_process_owner test/teleop/test_expert_validation_process_owner.py)
  so101_add_pytest_test(test_expert_validation_process_owner_integration test/teleop/test_expert_validation_process_owner_integration.py)
  so101_add_pytest_test(test_expert_validation_production_projection test/teleop/test_expert_validation_production_projection.py)
  so101_add_pytest_test(test_expert_validation_projection test/teleop/test_expert_validation_projection.py)
  so101_add_pytest_test(test_expert_validation_service test/teleop/test_expert_validation_service.py)
  so101_add_pytest_test(test_expert_validation_statistics test/teleop/test_expert_validation_statistics.py)
  so101_add_pytest_test(test_expert_validation_store test/teleop/test_expert_validation_store.py)
  so101_add_pytest_test(test_expert_validation_supervisor test/teleop/test_expert_validation_supervisor.py)
endif()

ament_package()

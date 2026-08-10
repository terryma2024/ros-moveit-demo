include(CMakeParseArguments)

set(SO101_GAZEBO_CPP_QUALITY_GATE_MODULE_DIR "${CMAKE_CURRENT_LIST_DIR}")

function(so101_gazebo_add_cpp_quality_gate)
  cmake_parse_arguments(
    QUALITY_GATE
    ""
    "WORKSPACE_ROOT;SOURCE_ROOT;RUN_CLANG_TIDY_EXECUTABLE;CLANG_FORMAT_EXECUTABLE"
    "TARGETS;EXCLUDE_FILES"
    ${ARGN}
  )

  foreach(required_argument IN ITEMS WORKSPACE_ROOT SOURCE_ROOT
                                    RUN_CLANG_TIDY_EXECUTABLE
                                    CLANG_FORMAT_EXECUTABLE)
    if(NOT QUALITY_GATE_${required_argument})
      message(FATAL_ERROR
              "cpp_quality_gate requires ${required_argument}")
    endif()
  endforeach()

  foreach(executable_argument IN ITEMS
      RUN_CLANG_TIDY_EXECUTABLE
      CLANG_FORMAT_EXECUTABLE)
    if(NOT EXISTS "${QUALITY_GATE_${executable_argument}}")
      message(FATAL_ERROR
              "${executable_argument} must identify an existing executable: "
              "${QUALITY_GATE_${executable_argument}}")
    endif()
  endforeach()

  foreach(config_file IN ITEMS
      "${QUALITY_GATE_WORKSPACE_ROOT}/.clang-tidy"
      "${QUALITY_GATE_WORKSPACE_ROOT}/.clang-format")
    if(NOT EXISTS "${config_file}")
      message(FATAL_ERROR
              "cpp_quality_gate requires configuration file: ${config_file}")
    endif()
  endforeach()

  foreach(target IN LISTS QUALITY_GATE_TARGETS)
    if(NOT TARGET "${target}")
      message(FATAL_ERROR "cpp_quality_gate target does not exist: ${target}")
    endif()
  endforeach()

  file(
    GLOB_RECURSE quality_source_files
    "${QUALITY_GATE_SOURCE_ROOT}/src/*.c"
    "${QUALITY_GATE_SOURCE_ROOT}/src/*.cc"
    "${QUALITY_GATE_SOURCE_ROOT}/src/*.cpp"
    "${QUALITY_GATE_SOURCE_ROOT}/src/*.cxx"
    "${QUALITY_GATE_SOURCE_ROOT}/include/*.h"
    "${QUALITY_GATE_SOURCE_ROOT}/include/*.hh"
    "${QUALITY_GATE_SOURCE_ROOT}/include/*.hpp"
    "${QUALITY_GATE_SOURCE_ROOT}/include/*.hxx"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.c"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.cc"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.cpp"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.cxx"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.h"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.hh"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.hpp"
    "${QUALITY_GATE_SOURCE_ROOT}/test/*.hxx"
  )
  list(REMOVE_DUPLICATES quality_source_files)
  foreach(excluded_file IN LISTS QUALITY_GATE_EXCLUDE_FILES)
    if(NOT IS_ABSOLUTE "${excluded_file}")
      set(excluded_file "${QUALITY_GATE_SOURCE_ROOT}/${excluded_file}")
    endif()
    if(NOT EXISTS "${excluded_file}")
      message(FATAL_ERROR
              "cpp_quality_gate excluded file does not exist: ${excluded_file}")
    endif()
    list(REMOVE_ITEM quality_source_files "${excluded_file}")
  endforeach()
  if(NOT quality_source_files)
    message(FATAL_ERROR
            "cpp_quality_gate found no C/C++ files under ${QUALITY_GATE_SOURCE_ROOT}")
  endif()

  set(quality_gate_stamp "${CMAKE_CURRENT_BINARY_DIR}/cpp_quality_gate.stamp")
  set(quality_gate_script
      "${SO101_GAZEBO_CPP_QUALITY_GATE_MODULE_DIR}/run_cpp_quality_gate.cmake")
  set(quality_source_manifest
      "${CMAKE_CURRENT_BINARY_DIR}/cpp_quality_gate_sources.cmake")
  file(WRITE "${quality_source_manifest}" "set(QUALITY_SOURCE_FILES\n")
  foreach(quality_source_file IN LISTS quality_source_files)
    file(APPEND "${quality_source_manifest}" "  [=[${quality_source_file}]=]\n")
  endforeach()
  file(APPEND "${quality_source_manifest}" ")\n")

  add_custom_command(
    OUTPUT "${quality_gate_stamp}"
    COMMAND
      "${CMAKE_COMMAND}"
      "-DRUN_CLANG_TIDY_EXECUTABLE=${QUALITY_GATE_RUN_CLANG_TIDY_EXECUTABLE}"
      "-DCLANG_FORMAT_EXECUTABLE=${QUALITY_GATE_CLANG_FORMAT_EXECUTABLE}"
      "-DCOMPILATION_DATABASE_DIR=${CMAKE_BINARY_DIR}"
      "-DWORKSPACE_ROOT=${QUALITY_GATE_WORKSPACE_ROOT}"
      "-DQUALITY_SOURCE_MANIFEST=${quality_source_manifest}"
      -P
      "${quality_gate_script}"
    COMMAND "${CMAKE_COMMAND}" -E touch "${quality_gate_stamp}"
    DEPENDS
      "${quality_gate_script}"
      "${QUALITY_GATE_WORKSPACE_ROOT}/.clang-tidy"
      "${QUALITY_GATE_WORKSPACE_ROOT}/.clang-format"
      "${quality_source_manifest}"
      "${CMAKE_BINARY_DIR}/compile_commands.json"
      ${quality_source_files}
    VERBATIM
  )
  add_custom_target(cpp_quality_gate DEPENDS "${quality_gate_stamp}")

  foreach(target IN LISTS QUALITY_GATE_TARGETS)
    add_dependencies("${target}" cpp_quality_gate)
  endforeach()
endfunction()

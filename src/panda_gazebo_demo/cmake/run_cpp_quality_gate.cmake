function(require_defined_variable variable_name)
  if(NOT DEFINED ${variable_name} OR "${${variable_name}}" STREQUAL "")
    message(FATAL_ERROR "${variable_name} must be provided")
  endif()
endfunction()

require_defined_variable(RUN_CLANG_TIDY_EXECUTABLE)
require_defined_variable(CLANG_FORMAT_EXECUTABLE)
require_defined_variable(COMPILATION_DATABASE_DIR)
require_defined_variable(WORKSPACE_ROOT)
require_defined_variable(QUALITY_SOURCE_FILES)

foreach(executable IN ITEMS "${RUN_CLANG_TIDY_EXECUTABLE}" "${CLANG_FORMAT_EXECUTABLE}")
  if(NOT EXISTS "${executable}")
    message(FATAL_ERROR "Required quality-gate executable does not exist: ${executable}")
  endif()
endforeach()

if(NOT EXISTS "${COMPILATION_DATABASE_DIR}/compile_commands.json")
  message(FATAL_ERROR
          "Compilation database is missing: ${COMPILATION_DATABASE_DIR}/compile_commands.json")
endif()

foreach(config_file IN ITEMS "${WORKSPACE_ROOT}/.clang-tidy"
                             "${WORKSPACE_ROOT}/.clang-format")
  if(NOT EXISTS "${config_file}")
    message(FATAL_ERROR "Required quality-gate configuration is missing: ${config_file}")
  endif()
endforeach()

message(STATUS "C++ quality gate: running clang-tidy")
execute_process(
  COMMAND
    "${RUN_CLANG_TIDY_EXECUTABLE}"
    -p
    "${COMPILATION_DATABASE_DIR}"
    -warnings-as-errors=*
    -config-file
    "${WORKSPACE_ROOT}/.clang-tidy"
  RESULT_VARIABLE clang_tidy_result
)
if(NOT clang_tidy_result EQUAL 0)
  message(FATAL_ERROR "clang-tidy failed with exit code ${clang_tidy_result}")
endif()

message(STATUS "C++ quality gate: running clang-format")
execute_process(
  COMMAND "${CLANG_FORMAT_EXECUTABLE}" -i --style=file ${QUALITY_SOURCE_FILES}
  RESULT_VARIABLE clang_format_result
)
if(NOT clang_format_result EQUAL 0)
  message(FATAL_ERROR "clang-format failed with exit code ${clang_format_result}")
endif()

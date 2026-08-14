get_filename_component(_mujoco_vendor_prefix "${mujoco_vendor_DIR}/../../.." ABSOLUTE)
set(MUJOCO_VENDOR_ROOT "${_mujoco_vendor_prefix}/opt/mujoco_vendor")
set(MUJOCO_INCLUDE_DIR "${MUJOCO_VENDOR_ROOT}/include")
set(MUJOCO_LIB_DIR "${MUJOCO_VENDOR_ROOT}/lib")
set(MUJOCO_BIN_DIR "${MUJOCO_VENDOR_ROOT}/bin")
set(MUJOCO_PLUGIN_DIR "${MUJOCO_VENDOR_ROOT}/bin/mujoco_plugin")
set(MUJOCO_SIMULATE_DIR "${MUJOCO_VENDOR_ROOT}/include/simulate")
set(MUJOCO_DEP_VERSION_lodepng "b4ed2cd7ecf61d29076169b49199371456d4f90b")

if(NOT TARGET mujoco::mujoco)
  add_library(mujoco::mujoco SHARED IMPORTED)
  set_target_properties(
    mujoco::mujoco
    PROPERTIES
      IMPORTED_LOCATION "${MUJOCO_LIB_DIR}/libmujoco.dylib"
      INTERFACE_INCLUDE_DIRECTORIES "${MUJOCO_INCLUDE_DIR}"
      INTERFACE_LINK_OPTIONS "-Wl,-rpath,${MUJOCO_LIB_DIR}"
  )
endif()

set(mujoco_vendor_LIBRARIES mujoco::mujoco)
set(mujoco_vendor_LIBRARY_DIRS "${MUJOCO_LIB_DIR}")

# Homebrew Gazebo Harmonic exports TINYXML2::TINYXML2, while the ROS underlay's
# FindTinyXML2.cmake supplies a different target name. Make the Homebrew target
# available before Gazebo's package configurations are loaded.
if(APPLE AND NOT TARGET TINYXML2::TINYXML2)
  find_package(tinyxml2 CONFIG REQUIRED)
  add_library(TINYXML2::TINYXML2 INTERFACE IMPORTED)
  target_link_libraries(TINYXML2::TINYXML2 INTERFACE tinyxml2::tinyxml2)
endif()

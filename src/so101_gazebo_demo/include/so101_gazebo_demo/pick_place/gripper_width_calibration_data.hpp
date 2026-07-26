#pragma once

// DO NOT EDIT: generated from the real SO-101 STL meshes by:
// python3 scripts/gripper_preopen_calc.py --mesh-dir meshes/so101 \
//   --urdf-path urdf/so101_base.xacro --print-calibration-header \
//   --calibration-q-min 0.660818811 --calibration-q-max 0.709194871 \
//   --calibration-samples 49

#include <array>
#include <string_view>

namespace so101_gazebo_demo::pick_place::gripper_calibration
{

struct CalibrationSample
{
  double q6;
  double width;
};

inline constexpr std::string_view kModelVersion{"so101-gripper-d20-mesh-v1"};
inline constexpr std::string_view kFixedMeshSha256{"4b17b410a12d64ec39554abc3e8054d8a97384b2dc4a8d95a5ecb2a93670f5f4"};
inline constexpr std::string_view kMovingMeshSha256{"785a9dded2f474bc1d869e0d3dae398a3dcd9c0c345640040472210d2861fa9d"};
inline constexpr std::string_view kUrdfSha256{"0a89707d4fea7a0b6c24881f8b62819a349cfe32477a573d4db3a96b98e78408"};
inline constexpr std::string_view kConstantsSha256{"763d5a46650007c53f9962bdcb8975774b46de554005c41251c848cec190dcc2"};
inline constexpr std::string_view kModelFingerprint{"33be401ad080298b31265a7ab60f4e233da4d3abd6aafb090f6a4fce7bed2a4e"};
inline constexpr double kGraspDepth{0.020000000000};
inline constexpr double kCokeDiameter{0.066000000000};
inline constexpr std::array<CalibrationSample, 49> kSamples{{
  CalibrationSample{0.660818811000, 0.065825751847},
  CalibrationSample{0.661826645583, 0.065913497208},
  CalibrationSample{0.662834480167, 0.066001367190},
  CalibrationSample{0.663842314750, 0.066089362265},
  CalibrationSample{0.664850149333, 0.066177482909},
  CalibrationSample{0.665857983917, 0.066265729598},
  CalibrationSample{0.666865818500, 0.066354102811},
  CalibrationSample{0.667873653083, 0.066442603029},
  CalibrationSample{0.668881487667, 0.066531230735},
  CalibrationSample{0.669889322250, 0.066619986414},
  CalibrationSample{0.670897156833, 0.066708870553},
  CalibrationSample{0.671904991417, 0.066797883641},
  CalibrationSample{0.672912826000, 0.066887026169},
  CalibrationSample{0.673920660583, 0.066976298631},
  CalibrationSample{0.674928495167, 0.067065701522},
  CalibrationSample{0.675936329750, 0.067155235340},
  CalibrationSample{0.676944164333, 0.067244900583},
  CalibrationSample{0.677951998917, 0.067334697755},
  CalibrationSample{0.678959833500, 0.067424627358},
  CalibrationSample{0.679967668083, 0.067514689899},
  CalibrationSample{0.680975502667, 0.067604885886},
  CalibrationSample{0.681983337250, 0.067695215829},
  CalibrationSample{0.682991171833, 0.067785680242},
  CalibrationSample{0.683999006417, 0.067876279639},
  CalibrationSample{0.685006841000, 0.067967014537},
  CalibrationSample{0.686014675583, 0.068057885455},
  CalibrationSample{0.687022510167, 0.068148892916},
  CalibrationSample{0.688030344750, 0.068240037442},
  CalibrationSample{0.689038179333, 0.068331319561},
  CalibrationSample{0.690046013917, 0.068422739799},
  CalibrationSample{0.691053848500, 0.068514298689},
  CalibrationSample{0.692061683083, 0.068605996764},
  CalibrationSample{0.693069517667, 0.068697834557},
  CalibrationSample{0.694077352250, 0.068789812608},
  CalibrationSample{0.695085186833, 0.068881931457},
  CalibrationSample{0.696093021417, 0.068974191645},
  CalibrationSample{0.697100856000, 0.069066593718},
  CalibrationSample{0.698108690583, 0.069159138223},
  CalibrationSample{0.699116525167, 0.069251825709},
  CalibrationSample{0.700124359750, 0.069344656730},
  CalibrationSample{0.701132194333, 0.069437631838},
  CalibrationSample{0.702140028917, 0.069530751592},
  CalibrationSample{0.703147863500, 0.069624016550},
  CalibrationSample{0.704155698083, 0.069717427275},
  CalibrationSample{0.705163532667, 0.069810984331},
  CalibrationSample{0.706171367250, 0.069904688285},
  CalibrationSample{0.707179201833, 0.069998539707},
  CalibrationSample{0.708187036417, 0.070092539169},
  CalibrationSample{0.709194871000, 0.070186687245},
}};

}  // namespace so101_gazebo_demo::pick_place::gripper_calibration

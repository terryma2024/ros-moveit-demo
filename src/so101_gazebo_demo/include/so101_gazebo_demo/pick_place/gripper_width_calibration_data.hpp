#pragma once

// DO NOT EDIT: generated from the real SO-101 STL meshes by:
// python3 scripts/gripper_preopen_calc.py --mesh-dir meshes/so101 \
//   --urdf-path urdf/so101_base.xacro --print-calibration-header \
//   --calibration-q-min 0.662818811 --calibration-q-max 0.795386732 \
//   --calibration-samples 80

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
inline constexpr std::string_view kUrdfSha256{"9a3b86c8ee81b5847f73e8787579f812715a02c57b79fe1fbb7e827f41653142"};
inline constexpr std::string_view kConstantsSha256{"763d5a46650007c53f9962bdcb8975774b46de554005c41251c848cec190dcc2"};
inline constexpr std::string_view kModelFingerprint{"09bca45c3397d9c53fbbf995944d002a52b28eb902cf854f0e5fe9e58dcc51bb"};
inline constexpr double kGraspDepth{0.020000000000};
inline constexpr double kCokeDiameter{0.066000000000};
inline constexpr std::array<CalibrationSample, 80> kSamples{{
  CalibrationSample{0.662818811000, 0.066000000088},
  CalibrationSample{0.664496885949, 0.066146580782},
  CalibrationSample{0.666174960899, 0.066293510452},
  CalibrationSample{0.667853035848, 0.066440791308},
  CalibrationSample{0.669531110797, 0.066588425575},
  CalibrationSample{0.671209185747, 0.066736415495},
  CalibrationSample{0.672887260696, 0.066884763325},
  CalibrationSample{0.674565335646, 0.067033471341},
  CalibrationSample{0.676243410595, 0.067182541830},
  CalibrationSample{0.677921485544, 0.067331977099},
  CalibrationSample{0.679599560494, 0.067481779470},
  CalibrationSample{0.681277635443, 0.067631951283},
  CalibrationSample{0.682955710392, 0.067782494893},
  CalibrationSample{0.684633785342, 0.067933412674},
  CalibrationSample{0.686311860291, 0.068084707015},
  CalibrationSample{0.687989935241, 0.068236380324},
  CalibrationSample{0.689668010190, 0.068388435024},
  CalibrationSample{0.691346085139, 0.068540873559},
  CalibrationSample{0.693024160089, 0.068693698389},
  CalibrationSample{0.694702235038, 0.068846911991},
  CalibrationSample{0.696380309987, 0.069000516862},
  CalibrationSample{0.698058384937, 0.069154515517},
  CalibrationSample{0.699736459886, 0.069308910487},
  CalibrationSample{0.701414534835, 0.069463704326},
  CalibrationSample{0.703092609785, 0.069618899603},
  CalibrationSample{0.704770684734, 0.069774498908},
  CalibrationSample{0.706448759684, 0.069930504850},
  CalibrationSample{0.708126834633, 0.070086920057},
  CalibrationSample{0.709804909582, 0.070243747176},
  CalibrationSample{0.711482984532, 0.070400988877},
  CalibrationSample{0.713161059481, 0.070558647845},
  CalibrationSample{0.714839134430, 0.070716726790},
  CalibrationSample{0.716517209380, 0.070875228439},
  CalibrationSample{0.718195284329, 0.071034155541},
  CalibrationSample{0.719873359278, 0.071193510866},
  CalibrationSample{0.721551434228, 0.071353297204},
  CalibrationSample{0.723229509177, 0.071513517368},
  CalibrationSample{0.724907584127, 0.071674174191},
  CalibrationSample{0.726585659076, 0.071835270527},
  CalibrationSample{0.728263734025, 0.071996809255},
  CalibrationSample{0.729941808975, 0.072107067764},
  CalibrationSample{0.731619883924, 0.072133187884},
  CalibrationSample{0.733297958873, 0.072159513463},
  CalibrationSample{0.734976033823, 0.072186043500},
  CalibrationSample{0.736654108772, 0.072212777008},
  CalibrationSample{0.738332183722, 0.072239713008},
  CalibrationSample{0.740010258671, 0.072266850534},
  CalibrationSample{0.741688333620, 0.072294188626},
  CalibrationSample{0.743366408570, 0.072321726339},
  CalibrationSample{0.745044483519, 0.072349462734},
  CalibrationSample{0.746722558468, 0.072377396884},
  CalibrationSample{0.748400633418, 0.072405527872},
  CalibrationSample{0.750078708367, 0.072433854789},
  CalibrationSample{0.751756783316, 0.072462376738},
  CalibrationSample{0.753434858266, 0.072491092829},
  CalibrationSample{0.755112933215, 0.072520002182},
  CalibrationSample{0.756791008165, 0.072549103927},
  CalibrationSample{0.758469083114, 0.072578397203},
  CalibrationSample{0.760147158063, 0.072607881159},
  CalibrationSample{0.761825233013, 0.072637554950},
  CalibrationSample{0.763503307962, 0.072728175379},
  CalibrationSample{0.765181382911, 0.072895764129},
  CalibrationSample{0.766859457861, 0.073063845812},
  CalibrationSample{0.768537532810, 0.073232423768},
  CalibrationSample{0.770215607759, 0.073401501367},
  CalibrationSample{0.771893682709, 0.073571082005},
  CalibrationSample{0.773571757658, 0.073741169106},
  CalibrationSample{0.775249832608, 0.073911766123},
  CalibrationSample{0.776927907557, 0.074082876536},
  CalibrationSample{0.778605982506, 0.074254503855},
  CalibrationSample{0.780284057456, 0.074426651618},
  CalibrationSample{0.781962132405, 0.074599323391},
  CalibrationSample{0.783640207354, 0.074772522773},
  CalibrationSample{0.785318282304, 0.074946253389},
  CalibrationSample{0.786996357253, 0.075120518898},
  CalibrationSample{0.788674432203, 0.075295322986},
  CalibrationSample{0.790352507152, 0.075470669372},
  CalibrationSample{0.792030582101, 0.075646561806},
  CalibrationSample{0.793708657051, 0.075823004069},
  CalibrationSample{0.795386732000, 0.075999999973},
}};

}  // namespace so101_gazebo_demo::pick_place::gripper_calibration

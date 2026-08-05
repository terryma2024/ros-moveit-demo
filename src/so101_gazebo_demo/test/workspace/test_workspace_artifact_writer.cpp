#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <cstring>
#include <sstream>

#include "so101_gazebo_demo/workspace/workspace_artifact_writer.hpp"

namespace ws = so101_gazebo_demo::workspace;

namespace
{
std::filesystem::path outputDirectory()
{
  const auto path =
    std::filesystem::temp_directory_path() /
    ("workspace-writer-" + std::to_string(::testing::UnitTest::GetInstance()->random_seed()));
  std::filesystem::remove_all(path);
  return path;
}

std::vector<ws::PoseSample> twoSamples()
{
  ws::PoseSample first{};
  first.sample_id = 1;
  first.source = ws::SampleSource::HALTON_GLOBAL;
  first.arm_joints = {0.1, 0.2, 0.3, 0.4, 0.5};
  first.gripper_q6 = 0.465038;
  first.tcp_pose = {0.01, 0.02, 0.03, 0.0, 0.0, 0.0, 1.0};
  first.bounds_valid = true;
  first.collision_free = true;
  first.position_voxel = {2, 4, 6};
  first.orientation_cluster_id = 3;
  auto second = first;
  second.sample_id = 2;
  second.self_collision = true;
  second.collision_free = false;
  return {first, second};
}

std::string readText(const std::filesystem::path & path)
{
  std::ifstream stream(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}
}  // namespace

TEST(WorkspaceArtifactWriter, CsvIsTheDoublePrecisionCanonicalRecord)
{
  ws::WorkspaceArtifactWriter writer(outputDirectory());
  const auto committed = writer.writeBatch(1, twoSamples());
  const auto csv = readText(committed.csv_path);
  EXPECT_NE(csv.find("sample_id,sample_source,q1,q2,q3,q4,q5,q6"), std::string::npos);
  EXPECT_NE(csv.find("1,2,0.100000000000000,0.200000000000000"), std::string::npos);
  EXPECT_NE(csv.find("0.465038000000000"), std::string::npos);
  EXPECT_EQ(committed.sample_count, 2U);
  EXPECT_EQ(committed.collision_free_count, 1U);
}

TEST(WorkspaceArtifactWriter, PlyUsesApprovedPortablePropertyTypes)
{
  ws::WorkspaceArtifactWriter writer(outputDirectory());
  const auto committed = writer.writeBatch(1, twoSamples());
  const auto content = readText(committed.all_ply_path);
  const auto end = content.find("end_header\n");
  ASSERT_NE(end, std::string::npos);
  const auto header = content.substr(0, end);
  EXPECT_NE(header.find("format binary_little_endian 1.0"), std::string::npos);
  EXPECT_NE(header.find("property uint sample_id"), std::string::npos);
  EXPECT_NE(header.find("property uchar sample_source"), std::string::npos);
  EXPECT_NE(header.find("property double x"), std::string::npos);
  EXPECT_NE(header.find("property float qx"), std::string::npos);
  EXPECT_NE(header.find("property int position_voxel_x"), std::string::npos);
}

TEST(WorkspaceArtifactWriter, FinalMergePreservesCountsAndFreeSubset)
{
  const auto output = outputDirectory();
  ws::WorkspaceArtifactWriter writer(output);
  const auto first = writer.writeBatch(1, twoSamples());
  const auto second = writer.writeBatch(2, twoSamples());
  const std::vector<ws::PositionVoxelSummary> voxels{{{2, 4, 6}, 4, 2, 1, 1}};
  const auto final = writer.finalize({first, second}, voxels);
  EXPECT_EQ(final.total_vertices, 4U);
  EXPECT_EQ(final.collision_free_vertices, 2U);
  EXPECT_EQ(final.position_voxels, 1U);
  EXPECT_TRUE(std::filesystem::exists(final.paths.samples_csv));
  EXPECT_TRUE(std::filesystem::exists(final.paths.all_poses_ply));
  EXPECT_TRUE(std::filesystem::exists(final.paths.collision_free_poses_ply));
  EXPECT_TRUE(std::filesystem::exists(final.paths.position_voxels_ply));
}

TEST(WorkspaceArtifactWriter, VoxelVerticesUseWorldSpaceCellCenters)
{
  const auto output = outputDirectory();
  ws::WorkspaceArtifactWriter writer(output, 0.005);
  const auto batch = writer.writeBatch(1, twoSamples());
  const auto final = writer.finalize({batch}, {{{-1, 4, 6}, 2, 1, 1, 1}});
  const auto bytes = readText(final.paths.position_voxels_ply);
  const auto payload = bytes.find("end_header\n") + std::string("end_header\n").size();
  ASSERT_LE(payload + 3 * sizeof(double), bytes.size());
  std::array<double, 3> xyz{};
  std::memcpy(xyz.data(), bytes.data() + payload, 3 * sizeof(double));
  EXPECT_DOUBLE_EQ(xyz[0], -0.0025);
  EXPECT_DOUBLE_EQ(xyz[1], 0.0225);
  EXPECT_DOUBLE_EQ(xyz[2], 0.0325);
}

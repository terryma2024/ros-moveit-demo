#include "so101_gazebo_demo/workspace/workspace_artifact_writer.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <type_traits>

#include <openssl/evp.h>

namespace so101_gazebo_demo::workspace
{
namespace
{
constexpr std::string_view kCsvHeader =
  "sample_id,sample_source,q1,q2,q3,q4,q5,q6,tcp_x,tcp_y,tcp_z,"
  "tcp_qx,tcp_qy,tcp_qz,tcp_qw,bounds_valid,self_collision,scene_collision,"
  "collision_free,position_voxel_x,position_voxel_y,position_voxel_z,"
  "orientation_cluster_id\n";

std::string samplePlyHeader(std::uint64_t vertices)
{
  std::ostringstream output;
  output << "ply\nformat binary_little_endian 1.0\nelement vertex " << vertices << '\n'
         << "property double x\nproperty double y\nproperty double z\n"
         << "property float qx\nproperty float qy\nproperty float qz\nproperty float qw\n"
         << "property float q1\nproperty float q2\nproperty float q3\nproperty float q4\n"
         << "property float q5\nproperty float q6\nproperty uint sample_id\n"
         << "property uchar sample_source\nproperty uchar self_collision\n"
         << "property uchar scene_collision\nproperty uchar collision_free\n"
         << "property int position_voxel_x\nproperty int position_voxel_y\n"
         << "property int position_voxel_z\nproperty uint orientation_cluster_id\nend_header\n";
  return output.str();
}

std::string voxelPlyHeader(std::uint64_t vertices)
{
  std::ostringstream output;
  output << "ply\nformat binary_little_endian 1.0\nelement vertex " << vertices << '\n'
         << "property double x\nproperty double y\nproperty double z\n"
         << "property uint sample_count\nproperty uint collision_free_count\n"
         << "property uint colliding_count\nproperty uint orientation_count\n"
         << "property uint collision_free_orientation_count\nend_header\n";
  return output.str();
}

template <typename T> void writeLittleEndian(std::ostream & stream, T value)
{
  static_assert(std::is_trivially_copyable_v<T>);
  std::array<std::byte, sizeof(T)> bytes{};
  std::memcpy(bytes.data(), &value, sizeof(T));
  const std::uint16_t marker = 1;
  const bool host_is_little_endian =
    *reinterpret_cast<const std::uint8_t *>(&marker) == 1;  // NOLINT
  if (!host_is_little_endian)
    std::reverse(bytes.begin(), bytes.end());
  stream.write(reinterpret_cast<const char *>(bytes.data()),  // NOLINT
               static_cast<std::streamsize>(bytes.size()));
}

void writeSample(std::ostream & stream, const PoseSample & sample)
{
  writeLittleEndian(stream, sample.tcp_pose.x);
  writeLittleEndian(stream, sample.tcp_pose.y);
  writeLittleEndian(stream, sample.tcp_pose.z);
  writeLittleEndian(stream, static_cast<float>(sample.tcp_pose.qx));
  writeLittleEndian(stream, static_cast<float>(sample.tcp_pose.qy));
  writeLittleEndian(stream, static_cast<float>(sample.tcp_pose.qz));
  writeLittleEndian(stream, static_cast<float>(sample.tcp_pose.qw));
  for (double joint : sample.arm_joints)
    writeLittleEndian(stream, static_cast<float>(joint));
  writeLittleEndian(stream, static_cast<float>(sample.gripper_q6));
  writeLittleEndian(stream, static_cast<std::uint32_t>(sample.sample_id));
  writeLittleEndian(stream, static_cast<std::uint8_t>(sample.source));
  writeLittleEndian(stream, static_cast<std::uint8_t>(sample.self_collision));
  writeLittleEndian(stream, static_cast<std::uint8_t>(sample.scene_collision));
  writeLittleEndian(stream, static_cast<std::uint8_t>(sample.collision_free));
  writeLittleEndian(stream, sample.position_voxel.x);
  writeLittleEndian(stream, sample.position_voxel.y);
  writeLittleEndian(stream, sample.position_voxel.z);
  writeLittleEndian(stream, sample.orientation_cluster_id);
}

void ensureClosed(std::ofstream & stream, const std::filesystem::path & path)
{
  stream.flush();
  if (!stream)
    throw std::runtime_error("failed writing " + path.string());
  stream.close();
  if (!stream)
    throw std::runtime_error("failed closing " + path.string());
}

std::string sha256File(const std::filesystem::path & path)
{
  std::ifstream stream(path, std::ios::binary);
  if (!stream)
    throw std::runtime_error("cannot hash " + path.string());
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> context(EVP_MD_CTX_new(),
                                                                  EVP_MD_CTX_free);
  if (!context || EVP_DigestInit_ex(context.get(), EVP_sha256(), nullptr) != 1) {
    throw std::runtime_error("cannot initialize SHA-256");
  }
  std::array<char, 65536> buffer{};
  while (stream) {
    stream.read(buffer.data(), static_cast<std::streamsize>(buffer.size()));
    if (stream.gcount() > 0 && EVP_DigestUpdate(context.get(), buffer.data(),
                                                static_cast<std::size_t>(stream.gcount())) != 1) {
      throw std::runtime_error("cannot update SHA-256");
    }
  }
  std::array<unsigned char, EVP_MAX_MD_SIZE> digest{};
  unsigned int length = 0;
  if (EVP_DigestFinal_ex(context.get(), digest.data(), &length) != 1) {
    throw std::runtime_error("cannot finalize SHA-256");
  }
  std::ostringstream hex;
  for (unsigned int index = 0; index < length; ++index) {
    hex << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(digest[index]);
  }
  return hex.str();
}

void streamPlyPayload(const std::filesystem::path & path, std::ostream & output)
{
  std::ifstream input(path, std::ios::binary);
  std::string line;
  bool found = false;
  while (std::getline(input, line)) {
    if (line == "end_header") {
      found = true;
      break;
    }
  }
  if (!found)
    throw std::runtime_error("invalid PLY header in " + path.string());
  output << input.rdbuf();
}

std::string batchStem(std::uint64_t number)
{
  std::ostringstream output;
  output << "batch-" << std::setw(6) << std::setfill('0') << number;
  return output.str();
}
}  // namespace

WorkspaceArtifactWriter::WorkspaceArtifactWriter(std::filesystem::path output_directory,
                                                 double position_voxel_size_m) :
    output_directory_(std::move(output_directory)), position_voxel_size_m_(position_voxel_size_m)
{
  if (!std::isfinite(position_voxel_size_m_) || position_voxel_size_m_ <= 0.0)
    throw std::invalid_argument("position voxel size must be finite and positive");
  std::filesystem::create_directories(output_directory_ / "chunks");
}

CommittedBatch WorkspaceArtifactWriter::writeBatch(std::uint64_t batch_number,
                                                   const std::vector<PoseSample> & samples)
{
  const auto chunks = output_directory_ / "chunks";
  const auto stem = batchStem(batch_number);
  const auto csv = chunks / (stem + ".csv");
  const auto all = chunks / (stem + "-all.ply");
  const auto free = chunks / (stem + "-free.ply");
  const auto csv_partial = std::filesystem::path(csv.string() + ".partial");
  const auto all_partial = std::filesystem::path(all.string() + ".partial");
  const auto free_partial = std::filesystem::path(free.string() + ".partial");
  const auto free_count = static_cast<std::uint64_t>(std::count_if(
    samples.begin(), samples.end(), [](const auto & sample) { return sample.collision_free; }));
  {
    std::ofstream stream(csv_partial, std::ios::binary | std::ios::trunc);
    stream << kCsvHeader << std::fixed << std::setprecision(15);
    for (const auto & sample : samples) {
      stream << sample.sample_id << ',' << static_cast<unsigned>(sample.source);
      for (double joint : sample.arm_joints)
        stream << ',' << joint;
      stream << ',' << sample.gripper_q6 << ',' << sample.tcp_pose.x << ',' << sample.tcp_pose.y
             << ',' << sample.tcp_pose.z << ',' << sample.tcp_pose.qx << ',' << sample.tcp_pose.qy
             << ',' << sample.tcp_pose.qz << ',' << sample.tcp_pose.qw << ',' << sample.bounds_valid
             << ',' << sample.self_collision << ',' << sample.scene_collision << ','
             << sample.collision_free << ',' << sample.position_voxel.x << ','
             << sample.position_voxel.y << ',' << sample.position_voxel.z << ','
             << sample.orientation_cluster_id << '\n';
    }
    ensureClosed(stream, csv_partial);
  }
  {
    std::ofstream stream(all_partial, std::ios::binary | std::ios::trunc);
    stream << samplePlyHeader(samples.size());
    for (const auto & sample : samples)
      writeSample(stream, sample);
    ensureClosed(stream, all_partial);
  }
  {
    std::ofstream stream(free_partial, std::ios::binary | std::ios::trunc);
    stream << samplePlyHeader(free_count);
    for (const auto & sample : samples)
      if (sample.collision_free)
        writeSample(stream, sample);
    ensureClosed(stream, free_partial);
  }
  std::filesystem::rename(csv_partial, csv);
  std::filesystem::rename(all_partial, all);
  std::filesystem::rename(free_partial, free);
  return {batch_number,
          samples.size(),
          free_count,
          csv,
          all,
          free,
          {{csv.filename().string(), sha256File(csv)},
           {all.filename().string(), sha256File(all)},
           {free.filename().string(), sha256File(free)}}};
}

FinalArtifacts WorkspaceArtifactWriter::finalize(const std::vector<CommittedBatch> & batches,
                                                 const std::vector<PositionVoxelSummary> & voxels)
{
  std::uint64_t total = 0;
  std::uint64_t free_total = 0;
  for (const auto & batch : batches) {
    total += batch.sample_count;
    free_total += batch.collision_free_count;
  }
  WorkspaceArtifactPaths paths{
    output_directory_ / "samples.csv", output_directory_ / "all_poses.ply",
    output_directory_ / "collision_free_poses.ply", output_directory_ / "position_voxels.ply"};
  const auto csv_partial = std::filesystem::path(paths.samples_csv.string() + ".partial");
  const auto all_partial = std::filesystem::path(paths.all_poses_ply.string() + ".partial");
  const auto free_partial =
    std::filesystem::path(paths.collision_free_poses_ply.string() + ".partial");
  const auto voxel_partial = std::filesystem::path(paths.position_voxels_ply.string() + ".partial");
  {
    std::ofstream output(csv_partial, std::ios::binary | std::ios::trunc);
    output << kCsvHeader;
    for (const auto & batch : batches) {
      std::ifstream input(batch.csv_path, std::ios::binary);
      std::string header;
      std::getline(input, header);
      output << input.rdbuf();
    }
    ensureClosed(output, csv_partial);
  }
  {
    std::ofstream output(all_partial, std::ios::binary | std::ios::trunc);
    output << samplePlyHeader(total);
    for (const auto & batch : batches)
      streamPlyPayload(batch.all_ply_path, output);
    ensureClosed(output, all_partial);
  }
  {
    std::ofstream output(free_partial, std::ios::binary | std::ios::trunc);
    output << samplePlyHeader(free_total);
    for (const auto & batch : batches)
      streamPlyPayload(batch.free_ply_path, output);
    ensureClosed(output, free_partial);
  }
  {
    std::ofstream output(voxel_partial, std::ios::binary | std::ios::trunc);
    output << voxelPlyHeader(voxels.size());
    for (const auto & voxel : voxels) {
      writeLittleEndian(output, (static_cast<double>(voxel.key.x) + 0.5) * position_voxel_size_m_);
      writeLittleEndian(output, (static_cast<double>(voxel.key.y) + 0.5) * position_voxel_size_m_);
      writeLittleEndian(output, (static_cast<double>(voxel.key.z) + 0.5) * position_voxel_size_m_);
      writeLittleEndian(output, static_cast<std::uint32_t>(voxel.sample_count));
      writeLittleEndian(output, static_cast<std::uint32_t>(voxel.collision_free_count));
      writeLittleEndian(
        output, static_cast<std::uint32_t>(voxel.sample_count - voxel.collision_free_count));
      writeLittleEndian(output, voxel.orientation_count);
      writeLittleEndian(output, voxel.collision_free_orientation_count);
    }
    ensureClosed(output, voxel_partial);
  }
  std::filesystem::rename(csv_partial, paths.samples_csv);
  std::filesystem::rename(all_partial, paths.all_poses_ply);
  std::filesystem::rename(free_partial, paths.collision_free_poses_ply);
  std::filesystem::rename(voxel_partial, paths.position_voxels_ply);
  return {paths, total, free_total, voxels.size()};
}

const std::filesystem::path & WorkspaceArtifactWriter::outputDirectory() const noexcept
{
  return output_directory_;
}
}  // namespace so101_gazebo_demo::workspace

// Native rosbag2 Recorder with explicit shard namespace and the current record-only policy.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdlib>
#include <iostream>
#include <memory>
#include <string>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rcutils/logging.h>
#include <rosbag2_cpp/writer.hpp>
#include <rosbag2_storage/qos.hpp>
#include <rosbag2_storage/storage_options.hpp>
#include <rosbag2_transport/recorder.hpp>
#include <rosbag2_transport/record_options.hpp>
#include <yaml-cpp/yaml.h>

namespace
{
volatile std::sig_atomic_t stop_requested = 0;
void request_stop(int) {stop_requested = 1;}
}  // namespace

int main(int argc, char ** argv)
{
  try {
    const auto arguments = rclcpp::remove_ros_arguments(argc, argv);
    const char * marker = std::getenv("SO101_ACT_CONTAINER_NAMESPACE");
    if (arguments.size() < 5 || marker == nullptr || std::string(marker).empty() ||
      std::string(marker) == "/")
    {
      throw std::invalid_argument("SCOPED_BAG_ARGUMENTS_INVALID");
    }
    const std::string namespace_prefix = std::string(marker) + "/";
    rosbag2_storage::StorageOptions storage;
    storage.uri = arguments[1];
    storage.storage_id = "mcap";
    storage.max_cache_size = 256ULL * 1024ULL * 1024ULL;
    rosbag2_transport::RecordOptions options;
    options.topics.assign(arguments.begin() + 4, arguments.end());
    options.rmw_serialization_format = "cdr";
    options.disable_keyboard_controls = true;
    options.topic_polling_interval = std::chrono::milliseconds(100);
    const auto overrides = YAML::LoadFile(arguments[2]);
    if (!overrides.IsMap()) {throw std::invalid_argument("SCOPED_BAG_QOS_INVALID");}
    for (const auto & item : overrides) {
      const auto profile = item.second;
      if (!profile.IsMap() || profile.size() != 4 ||
        profile["history"].as<std::string>() != "keep_last" ||
        profile["reliability"].as<std::string>() != "reliable" ||
        profile["durability"].as<std::string>() != "volatile")
      {
        throw std::invalid_argument("SCOPED_BAG_QOS_INVALID");
      }
      const auto depth = profile["depth"].as<unsigned int>();
      if (depth == 0) {throw std::invalid_argument("SCOPED_BAG_QOS_INVALID");}
      options.topic_qos_profile_overrides.emplace(
        item.first.as<std::string>(),
        rclcpp::QoS(rclcpp::KeepLast(depth)).reliable().durability_volatile());
    }
    for (const auto & topic : options.topics) {
      if (topic.rfind(namespace_prefix, 0) != 0) {
        throw std::invalid_argument("SCOPED_BAG_FOREIGN_TOPIC");
      }
    }
    for (const auto & item : options.topic_qos_profile_overrides) {
      if (std::find(options.topics.begin(), options.topics.end(),
        item.first) == options.topics.end())
      {
        throw std::invalid_argument("SCOPED_BAG_FOREIGN_QOS");
      }
    }
    std::signal(SIGINT, request_stop);
    std::signal(SIGTERM, request_stop);
    rclcpp::init(argc, argv, rclcpp::InitOptions(), rclcpp::SignalHandlerOptions::None);
    auto recorder = std::make_shared<rosbag2_transport::Recorder>(
      std::make_shared<rosbag2_cpp::Writer>(), storage, options, arguments[3]);
    if (std::string(recorder->get_namespace()) != marker) {
      throw std::invalid_argument("SCOPED_BAG_NAMESPACE_DRIFT");
    }
    if (rcutils_logging_set_logger_level(
        recorder->get_logger().get_name(), RCUTILS_LOG_SEVERITY_DEBUG) != RCUTILS_RET_OK)
    {
      throw std::runtime_error("SCOPED_BAG_DEBUG_LOG_UNAVAILABLE");
    }
    recorder->record();
    rclcpp::executors::SingleThreadedExecutor executor;
    executor.add_node(recorder);
    std::atomic<bool> finished{false};
    std::thread signal_monitor([&executor, &finished]() {
        while (!finished.load()) {
          if (stop_requested != 0) {executor.cancel();}
          std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
      });
    try {
      executor.spin();
    } catch (...) {
      finished.store(true);
      signal_monitor.join();
      throw;
    }
    finished.store(true);
    signal_monitor.join();
    // Flush and close the native writer with the ROS context still alive.
    // The parent retains its existing bounded signal escalation/exit readback.
    recorder->stop();
    executor.remove_node(recorder);
    recorder.reset();
    rclcpp::shutdown();
    return 0;
  } catch (const std::exception & error) {
    std::cerr << "SCOPED_BAG_FAILED: " << error.what() << std::endl;
    if (rclcpp::ok()) {rclcpp::shutdown();}
    return 1;
  }
}

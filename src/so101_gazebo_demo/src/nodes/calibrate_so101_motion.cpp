#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

void usage()
{
  std::cout << "Usage: calibrate_so101_motion <search|fk|plan> [numbers...]\n"
            << "  search x y z local_ax local_ay local_az target_ax target_ay target_az [seeds]\n"
            << "  fk q1 q2 q3 q4 q5\n"
            << "  plan q1 q2 q3 q4 q5\n";
}

std::vector<double> numbers(int argc, char ** argv, int first)
{
  std::vector<double> result;
  for (int i = first; i < argc; ++i) result.push_back(std::stod(argv[i]));
  return result;
}

void printCandidate(const spp::CalibrationCandidate & candidate, std::size_t index)
{
  std::cout << "CANDIDATE index=" << index << " joints=";
  for (double q : candidate.joints) std::cout << q << ',';
  const auto & p = candidate.tcp_pose;
  std::cout << " tcp=" << p.x << ',' << p.y << ',' << p.z << ',' << p.qx << ',' << p.qy << ','
            << p.qz << ',' << p.qw << " position_error=" << candidate.position_error
            << " axis_error=" << candidate.axis_error
            << " collision_free=" << (candidate.collision_free ? 1 : 0) << '\n';
}

}  // namespace

int main(int argc, char ** argv)
{
  if (argc < 2 || std::string(argv[1]) == "--help" || std::string(argv[1]) == "-h") {
    usage();
    return argc < 2 ? 2 : 0;
  }
  const std::string command = argv[1];
  if ((command == "fk" || command == "plan") && argc != 7) {
    usage();
    return 2;
  }
  if (command == "search" && argc != 12 && argc != 13) {
    usage();
    return 2;
  }
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("calibrate_so101_motion");
  auto boundary = std::make_shared<spp::MoveItJointPlanningBoundary>(node);
  std::cout << std::fixed << std::setprecision(9);
  int status = 0;
  if (command == "fk") {
    if (!boundary->sceneFacts()) {
      std::cerr << "SCENE_UNAVAILABLE\n";
      status = 3;
    } else if (auto evidence = boundary->evaluate(spp::SO101Profile::canonical().arm_joints,
                                                   numbers(argc, argv, 2))) {
      spp::CalibrationCandidate candidate{numbers(argc, argv, 2), evidence->tcp_pose, 0, 0,
                                          evidence->collision_free};
      printCandidate(candidate, 0);
    } else {
      std::cerr << "FK_UNAVAILABLE\n";
      status = 3;
    }
  } else if (command == "plan") {
    const auto current = boundary->currentState();
    if (!current) {
      std::cerr << "CURRENT_STATE_TIMEOUT\n";
      status = 3;
    } else {
      const auto result = boundary->planSegment(current->joint_names, current->positions,
                                                numbers(argc, argv, 2));
      if (!result.segment) {
        std::cerr << "PLAN_FAILED code="
                  << (result.action.failure ? result.action.failure->code : "UNKNOWN") << '\n';
        status = 4;
      } else {
        std::cout << "PLAN_SUCCEEDED points=" << result.segment->points.size()
                  << " planner_id=" << result.segment->planner_id
                  << " error_code=" << result.segment->moveit_error_code << '\n';
      }
    }
  } else if (command == "search") {
    const auto values = numbers(argc, argv, 2);
    const auto count = argc == 13 ? static_cast<std::size_t>(std::stoul(argv[12])) : 4096U;
    const auto candidates = boundary->search({values[0], values[1], values[2]},
                                             {values[3], values[4], values[5]},
                                             {values[6], values[7], values[8]}, count);
    for (std::size_t i = 0; i < candidates.size(); ++i) printCandidate(candidates[i], i);
    if (candidates.empty()) status = 5;
  } else {
    usage();
    status = 2;
  }
  rclcpp::shutdown();
  return status;
}

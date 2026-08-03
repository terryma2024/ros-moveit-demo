#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>

#include "so101_gazebo_demo/pick_place/moveit_joint_planning_boundary.hpp"
#include "so101_gazebo_demo/pick_place/node_spinner.hpp"
#include "so101_gazebo_demo/pick_place/calibration_cli_options.hpp"
#include "so101_gazebo_demo/pick_place/so101_motion_evidence_builder.hpp"

namespace spp = so101_gazebo_demo::pick_place;

namespace
{

void usage()
{
  std::cout << "Usage: calibrate_so101_motion <search|fk|fk-touch|plan|plan-touch|clock> [numbers...]\n"
            << "  search x y z local_ax local_ay local_az target_ax target_ay target_az"
               " [seeds] [gripper_q6]\n"
            << "  fk q1 q2 q3 q4 q5\n"
            << "  plan q1 q2 q3 q4 q5\n"
            << "  fk-touch q1 q2 q3 q4 q5  # exact TaskObject/gripper,jaw evidence\n"
            << "  plan-touch q1 q2 q3 q4 q5  # request-scoped ACM, plan only\n"
            << "  clock\n";
}

std::set<std::string> touchWhitelist()
{
  const auto & profile = spp::SO101Profile::canonical();
  std::set<std::string> result;
  for (const auto & link : profile.moveit_touch_links) {
    result.insert(profile.task_object_id + ":" + link);
  }
  return result;
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
            << " collision_free=" << (candidate.collision_free ? 1 : 0)
            << " minimum_distance=" << candidate.minimum_distance
            << " collision_pairs=";
  if (candidate.collision_pairs.empty()) {
    std::cout << '-';
  } else {
    for (const auto & pair : candidate.collision_pairs) std::cout << pair << ',';
  }
  std::cout << '\n';
}

}  // namespace

int main(int argc, char ** argv)
{
  if (argc < 2 || std::string(argv[1]) == "--help" || std::string(argv[1]) == "-h") {
    usage();
    return argc < 2 ? 2 : 0;
  }
  const std::string command = argv[1];
  if ((command == "fk" || command == "fk-touch" || command == "plan" ||
       command == "plan-touch") && argc != 7) {
    usage();
    return 2;
  }
  std::optional<spp::CalibrationSearchOptions> search_options;
  if (command == "search") {
    std::vector<std::string> arguments;
    for (int i = 2; i < argc; ++i) arguments.emplace_back(argv[i]);
    auto parsed = spp::parseCalibrationSearchOptions(
      arguments, spp::SO101Profile::canonical().q6_preopen);
    if (!parsed.options) {
      std::cerr << parsed.error << '\n';
      usage();
      return 2;
    }
    search_options = *parsed.options;
  }
  rclcpp::init(argc, argv);
  rclcpp::NodeOptions options;
  options.automatically_declare_parameters_from_overrides(true);
  options.parameter_overrides({rclcpp::Parameter("use_sim_time", true)});
  auto node = std::make_shared<rclcpp::Node>("calibrate_so101_motion", options);
  auto spinner = std::make_unique<spp::NodeSpinner>(node);
  auto boundary = std::make_shared<spp::MoveItJointPlanningBoundary>(node);
  std::cout << std::fixed << std::setprecision(9);
  int status = 0;
  if (command == "clock") {
    bool use_sim_time = false;
    node->get_parameter("use_sim_time", use_sim_time);
    std::cout << "use_sim_time=" << (use_sim_time ? "true" : "false") << '\n';
  } else if (command == "fk" || command == "fk-touch") {
    const auto allowed = command == "fk-touch" ? touchWhitelist() : std::set<std::string>{};
    if (!boundary->sceneFacts()) {
      std::cerr << "SCENE_UNAVAILABLE\n";
      status = 3;
    } else if (auto evidence = boundary->evaluate(spp::SO101Profile::canonical().arm_joints,
                                                   numbers(argc, argv, 2), allowed,
                                                   {},
                                                   spp::SO101Profile::canonical().q6_preopen)) {
      spp::CalibrationCandidate candidate{numbers(argc, argv, 2), evidence->tcp_pose, 0, 0,
                                          evidence->collision_free, 0.0, {}};
      printCandidate(candidate, 0);
      std::cout << "EVIDENCE acm_collision_free=" << (evidence->collision_free ? 1 : 0)
                << " raw_contact_pairs=";
      if (evidence->raw_contact_pairs.empty()) std::cout << '-';
      for (const auto & pair : evidence->raw_contact_pairs) std::cout << pair << ',';
      std::cout << '\n';
    } else {
      std::cerr << "FK_UNAVAILABLE\n";
      status = 3;
    }
  } else if (command == "plan" || command == "plan-touch") {
    const auto allowed = command == "plan-touch" ? touchWhitelist() : std::set<std::string>{};
    const auto scene = boundary->sceneFacts();
    const auto current = scene ? boundary->currentState() : std::nullopt;
    if (!scene) {
      std::cerr << "SCENE_UNAVAILABLE\n";
      status = 3;
    } else if (!current) {
      std::cerr << "CURRENT_STATE_TIMEOUT\n";
      status = 3;
    } else {
      const auto result = boundary->planSegment(current->joint_names, current->positions,
                                                numbers(argc, argv, 2), allowed,
                                                {},
                                                spp::SO101Profile::canonical().q6_preopen,
                                                0.1, 0.1);
      if (!result.segment) {
        std::cerr << "PLAN_FAILED code="
                  << (result.action.failure ? result.action.failure->code : "UNKNOWN") << '\n';
        status = 4;
      } else {
        spp::TrajectoryEvidenceInput input;
        input.joint_names = current->joint_names;
        input.current_joint_snapshot = current->positions;
        input.points = result.segment->points;
        input.moveit_success = result.segment->moveit_success;
        input.moveit_error_code = result.segment->moveit_error_code;
        input.planner_id = result.segment->planner_id;
        input.start_state_stamp_nanoseconds = current->observed_stamp_nanoseconds;
        input.collision_aware_planner = result.segment->collision_aware;
        input.allowed_touch_pairs = allowed;
        input.gripper_position = spp::SO101Profile::canonical().q6_preopen;
        const auto built = spp::buildMotionPlanEvidence(input, *boundary);
        if (!built.artifact) {
          std::cerr << "EVIDENCE_FAILED code="
                    << (built.failure ? built.failure->code : "UNKNOWN") << '\n';
          status = 4;
        } else {
          std::cout << "PLAN_SUCCEEDED points=" << result.segment->points.size()
                  << " planner_id=" << result.segment->planner_id
                  << " error_code=" << result.segment->moveit_error_code
                  << " acm_collision_free=";
          bool all_safe = true;
          for (const auto & sample : built.artifact->samples) all_safe &= sample.collision_free;
          std::cout << (all_safe ? 1 : 0) << " raw_contact_pairs=";
          if (built.artifact->raw_contact_pairs.empty()) std::cout << '-';
          for (const auto & pair : built.artifact->raw_contact_pairs) std::cout << pair << ',';
          std::cout << '\n';
        }
      }
    }
  } else if (command == "search") {
    const auto & values = search_options->values;
    const auto candidates = boundary->search({values[0], values[1], values[2]},
                                             {values[3], values[4], values[5]},
                                             {values[6], values[7], values[8]},
                                             search_options->seed_count, 8,
                                             search_options->gripper_q6);
    for (std::size_t i = 0; i < candidates.size(); ++i) printCandidate(candidates[i], i);
    if (candidates.empty()) status = 5;
  } else {
    usage();
    status = 2;
  }
  spinner.reset();
  rclcpp::shutdown();
  return status;
}

#include <gtest/gtest.h>

#include <array>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "so101_mujoco_support/controller_reservation_protocol.hpp"
#include "so101_mujoco_support/controller_reservation_provision.hpp"

namespace
{
using so101_mujoco_support::ControllerReservationCapability;
using so101_mujoco_support::ControllerReservationRole;
using so101_mujoco_support::ReservationReplyStatus;
using so101_mujoco_support::encode_controller_ingress_reply;
using so101_mujoco_support::encode_controller_reservation_reply;
using so101_mujoco_support::parse_controller_ingress_query_frame;
using so101_mujoco_support::parse_controller_reservation_frame;
using so101_mujoco_support::parse_controller_reservation_close_frame;
using so101_mujoco_support::parse_controller_reservation_arm_frame;

ControllerReservationCapability capability()
{
  ControllerReservationCapability value{};
  value.fill(0xa5);
  return value;
}

std::vector<uint8_t> fixture_payload()
{
  const auto path = std::filesystem::path(__FILE__).parent_path() /
    "fixtures/follow_joint_trajectory_goal.cdr.hex";
  std::ifstream input(path);
  std::string hex;
  input >> hex;
  std::vector<uint8_t> bytes;
  for (size_t i = 0; i + 1 < hex.size(); i += 2) {
    bytes.push_back(static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}

std::vector<uint8_t> valid_frame()
{
  const auto payload = fixture_payload();
  std::vector<uint8_t> frame{0, 0, 1, 62, 'S', 'O', 'G', 'R', 1, 1};
  const auto key = capability();
  frame.insert(frame.end(), key.begin(), key.end());
  frame.insert(frame.end(), {0, 0, 0, 0, 0, 0, 0, 5});
  frame.insert(frame.end(), 16, 0x11);
  frame.insert(frame.end(), payload.begin(), payload.end());
  return frame;
}
}  // namespace

TEST(ControllerReservationProtocol, PythonGoalFrameDecodesEveryReservedField)
{
  const auto frame = valid_frame();
  ASSERT_EQ(frame.size(), 322u);
  const auto request = parse_controller_reservation_frame(frame, capability());
  EXPECT_EQ(request.generation, 5u);
  EXPECT_EQ(request.uuid, (std::array<uint8_t, 16>{
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11,
    0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11}));
  const auto & goal = request.goal;
  EXPECT_EQ(goal.trajectory.header.stamp.sec, 123);
  EXPECT_EQ(goal.trajectory.header.stamp.nanosec, 456u);
  EXPECT_EQ(goal.trajectory.header.frame_id, "base_link");
  EXPECT_EQ(goal.trajectory.joint_names, (std::vector<std::string>{"1", "2"}));
  ASSERT_EQ(goal.trajectory.points.size(), 1u);
  EXPECT_EQ(goal.trajectory.points[0].positions, (std::vector<double>{0.125, -0.25}));
  EXPECT_EQ(goal.trajectory.points[0].velocities, (std::vector<double>{0.0, 0.5}));
  EXPECT_EQ(goal.trajectory.points[0].accelerations, (std::vector<double>{0.125, -0.125}));
  EXPECT_EQ(goal.trajectory.points[0].time_from_start.nanosec, 2000000u);
  ASSERT_EQ(goal.path_tolerance.size(), 1u);
  EXPECT_EQ(goal.path_tolerance[0].name, "1");
  EXPECT_DOUBLE_EQ(goal.path_tolerance[0].position, 0.001);
  ASSERT_EQ(goal.goal_tolerance.size(), 1u);
  EXPECT_EQ(goal.goal_tolerance[0].name, "2");
  EXPECT_DOUBLE_EQ(goal.goal_tolerance[0].velocity, 0.005);
  EXPECT_EQ(goal.goal_time_tolerance.nanosec, 50000000u);
  EXPECT_TRUE(goal.multi_dof_trajectory.points.empty());
  EXPECT_TRUE(goal.component_path_tolerance.empty());
  EXPECT_TRUE(goal.component_goal_tolerance.empty());

  EXPECT_EQ(encode_controller_reservation_reply(ReservationReplyStatus::ACK, 5),
    (std::array<uint8_t, 16>{'S', 'O', 'G', 'A', 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 5}));
}

TEST(ControllerReservationProtocol, RejectsMalformedOrUnauthenticatedFrames)
{
  const auto valid = valid_frame();
  ASSERT_EQ(valid.size(), 322u);
  auto wrong_key = capability();
  wrong_key[0] ^= 1;
  EXPECT_THROW(parse_controller_reservation_frame(valid, wrong_key), std::invalid_argument);
  wrong_key = capability();
  wrong_key[31] ^= 1;
  EXPECT_THROW(parse_controller_reservation_frame(valid, wrong_key), std::invalid_argument);
  for (const auto [offset, value] : std::vector<std::pair<size_t, uint8_t>>{
    {0, 1}, {7, 'X'}, {8, 2}, {9, 2}})
  {
    auto frame = valid;
    frame[offset] = value;
    EXPECT_THROW(parse_controller_reservation_frame(frame, capability()), std::invalid_argument);
  }
  auto truncated = valid;
  truncated.pop_back();
  EXPECT_THROW(parse_controller_reservation_frame(truncated, capability()), std::invalid_argument);
  auto oversized = valid;
  oversized[0] = 1;
  EXPECT_THROW(parse_controller_reservation_frame(oversized, capability()), std::invalid_argument);
  auto zero_uuid = valid;
  for (size_t i = 50; i < 66; ++i) {
    zero_uuid[i] = 0;
  }
  EXPECT_THROW(parse_controller_reservation_frame(zero_uuid, capability()), std::invalid_argument);
  auto zero_generation = valid;
  for (size_t i = 42; i < 50; ++i) {
    zero_generation[i] = 0;
  }
  EXPECT_THROW(parse_controller_reservation_frame(zero_generation, capability()),
    std::invalid_argument);
  auto invalid_cdr = valid;
  invalid_cdr.resize(70);
  invalid_cdr[2] = 0;
  invalid_cdr[3] = 66;
  EXPECT_THROW(parse_controller_reservation_frame(invalid_cdr, capability()),
    std::invalid_argument);
}

TEST(ControllerReservationProtocol, CloseFrameCarriesOnlyAnAuthenticatedGeneration)
{
  std::vector<uint8_t> frame{0, 0, 0, 62, 'S', 'O', 'G', 'R', 1, 2};
  const auto key = capability();
  frame.insert(frame.end(), key.begin(), key.end());
  frame.insert(frame.end(), {0, 0, 0, 0, 0, 0, 0, 5});
  frame.insert(frame.end(), 16, 0);
  ASSERT_EQ(frame.size(), 66u);
  EXPECT_EQ(parse_controller_reservation_close_frame(frame, key), 5u);
  auto invalid = frame;
  invalid[10] ^= 1;
  EXPECT_THROW(parse_controller_reservation_close_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid[50] = 1;
  EXPECT_THROW(parse_controller_reservation_close_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid[9] = 1;
  EXPECT_THROW(parse_controller_reservation_close_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid[49] = 0;
  EXPECT_THROW(parse_controller_reservation_close_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid.push_back(1);
  EXPECT_THROW(parse_controller_reservation_close_frame(invalid, key), std::invalid_argument);
}

TEST(ControllerReservationProtocol, ArmFrameCarriesOnlyAnAuthenticatedStoppedGeneration)
{
  std::vector<uint8_t> frame{0, 0, 0, 62, 'S', 'O', 'G', 'R', 1, 3};
  const auto key = capability();
  frame.insert(frame.end(), key.begin(), key.end());
  frame.insert(frame.end(), {0, 0, 0, 0, 0, 0, 0, 5});
  frame.insert(frame.end(), 16, 0);
  ASSERT_EQ(frame.size(), 66u);
  EXPECT_EQ(parse_controller_reservation_arm_frame(frame, key), 5u);
  auto invalid = frame;
  invalid[10] ^= 1;
  EXPECT_THROW(parse_controller_reservation_arm_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid[9] = 2;
  EXPECT_THROW(parse_controller_reservation_arm_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid[49] = 0;
  EXPECT_THROW(parse_controller_reservation_arm_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid[50] = 1;
  EXPECT_THROW(parse_controller_reservation_arm_frame(invalid, key), std::invalid_argument);
  invalid = frame;
  invalid.push_back(1);
  EXPECT_THROW(parse_controller_reservation_arm_frame(invalid, key), std::invalid_argument);
}

TEST(ControllerReservationProtocol, ReadOnlyIngressQueryBindsRoleAndGeneration)
{
  std::vector<uint8_t> frame{0, 0, 0, 62, 'S', 'O', 'G', 'R', 1, 4};
  const auto key = capability();
  frame.insert(frame.end(), key.begin(), key.end());
  frame.insert(frame.end(), {0, 0, 0, 0, 0, 0, 0, 5});
  frame.push_back(static_cast<uint8_t>(ControllerReservationRole::ARM));
  frame.insert(frame.end(), 15, 0);
  ASSERT_EQ(frame.size(), 66u);
  EXPECT_EQ(parse_controller_ingress_query_frame(frame, key, ControllerReservationRole::ARM), 5u);
  auto invalid = frame;
  invalid[50] = static_cast<uint8_t>(ControllerReservationRole::NECK);
  EXPECT_THROW(parse_controller_ingress_query_frame(invalid, key,
    ControllerReservationRole::ARM), std::invalid_argument);
  invalid = frame;
  invalid[51] = 1;
  EXPECT_THROW(parse_controller_ingress_query_frame(invalid, key,
    ControllerReservationRole::ARM), std::invalid_argument);
  invalid = frame;
  invalid[10] ^= 1;
  EXPECT_THROW(parse_controller_ingress_query_frame(invalid, key,
    ControllerReservationRole::ARM), std::invalid_argument);
  invalid = frame;
  invalid[49] = 0;
  EXPECT_THROW(parse_controller_ingress_query_frame(invalid, key,
    ControllerReservationRole::ARM), std::invalid_argument);

  const auto reply = encode_controller_ingress_reply(
    ReservationReplyStatus::ACK, ControllerReservationRole::ARM, 5, 7, 123, 140);
  ASSERT_EQ(reply.size(), 40u);
  EXPECT_EQ((std::vector<uint8_t>(reply.begin(), reply.begin() + 8)),
    (std::vector<uint8_t>{'S', 'O', 'G', 'I', 1, 0, 1, 0}));
  EXPECT_EQ(reply[15], 5u);
  EXPECT_EQ(reply[23], 7u);
  EXPECT_EQ(reply[31], 123u);
  EXPECT_EQ(reply[39], 140u);
  EXPECT_THROW(encode_controller_ingress_reply(
    ReservationReplyStatus::ACK, ControllerReservationRole::ARM, 5, 7, 141, 140),
    std::invalid_argument);
}

namespace
{
using namespace so101_mujoco_support;
StopProofRecord passing_record()
{
  StopProofRecord p;
  p.evaluation_id = 47; p.wrapper_reason = StopWrapperReason::PASS;
  p.flags = 5; p.last_reset_reason = 1; p.sample_count = 51;
  p.first_sequence = 90; p.last_sequence = 140;
  p.first_sim_time_ns = 100000000; p.last_sim_time_ns = 200000000;
  p.first_received_ns = 300000000; p.last_received_ns = 400000000;
  p.evaluated_ns = 400000001; p.cumulative_observation_lock_losses = 0xff001234;
  return p;
}
std::vector<uint8_t> startup_request(const char * magic, uint8_t operation)
{
  std::vector<uint8_t> f{0,0,0,62};
  f.insert(f.end(),magic,magic+4); f.push_back(1); f.push_back(operation);
  const auto cap=capability(); f.insert(f.end(),cap.begin(),cap.end());
  f.insert(f.end(),{0,0,0,0,0,0,0,17}); f.insert(f.end(),16,0);
  return f;
}
}
TEST(ControllerReservationProtocol, new_fixed_requests_exact_shapes_and_legacy_unchanged)
{
  auto f=startup_request("SOGR",5);
  EXPECT_EQ(parse_prearm_query_frame(f,capability()),17u);
  f[9]=6; EXPECT_EQ(parse_diagnostic_arm_frame(f,capability()),17u);
  f[9]=3; EXPECT_EQ(parse_controller_reservation_arm_frame(f,capability()),17u);
  f=startup_request("SOPQ",2); EXPECT_EQ(parse_bootstrap_identity_frame(f,capability()),17u);
  for(size_t offset: {size_t(0),size_t(7),size_t(8),size_t(9),size_t(10),size_t(65)}) {
    auto bad=f; bad[offset]^=1;
    EXPECT_THROW(parse_bootstrap_identity_frame(bad,capability()),std::invalid_argument);
  }
}
TEST(ControllerReservationProtocol, new_wire_frames_reject_bad_lengths_codes_and_reserved_bytes)
{
  const auto proof=encode_stop_proof_record(passing_record());
  EXPECT_EQ(proof.size(),80u);
  EXPECT_EQ(proof[7],47); EXPECT_EQ(proof[14],255); EXPECT_EQ(proof[18],0xff);
  std::vector<uint8_t> b(proof.begin(),proof.end());
  auto decoded=parse_stop_proof_record(b);
  EXPECT_EQ(decoded.evaluation_id,47u); EXPECT_EQ(decoded.evaluated_ns,400000001);
  EXPECT_EQ(decoded.cumulative_observation_lock_losses,0xff001234u);
  for (size_t offset: {size_t(8),size_t(9),size_t(10),size_t(11),size_t(17),size_t(22),size_t(23)}) {
    auto bad=b; bad[offset]=255;
    EXPECT_THROW(parse_stop_proof_record(bad),std::invalid_argument) << offset;
  }
  b.push_back(0); EXPECT_THROW(parse_stop_proof_record(b),std::invalid_argument);
  StopProofRecord none;
  EXPECT_THROW(parse_stop_proof_record(std::vector<uint8_t>(80,0)),std::invalid_argument);
  const auto empty=encode_stop_proof_record(none);
  EXPECT_EQ(parse_stop_proof_record(std::vector<uint8_t>(empty.begin(),empty.end())).evaluation_id,0u);
}
TEST(ControllerReservationProtocol, scoped_identity_and_prearm_reply_maximum_roundtrip)
{
  IdentityScopeReply scope{0,17,0,{ControllerReservationRole::NECK,std::string(64,'i'),std::string(64,'b')}};
  const auto bootstrap=encode_identity_scope_reply(scope,false);
  EXPECT_EQ(bootstrap.size(),154u);
  EXPECT_EQ(parse_identity_scope_reply(bootstrap,false).identity.boot,scope.identity.boot);
  EXPECT_THROW(parse_identity_scope_reply(bootstrap,true),std::invalid_argument);
  scope.status=1;
  auto close=encode_identity_scope_reply(scope,true);
  EXPECT_EQ(close.size(),154u);
  EXPECT_EQ(parse_identity_scope_reply(close,true).stored_generation,0u);
  close[7]=1; EXPECT_THROW(parse_identity_scope_reply(close,true),std::invalid_argument);
  PrearmReply ready{PrearmStatus::READY,17,0,GateReason::NONE,scope.identity,passing_record()};
  const auto body=encode_prearm_reply(ready);
  EXPECT_EQ(body.size(),236u); EXPECT_EQ(parse_prearm_reply(body).proof.evaluation_id,47u);
  auto bad=body; bad[5]=1; EXPECT_THROW(parse_prearm_reply(bad),std::invalid_argument);
  bad=body; bad[25]=1; EXPECT_THROW(parse_prearm_reply(bad),std::invalid_argument);
  ready.proof.wrapper_reason=StopWrapperReason::WITNESS_REJECT;
  ready.proof.witness_rejection=2;
  EXPECT_THROW(encode_prearm_reply(ready),std::invalid_argument);
  ready.status=PrearmStatus::NOT_READY;
  EXPECT_EQ(parse_prearm_reply(encode_prearm_reply(ready)).status,PrearmStatus::NOT_READY);
}
TEST(ControllerReservationProtocol, scoped_close_request_bounds_and_arm_fixed_104)
{
  for(size_t length: {size_t(1),size_t(64)}) {
    auto f=startup_request("SOPC",1); f.resize(50);
    f.push_back(3); f.push_back(length); f.insert(f.end(),length,'i');
    f.push_back(length); f.insert(f.end(),length,'b'); f[3]=f.size()-4;
    const auto request=parse_scoped_close_frame(f);
    EXPECT_EQ(f.size()-4,49+2*length); EXPECT_EQ(request.generation,17u);
    EXPECT_EQ(request.expected_identity.incarnation,std::string(length,'i'));
    auto bad=f; bad.push_back(0); EXPECT_THROW(parse_scoped_close_frame(bad),std::invalid_argument);
    bad=f; bad[50]=1; EXPECT_THROW(parse_scoped_close_frame(bad),std::invalid_argument);
  }
  DiagnosticArmReply ack{ReservationReplyStatus::ACK,ControllerReservationRole::NECK,
    ArmPhase::NONE,17,GateReason::NONE,passing_record()};
  auto a=encode_diagnostic_arm_reply(ack);
  EXPECT_EQ(a.size(),104u);
  auto parsed=parse_diagnostic_arm_reply(std::vector<uint8_t>(a.begin(),a.end()));
  EXPECT_EQ(parsed.proof.evaluation_id,47u);
  for(size_t offset: {size_t(4),size_t(5),size_t(6),size_t(7),size_t(17),size_t(18),size_t(23)}) {
    auto bad=std::vector<uint8_t>(a.begin(),a.end()); bad[offset]=255;
    EXPECT_THROW(parse_diagnostic_arm_reply(bad),std::invalid_argument);
  }
}
TEST(ControllerReservationProtocol, ProofRecordRetains64SampleHistoryAnd51SampleWindow)
{
  auto proof=passing_record(); proof.sample_count=64;
  const auto bytes=encode_stop_proof_record(proof);
  const auto decoded=parse_stop_proof_record(std::vector<uint8_t>(bytes.begin(),bytes.end()));
  EXPECT_EQ(decoded.sample_count,64u);
  EXPECT_EQ(decoded.last_sequence-decoded.first_sequence,50u);
  proof.sample_count=65;
  EXPECT_THROW(encode_stop_proof_record(proof),std::invalid_argument);
}

TEST(ControllerReservationProtocol, WrapperEightRoundTripsOnlyCanonicalRecord)
{
  StopProofRecord p;
  p.evaluation_id = 101;
  p.wrapper_reason = static_cast<StopWrapperReason>(8);
  EXPECT_NO_THROW({
    const auto bytes = encode_stop_proof_record(p);
    EXPECT_EQ(bytes.size(), 80u);
    const auto decoded = parse_stop_proof_record(std::vector<uint8_t>(bytes.begin(), bytes.end()));
    EXPECT_EQ(static_cast<uint8_t>(decoded.wrapper_reason), 8);
    EXPECT_EQ(decoded.evaluation_id, 101u);
  });
  PrearmReply prearm{PrearmStatus::NOT_READY, 17, 0, GateReason::NONE,
    {ControllerReservationRole::NECK, "inc", "boot"}, p};
  EXPECT_NO_THROW(parse_prearm_reply(encode_prearm_reply(prearm)));
  for (const auto phase : {ArmPhase::STOP_BEFORE, ArmPhase::STOP_AFTER}) {
    DiagnosticArmReply arm{ReservationReplyStatus::REJECT, ControllerReservationRole::NECK,
      phase, 17, GateReason::NONE, p};
    EXPECT_NO_THROW({
      const auto bytes = encode_diagnostic_arm_reply(arm);
      EXPECT_EQ(bytes.size(), 104u);
      parse_diagnostic_arm_reply(std::vector<uint8_t>(bytes.begin(), bytes.end()));
    });
  }
}
TEST(ControllerReservationProtocol, WrapperEightRejectsForgedFieldsAndSuccessPhases)
{
  StopProofRecord canonical;
  canonical.evaluation_id = 102;
  canonical.wrapper_reason = static_cast<StopWrapperReason>(8);
  for (int field = 0; field < 17; ++field) {
    auto p = canonical;
    switch (field) {
      case 0: p.evaluation_id = 0; break;
      case 1: p.flags = 1; break;
      case 2: p.witness_rejection = 1; break;
      case 3: p.last_reset_reason = 1; break;
      case 4: p.sample_count = 1; break;
      case 5: p.failing_sample_index = 0; break;
      case 6: p.failing_joint_index = 0; break;
      case 7: p.last_reset_joint_index = 0; break;
      case 8: p.cumulative_observation_lock_losses = 1; break;
      case 9: p.first_sequence = 1; break;
      case 10: p.last_sequence = 1; break;
      case 11: p.first_sim_time_ns = 1; break;
      case 12: p.last_sim_time_ns = 1; break;
      case 13: p.first_received_ns = 1; break;
      case 14: p.last_received_ns = 1; break;
      case 15: p.evaluated_ns = 1; break;
      case 16: p.flags = 7; break;
    }
    EXPECT_THROW(encode_stop_proof_record(p), std::invalid_argument) << field;
  }
  PrearmReply ready{PrearmStatus::READY, 17, 0, GateReason::NONE,
    {ControllerReservationRole::NECK, "inc", "boot"}, canonical};
  EXPECT_THROW(encode_prearm_reply(ready), std::invalid_argument);
  DiagnosticArmReply arm{ReservationReplyStatus::ACK, ControllerReservationRole::NECK,
    ArmPhase::NONE, 17, GateReason::NONE, canonical};
  EXPECT_THROW(encode_diagnostic_arm_reply(arm), std::invalid_argument);
  arm.status = ReservationReplyStatus::REJECT;
  arm.phase = ArmPhase::GATE_ARM;
  arm.gate_reason = GateReason::NONINCREASING_GENERATION;
  EXPECT_THROW(encode_diagnostic_arm_reply(arm), std::invalid_argument);
}
TEST(ControllerReservationProtocol, SaturatedLossAndLegacyU32RemainWireCompatible)
{
  for (const uint32_t count : {uint32_t{0xFFFFFF}, uint32_t{0xFFFFFFFF}}) {
    auto p = passing_record();
    p.wrapper_reason = StopWrapperReason::WITNESS_REJECT;
    p.witness_rejection = 1;
    p.last_reset_reason = 4;
    p.flags = 7;
    p.cumulative_observation_lock_losses = count;
    const auto bytes = encode_stop_proof_record(p);
    EXPECT_EQ(parse_stop_proof_record(std::vector<uint8_t>(bytes.begin(), bytes.end())).cumulative_observation_lock_losses, count);
  }
}

TEST(ControllerReservationProtocol, OldOpcodeThreeReplyShapeUnchanged)
{
  for (const auto status : {ReservationReplyStatus::ACK, ReservationReplyStatus::REJECT}) {
    const auto reply = encode_controller_reservation_reply(status, 0x0102030405060708);
    const std::array<uint8_t, 16> expected{
      'S', 'O', 'G', 'A', 1, static_cast<uint8_t>(status), 0, 0,
      1, 2, 3, 4, 5, 6, 7, 8};
    EXPECT_EQ(reply, expected);
  }
}

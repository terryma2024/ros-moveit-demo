#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <poll.h>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <future>
#include <sstream>
#include <vector>
#include <cstdlib>
#include <gtest/gtest.h>
#include <time.h>
#include <unistd.h>

#include <array>
#include <cstdint>
#include <limits>

#include "so101_mujoco_support/head_revocation_transport.h"

namespace
{
uint64_t current_ns()
{
  timespec now{};
  EXPECT_EQ(clock_gettime(CLOCK_MONOTONIC, &now), 0);
  return static_cast<uint64_t>(now.tv_sec) * 1000000000ULL + now.tv_nsec;
}

uint32_t call(uint64_t request, uint64_t budget, uint32_t operation,
  So101HeadRevocationResult & result, bool simulation = false)
{
  std::array<uint8_t, 32> capability{};capability[0] = 1;
  const auto transport = simulation ? so101_head_revocation_simulation_exchange :
    so101_head_revocation_exchange;
  return transport("/no/actual/socket", capability.data(), 5,
    geteuid(), getpid(), 1, request, budget, operation, nullptr, &result);
}
}  // namespace

TEST(HeadRevocationTransport, DelayedNativeEntryConsumesOriginalDeadline)
{
  So101HeadRevocationResult result{};
  const auto request = current_ns() - 3000000;
  EXPECT_EQ(call(request, 2000000, 2, result), 5U);
  EXPECT_EQ(result.phase, 0U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(result.ack_ns, 0U);
  EXPECT_GE(result.entry_ns, request + 2000000);
}

TEST(HeadRevocationTransport, ExcessBudgetAndClockOverflowNeverReachSocket)
{
  So101HeadRevocationResult result{};
  EXPECT_EQ(call(current_ns(), 2000001, 2, result), 1U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(call(std::numeric_limits<uint64_t>::max(), 2000000, 2, result), 1U);
  EXPECT_EQ(result.ack_ns, 0U);
}

TEST(HeadRevocationTransport, InterfaceCannotEncodeArmOrReserve)
{
  So101HeadRevocationResult result{};
  for (uint32_t operation : {0U, 5U, 6U}) {
    EXPECT_EQ(call(current_ns(), 2000000, operation, result), 1U);
    EXPECT_EQ(result.phases_present, 0U);
    EXPECT_EQ(result.reply_size, 0U);
  }
}

TEST(HeadRevocationTransport, ExplicitSimulationBudgetIsFiniteAndIncludesDelayedEntry)
{
  EXPECT_EQ(so101_head_revocation_simulation_max_budget_ns(), 250000000U);
  So101HeadRevocationResult result{};
  EXPECT_EQ(call(current_ns() - 60000000, 50000000, 2, result, true), 5U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(result.ack_ns, 0U);
  EXPECT_EQ(call(current_ns(), 250000001, 2, result, true), 1U);
  EXPECT_EQ(result.phases_present, 0U);
  EXPECT_EQ(call(current_ns(), 0, 2, result, true), 1U);
  EXPECT_EQ(call(std::numeric_limits<uint64_t>::max(), 50000000, 2, result, true), 1U);
  // Within the explicit budget, the unchanged private-path check is reached.
  EXPECT_EQ(call(current_ns(), 50000000, 2, result, true), 2U);
}

TEST(HeadRevocationTransport, ExplicitSimulationCannotEncodeArmOrReserve)
{
  So101HeadRevocationResult result{};
  for (uint32_t operation : {0U, 5U, 6U}) {
    EXPECT_EQ(call(current_ns(), 50000000, operation, result, true), 1U);
    EXPECT_EQ(result.phases_present, 0U);
    EXPECT_EQ(result.reply_size, 0U);
  }
}
TEST(HeadRevocationTransport, Abi2BootstrapAndScopedCloseAreReadOnlyOrCloseOnly)
{
  EXPECT_EQ(so101_head_revocation_abi(),2u);
  EXPECT_EQ(sizeof(So101HeadExpectedIdentity),131u);
  EXPECT_EQ(sizeof(So101HeadRevocationResult::reply),154u);
  So101HeadRevocationResult result{};
  EXPECT_EQ(call(current_ns(),50000000,3,result,true),2u); // valid bootstrap reaches private-path check
  EXPECT_EQ(call(current_ns(),50000000,4,result,true),1u); // scoped close requires expected identity
}

namespace
{
uint64_t transport_self_ticks()
{
  std::ifstream input("/proc/self/stat"); std::string line; std::getline(input,line);
  std::istringstream fields(line.substr(line.rfind(')')+2));std::string token;
  for(int i=3;i<=22;++i) {fields>>token;}
  return std::stoull(token);
}
class ScopedReplyPeer
{
public:
  ScopedReplyPeer(std::vector<uint8_t> reply,bool truncate=false,bool oversize=false)
  {
    const auto parent=std::filesystem::path(std::getenv("SO101_IPC_SOCKET_BASE"))/"abi2";
    std::filesystem::create_directory(parent);chmod(parent.c_str(),0700);
    path=parent/("wire"+std::to_string(++sequence)+".sock");
    listener=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0);
    sockaddr_un address{};address.sun_family=AF_UNIX;
    std::memcpy(address.sun_path,path.c_str(),path.string().size()+1);
    if(bind(listener,reinterpret_cast<sockaddr *>(&address),sizeof(address)) ||
      chmod(path.c_str(),0600) || listen(listener,1)) {throw std::runtime_error("ABI_TEST_PEER_SETUP_FAILED");}
    worker=std::async(std::launch::async,[this,reply,truncate,oversize] {
      pollfd ready{listener,POLLIN,0}; if(poll(&ready,1,500)<=0) {return;}
      int fd=accept(listener,nullptr,nullptr);if(fd<0) {return;}
      timeval bound{1,0};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&bound,sizeof(bound));
      std::array<uint8_t,4> prefix{};
      auto exact=[&](uint8_t * data,size_t size) {
        size_t n=0;while(n<size) {const auto got=recv(fd,data+n,size-n,0);if(got<=0) {return false;} n+=got;}return true;
      };
      if(!exact(prefix.data(),4)) {close(fd);return;}
      size_t size=0;for(auto b:prefix) {size=(size<<8)|b;}
      if(size>177) {close(fd);return;}
      request.resize(size);
      if(!exact(request.data(),size)) {close(fd);return;}
      std::vector<uint8_t> response{0,0,0,static_cast<uint8_t>(oversize?155:reply.size())};
      response.insert(response.end(),reply.begin(),reply.end());
      if(truncate) {response.resize(response.size()-10);}
      send(fd,response.data(),response.size(),MSG_NOSIGNAL);close(fd);
    });
  }
  ~ScopedReplyPeer() {worker.wait();close(listener);unlink(path.c_str());}
  std::filesystem::path path; std::vector<uint8_t> request; std::future<void> worker;
private:
  int listener{-1}; inline static unsigned sequence=0;
};
So101HeadExpectedIdentity full_expected_identity()
{
  So101HeadExpectedIdentity id{};id.role=3;id.incarnation_length=64;id.boot_length=64;
  std::fill_n(id.incarnation,64,'i');std::fill_n(id.boot,64,'b');return id;
}
std::vector<uint8_t> full_scope_reply(bool close,uint8_t status,uint64_t stored)
{
  std::vector<uint8_t> body{'S','O','P',static_cast<uint8_t>(close?'D':'I'),1,status,3,0};
  for(uint64_t value:{uint64_t(5),stored}) {for(int shift=56;shift>=0;shift-=8) {body.push_back(value>>shift);}}
  body.push_back(64);body.insert(body.end(),64,'i');body.push_back(64);body.insert(body.end(),64,'b');return body;
}
uint32_t exchange_scope(ScopedReplyPeer & peer,uint32_t operation,So101HeadRevocationResult & result,
  const So101HeadExpectedIdentity * id=nullptr,uint64_t budget=50000000,uint64_t request=0)
{
  std::array<uint8_t,32> cap{};cap[0]=1;
  return so101_head_revocation_simulation_exchange(peer.path.c_str(),cap.data(),5,
    geteuid(),getpid(),transport_self_ticks(),request?request:current_ns(),budget,operation,id,&result);
}
}
TEST(HeadRevocationTransport, abi2_checks_full_154_byte_reply_and_deadline)
{
  So101HeadRevocationResult result{};
  {
    ScopedReplyPeer peer(full_scope_reply(false,0,0));
    EXPECT_EQ(exchange_scope(peer,3,result),0u);peer.worker.wait();
    EXPECT_EQ(result.reply_size,154u);EXPECT_GT(result.ack_ns,0u);
    ASSERT_EQ(peer.request.size(),62u);EXPECT_EQ(std::string(peer.request.begin(),peer.request.begin()+4),"SOPQ");
    EXPECT_EQ(peer.request[5],2); EXPECT_EQ(peer.request[45],5);
  }
  auto id=full_expected_identity();
  for(uint8_t state:{uint8_t(0),uint8_t(1)}) {
    ScopedReplyPeer peer(full_scope_reply(true,state,state==0?5:0));
    EXPECT_EQ(exchange_scope(peer,4,result,&id),0u);peer.worker.wait();
    EXPECT_EQ(result.reply_size,154u);ASSERT_EQ(peer.request.size(),177u);
    EXPECT_EQ(std::string(peer.request.begin(),peer.request.begin()+4),"SOPC");
    EXPECT_EQ(peer.request[46],3);EXPECT_EQ(peer.request[47],64);EXPECT_EQ(peer.request[112],64);
  }
  {
    ScopedReplyPeer peer(full_scope_reply(true,1,0));
    EXPECT_EQ(exchange_scope(peer,4,result,&id,50000000,current_ns()-60000000),5u);
    EXPECT_EQ(result.ack_ns,0u);EXPECT_EQ(result.phases_present,0u);
  }
}
TEST(HeadRevocationTransport, Abi2MalformedOrMismatchedRepliesCannotSeal)
{
  auto id=full_expected_identity();
  for(int damage=0;damage<10;++damage) {
    auto reply=full_scope_reply(true,1,0);
    if(damage==0) {reply[4]=2;}if(damage==1) {reply[6]=1;}
    if(damage==2) {reply[7]=1;}if(damage==3) {reply[5]=4;}
    if(damage==4) {reply[23]=5;}if(damage==5) {reply[15]=6;}
    if(damage==6) {reply[25]='x';}if(damage==7) {reply[24]=0;}
    ScopedReplyPeer peer(reply,damage==8,damage==9);So101HeadRevocationResult result{};
    EXPECT_NE(exchange_scope(peer,4,result,&id),0u) << damage;
    EXPECT_EQ(result.ack_ns,0u) << damage;
  }
}

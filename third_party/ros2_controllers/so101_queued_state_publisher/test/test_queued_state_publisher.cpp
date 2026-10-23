// Copyright 2026 SO-101 maintainers
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <gtest/gtest.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "so101_queued_state_publisher/queued_state_publisher.hpp"

namespace
{
struct Msg
{
  uint64_t sequence{0};
  std::vector<double> values;
  std::string label;
  bool operator==(const Msg & other) const
  {
    return sequence == other.sequence && values == other.values && label == other.label;
  }
};

Msg make_message(uint64_t sequence, const Msg & shape)
{
  Msg out = shape;
  out.sequence = sequence;
  for (std::size_t i = 0; i < out.values.size(); ++i) {
    out.values[i] = static_cast<double>(sequence) * 10.0 + static_cast<double>(i);
  }
  return out;
}

Msg prototype()
{
  Msg shape;
  shape.values.resize(6);
  shape.label = "arm";
  return shape;
}

using Publisher = so101_queued_state_publisher::QueuedStatePublisher<Msg>;

/// A sink that records what it receives and can be held shut, standing in for a publishing thread that is late.
class Receiver
{
public:
  void operator()(const Msg & message)
  {
    std::unique_lock<std::mutex> lock(mutex_);
    gate_.wait(lock, [this] {return open_;});
    if (throw_on_ == message.sequence) {
      throw std::runtime_error("sink failure");
    }
    received_.push_back(message);
    changed_.notify_all();
  }
  void close() {std::lock_guard<std::mutex> lock(mutex_); open_ = false;}
  void open() {{std::lock_guard<std::mutex> lock(mutex_); open_ = true;} gate_.notify_all();}
  void throw_on(uint64_t sequence) {std::lock_guard<std::mutex> lock(mutex_); throw_on_ = sequence;}
  bool wait_for_count(std::size_t count, std::chrono::seconds timeout = std::chrono::seconds(5))
  {
    std::unique_lock<std::mutex> lock(mutex_);
    return changed_.wait_for(lock, timeout, [&] {return received_.size() >= count;});
  }
  std::vector<Msg> received()
  {
    std::lock_guard<std::mutex> lock(mutex_);
    return received_;
  }

private:
  std::mutex mutex_;
  std::condition_variable gate_;
  std::condition_variable changed_;
  bool open_{true};
  uint64_t throw_on_{UINT64_MAX};
  std::vector<Msg> received_;
};


/// Opens the receiver when the test scope ends (declared after the publisher, so it runs before the publisher joins):
/// a failed assertion must not leave the publishing thread stuck behind a closed gate.
struct OpenOnExit
{
  explicit OpenOnExit(Receiver & r) : receiver(r) {}
  ~OpenOnExit() {receiver.open();}
  Receiver & receiver;
};
}  // namespace

// The receiver sees a message inside the sink, but the publisher counts it as published only after the sink returns: a test that
// has just seen the last message must wait for the counter instead of reading it at once (under load the two differ by one).
template<typename P>
bool wait_for_published(P & publisher, uint64_t count, std::chrono::seconds timeout = std::chrono::seconds(20))
{
  const auto deadline = std::chrono::steady_clock::now() + timeout;
  while (publisher.stats().published < count) {
    if (std::chrono::steady_clock::now() >= deadline) {return false;}
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  return true;
}

TEST(QueuedStatePublisherTest, EveryMessageIsPublishedInOrderWhileThePublishingThreadIsBlocked)
{
  Receiver receiver;
  receiver.close();
  Publisher publisher(prototype(), 1024, [&receiver](const Msg & m) {receiver(m);});
  OpenOnExit guard(receiver);
  const auto shape = prototype();
  std::vector<Msg> sent;
  const auto begin = std::chrono::steady_clock::now();
  for (uint64_t i = 0; i < 700; ++i) {
    sent.push_back(make_message(i, shape));
    ASSERT_TRUE(publisher.push(sent.back())) << "message " << i;
  }
  // The realtime side finished although nothing could be published yet: push never waits for the sink.
  EXPECT_LT(std::chrono::steady_clock::now() - begin, std::chrono::seconds(2));
  EXPECT_EQ(receiver.received().size(), 0U);
  receiver.open();
  ASSERT_TRUE(receiver.wait_for_count(700));
  ASSERT_TRUE(wait_for_published(publisher, 700));
  EXPECT_EQ(receiver.received(), sent);
  const auto stats = publisher.stats();
  EXPECT_EQ(stats.enqueued, 700U);
  EXPECT_EQ(stats.published, 700U);
  EXPECT_EQ(stats.overflowed, 0U);
  EXPECT_EQ(stats.sink_errors, 0U);
  EXPECT_GE(stats.high_water, 600U);
  EXPECT_EQ(stats.capacity, 1024U);
}

TEST(QueuedStatePublisherTest, AFullQueueIsCountedAndWarnedAboutNeverSilentlyDropped)
{
  Receiver receiver;
  receiver.close();
  std::mutex log_mutex;
  std::vector<std::string> warnings;
  Publisher publisher(
    prototype(), 8, [&receiver](const Msg & m) {receiver(m);},
    [&](Publisher::Level level, const std::string & text) {
      if (level == Publisher::Level::kWarn) {
        std::lock_guard<std::mutex> lock(log_mutex);
        warnings.push_back(text);
      }
    },
    "arm");
  OpenOnExit guard(receiver);
  const auto shape = prototype();
  std::vector<Msg> accepted;
  std::size_t refused = 0;
  for (uint64_t i = 0; i < 20; ++i) {
    const auto message = make_message(i, shape);
    if (publisher.push(message)) {
      accepted.push_back(message);
    } else {
      ++refused;
    }
  }
  EXPECT_EQ(accepted.size(), 8U);
  EXPECT_EQ(refused, 12U);
  EXPECT_EQ(publisher.stats().overflowed, 12U);
  EXPECT_EQ(publisher.stats().enqueued, 8U);
  // The warning comes from the publishing thread, which is blocked in the sink; free it and wait for the line.
  receiver.open();
  ASSERT_TRUE(receiver.wait_for_count(8));
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  for (;;) {
    {
      std::lock_guard<std::mutex> lock(log_mutex);
      if (!warnings.empty() || std::chrono::steady_clock::now() > deadline) {break;}
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  std::lock_guard<std::mutex> lock(log_mutex);
  ASSERT_FALSE(warnings.empty());
  EXPECT_NE(warnings.front().find("queue full"), std::string::npos) << warnings.front();
  EXPECT_NE(warnings.front().find("[arm]"), std::string::npos) << warnings.front();
  EXPECT_EQ(receiver.received(), accepted) << "the accepted messages stay complete and in order";
}

TEST(QueuedStatePublisherTest, ASlowSinkLosesNothingAtTheControllerRate)
{
  Receiver receiver;
  Publisher publisher(prototype(), 2048, [&receiver](const Msg & m) {
      std::this_thread::sleep_for(std::chrono::microseconds(300));  // slower than the producer below
      receiver(m);
    });
  const auto shape = prototype();
  std::vector<Msg> sent;
  for (uint64_t i = 0; i < 2000; ++i) {
    sent.push_back(make_message(i, shape));
    ASSERT_TRUE(publisher.push(sent.back()));
    if (i % 4 == 0) {std::this_thread::sleep_for(std::chrono::microseconds(100));}
  }
  ASSERT_TRUE(receiver.wait_for_count(2000, std::chrono::seconds(20)));
  ASSERT_TRUE(wait_for_published(publisher, 2000));
  EXPECT_EQ(receiver.received(), sent);
  const auto stats = publisher.stats();
  EXPECT_EQ(stats.overflowed, 0U);
  EXPECT_EQ(stats.published, 2000U);
  EXPECT_GT(stats.would_have_skipped, 0U) << "a single-slot publisher would have lost messages here";
}

TEST(QueuedStatePublisherTest, CountsTheMessagesASingleSlotPublisherWouldHaveRefused)
{
  Receiver receiver;
  receiver.close();
  Publisher publisher(prototype(), 16, [&receiver](const Msg & m) {receiver(m);});
  OpenOnExit guard(receiver);
  const auto shape = prototype();
  for (uint64_t i = 0; i < 3; ++i) {
    ASSERT_TRUE(publisher.push(make_message(i, shape)));
  }
  // The first message found an idle publisher; the 2nd and 3rd found the previous one still unpublished.
  EXPECT_EQ(publisher.stats().would_have_skipped, 2U);
  receiver.open();
  ASSERT_TRUE(receiver.wait_for_count(3));
}

TEST(QueuedStatePublisherTest, AFailingSinkIsCountedAndTheStreamContinues)
{
  Receiver receiver;
  receiver.throw_on(2);
  Publisher publisher(prototype(), 16, [&receiver](const Msg & m) {receiver(m);});
  const auto shape = prototype();
  for (uint64_t i = 0; i < 5; ++i) {
    ASSERT_TRUE(publisher.push(make_message(i, shape)));
  }
  ASSERT_TRUE(receiver.wait_for_count(4));
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  while (publisher.stats().sink_errors == 0 && std::chrono::steady_clock::now() < deadline) {
    std::this_thread::sleep_for(std::chrono::milliseconds(2));
  }
  ASSERT_TRUE(wait_for_published(publisher, 4));
  const auto stats = publisher.stats();
  EXPECT_EQ(stats.sink_errors, 1U);
  EXPECT_EQ(stats.published, 4U);
  std::vector<uint64_t> sequences;
  for (const auto & message : receiver.received()) {sequences.push_back(message.sequence);}
  EXPECT_EQ(sequences, (std::vector<uint64_t>{0, 1, 3, 4}));
}

TEST(QueuedStatePublisherTest, ThePeriodicLineCarriesEveryCounter)
{
  Receiver receiver;
  std::mutex log_mutex;
  std::vector<std::string> lines;
  Publisher publisher(
    prototype(), 32, [&receiver](const Msg & m) {receiver(m);},
    [&](Publisher::Level level, const std::string & text) {
      if (level == Publisher::Level::kInfo) {
        std::lock_guard<std::mutex> lock(log_mutex);
        lines.push_back(text);
      }
    },
    "neck", std::chrono::milliseconds(20));
  const auto shape = prototype();
  for (uint64_t i = 0; i < 5; ++i) {
    ASSERT_TRUE(publisher.push(make_message(i, shape)));
  }
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
  for (;;) {
    {
      std::lock_guard<std::mutex> lock(log_mutex);
      if (!lines.empty() || std::chrono::steady_clock::now() > deadline) {break;}
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
  }
  std::lock_guard<std::mutex> lock(log_mutex);
  ASSERT_FALSE(lines.empty());
  for (const char * needle :
    {"queued state publisher [neck]", "enqueued(total) 5", "published(total) 5", "overflowed(total) 0",
      "would_have_skipped_by_try_publish(total)", "sink_errors(total) 0", "queue high-water"})
  {
    EXPECT_NE(lines.front().find(needle), std::string::npos) << needle << " in " << lines.front();
  }
}

TEST(QueuedStatePublisherTest, StopPublishesWhatIsStillQueuedAndJoins)
{
  Receiver receiver;
  receiver.close();
  {
    Publisher publisher(prototype(), 16, [&receiver](const Msg & m) {receiver(m);});
    OpenOnExit guard(receiver);
    const auto shape = prototype();
    for (uint64_t i = 0; i < 10; ++i) {
      ASSERT_TRUE(publisher.push(make_message(i, shape)));
    }
    std::thread release([&receiver] {
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        receiver.open();
      });
    publisher.stop();
    release.join();
    publisher.stop();  // idempotent
    EXPECT_EQ(receiver.received().size(), 10U) << "stop publishes what is still queued";
  }
}

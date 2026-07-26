#include <gtest/gtest.h>

#include "so101_gazebo_demo/pick_place/attachment_state_reducer.hpp"

namespace pick_place = so101_gazebo_demo::pick_place;

TEST(AttachmentStateReducer, StartsUnknownAndIgnoresUnrecognizedEvents)
{
  pick_place::AttachmentStateReducer reducer;

  EXPECT_FALSE(reducer.state().has_value());
  EXPECT_FALSE(reducer.consume(""));
  EXPECT_FALSE(reducer.consume("command_delivered"));
  EXPECT_FALSE(reducer.state().has_value());
}

TEST(AttachmentStateReducer, BecomesDurableOnlyFromRawPluginEvents)
{
  pick_place::AttachmentStateReducer reducer;

  EXPECT_TRUE(reducer.consume("detached"));
  ASSERT_TRUE(reducer.state().has_value());
  EXPECT_FALSE(*reducer.state());

  EXPECT_TRUE(reducer.consume("attached"));
  ASSERT_TRUE(reducer.state().has_value());
  EXPECT_TRUE(*reducer.state());
}

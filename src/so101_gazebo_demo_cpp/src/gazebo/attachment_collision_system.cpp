#include <atomic>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include <gz/common/Console.hh>
#include <gz/msgs/empty.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/EntityComponentManager.hh>
#include <gz/sim/System.hh>
#include <gz/sim/components/Collision.hh>
#include <gz/sim/components/Model.hh>
#include <gz/sim/components/Name.hh>
#include <gz/transport/Node.hh>

namespace so101_gazebo_demo
{

class AttachmentCollisionSystem final : public gz::sim::System,
                                        public gz::sim::ISystemConfigure,
                                        public gz::sim::ISystemPreUpdate
{
public:
  void Configure(const gz::sim::Entity &, const std::shared_ptr<const sdf::Element> & sdf,
                 gz::sim::EntityComponentManager &, gz::sim::EventManager &) override
  {
    if (sdf && sdf->HasElement("child_model")) {
      child_model_ = sdf->Get<std::string>("child_model");
    }
    if (sdf && sdf->HasElement("attach_topic")) {
      attach_topic_ = sdf->Get<std::string>("attach_topic");
    }
    if (sdf && sdf->HasElement("detach_topic")) {
      detach_topic_ = sdf->Get<std::string>("detach_topic");
    }
    if (sdf && sdf->HasElement("joint_state_topic")) {
      joint_state_topic_ = sdf->Get<std::string>("joint_state_topic");
    }
    if (sdf && sdf->HasElement("collision_state_topic")) {
      collision_state_topic_ = sdf->Get<std::string>("collision_state_topic");
    }
    if (child_model_.empty() || attach_topic_.empty() || detach_topic_.empty() ||
        joint_state_topic_.empty() || collision_state_topic_.empty()) {
      gzerr << "AttachmentCollisionSystem requires child_model, command, joint-state and "
               "collision-state topics\n";
      configured_ = false;
      return;
    }
    const bool attach_ok =
      node_.Subscribe(attach_topic_, &AttachmentCollisionSystem::OnAttach, this);
    const bool detach_ok =
      node_.Subscribe(detach_topic_, &AttachmentCollisionSystem::OnDetach, this);
    const bool state_ok =
      node_.Subscribe(joint_state_topic_, &AttachmentCollisionSystem::OnJointState, this);
    state_publisher_ = node_.Advertise<gz::msgs::StringMsg>(collision_state_topic_);
    configured_ = attach_ok && detach_ok && state_ok && state_publisher_.Valid();
    if (!configured_) {
      gzerr << "AttachmentCollisionSystem failed to subscribe to attachment topics\n";
    }
  }

  void PreUpdate(const gz::sim::UpdateInfo &, gz::sim::EntityComponentManager & ecm) override
  {
    if (!configured_)
      return;
    const bool enabled = collision_enabled_.load(std::memory_order_acquire);
    if (applied_ && *applied_ == enabled)
      return;
    const auto entity =
      ecm.EntityByComponents(gz::sim::components::Model(), gz::sim::components::Name(child_model_));
    if (entity == gz::sim::kNullEntity)
      return;
    if (enabled) {
      for (const auto collision : disabled_collisions_) {
        if (!ecm.Component<gz::sim::components::Collision>(collision)) {
          ecm.CreateComponent(collision, gz::sim::components::Collision());
        }
      }
    } else {
      disabled_collisions_.clear();
      for (const auto descendant : ecm.Descendants(entity)) {
        if (ecm.Component<gz::sim::components::Collision>(descendant)) {
          disabled_collisions_.push_back(descendant);
          ecm.RemoveComponent<gz::sim::components::Collision>(descendant);
        }
      }
    }
    applied_ = enabled;
    gz::msgs::StringMsg state;
    state.set_data(enabled ? "enabled" : "disabled");
    static_cast<void>(state_publisher_.Publish(state));
    gzmsg << "AttachmentCollisionSystem child_model=" << child_model_
          << " collision_enabled=" << (enabled ? "true" : "false")
          << " collision_count=" << disabled_collisions_.size() << '\n';
  }

private:
  void OnAttach(const gz::msgs::Empty &)
  {
    requested_attached_.store(true, std::memory_order_release);
  }

  void OnDetach(const gz::msgs::Empty &)
  {
    requested_attached_.store(false, std::memory_order_release);
  }

  void OnJointState(const gz::msgs::StringMsg & state)
  {
    if (state.data() == "detached") {
      collision_enabled_.store(true, std::memory_order_release);
      return;
    }
    if (state.data() == "attached" && requested_attached_.load(std::memory_order_acquire)) {
      collision_enabled_.store(false, std::memory_order_release);
    }
  }

  gz::transport::Node node_;
  std::string child_model_;
  std::string attach_topic_;
  std::string detach_topic_;
  std::string joint_state_topic_;
  std::string collision_state_topic_;
  gz::transport::Node::Publisher state_publisher_;
  std::atomic<bool> requested_attached_{false};
  std::atomic<bool> collision_enabled_{true};
  std::optional<bool> applied_;
  std::vector<gz::sim::Entity> disabled_collisions_;
  bool configured_{false};
};

}  // namespace so101_gazebo_demo

GZ_ADD_PLUGIN(so101_gazebo_demo::AttachmentCollisionSystem, gz::sim::System,
              so101_gazebo_demo::AttachmentCollisionSystem::ISystemConfigure,
              so101_gazebo_demo::AttachmentCollisionSystem::ISystemPreUpdate)

GZ_ADD_PLUGIN_ALIAS(so101_gazebo_demo::AttachmentCollisionSystem,
                    "so101_gazebo_demo::AttachmentCollisionSystem")

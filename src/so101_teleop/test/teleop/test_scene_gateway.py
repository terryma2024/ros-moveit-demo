import asyncio

from so101_teleop.scene_gateway import SceneGateway


def test_attach_rolls_back_gazebo_after_moveit_failure():
    """Leaving Gazebo attached after MoveIt attach fails causes a physical/scene split brain."""
    async def scenario():
        calls = []

        class Backend:
            async def gazebo_attach(self, object_name): calls.append("gazebo_attach"); return True
            async def gazebo_detach(self, object_name): calls.append("gazebo_detach"); return True
            async def gazebo_attached(self, object_name):
                calls.append("verify_gazebo" if "gazebo_detach" not in calls else "verify_gazebo_detached")
                return "gazebo_detach" not in calls
            async def moveit_attach(self, object_name): calls.append("moveit_attach"); return False
            async def moveit_detach_to_world(self, object_name, pose): calls.append("moveit_detach"); return True
            async def object_pose(self, object_name): return None
            async def wait_stationary(self, object_name): return True
            async def reset_world(self): return True
            async def verify_reset(self): return False

        result = await SceneGateway(Backend()).attach("plastic_cup")

        assert calls == ["gazebo_attach", "verify_gazebo", "moveit_attach", "gazebo_detach", "verify_gazebo_detached"]
        assert result.layers == {"gazebo": "detached", "moveit": "world"}
        assert result.code == "MOVEIT_ATTACH_FAILED"

    asyncio.run(scenario())


def test_reset_reports_unconverged_scene():
    """Reporting reset success before every layer converges would re-enable unsafe controls."""
    async def scenario():
        class Backend:
            async def gazebo_attach(self, object_name): return True
            async def gazebo_detach(self, object_name): return True
            async def gazebo_attached(self, object_name): return False
            async def moveit_attach(self, object_name): return True
            async def moveit_detach_to_world(self, object_name, pose): return True
            async def object_pose(self, object_name): return None
            async def wait_stationary(self, object_name): return True
            async def reset_world(self): return True
            async def verify_reset(self): return False

        result = await SceneGateway(Backend()).reset_simulation()

        assert result.code == "RESET_INCOMPLETE"
        assert result.succeeded is False

    asyncio.run(scenario())

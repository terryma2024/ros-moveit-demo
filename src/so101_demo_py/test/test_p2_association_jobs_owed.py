"""Pilot 8d9ed9d3: the first row (21.9 s) was verified against the `initial` association because the Teacher's SETUP
apply (21.862 s) and read-back (21.884 s) had been ingested but their association job was not built yet: neither owed (the
tracker had paired them) nor pending (nothing was built), so `at()` returned the older association and the row failed
`LIVE_PHYSICAL_SCENE_GEOMETRY_INVALID`. A job issued and not yet admitted is owed like an open apply."""

from types import SimpleNamespace

from so101_demo.act.recorder_scene import AssociationJob, SceneAssociations


def _bound(operation, sim_ns):
    association = {"operation": operation, "association_id": operation,
                   "apply": None if operation == "initial" else {"record": {"response_ros_clock": {"sim_time_ns": sim_ns}}},
                   "query": {"record": {"response_ros_clock": {"sim_time_ns": sim_ns}}}}
    return {"association": association}


def _associations():
    associations = SceneAssociations()
    associations.history.append(_bound("initial", 21_664_000_000))
    return associations


def test_a_row_waits_for_an_association_job_that_is_issued_and_not_built_yet():
    associations = _associations()
    assert associations.at(21.9, None)["association"]["operation"] == "initial"
    assert associations.at(21.9, None, unbuilt_sim_times=[21_862_000_000]) is None
    assert associations.at(21.8, None, unbuilt_sim_times=[21_862_000_000])["association"]["operation"] == "initial"


def test_the_sources_report_the_apply_time_of_every_unbuilt_job():
    from so101_demo.ros.episode_recorder_sources import RosRecorderSources

    sources = object.__new__(RosRecorderSources)
    apply = {"response_ros_clock": {"sim_time_ns": 21_862_000_000}}
    query = {"response_ros_clock": {"sim_time_ns": 21_884_000_000}}
    sources._jobs = [AssociationJob("world_sync", apply, query, None, 0.0),
                     AssociationJob("initial", None, {"response_ros_clock": {"sim_time_ns": 21_664_000_000}}, None, 0.0)]
    sources.associations, sources.tracker = _associations(), SimpleNamespace(owed_apply_sim_times=lambda: [])
    assert sorted(sources._unbuilt_job_sim_times()) == [21_664_000_000, 21_862_000_000]
    assert sources._association_at(21.9) is None
    sources._jobs = []
    assert sources._association_at(21.9)["association"]["operation"] == "initial"

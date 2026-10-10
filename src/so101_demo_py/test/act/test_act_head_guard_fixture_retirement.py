"""Retired guard fixtures release their large native buffers without waiting for GC."""
import inspect
import weakref
from types import SimpleNamespace

from test_act_head_trajectory_guard import guard
from test_act_head_paused_admission import paused_head

def test_guard_owner_releases_native_model_and_data_after_fixture_retirement(tmp_path_factory):
    fixture=guard.__wrapped__(tmp_path_factory)
    value=next(fixture) if inspect.isgenerator(fixture) else fixture
    retained=[weakref.ref(value._model),weakref.ref(value._data),weakref.ref(value.checker._data)]
    if inspect.isgenerator(fixture):fixture.close()
    assert all(ref() is None for ref in retained), 'retired fixture still owns native model/data buffers'

def test_paused_peer_releases_owned_data_but_preserves_borrowed_model(guard,monkeypatch,tmp_path_factory):
    request=SimpleNamespace(getfixturevalue=lambda name:guard,param=None)
    fixture=paused_head.__wrapped__(monkeypatch,tmp_path_factory,request)
    value=next(fixture)
    peer_data=weakref.ref(value.data); guard_data=weakref.ref(value.guard._data)
    model=weakref.ref(guard._model)
    fixture.close()
    assert peer_data() is None and guard_data() is None, 'retired peer still owns native data buffers'
    assert model() is guard.checker.model and model() is not None, 'peer released its borrowed model'

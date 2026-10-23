"""Old online Head entries refuse before allocating any runtime resources."""
import inspect

import pytest

from so101_demo.act.head_search_restarts import contracts as restarts_contracts
from so101_demo.act.head_search_restarts import restart_run, search_flight


@pytest.mark.parametrize('entry', ['run_anchor_restart', 'measure_and_search'])
def test_direct_legacy_execution_refuses_before_claiming_run_root(tmp_path, entry):
    function = getattr(restart_run if entry == 'run_anchor_restart' else search_flight, entry)
    kwargs = {name: None for name, parameter in inspect.signature(function).parameters.items()
              if parameter.default is inspect.Parameter.empty}
    root = tmp_path / 'unclaimed'
    kwargs.update(anchor='default')
    kwargs['anchor_root' if entry == 'run_anchor_restart' else 'root'] = root
    with pytest.raises(restarts_contracts.RestartRefused, match='HEAD_LEGACY_EXECUTION_REMOVED'):
        function(**kwargs)
    assert not root.exists()

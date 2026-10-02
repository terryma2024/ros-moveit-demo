"""Actual owned CPU threads must exit before a Head retirement receipt exists."""
import os
import threading
from types import SimpleNamespace

import pytest
from so101_demo.adapters.act.head_monitor_runtime import HeadMonitorRuntime,_peer


def runtime():
    return HeadMonitorRuntime(epoch='attempt',generation=5,session_id='session',primary=_peer(os.getppid()))


@pytest.mark.parametrize('owned',['watchdog','spinner','configuration'])
def test_live_owned_thread_cannot_be_certified_retired(owned):
    monitor=runtime();release=threading.Event()
    thread=threading.Thread(target=release.wait,name='controlled-owned-'+owned);thread.start()
    if owned=='watchdog':monitor._threads=[thread]
    elif owned=='spinner':monitor._spinner=thread
    else:monitor._configure_thread=thread
    try:
        with pytest.raises(PermissionError,match='RETIRE_UNCONFIRMED'):monitor.close()
        assert not monitor._finished and thread.is_alive()
    finally:
        release.set();thread.join(1.)
        assert not thread.is_alive()
        monitor.close()


def test_executor_incomplete_shutdown_cannot_be_certified_retired():
    monitor=runtime();monitor._executor=SimpleNamespace(shutdown=lambda **kw:False)
    try:
        with pytest.raises(PermissionError,match='RETIRE_UNCONFIRMED'):monitor.close()
        assert not monitor._finished
    finally:
        monitor._executor.shutdown=lambda **kw:True
        monitor.close()


def test_blocked_owned_action_io_cannot_be_certified_retired():
    from test_act_head_monitor_ros import observer
    _,owned,_,_=observer();monitor=runtime();monitor._observer=owned
    release=threading.Event();started=threading.Event()
    def blocked():started.set();release.wait()
    owned.port._head_io['result'].submit(blocked,lambda error:None)
    assert started.wait(1.)
    try:
        with pytest.raises(PermissionError,match='RETIRE_UNCONFIRMED'):monitor.close()
        assert not monitor._finished
    finally:
        release.set()
        assert owned.close(timeout_s=1.)['result']['retired'] is True
        monitor.close()

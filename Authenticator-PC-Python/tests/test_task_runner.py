"""验证后台工作成功/失败后只经 ``drain`` 调度完成回调。"""

import threading

from infrastructure.task_runner import BackgroundTaskRunner


def test_background_task_runner_dispatches_success_and_error():
    """成功和异常工作都应在 ``drain`` 后调用对应主线程回调。"""

    runner = BackgroundTaskRunner(max_workers=1)
    success_ready = threading.Event()
    error_ready = threading.Event()

    success = runner.submit(lambda: 42, lambda value: (success_ready.set(), value), lambda _error: None)
    success.result(timeout=2)
    runner.drain()
    assert success_ready.is_set()

    failure = runner.submit(
        lambda: (_ for _ in ()).throw(ValueError("bad")),
        lambda _value: None,
        lambda error: error_ready.set() if str(error) == "bad" else None,
    )
    try:
        failure.result(timeout=2)
    except ValueError:
        pass
    runner.drain()
    assert error_ready.is_set()
    runner.close()

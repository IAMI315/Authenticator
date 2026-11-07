"""验证 API 控制器可在无 Tk 控件时消费队列并回写响应。"""

from presentation.api_controller import ApiController


def test_api_controller_processes_requests_without_ui_objects():
    """控制器在无实际窗口时仍可读取请求队列并回写服务响应。"""

    class Service:
        """最小业务替身：回显动作和负载，验证控制器不依赖具体 API 服务。"""

        def handle(self, action, payload):
            """返回可断言的固定成功响应。"""

            return 200, {"action": action, "payload": payload}

    controller = ApiController(Service(), "token")
    response_queue = controller.requests
    import queue

    replies = queue.Queue(maxsize=1)
    from infrastructure.api_server import ApiRequest

    response_queue.put(ApiRequest("health", {"x": 1}, replies))
    assert controller.process() == 1
    assert replies.get_nowait() == (200, {"action": "health", "payload": {"x": 1}})


def test_api_controller_defers_scan_response_until_ui_flow_completes():
    """扫码启动后 HTTP 响应必须等待 UI 流程的完成回调。"""

    import queue

    callbacks = []

    class Service:
        def handle(self, action, payload):
            assert action == "scan_add"
            return 200, {"group_ids": ["default"]}

    def start_scan(payload, completion):
        assert payload == {"group_ids": ["default"]}
        callbacks.append(completion)
        return True

    controller = ApiController(Service(), "token", scan_request_handler=start_scan)
    replies = queue.Queue(maxsize=1)
    from infrastructure.api_server import ApiRequest

    controller.requests.put(ApiRequest("scan_add", {}, replies))
    assert controller.process() == 1
    assert replies.empty()
    callbacks.pop()((201, {"completed": True, "accounts_added": 1}))
    assert replies.get_nowait() == (201, {"completed": True, "accounts_added": 1})

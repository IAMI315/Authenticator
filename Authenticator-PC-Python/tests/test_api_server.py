"""验证 loopback HTTP 服务的令牌认证、队列分发和请求体校验。"""

import http.client
import json
import queue
import threading

from infrastructure.api_server import LOCAL_API_BASE_PATH, LocalApiServer


def test_local_api_server_authentication_and_dispatch():
    """未带令牌的请求拒绝；有效令牌请求应经队列获得主线程响应。"""

    requests = queue.Queue()
    server = LocalApiServer("test-token", requests, port=0)
    assert server.start() is None

    def consume_one():
        """模拟 Tk 主线程消费一条健康检查并将结果写回响应队列。"""

        request = requests.get(timeout=2)
        assert request.action == "health"
        request.response.put((200, {"status": "ready", "locked": False, "api_version": 1}))

    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
        connection.request("GET", f"{LOCAL_API_BASE_PATH}/health")
        response = connection.getresponse()
        assert response.status == 401
        response.read()
        connection.close()

        worker = threading.Thread(target=consume_one)
        worker.start()
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
        connection.request("GET", f"{LOCAL_API_BASE_PATH}/health", headers={"X-Authenticator-Token": "test-token"})
        response = connection.getresponse()
        document = json.loads(response.read().decode("utf-8"))
        worker.join(timeout=2)
        assert response.status == 200
        assert document["status"] == "ready"
        connection.close()
    finally:
        server.stop()


def test_local_api_server_rejects_malformed_post_without_dispatch():
    """JSON 数组不是账户创建要求的对象，传输层应在入队前拒绝。"""

    requests = queue.Queue()
    server = LocalApiServer("test-token", requests, port=0)
    assert server.start() is None
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=3)
        connection.request(
            "POST",
            f"{LOCAL_API_BASE_PATH}/accounts",
            body="[]",
            headers={"X-Authenticator-Token": "test-token", "Content-Type": "application/json"},
        )
        response = connection.getresponse()
        assert response.status == 400
        assert json.loads(response.read().decode("utf-8")) == {"error": "json_object_required"}
        assert requests.empty()
        connection.close()
    finally:
        server.stop()

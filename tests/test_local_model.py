import json

import pytest

from insightflow import local_model


class Reply:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def read(self, limit):
        return self.body[:limit]


def install_transport(monkeypatch, reply):
    calls = []

    class Stub:
        def __init__(self, host, port, timeout):
            calls.append((host, port, timeout))

        def request(self, method, path, body, headers):
            calls.append((method, path, json.loads(body), headers))

        def getresponse(self):
            return reply

        def close(self):
            pass

    monkeypatch.setattr(local_model.http.client, "HTTPConnection", Stub)
    return calls


def test_planner_sends_only_question_and_schema_to_loopback(monkeypatch):
    plan = {"operation": "sum", "metric": "销售额"}
    envelope = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"shape": "scalar", **plan})}}]}
    calls = install_transport(monkeypatch, Reply(200, json.dumps(envelope).encode()))
    schema = {"销售额": "int64", "客户": "object"}
    assert local_model.get_planner()("总销售额是多少？", schema) == plan
    assert calls[0][0:2] == ("127.0.0.1", 18089)
    method, path, payload, headers = calls[1]
    assert (method, path) == ("POST", "/v1/chat/completions")
    assert json.loads(payload["messages"][-1]["content"]) == {"columns": schema, "question": "总销售额是多少？"}
    assert payload["response_format"]["schema"]["oneOf"][0]["properties"]["metric"]["enum"] == ["销售额"]
    assert "Authorization" not in headers


@pytest.mark.parametrize("reply", [
    Reply(307, b""),
    Reply(503, b""),
    Reply(200, b"X" * 33_000),
    Reply(200, b"not a chat response"),
    Reply(200, b'{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}'),
    Reply(200, b'{"choices":[{"finish_reason":"stop","message":{"content":"[]"}}]}'),
])
def test_untrusted_transport_response_fails_without_retry(monkeypatch, reply):
    calls = install_transport(monkeypatch, reply)
    with pytest.raises(ValueError):
        local_model.get_planner()("total", {"value": "int64"})
    assert len(calls) == 2


@pytest.mark.parametrize("wire, normalized", [
    ({"shape": "scalar", "operation": "count"}, {"operation": "count"}),
    ({"shape": "grouped", "operation": "count", "group_by": "site"}, {"operation": "count", "group_by": "site"}),
    ({"shape": "unsupported"}, {"unsupported": True}),
])
def test_shape_adapts_to_common_engine(monkeypatch, wire, normalized):
    monkeypatch.setattr(local_model, "_post", lambda _: dict(wire))
    assert local_model.get_planner()("test question", {"site": "object"}) == normalized


def test_inconsistent_model_shape_is_rejected(monkeypatch):
    monkeypatch.setattr(local_model, "_post", lambda _: {"shape": "scalar", "operation": "count", "group_by": "site"})
    with pytest.raises(ValueError, match="inconsistent"):
        local_model.get_planner()("test question", {"site": "object"})

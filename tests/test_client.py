import json
from pathlib import Path

import pytest

from app import weibo_client
from app.config import Settings
from app.weibo_client import WeiboAuthError, WeiboClient

SETTINGS = Settings(cookie_file=Path("unused"), request_min_delay=0, request_max_delay=0)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def make_client(monkeypatch, responses):
    client = WeiboClient("SUB=test", SETTINGS)
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params))
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(weibo_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(client._session, "get", fake_get)
    return client, calls


def test_resolve_follow_gid_from_all_groups(monkeypatch):
    groups = {"ok": 1, "groups": [{"title": "默认分组", "group": [
        {"title": "全部关注", "gid": "100011234567890"},
        {"title": "原创", "gid": "110011234567890"}]}]}
    client, _ = make_client(monkeypatch, [groups])
    assert client.resolve_follow_gid() == "100011234567890"


def test_auth_error_raised_on_minus_100(monkeypatch):
    client, _ = make_client(monkeypatch, [{"ok": -100, "msg": "未登录"}])
    with pytest.raises(WeiboAuthError):
        client.fetch_all_groups()


def test_fetch_feed_parses_statuses(monkeypatch):
    groups = {"ok": 1, "groups": [{"group": [{"title": "全部关注", "gid": "1"}]}]}
    feed = {"ok": 1, "statuses": [
        {"mid": "100",
         "user": {"idstr": "7", "screen_name": "A", "following": True},
         "text_raw": "hi", "isAd": False, "pic_ids": []}]}
    client, calls = make_client(monkeypatch, [groups, feed])
    posts = client.fetch_feed()
    assert posts[0].mid == "100" and posts[0].author.following is True
    assert calls[0][0].endswith("/ajax/feed/allGroups")
    assert calls[1][0].endswith("/ajax/feed/friendstimeline")
    assert calls[1][1]["list_id"] == "1"


def test_fetch_status_parses_top_level_status(monkeypatch):
    status = {"ok": 1, "mid": "200", "user": {"idstr": "8", "screen_name": "A",
                                              "following": True}, "text_raw": "正文"}
    client, _ = make_client(monkeypatch, [status])
    post = client.fetch_status("200")
    assert post.mid == "200" and post.text == "正文"


def test_fetch_replies_parses_target(monkeypatch):
    data = {"ok": 1, "data": [{
        "id": "666", "rootid": "555",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "回复",
        "reply_comment": {"user": {"idstr": "2", "screen_name": "B", "following": True}}}]}
    client, _ = make_client(monkeypatch, [data])
    replies = client.fetch_replies("555", "100", "7")
    assert replies[0].cid == "666"
    assert replies[0].target is not None and replies[0].target.uid == "2"

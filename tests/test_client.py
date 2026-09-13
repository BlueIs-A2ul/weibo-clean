import json
from pathlib import Path

import pytest

from app import weibo_client
from app.cache import TTLCache
from app.config import Settings
from app.weibo_client import WeiboAuthError, WeiboClient, WeiboRateLimitError

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


def test_ttl_cache_hits_and_expires(monkeypatch):
    now = {"value": 100.0}
    monkeypatch.setattr("app.cache.time.monotonic", lambda: now["value"])
    cache = TTLCache(ttl_seconds=10)
    calls = []
    value = cache.get_or_set("k", lambda: calls.append(1) or "v")
    assert value == "v" and len(calls) == 1
    assert cache.get_or_set("k", lambda: calls.append(2) or "other") == "v"
    assert len(calls) == 1
    now["value"] = 111.0
    assert cache.get("k") is None


def test_rate_limit_error_raised_on_rejection(monkeypatch):
    client, _ = make_client(monkeypatch, [{"ok": 0, "errno": 99999}])
    with pytest.raises(WeiboRateLimitError):
        client.fetch_all_groups()


def test_resolve_follow_gid_ignores_malformed_groups(monkeypatch):
    groups = {"ok": 1, "groups": ["oops", {"group": [{"title": "全部关注", "gid": "42"}]}]}
    client, _ = make_client(monkeypatch, [groups])
    assert client.resolve_follow_gid() == "42"


def test_fetch_root_comments_params_and_parsing(monkeypatch):
    data = {"ok": 1, "data": [{"id": "555",
                               "user": {"idstr": "1", "screen_name": "A", "following": True},
                               "text_raw": "一级评论", "total_number": 2}]}
    client, calls = make_client(monkeypatch, [data])
    comments = client.fetch_root_comments("100", "7")
    assert comments[0].cid == "555" and comments[0].total_replies == 2
    assert calls[0][1]["fetch_level"] == "0"
    assert calls[0][1]["uid"] == "7" and calls[0][1]["count"] == "20"


def test_fetch_feed_force_bypasses_cache(monkeypatch):
    groups = {"ok": 1, "groups": [{"group": [{"title": "全部关注", "gid": "1"}]}]}
    feed = {"ok": 1, "statuses": [
        {"mid": "1", "user": {"idstr": "7", "following": True},
         "text_raw": "x", "pic_ids": []}]}
    client, calls = make_client(monkeypatch, [groups, feed, feed])
    client.fetch_feed()
    client.fetch_feed()
    assert len(calls) == 2
    client.fetch_feed(force=True)
    assert len(calls) == 3

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import weibo_client
from app.cache import TTLCache
from app.config import Settings
from app.weibo_client import WeiboAuthError, WeiboClient, WeiboError, WeiboRateLimitError

SETTINGS = Settings(cookie_file=Path("unused"), request_min_delay=0, request_max_delay=0)


def fail_get(*args, **kwargs):
    raise AssertionError("network should not be used")


def disk_settings(tmp_path, refresh_in_background=False):
    return Settings(cookie_file=Path("unused"), request_min_delay=0, request_max_delay=0,
                    following_cache_file=tmp_path / "following.json",
                    refresh_in_background=refresh_in_background)


def write_following_cache(path, uid, saved_at):
    path.write_text(json.dumps({
        "version": 1, "saved_at": saved_at.isoformat(),
        "users": [{"idstr": uid, "screen_name": f"u{uid}", "profile_image_url": "",
                   "following": True}],
    }, ensure_ascii=False), encoding="utf-8")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def make_client(monkeypatch, responses, settings=SETTINGS):
    client = WeiboClient("SUB=test", settings)
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
    feed = {"ok": 1, "max_id_str": "99", "statuses": [
        {"mid": "100",
         "user": {"idstr": "7", "screen_name": "A", "following": True},
         "text_raw": "hi", "isAd": False, "pic_ids": []}]}
    client, calls = make_client(monkeypatch, [groups, feed])
    posts, cursor = client.fetch_feed()
    assert posts[0].mid == "100" and posts[0].author.following is True
    assert cursor == "99"
    assert calls[0][0].endswith("/ajax/feed/allGroups")
    assert calls[1][0].endswith("/ajax/feed/friendstimeline")
    assert calls[1][1]["list_id"] == "1"
    assert "max_id" not in calls[1][1]


def test_fetch_feed_paginates_with_max_id_and_caches_page(monkeypatch):
    groups = {"ok": 1, "groups": [{"group": [{"title": "全部关注", "gid": "1"}]}]}
    page1 = {"ok": 1, "max_id_str": "111", "statuses": [
        {"mid": "1", "user": {"idstr": "7", "following": True}, "pic_ids": []}]}
    page2 = {"ok": 1, "max_id_str": "0", "statuses": [
        {"mid": "2", "user": {"idstr": "7", "following": True}, "pic_ids": []}]}
    client, calls = make_client(monkeypatch, [groups, page1, page2])
    posts1, cursor1 = client.fetch_feed()
    assert [p.mid for p in posts1] == ["1"] and cursor1 == "111"
    posts2, cursor2 = client.fetch_feed(max_id="111")
    assert [p.mid for p in posts2] == ["2"] and cursor2 == "0"
    assert calls[2][1]["max_id"] == "111"
    client.fetch_feed(max_id="111")
    assert len(calls) == 3


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


def test_fetch_following_paginates_and_dedupes(monkeypatch):
    page1 = {"ok": 1, "data": {"follows": {"users": [
        {"idstr": "1", "screen_name": "A", "following": True},
        {"idstr": "2", "screen_name": "B", "following": True}], "next_cursor": 50}}}
    page2 = {"ok": 1, "data": {"follows": {"users": [
        {"idstr": "2", "screen_name": "B", "following": True},
        {"idstr": "3", "screen_name": "C", "following": True}], "next_cursor": 0}}}
    client, calls = make_client(monkeypatch, [page1, page2])
    users = client.fetch_following()
    assert [u.uid for u in users] == ["1", "2", "3"]
    assert calls[0][1]["page"] == 1 and calls[1][1]["page"] == 2
    assert calls[0][1]["sortType"] == "all"
    assert calls[0][0].endswith("/ajax/profile/followContent")


def test_fetch_following_cached_between_calls(monkeypatch):
    page1 = {"ok": 1, "data": {"follows": {"users": [
        {"idstr": "1", "screen_name": "A", "following": True}], "next_cursor": 0}}}
    client, calls = make_client(monkeypatch, [page1])
    client.fetch_following()
    client.fetch_following()
    assert len(calls) == 1


def test_fetch_user_parses_profile_info(monkeypatch):
    data = {"ok": 1, "data": {"user": {
        "idstr": "9", "screen_name": "Z", "profile_image_url": "http://img/z.jpg",
        "following": False}}}
    client, calls = make_client(monkeypatch, [data])
    user = client.fetch_user("9")
    assert user.uid == "9" and user.screen_name == "Z" and user.following is False
    assert calls[0][0].endswith("/ajax/profile/info")


def test_fetch_user_timeline_parses_caches_and_forces(monkeypatch):
    data = {"ok": 1, "data": {"list": [
        {"mid": "5", "user": {"idstr": "9", "following": False},
         "text_raw": "hi", "created_at": "Sat Sep 13 20:00:00 +0800 2026"}]}}
    client, calls = make_client(monkeypatch, [data, data])
    posts = client.fetch_user_timeline("9")
    assert posts[0].mid == "5" and posts[0].created_ts > 0
    client.fetch_user_timeline("9")
    assert len(calls) == 1
    client.fetch_user_timeline("9", force=True)
    assert len(calls) == 2
    assert calls[0][0].endswith("/ajax/statuses/mymblog")
    assert calls[0][1]["uid"] == "9" and calls[0][1]["feature"] == "0"


def test_fetch_root_comments_paginates_until_cursor_end(monkeypatch):
    page1 = {"ok": 1, "data": [{"id": "1", "user": {"idstr": "1"}}], "max_id": 100}
    page2 = {"ok": 1, "data": [{"id": "2", "user": {"idstr": "2"}}], "max_id": 0}
    client, calls = make_client(monkeypatch, [page1, page2])
    comments = client.fetch_root_comments("100", "7")
    assert [c.cid for c in comments] == ["1", "2"]
    assert len(calls) == 2
    assert calls[0][1]["max_id"] == "0"
    assert calls[1][1]["max_id"] == "100"
    assert calls[1][1]["fetch_level"] == "0"


def test_fetch_replies_paginates(monkeypatch):
    page1 = {"ok": 1, "data": [{"id": "a", "rootid": "9", "user": {"idstr": "1"}}],
             "max_id": "55"}
    page2 = {"ok": 1, "data": [{"id": "b", "rootid": "9", "user": {"idstr": "2"}}],
             "max_id": 0}
    client, calls = make_client(monkeypatch, [page1, page2])
    replies = client.fetch_replies("9", "100", "7")
    assert [c.cid for c in replies] == ["a", "b"]
    assert calls[1][1]["id"] == "9" and calls[1][1]["fetch_level"] == "1"
    assert calls[1][1]["max_id"] == "55"


def test_fetch_self_uid_parses_home_html_and_caches(monkeypatch):
    client = WeiboClient("SUB=test", SETTINGS)
    calls = []

    class HtmlResponse:
        status_code = 200
        text = '<html><script>var config = {"uid":1234567890,"x":1}</script></html>'

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return HtmlResponse()

    monkeypatch.setattr(weibo_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(client._session, "get", fake_get)
    assert client.fetch_self_uid() == "1234567890"
    assert client.fetch_self_uid() == "1234567890"
    assert calls == ["https://weibo.com/"]


def test_fetch_self_uid_raises_without_uid(monkeypatch):
    client = WeiboClient("SUB=test", SETTINGS)

    class NoUidResponse:
        status_code = 200
        text = "<html></html>"

    monkeypatch.setattr(weibo_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(client._session, "get",
                        lambda url, headers=None, timeout=None: NoUidResponse())
    with pytest.raises(WeiboError):
        client.fetch_self_uid()


def test_fetch_following_uses_disk_cache_without_network(tmp_path, monkeypatch):
    settings = disk_settings(tmp_path)
    write_following_cache(settings.following_cache_file, "1", datetime.now(timezone.utc))
    client = WeiboClient("SUB=test", settings)
    monkeypatch.setattr(client._session, "get", fail_get)
    users = client.fetch_following()
    assert [u.uid for u in users] == ["1"]


def test_fetch_following_persists_and_reuses_disk(tmp_path, monkeypatch):
    settings = disk_settings(tmp_path)
    page1 = {"ok": 1, "data": {"follows": {"users": [
        {"idstr": "1", "screen_name": "A", "following": True}], "next_cursor": 0}}}
    client, calls = make_client(monkeypatch, [page1], settings)
    assert [u.uid for u in client.fetch_following()] == ["1"]
    assert len(calls) == 1
    payload = json.loads(settings.following_cache_file.read_text(encoding="utf-8"))
    assert payload["users"][0]["idstr"] == "1" and payload["saved_at"]

    second = WeiboClient("SUB=test", settings)
    monkeypatch.setattr(second._session, "get", fail_get)
    assert [u.uid for u in second.fetch_following()] == ["1"]


def test_stale_disk_cache_triggers_background_refresh(tmp_path, monkeypatch):
    settings = disk_settings(tmp_path, refresh_in_background=True)
    write_following_cache(settings.following_cache_file, "1",
                          datetime.now(timezone.utc) - timedelta(hours=2))
    client = WeiboClient("SUB=test", settings)
    page1 = {"ok": 1, "data": {"follows": {"users": [
        {"idstr": "2", "screen_name": "B", "following": True}], "next_cursor": 0}}}

    class InlineThread:
        def __init__(self, target, daemon=False):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(weibo_client.threading, "Thread", InlineThread)
    monkeypatch.setattr(weibo_client.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(client._session, "get",
                        lambda url, params=None, headers=None, timeout=None:
                        FakeResponse(page1))

    users = client.fetch_following()
    assert [u.uid for u in users] == ["1"]
    assert [u.uid for u in client.fetch_following()] == ["2"]
    payload = json.loads(settings.following_cache_file.read_text(encoding="utf-8"))
    assert payload["users"][0]["idstr"] == "2"


def test_corrupt_following_cache_falls_back_to_network(tmp_path, monkeypatch):
    settings = disk_settings(tmp_path)
    settings.following_cache_file.write_text("{oops", encoding="utf-8")
    page1 = {"ok": 1, "data": {"follows": {"users": [
        {"idstr": "1", "screen_name": "A", "following": True}], "next_cursor": 0}}}
    client, calls = make_client(monkeypatch, [page1], settings)
    assert [u.uid for u in client.fetch_following()] == ["1"]
    assert len(calls) == 1

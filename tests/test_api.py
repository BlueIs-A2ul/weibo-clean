from fastapi.testclient import TestClient

from app import main
from app.config import load_settings
from app.models import Comment, Post, User
from app.weibo_client import WeiboAuthError, WeiboError, WeiboRateLimitError


def u(uid: str, following: bool, avatar: str = "") -> User:
    return User(uid=uid, screen_name=f"u{uid}", avatar=avatar, following=following)


class FakeClient:
    settings = load_settings()

    def fetch_feed(self, force=False):
        return [
            Post(mid="1", author=u("a", True, "https://tvax1.sinaimg.cn/a.jpg"),
                 text="hello", pics=["https://wx2.sinaimg.cn/p.jpg"]),
            Post(mid="2", author=u("b", False), text="stranger"),
            Post(mid="3", author=u("c", True), text="ad", is_ad=True),
        ]

    def fetch_status(self, mid):
        return Post(mid=mid, author=u("a", True), text="post")

    def fetch_root_comments(self, mid, author_uid):
        return [
            Comment(cid="10", author=u("a", True), text="visible root", total_replies=1),
            Comment(cid="11", author=u("x", False), text="hidden root", total_replies=2),
        ]

    def fetch_replies(self, root_cid, mid, author_uid):
        if root_cid == "11":
            return [Comment(cid="21", author=u("b", True), text="orphan",
                            target=u("c", True))]
        return [Comment(cid="20", author=u("b", True), text="reply",
                        target=u("c", False))]


def make_client(monkeypatch):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    return TestClient(main.app, raise_server_exceptions=False)


def test_feed_filters_ads_and_strangers(monkeypatch):
    resp = make_client(monkeypatch).get("/api/feed")
    assert resp.status_code == 200
    assert [item["mid"] for item in resp.json()["items"]] == ["1"]


def test_comments_returns_threads_and_promoted_orphans(monkeypatch):
    resp = make_client(monkeypatch).get("/api/status/100/comments")
    body = resp.json()
    assert [t["cid"] for t in body["threads"]] == ["10"]
    assert [o["cid"] for o in body["orphans"]] == ["21"]
    assert body["orphans"][0]["promoted"] is True


def test_replies_endpoint_filters_pair_rule(monkeypatch):
    resp = make_client(monkeypatch).get("/api/comment/10/replies?mid=100")
    assert resp.json()["items"] == []


def test_auth_error_maps_to_401(monkeypatch):
    def raise_auth():
        raise WeiboAuthError("Cookie 已失效")

    monkeypatch.setattr(main, "get_client", raise_auth)
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 401
    assert "Cookie" in resp.json()["error"]


def test_rate_limit_error_maps_to_429(monkeypatch):
    def raise_rate_limit():
        raise WeiboRateLimitError("请求过快")

    monkeypatch.setattr(main, "get_client", raise_rate_limit)
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 429
    assert resp.json()["error"] == "请求过快"


def test_weibo_error_maps_to_502(monkeypatch):
    def raise_weibo_error():
        raise WeiboError("接口结构异常")

    monkeypatch.setattr(main, "get_client", raise_weibo_error)
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 502
    assert resp.json()["error"] == "接口结构异常"


def test_get_client_caches_singleton(monkeypatch):
    monkeypatch.setattr(main, "_client", None)
    monkeypatch.setattr(main, "load_cookie", lambda settings: "SUB=test")
    first = main.get_client()
    second = main.get_client()
    assert first is second


def test_feed_force_query_passes_through(monkeypatch):
    recorded = {}

    class RecordingClient(FakeClient):
        def fetch_feed(self, force=False):
            recorded["force"] = force
            return super().fetch_feed()

    monkeypatch.setattr(main, "get_client", lambda: RecordingClient())
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed?force=1")
    assert resp.status_code == 200
    assert recorded["force"] is True


def test_feed_proxies_image_urls(monkeypatch):
    resp = make_client(monkeypatch).get("/api/feed")
    item = resp.json()["items"][0]
    assert item["author"]["avatar"].startswith("/api/image?url=")
    assert item["pics"][0].startswith("/api/image?url=")


def test_image_proxy_rejects_foreign_hosts(monkeypatch):
    resp = TestClient(main.app, raise_server_exceptions=False).get(
        "/api/image", params={"url": "https://example.com/a.jpg"})
    assert resp.status_code == 400


def test_image_proxy_streams_upstream(monkeypatch):
    captured = {}

    class FakeUpstream:
        status_code = 200
        headers = {"Content-Type": "image/jpeg"}

        def iter_content(self, size):
            yield b"fake-image"

        def close(self):
            pass

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["referer"] = kwargs["headers"]["Referer"]
        return FakeUpstream()

    monkeypatch.setattr(main.requests, "get", fake_get)
    resp = TestClient(main.app, raise_server_exceptions=False).get(
        "/api/image", params={"url": "https://tvax1.sinaimg.cn/a.jpg"})
    assert resp.status_code == 200
    assert resp.content == b"fake-image"
    assert resp.headers["content-type"] == "image/jpeg"
    assert captured["referer"] == "https://weibo.com/"

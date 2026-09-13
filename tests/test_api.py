from fastapi.testclient import TestClient

from app import main
from app.config import load_settings
from app.models import Comment, Post, User
from app.weibo_client import WeiboAuthError


def u(uid: str, following: bool) -> User:
    return User(uid=uid, screen_name=f"u{uid}", avatar="", following=following)


class FakeClient:
    settings = load_settings()

    def fetch_feed(self):
        return [
            Post(mid="1", author=u("a", True), text="hello"),
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

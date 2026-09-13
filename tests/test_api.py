from fastapi.testclient import TestClient

from app import main
from app.config import load_settings
from app.models import Comment, Post, User
from app.weibo_client import WeiboAuthError, WeiboError, WeiboRateLimitError
from app.whitelist import WhitelistEntry, WhitelistStore


def u(uid: str, following: bool, avatar: str = "") -> User:
    return User(uid=uid, screen_name=f"u{uid}", avatar=avatar, following=following)


class FakeClient:
    settings = load_settings()

    def fetch_feed(self, force=False):
        return [
            Post(mid="1", author=u("a", True, "https://tvax1.sinaimg.cn/a.jpg"),
                 text="hello", pics=["https://wx2.sinaimg.cn/p.jpg"], created_ts=100.0),
            Post(mid="2", author=u("b", False), text="stranger", created_ts=90.0),
            Post(mid="3", author=u("c", True), text="ad", is_ad=True, created_ts=95.0),
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

    def fetch_following(self):
        return [u("a", True), u("c", True), u("d", True), u("z", False)]

    def fetch_user(self, uid):
        if uid == "404":
            return None
        return u(uid, False, f"https://tvax1.sinaimg.cn/{uid}.jpg")

    def fetch_user_timeline(self, uid, force=False):
        if uid != "z":
            return []
        return [Post(mid="9", author=u("z", False), text="manual post", created_ts=200.0)]


def make_client(monkeypatch, tmp_path, store=None):
    monkeypatch.setattr(main, "get_client", lambda: FakeClient())
    monkeypatch.setattr(main, "get_store",
                        lambda: store if store is not None
                        else WhitelistStore(tmp_path / "whitelist.json"))
    return TestClient(main.app, raise_server_exceptions=False)


def test_feed_filters_ads_and_strangers(monkeypatch, tmp_path):
    resp = make_client(monkeypatch, tmp_path).get("/api/feed")
    assert resp.status_code == 200
    assert [item["mid"] for item in resp.json()["items"]] == ["1"]


def test_feed_merges_manual_added_timeline(monkeypatch, tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(WhitelistEntry(uid="z", name="uz"))
    resp = make_client(monkeypatch, tmp_path, store).get("/api/feed")
    items = resp.json()["items"]
    assert [item["mid"] for item in items] == ["9", "1"]
    assert items[0]["manual"] is True
    assert items[1]["manual"] is False


def test_added_user_hidden_when_removed(monkeypatch, tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.hide(WhitelistEntry(uid="a", name="ua"))
    assert make_client(monkeypatch, tmp_path, store).get("/api/feed").json()["items"] == []


def test_comments_returns_threads_and_promoted_orphans(monkeypatch, tmp_path):
    resp = make_client(monkeypatch, tmp_path).get("/api/status/100/comments")
    body = resp.json()
    assert [t["cid"] for t in body["threads"]] == ["10"]
    assert [o["cid"] for o in body["orphans"]] == ["21"]
    assert body["orphans"][0]["promoted"] is True


def test_replies_endpoint_filters_pair_rule(monkeypatch, tmp_path):
    resp = make_client(monkeypatch, tmp_path).get("/api/comment/10/replies?mid=100")
    assert resp.json()["items"] == []


def test_whitelist_add_parses_uid_and_stores(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    resp = client.post("/api/whitelist/add", json={"input": "https://weibo.com/u/777"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["uid"] == "777" and body["following"] is False
    listing = client.get("/api/whitelist").json()
    assert [entry["uid"] for entry in listing["added"]] == ["777"]


def test_whitelist_add_rejects_bad_input(monkeypatch, tmp_path):
    resp = make_client(monkeypatch, tmp_path).post(
        "/api/whitelist/add", json={"input": "昵称没法解析"})
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_whitelist_add_missing_user_404(monkeypatch, tmp_path):
    resp = make_client(monkeypatch, tmp_path).post(
        "/api/whitelist/add", json={"input": "404"})
    assert resp.status_code == 404


def test_whitelist_remove_then_restore_followed_user(monkeypatch, tmp_path):
    client = make_client(monkeypatch, tmp_path)
    resp = client.post("/api/whitelist/remove", json={"uid": "a"})
    assert resp.status_code == 200 and resp.json()["action"] == "hidden"
    assert client.get("/api/feed").json()["items"] == []
    resp = client.post("/api/whitelist/restore", json={"uid": "a"})
    assert resp.json()["action"] == "restored"
    assert client.get("/api/feed").json()["items"][0]["mid"] == "1"


def test_whitelist_remove_deletes_manual_entry(monkeypatch, tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(WhitelistEntry(uid="z", name="uz"))
    client = make_client(monkeypatch, tmp_path, store)
    resp = client.post("/api/whitelist/remove", json={"uid": "z"})
    assert resp.json()["action"] == "removed"
    assert client.get("/api/feed").json()["items"][0]["mid"] == "1"


def test_whitelist_listing_marks_hidden_and_added(monkeypatch, tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.hide(WhitelistEntry(uid="d", name="ud"))
    store.add(WhitelistEntry(uid="z", name="uz"))
    body = make_client(monkeypatch, tmp_path, store).get("/api/whitelist").json()
    following = {item["uid"]: item for item in body["following"]}
    assert following["d"]["hidden"] is True
    assert following["a"]["hidden"] is False
    assert [entry["uid"] for entry in body["added"]] == ["z"]
    assert [entry["uid"] for entry in body["removed"]] == ["d"]


def test_whitelist_file_error_maps_to_500(monkeypatch, tmp_path):
    def raise_corrupt():
        raise main.WhitelistError("白名单文件损坏")

    monkeypatch.setattr(main, "get_store", raise_corrupt)
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 500
    assert resp.json()["error"] == "白名单文件损坏"


def test_auth_error_maps_to_401(monkeypatch, tmp_path):
    def raise_auth():
        raise WeiboAuthError("Cookie 已失效")

    monkeypatch.setattr(main, "get_client", raise_auth)
    monkeypatch.setattr(main, "get_store",
                        lambda: WhitelistStore(tmp_path / "whitelist.json"))
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 401
    assert "Cookie" in resp.json()["error"]


def test_rate_limit_error_maps_to_429(monkeypatch, tmp_path):
    def raise_rate_limit():
        raise WeiboRateLimitError("请求过快")

    monkeypatch.setattr(main, "get_client", raise_rate_limit)
    monkeypatch.setattr(main, "get_store",
                        lambda: WhitelistStore(tmp_path / "whitelist.json"))
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 429
    assert resp.json()["error"] == "请求过快"


def test_weibo_error_maps_to_502(monkeypatch, tmp_path):
    def raise_weibo_error():
        raise WeiboError("接口结构异常")

    monkeypatch.setattr(main, "get_client", raise_weibo_error)
    monkeypatch.setattr(main, "get_store",
                        lambda: WhitelistStore(tmp_path / "whitelist.json"))
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed")
    assert resp.status_code == 502
    assert resp.json()["error"] == "接口结构异常"


def test_get_client_caches_singleton(monkeypatch):
    monkeypatch.setattr(main, "_client", None)
    monkeypatch.setattr(main, "load_cookie", lambda settings: "SUB=test")
    first = main.get_client()
    second = main.get_client()
    assert first is second


def test_feed_force_query_passes_through(monkeypatch, tmp_path):
    recorded = {}

    class RecordingClient(FakeClient):
        def fetch_feed(self, force=False):
            recorded["force"] = force
            return super().fetch_feed()

    monkeypatch.setattr(main, "get_client", lambda: RecordingClient())
    monkeypatch.setattr(main, "get_store",
                        lambda: WhitelistStore(tmp_path / "whitelist.json"))
    resp = TestClient(main.app, raise_server_exceptions=False).get("/api/feed?force=1")
    assert resp.status_code == 200
    assert recorded["force"] is True


def test_feed_proxies_image_urls(monkeypatch, tmp_path):
    resp = make_client(monkeypatch, tmp_path).get("/api/feed")
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

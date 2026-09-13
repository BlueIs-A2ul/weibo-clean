import threading
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_cookie, load_settings
from .filter_engine import (
    WhitelistPolicy,
    filter_roots,
    is_visible,
    visible_posts,
    visible_replies,
)
from .models import Comment, Post, User
from .weibo_client import (
    USER_AGENT,
    WeiboAuthError,
    WeiboClient,
    WeiboError,
    WeiboRateLimitError,
)
from .whitelist import WhitelistEntry, WhitelistError, WhitelistStore, parse_uid_input

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
IMAGE_HOST_SUFFIX = ".sinaimg.cn"
FEED_LIMIT = 60

app = FastAPI(title="weibo-clean demo")
_client: WeiboClient | None = None
_client_lock = threading.Lock()
_store: WhitelistStore | None = None
_store_lock = threading.Lock()


def get_client() -> WeiboClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                settings = load_settings()
                try:
                    cookie = load_cookie(settings)
                except (OSError, UnicodeDecodeError) as exc:
                    raise WeiboAuthError(f"无法读取 Cookie 文件 {settings.cookie_file}：{exc}") from exc
                if not cookie:
                    raise WeiboAuthError("Cookie 文件为空，请重新导入")
                _client = WeiboClient(cookie, settings)
    return _client


def get_store() -> WhitelistStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = WhitelistStore(load_settings().whitelist_file)
    return _store


def is_allowed_image_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme in ("http", "https")
        and parsed.hostname is not None
        and parsed.hostname.endswith(IMAGE_HOST_SUFFIX)
    )


def proxy_image_url(url: str) -> str:
    if not url or not is_allowed_image_url(url):
        return ""
    return f"/api/image?url={quote(url, safe='')}"


def user_view(user: User) -> dict:
    return {"uid": user.uid, "name": user.screen_name,
            "avatar": proxy_image_url(user.avatar), "following": user.following}


def post_view(post: Post, manual: bool = False) -> dict:
    pics = []
    for url in post.pics:
        proxied = proxy_image_url(url)
        if proxied:
            pics.append(proxied)
    return {
        "mid": post.mid,
        "author": user_view(post.author),
        "text": post.text,
        "pics": pics,
        "created_at": post.created_at,
        "reposts": post.reposts_count,
        "comments": post.comments_count,
        "attitudes": post.attitudes_count,
        "manual": manual,
        "retweeted": post_view(post.retweeted) if post.retweeted else None,
    }


def comment_view(comment: Comment) -> dict:
    return {
        "cid": comment.cid,
        "author": user_view(comment.author),
        "text": comment.text,
        "target": user_view(comment.target) if comment.target else None,
        "promoted": comment.promoted,
        "total_replies": comment.total_replies,
        "like_count": comment.like_count,
    }


def entry_view(entry: WhitelistEntry) -> dict:
    return {"uid": entry.uid, "name": entry.name,
            "avatar": proxy_image_url(entry.avatar), "at": entry.at}


def policy_with_following(client: WeiboClient) -> WhitelistPolicy:
    """评论接口的 user.following 字段不可信（恒为 false），需用本地关注集合判定。"""
    following = frozenset(user.uid for user in client.fetch_following())
    return WhitelistPolicy(get_store(), following, resolve_self_uid(client))


def resolve_self_uid(client: WeiboClient) -> str | None:
    try:
        return client.fetch_self_uid()
    except WeiboAuthError:
        raise
    except WeiboError:
        return None


class AddBody(BaseModel):
    input: str


class UidBody(BaseModel):
    uid: str


@app.exception_handler(WeiboAuthError)
def auth_error_handler(request: Request, exc: WeiboAuthError):
    return JSONResponse(status_code=401, content={"error": str(exc)})


@app.exception_handler(WeiboRateLimitError)
def rate_limit_handler(request: Request, exc: WeiboRateLimitError):
    return JSONResponse(status_code=429, content={"error": str(exc)})


@app.exception_handler(WeiboError)
def weibo_error_handler(request: Request, exc: WeiboError):
    return JSONResponse(status_code=502, content={"error": str(exc)})


@app.exception_handler(WhitelistError)
def whitelist_error_handler(request: Request, exc: WhitelistError):
    return JSONResponse(status_code=500, content={"error": str(exc)})


def merge_posts(groups: list[list[Post]]) -> list[Post]:
    unique: dict[str, Post] = {}
    for group in groups:
        for post in group:
            unique.setdefault(post.mid, post)
    ordered = sorted(unique.values(), key=lambda post: post.created_ts, reverse=True)
    return ordered[:FEED_LIMIT]


@app.get("/api/feed")
def api_feed(force: bool = False):
    client = get_client()
    store = get_store()
    policy = WhitelistPolicy(store, self_uid=resolve_self_uid(client))
    groups = [client.fetch_feed(force=force)]
    for entry in store.added_entries():
        try:
            groups.append(client.fetch_user_timeline(entry.uid, force=force))
        except WeiboAuthError:
            raise
        except WeiboError:
            continue
    posts = visible_posts(merge_posts(groups), policy)
    return {"items": [post_view(post, manual=store.is_added(post.author.uid))
                      for post in posts]}


@app.get("/api/status/{mid}")
def api_status(mid: str):
    post = get_client().fetch_status(mid)
    return {"post": post_view(post, manual=get_store().is_added(post.author.uid))}


@app.get("/api/status/{mid}/comments")
def api_comments(mid: str):
    client = get_client()
    policy = policy_with_following(client)
    post = client.fetch_status(mid)
    roots = client.fetch_root_comments(mid, post.author.uid)
    threads = [comment_view(root) for root in filter_roots(roots, policy)]
    return {
        "post": post_view(post, manual=get_store().is_added(post.author.uid)),
        "threads": threads,
    }


@app.get("/api/status/{mid}/orphans")
def api_orphans(mid: str):
    client = get_client()
    policy = policy_with_following(client)
    post = client.fetch_status(mid)
    roots = client.fetch_root_comments(mid, post.author.uid)
    hidden = [root for root in roots
              if not is_visible(root, policy) and root.total_replies > 0]
    hidden.sort(key=lambda root: root.total_replies, reverse=True)
    items: list[dict] = []
    for root in hidden[: client.settings.max_orphan_threads]:
        replies = client.fetch_replies(root.cid, mid, post.author.uid)
        items.extend(comment_view(reply)
                     for reply in visible_replies(replies, policy, promoted=True))
    return {"items": items}


@app.get("/api/comment/{root_cid}/replies")
def api_replies(root_cid: str, mid: str):
    client = get_client()
    policy = policy_with_following(client)
    post = client.fetch_status(mid)
    replies = client.fetch_replies(root_cid, mid, post.author.uid)
    return {"items": [comment_view(reply) for reply in visible_replies(replies, policy)]}


@app.get("/api/whitelist")
def api_whitelist():
    client = get_client()
    store = get_store()
    following = [dict(user_view(user), hidden=store.is_removed(user.uid))
                 for user in client.fetch_following()]
    return {
        "following": following,
        "added": [entry_view(entry) for entry in store.added_entries()],
        "removed": [entry_view(entry) for entry in store.removed_entries()],
    }


@app.post("/api/whitelist/add")
def api_whitelist_add(body: AddBody):
    try:
        uid = parse_uid_input(body.input)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    user = get_client().fetch_user(uid)
    if user is None or not user.uid:
        return JSONResponse(status_code=404, content={"error": "未找到该用户"})
    get_store().add(WhitelistEntry(uid=user.uid, name=user.screen_name, avatar=user.avatar))
    return {"ok": True, "uid": user.uid, "name": user.screen_name,
            "following": user.following}


@app.post("/api/whitelist/remove")
def api_whitelist_remove(body: UidBody):
    uid = body.uid.strip()
    if not uid:
        return JSONResponse(status_code=400, content={"error": "缺少 uid"})
    store = get_store()
    if store.is_added(uid):
        store.remove_added(uid)
        return {"ok": True, "action": "removed"}
    user = None
    try:
        for candidate in get_client().fetch_following():
            if candidate.uid == uid:
                user = candidate
                break
    except WeiboError:
        user = None
    if user is None:
        user = get_client().fetch_user(uid)
    if user is None:
        return JSONResponse(status_code=404, content={"error": "未找到该用户"})
    store.hide(WhitelistEntry(uid=user.uid, name=user.screen_name, avatar=user.avatar))
    return {"ok": True, "action": "hidden"}


@app.post("/api/whitelist/restore")
def api_whitelist_restore(body: UidBody):
    uid = body.uid.strip()
    if not uid:
        return JSONResponse(status_code=400, content={"error": "缺少 uid"})
    get_store().restore(uid)
    return {"ok": True, "action": "restored"}


@app.get("/api/image")
def api_image(url: str):
    if not is_allowed_image_url(url):
        raise HTTPException(status_code=400, detail="不支持的图片地址")
    try:
        upstream = requests.get(
            url,
            headers={"Referer": "https://weibo.com/", "User-Agent": USER_AGENT},
            timeout=20.0,
            stream=True,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise WeiboError(f"图片获取失败: {exc}") from exc
    if upstream.status_code != 200:
        upstream.close()
        raise WeiboError(f"图片获取失败（{upstream.status_code}）")
    media_type = upstream.headers.get("Content-Type") or "image/jpeg"
    return StreamingResponse(
        upstream.iter_content(65536),
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=600"},
    )


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

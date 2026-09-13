import threading
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_cookie, load_settings
from .filter_engine import filter_roots, is_visible, visible_posts, visible_replies
from .models import Comment, Post, User
from .weibo_client import WeiboAuthError, WeiboClient, WeiboError, WeiboRateLimitError

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

app = FastAPI(title="weibo-clean demo")
_client: WeiboClient | None = None
_client_lock = threading.Lock()


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


def user_view(user: User) -> dict:
    return {"uid": user.uid, "name": user.screen_name, "avatar": user.avatar,
            "following": user.following}


def post_view(post: Post) -> dict:
    return {
        "mid": post.mid,
        "author": user_view(post.author),
        "text": post.text,
        "pics": post.pics,
        "created_at": post.created_at,
        "reposts": post.reposts_count,
        "comments": post.comments_count,
        "attitudes": post.attitudes_count,
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


@app.exception_handler(WeiboAuthError)
def auth_error_handler(request: Request, exc: WeiboAuthError):
    return JSONResponse(status_code=401, content={"error": str(exc)})


@app.exception_handler(WeiboRateLimitError)
def rate_limit_handler(request: Request, exc: WeiboRateLimitError):
    return JSONResponse(status_code=429, content={"error": str(exc)})


@app.exception_handler(WeiboError)
def weibo_error_handler(request: Request, exc: WeiboError):
    return JSONResponse(status_code=502, content={"error": str(exc)})


@app.get("/api/feed")
def api_feed():
    posts = get_client().fetch_feed()
    return {"items": [post_view(post) for post in visible_posts(posts)]}


@app.get("/api/status/{mid}")
def api_status(mid: str):
    return {"post": post_view(get_client().fetch_status(mid))}


@app.get("/api/status/{mid}/comments")
def api_comments(mid: str):
    client = get_client()
    post = client.fetch_status(mid)
    roots = client.fetch_root_comments(mid, post.author.uid)
    threads = [comment_view(root) for root in filter_roots(roots)]
    hidden = [root for root in roots if not is_visible(root) and root.total_replies > 0]
    hidden.sort(key=lambda root: root.total_replies, reverse=True)
    orphans: list[dict] = []
    for root in hidden[: client.settings.max_orphan_threads]:
        replies = client.fetch_replies(root.cid, mid, post.author.uid)
        orphans.extend(comment_view(reply) for reply in visible_replies(replies, promoted=True))
    return {"threads": threads, "orphans": orphans}


@app.get("/api/comment/{root_cid}/replies")
def api_replies(root_cid: str, mid: str):
    client = get_client()
    post = client.fetch_status(mid)
    replies = client.fetch_replies(root_cid, mid, post.author.uid)
    return {"items": [comment_view(reply) for reply in visible_replies(replies)]}


app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

# 纯净微博 Demo 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 做出一个本地运行的移动端 Web Demo：展示过滤后的关注流，以及"只显示我关注的人"的评论树（含 R4 双向关注规则与孤儿回复标注）。

**Architecture:** FastAPI 后端持有 Cookie，调用 weibo.com 内部接口（M0 已验证），解析为领域模型；纯函数过滤引擎依据响应自带的 `following` 标记剪枝；前端为无构建步骤的原生 HTML/CSS/JS，由 FastAPI 静态托管；内存 TTL 缓存，无数据库。

**Tech Stack:** Python 3.10+ / FastAPI / uvicorn / requests / pytest / httpx（TestClient）；原生 JS；数据源见 `docs/technical-design.md` 第 2 节。

**关键前置事实（M0 实测，勿重新验证）：**

- 用户对象自带 `following`（我是否关注 TA），评论、帖子、转发、`reply_comment.user` 都有；
- 关注流：`GET /ajax/feed/friendstimeline?list_id={gid}&fid={gid}&refresh=4&since_id=0&count=25`；gid 从 `GET /ajax/feed/allGroups` 的 `groups[].group[]` 里找 `title=全部关注`；
- 评论：`GET /ajax/statuses/buildComments`，一级 `fetch_level=0&id={mid}`，楼中楼 `fetch_level=1&id={根评论id}`；
- 被回复者 uid：回复条目的 `reply_comment.user.idstr`；广告标记：帖子 `isAd`；
- Cookie 文件在项目根目录 `cookie.txt`（已在 `.gitignore` 中）。

**Demo 范围（YAGNI）：** 只读；关注流只展示最新一页；评论只展示一级第一页；回复按帖展开时懒加载（每楼一次请求）；无数据库、无 PWA、无写操作、无关注名单同步（过滤不依赖它）。

**Task 0（已完成）：** git 仓库初始化，首个提交 `f24b5ae`，`.gitignore` 已忽略 `cookie.txt`、`fixtures/live/`、`fixtures/*.json`、`__pycache__/`、`.venv/`。

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`

- [ ] **Step 1: 创建虚拟环境并安装依赖**

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

（先执行 Step 2 创建 `requirements.txt` 再运行本步。）

- [ ] **Step 2: 写 `requirements.txt`**

```text
fastapi>=0.115
uvicorn[standard]>=0.30
requests>=2.31
pytest>=8.0
httpx>=0.27
```

- [ ] **Step 3: 写 `app/__init__.py`**

```python
```

（空文件，仅用于包声明。）

- [ ] **Step 4: 写 `app/config.py`**

```python
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    cookie_file: Path
    request_min_delay: float = 1.0
    request_max_delay: float = 2.5
    request_timeout: float = 20.0
    cache_ttl_seconds: float = 600.0
    max_orphan_threads: int = 3


def load_settings() -> Settings:
    return Settings(cookie_file=Path(os.environ.get("WEIBO_COOKIE_FILE", "cookie.txt")))


def load_cookie(settings: Settings) -> str:
    return settings.cookie_file.read_text(encoding="utf-8-sig").strip()
```

- [ ] **Step 5: 冒烟验证**

```powershell
.venv\Scripts\python.exe -c "from app.config import load_settings; print(load_settings().cookie_file)"
```

Expected: 输出 `cookie.txt`。

- [ ] **Step 6: 提交**

```powershell
git add requirements.txt app/__init__.py app/config.py
git commit -m "chore: add project skeleton and settings"
```

---

### Task 2: 领域模型与响应解析（TDD）

**Files:**
- Create: `app/models.py`
- Create: `app/parsing.py`
- Test: `tests/test_parsing.py`

- [ ] **Step 1: 写失败测试 `tests/test_parsing.py`**

```python
from app.parsing import parse_post, parse_reply, parse_root_comment, parse_user


def test_parse_user_reads_following_flag():
    user = parse_user(
        {"idstr": "123", "screen_name": "某人", "profile_image_url": "http://img/x.jpg",
         "following": True}
    )
    assert (user.uid, user.screen_name, user.avatar, user.following) == (
        "123", "某人", "http://img/x.jpg", True)


def test_parse_post_with_retweet():
    raw = {
        "mid": "100",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "转发理由",
        "isAd": False,
        "pic_ids": [],
        "reposts_count": 1,
        "comments_count": 2,
        "attitudes_count": 3,
        "retweeted_status": {
            "mid": "99",
            "user": {"idstr": "2", "screen_name": "B", "following": False},
            "text_raw": "原博",
            "pic_ids": [],
        },
    }
    post = parse_post(raw)
    assert post.mid == "100"
    assert post.author.following is True
    assert post.reposts_count == 1 and post.comments_count == 2 and post.attitudes_count == 3
    assert post.retweeted is not None and post.retweeted.mid == "99"
    assert post.retweeted.author.following is False


def test_parse_post_pics_use_large_url():
    raw = {
        "mid": "100",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "带图",
        "pic_ids": ["p1"],
        "pic_infos": {"p1": {"large": {"url": "http://img/large.jpg"},
                             "bmiddle": {"url": "http://img/mid.jpg"}}},
    }
    post = parse_post(raw)
    assert post.pics == ["http://img/large.jpg"]


def test_parse_root_comment_has_no_target():
    raw = {"id": "555", "user": {"idstr": "1", "screen_name": "A", "following": True},
           "text_raw": "一级评论", "total_number": 3, "like_counts": 4}
    comment = parse_root_comment(raw)
    assert comment.cid == "555"
    assert comment.target is None
    assert comment.total_replies == 3 and comment.like_count == 4


def test_parse_reply_reads_target_user():
    raw = {
        "id": "666",
        "rootid": "555",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "回复内容",
        "reply_comment": {"user": {"idstr": "2", "screen_name": "B", "following": False}},
    }
    reply = parse_reply(raw)
    assert reply.cid == "666" and reply.root_cid == "555"
    assert reply.target is not None
    assert reply.target.uid == "2" and reply.target.following is False
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_parsing.py -v
```

Expected: FAIL（`ModuleNotFoundError: No module named 'app.parsing'`）。

- [ ] **Step 3: 写 `app/models.py`**

```python
from dataclasses import dataclass, field


@dataclass
class User:
    uid: str
    screen_name: str
    avatar: str = ""
    following: bool = False


@dataclass
class Post:
    mid: str
    author: User
    text: str = ""
    pics: list[str] = field(default_factory=list)
    created_at: str = ""
    is_ad: bool = False
    retweeted: "Post | None" = None
    reposts_count: int = 0
    comments_count: int = 0
    attitudes_count: int = 0


@dataclass
class Comment:
    cid: str
    author: User
    text: str = ""
    target: "User | None" = None
    root_cid: str = ""
    total_replies: int = 0
    like_count: int = 0
    promoted: bool = False
```

- [ ] **Step 4: 写 `app/parsing.py`**

```python
from typing import Any

from .models import Comment, Post, User


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def parse_user(raw: dict) -> User:
    return User(
        uid=_s(raw.get("idstr") or raw.get("id")),
        screen_name=_s(raw.get("screen_name")),
        avatar=_s(raw.get("profile_image_url")),
        following=bool(raw.get("following")),
    )


def _parse_pics(raw: dict) -> list[str]:
    infos = raw.get("pic_infos") or {}
    urls: list[str] = []
    for pic_id in raw.get("pic_ids") or []:
        info = infos.get(pic_id) or {}
        url = (info.get("large") or {}).get("url") or (info.get("bmiddle") or {}).get("url")
        if url:
            urls.append(url)
    return urls


def parse_post(raw: dict) -> Post:
    retweeted = raw.get("retweeted_status")
    return Post(
        mid=_s(raw.get("mid") or raw.get("idstr")),
        author=parse_user(raw.get("user") or {}),
        text=_s(raw.get("text_raw")),
        pics=_parse_pics(raw),
        created_at=_s(raw.get("created_at")),
        is_ad=bool(raw.get("isAd")),
        retweeted=parse_post(retweeted) if isinstance(retweeted, dict) else None,
        reposts_count=int(raw.get("reposts_count") or 0),
        comments_count=int(raw.get("comments_count") or 0),
        attitudes_count=int(raw.get("attitudes_count") or 0),
    )


def parse_root_comment(raw: dict) -> Comment:
    return Comment(
        cid=_s(raw.get("id") or raw.get("idstr")),
        author=parse_user(raw.get("user") or {}),
        text=_s(raw.get("text_raw")),
        total_replies=int(raw.get("total_number") or 0),
        like_count=int(raw.get("like_counts") or 0),
    )


def parse_reply(raw: dict) -> Comment:
    reply_comment = raw.get("reply_comment")
    target_raw = reply_comment.get("user") if isinstance(reply_comment, dict) else None
    return Comment(
        cid=_s(raw.get("id") or raw.get("idstr")),
        author=parse_user(raw.get("user") or {}),
        text=_s(raw.get("text_raw")),
        target=parse_user(target_raw) if isinstance(target_raw, dict) else None,
        root_cid=_s(raw.get("rootid") or raw.get("rootidstr")),
        like_count=int(raw.get("like_counts") or 0),
    )
```

- [ ] **Step 5: 运行测试确认通过**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_parsing.py -v
```

Expected: 5 passed。

- [ ] **Step 6: 提交**

```powershell
git add app/models.py app/parsing.py tests/test_parsing.py
git commit -m "feat: add domain models and response parsers"
```

---

### Task 3: 过滤引擎（TDD，核心）

**Files:**
- Create: `app/filter_engine.py`
- Test: `tests/test_filter_engine.py`

- [ ] **Step 1: 写失败测试 `tests/test_filter_engine.py`**

```python
from app.filter_engine import filter_roots, is_visible, visible_posts, visible_replies
from app.models import Comment, Post, User


def user(uid: str, following: bool) -> User:
    return User(uid=uid, screen_name=f"u{uid}", avatar="", following=following)


def root(cid: str, following: bool, total_replies: int = 0) -> Comment:
    return Comment(cid=cid, author=user(cid, following), text="root",
                   total_replies=total_replies)


def reply(cid: str, author_following: bool, target_following, target_uid: str = "t") -> Comment:
    target = None if target_following is None else user(target_uid, target_following)
    return Comment(cid=cid, author=user(cid, author_following), text="reply", target=target)


def test_unfollowed_root_is_hidden():
    assert is_visible(root("1", following=False)) is False
    kept = filter_roots([root("1", False), root("2", True)])
    assert [c.cid for c in kept] == ["2"]


def test_reply_requires_both_sides_followed():
    comments = [
        reply("10", True, True),     # A 回复 B，双方都关注 -> 可见
        reply("11", True, False),    # A 回复 C，C 未关注 -> 隐藏
        reply("12", False, True),    # C 回复 A，C 未关注 -> 隐藏
    ]
    assert [c.cid for c in visible_replies(comments)] == ["10"]


def test_reply_without_target_visible_if_author_followed():
    assert [c.cid for c in visible_replies([reply("10", True, None)])] == ["10"]


def test_promoted_flag_set_for_orphans():
    kept = visible_replies([reply("10", True, True), reply("11", True, False)], promoted=True)
    assert len(kept) == 1
    assert kept[0].cid == "10" and kept[0].promoted is True


def test_visible_posts_drops_ads_and_strangers():
    def post(mid: str, following: bool, is_ad: bool = False) -> Post:
        return Post(mid=mid, author=user(mid, following), text="", is_ad=is_ad)

    items = visible_posts([post("1", True), post("2", True, is_ad=True), post("3", False)])
    assert [p.mid for p in items] == ["1"]
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_filter_engine.py -v
```

Expected: FAIL（`No module named 'app.filter_engine'`）。

- [ ] **Step 3: 写 `app/filter_engine.py`**

```python
"""过滤引擎：输入原始模型，输出"只包含我关注的人"的视图。

规则:
- R2 一级评论/帖子：作者必须被关注
- R4 回复：回复者与被回复者都必须被关注
- 广告/推荐：isAd 或作者未被关注则丢弃
"""

from dataclasses import replace

from .models import Comment, Post


def is_visible(comment: Comment) -> bool:
    """仅适用于 Comment。target 为 None（一级评论）时只检查作者是否被关注。"""
    if not comment.author.following:
        return False
    if comment.target is not None and not comment.target.following:
        return False
    return True


def filter_roots(roots: list[Comment]) -> list[Comment]:
    return [root for root in roots if is_visible(root)]


def visible_replies(replies: list[Comment], promoted: bool = False) -> list[Comment]:
    """返回可见回复。promoted=True 时返回标记了"上下文已隐藏"的副本（不修改原对象）；
    promoted=False 时返回原对象（调用方不得修改）。"""
    kept = [reply for reply in replies if is_visible(reply)]
    if promoted:
        return [replace(reply, promoted=True) for reply in kept]
    return kept


def visible_posts(posts: list[Post]) -> list[Post]:
    return [post for post in posts if post.author.following and not post.is_ad]
```

- [ ] **Step 4: 运行全部测试确认通过**

```powershell
.venv\Scripts\python.exe -m pytest -v
```

Expected: 10 passed（Task 2 的 5 个 + 本任务 5 个）。

- [ ] **Step 5: 提交**

```powershell
git add app/filter_engine.py tests/test_filter_engine.py
git commit -m "feat: add follow-based filter engine with R2/R4 rules"
```

---

### Task 4: 内存缓存与微博客户端（TDD，monkeypatch 会话）

**Files:**
- Create: `app/cache.py`
- Create: `app/weibo_client.py`
- Test: `tests/test_client.py`

- [ ] **Step 1: 写失败测试 `tests/test_client.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_client.py -v
```

Expected: FAIL（`No module named 'app.weibo_client'`）。

- [ ] **Step 3: 写 `app/cache.py`**

```python
import time
from typing import Any, Callable


class TTLCache:
    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._items: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if time.monotonic() > expires_at:
            self._items.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._items[key] = (time.monotonic() + self._ttl, value)

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        value = self.get(key)
        if value is None:
            value = factory()
            self.set(key, value)
        return value
```

- [ ] **Step 4: 写 `app/weibo_client.py`**

```python
import random
import time
from typing import Any

import requests

from .cache import TTLCache
from .config import Settings
from .models import Comment, Post
from .parsing import parse_post, parse_reply, parse_root_comment

BASE = "https://weibo.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class WeiboError(Exception):
    pass


class WeiboAuthError(WeiboError):
    pass


class WeiboRateLimitError(WeiboError):
    pass


class WeiboClient:
    def __init__(self, cookie: str, settings: Settings):
        self._cookie = cookie
        self._settings = settings
        self._session = requests.Session()
        self._cache = TTLCache(settings.cache_ttl_seconds)
        self._follow_gid: str | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    def _headers(self) -> dict[str, str]:
        return {
            "Cookie": self._cookie,
            "User-Agent": USER_AGENT,
            "Referer": BASE + "/",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        time.sleep(random.uniform(self._settings.request_min_delay,
                                  self._settings.request_max_delay))
        try:
            resp = self._session.get(BASE + path, params=params, headers=self._headers(),
                                     timeout=self._settings.request_timeout)
        except requests.RequestException as exc:
            raise WeiboError(f"网络请求失败: {exc}") from exc
        if resp.status_code in (401, 403):
            raise WeiboAuthError("Cookie 已失效，请更新 cookie.txt 后重试")
        try:
            data = resp.json()
        except ValueError as exc:
            raise WeiboError("接口返回非 JSON，可能被风控，请稍后再试") from exc
        if not isinstance(data, dict):
            raise WeiboError("接口返回结构异常")
        if data.get("ok") != 1:
            code = data.get("errno") or data.get("code") or data.get("ok")
            if code in (-100, 100003, "100003"):
                raise WeiboAuthError("Cookie 已失效，请更新 cookie.txt 后重试")
            raise WeiboRateLimitError(f"接口拒绝请求（code={code}），请稍后再试")
        return data

    def _comment_params(self, extra: dict[str, str], author_uid: str) -> dict[str, str]:
        params = {
            "is_reload": "1", "is_show_bulletin": "3", "is_mix": "0", "count": "20",
            "type": "feed", "uid": author_uid, "locale": "zh-CN",
        }
        params.update(extra)
        return params

    def fetch_all_groups(self) -> dict:
        return self._cache.get_or_set("all_groups",
                                      lambda: self._get("/ajax/feed/allGroups"))

    def resolve_follow_gid(self) -> str:
        if self._follow_gid:
            return self._follow_gid
        data = self.fetch_all_groups()
        for group in data.get("groups") or []:
            if not isinstance(group, dict):
                continue
            for item in group.get("group") or []:
                if isinstance(item, dict) and item.get("title") == "全部关注" and item.get("gid"):
                    self._follow_gid = str(item["gid"])
                    return self._follow_gid
        raise WeiboError("未找到'全部关注'分组，接口可能已变更")

    def fetch_feed(self) -> list[Post]:
        def load() -> list[Post]:
            gid = self.resolve_follow_gid()
            data = self._get("/ajax/feed/friendstimeline",
                             {"list_id": gid, "fid": gid, "refresh": "4",
                              "since_id": "0", "count": "25"})
            return [parse_post(raw) for raw in data.get("statuses") or []]

        return self._cache.get_or_set("feed", load)

    def fetch_status(self, mid: str) -> Post:
        def load() -> Post:
            return parse_post(self._get("/ajax/statuses/show", {"id": mid}))

        return self._cache.get_or_set(f"status:{mid}", load)

    def fetch_root_comments(self, mid: str, author_uid: str) -> list[Comment]:
        def load() -> list[Comment]:
            data = self._get("/ajax/statuses/buildComments",
                             self._comment_params({"id": mid, "fetch_level": "0"}, author_uid))
            return [parse_root_comment(raw) for raw in data.get("data") or []]

        return self._cache.get_or_set(f"comments:{mid}", load)

    def fetch_replies(self, root_cid: str, mid: str, author_uid: str) -> list[Comment]:
        def load() -> list[Comment]:
            data = self._get("/ajax/statuses/buildComments",
                             self._comment_params({"id": root_cid, "fetch_level": "1"}, author_uid))
            return [parse_reply(raw) for raw in data.get("data") or []]

        return self._cache.get_or_set(f"replies:{mid}:{root_cid}", load)
```

- [ ] **Step 5: 运行全部测试确认通过**

```powershell
.venv\Scripts\python.exe -m pytest -v
```

Expected: 15 passed。

- [ ] **Step 6: 提交**

```powershell
git add app/cache.py app/weibo_client.py tests/test_client.py
git commit -m "feat: add weibo client with ttl cache and error mapping"
```

---

### Task 5: FastAPI 路由与静态托管（TDD，TestClient）

**Files:**
- Create: `app/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: 写失败测试 `tests/test_api.py`**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_api.py -v
```

Expected: FAIL（`No module named 'app.main'`）。

- [ ] **Step 3: 写 `app/main.py`**

```python
from pathlib import Path
import threading

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
                    raise WeiboAuthError(
                        f"无法读取 Cookie 文件 {settings.cookie_file}：{exc}") from exc
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
```

- [ ] **Step 4: 创建 `web/index.html` 占位文件（让静态挂载可导入）**

```html
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>纯净微博</title></head>
<body>placeholder</body>
</html>
```

- [ ] **Step 5: 运行全部测试确认通过**

```powershell
.venv\Scripts\python.exe -m pytest -v
```

Expected: 19 passed。

- [ ] **Step 6: 提交**

```powershell
git add app/main.py tests/test_api.py web/index.html
git commit -m "feat: add fastapi routes with error mapping and static hosting"
```

---

### Task 6: 前端静态页 + 关注流

**Files:**
- Modify: `web/index.html`
- Create: `web/style.css`
- Create: `web/app.js`（本任务先实现关注流；Task 7 会给出完整版覆盖）

- [ ] **Step 1: 写 `web/index.html`**

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>纯净微博</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header class="topbar">
    <button id="back-btn" class="back-btn" hidden type="button">‹</button>
    <h1 id="title">纯净微博</h1>
    <button id="refresh-btn" type="button">刷新</button>
  </header>
  <div id="banner" class="banner" hidden></div>
  <main id="feed" class="feed"></main>
  <section id="detail" class="detail" hidden></section>
  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 `web/style.css`**

```css
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  background: #f4f5f7; color: #1f2329; }
.topbar { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; background: #fff; border-bottom: 1px solid #e5e6eb; }
.topbar h1 { flex: 1; font-size: 17px; margin: 0; text-align: center; }
.topbar button { border: 1px solid #d0d3d9; background: #fff; color: inherit; border-radius: 6px;
  padding: 6px 10px; font-size: 14px; }
.banner { margin: 8px 12px; padding: 10px 12px; border-radius: 8px; background: #fde2e2;
  color: #a8071a; font-size: 14px; }
.feed, .detail { max-width: 640px; margin: 0 auto; padding: 8px 8px 48px; }
.card { background: #fff; border-radius: 10px; padding: 12px; margin: 8px 0; }
.head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: #e5e6eb; object-fit: cover; }
.name { font-weight: 600; font-size: 15px; }
.text { margin: 8px 0; font-size: 15px; line-height: 1.6; white-space: pre-wrap;
  word-break: break-word; }
.pics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; }
.pics img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; }
.retweet { background: #f7f8fa; border-radius: 8px; padding: 8px; margin: 8px 0; font-size: 14px; }
.meta { color: #86909c; font-size: 13px; }
.comment { border-top: 1px solid #f0f1f3; padding: 10px 0; }
.target { color: #86909c; font-size: 14px; }
.tag { display: inline-block; font-size: 12px; color: #86909c; border: 1px solid #e5e6eb;
  border-radius: 4px; padding: 0 6px; }
.replies { margin: 4px 0 0 12px; border-left: 2px solid #f0f1f3; padding-left: 10px; }
.more-btn { border: none; background: none; color: #165dff; font-size: 13px; padding: 4px 0;
  cursor: pointer; }
.loading { text-align: center; color: #86909c; padding: 16px; font-size: 14px; }
h2 { font-size: 15px; margin: 0 0 4px; }
@media (prefers-color-scheme: dark) {
  body { background: #17171a; color: #e5e6eb; }
  .topbar, .card { background: #232324; border-color: #2e2e30; }
  .topbar button { background: #232324; border-color: #3a3a3c; }
  .retweet { background: #2b2b2d; }
  .comment, .replies { border-color: #2e2e30; }
}
```

- [ ] **Step 3: 写 `web/app.js`（关注流版本）**

```js
const state = { mid: null, view: "feed" };

const $ = (selector) => document.querySelector(selector);

async function api(path) {
  const resp = await fetch(path);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `请求失败（HTTP ${resp.status}）`);
  }
  return resp.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showBanner(message) {
  const banner = $("#banner");
  banner.textContent = message;
  banner.hidden = false;
}

function hideBanner() { $("#banner").hidden = true; }

function userHead(user) {
  const head = el("div", "head");
  const avatar = el("img", "avatar");
  avatar.src = user.avatar || "";
  avatar.alt = "";
  head.append(avatar, el("span", "name", user.name));
  return head;
}

function postCard(post, onClick) {
  const card = el("article", "card");
  card.append(userHead(post.author));
  card.append(el("div", "text", post.text));
  if (post.pics.length) {
    const pics = el("div", "pics");
    for (const url of post.pics) {
      const img = el("img");
      img.src = url;
      img.loading = "lazy";
      pics.append(img);
    }
    card.append(pics);
  }
  if (post.retweeted) {
    const box = el("div", "retweet");
    box.append(el("div", "name", "@" + post.retweeted.author.name));
    box.append(el("div", "text", post.retweeted.text));
    card.append(box);
  }
  card.append(el("div", "meta",
    `转发 ${post.reposts} · 评论 ${post.comments} · 赞 ${post.attitudes}`));
  if (onClick) card.addEventListener("click", onClick);
  return card;
}

async function loadFeed() {
  hideBanner();
  const feed = $("#feed");
  feed.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api("/api/feed");
    feed.innerHTML = "";
    if (!data.items.length) feed.innerHTML = '<div class="loading">没有可显示的内容</div>';
    for (const post of data.items) feed.append(postCard(post, () => openDetail(post.mid)));
  } catch (error) {
    feed.innerHTML = "";
    showBanner(error.message);
  }
}

function setView(view) {
  state.view = view;
  $("#feed").hidden = view !== "feed";
  $("#detail").hidden = view !== "detail";
  $("#back-btn").hidden = view === "feed";
  $("#refresh-btn").hidden = view !== "feed";
  $("#title").textContent = view === "feed" ? "纯净微博" : "帖子详情";
  window.scrollTo(0, 0);
}

function openDetail(mid) {
  state.mid = mid;
  setView("detail");
  $("#detail").innerHTML = '<div class="loading">详情页将在下一个任务实现</div>';
}

$("#refresh-btn").addEventListener("click", loadFeed);
$("#back-btn").addEventListener("click", () => setView("feed"));
loadFeed();
```

- [ ] **Step 4: 启动服务并手工验证关注流**

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`，预期：

- 顶栏显示"纯净微博"，列表出现关注用户的帖子卡片（含转发卡片、图片）；
- 点击"刷新"重新加载；无广告卡片；
- 点击卡片进入详情占位提示（下个任务实现）。

- [ ] **Step 5: 提交**

```powershell
git add web/index.html web/style.css web/app.js
git commit -m "feat: add mobile web ui for filtered following feed"
```

---

### Task 7: 前端详情页与评论树

**Files:**
- Modify: `web/app.js`（用下面的完整版本整体替换）

- [ ] **Step 1: 用完整版本替换 `web/app.js`**

```js
const state = { mid: null, view: "feed" };

const $ = (selector) => document.querySelector(selector);

async function api(path) {
  const resp = await fetch(path);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `请求失败（HTTP ${resp.status}）`);
  }
  return resp.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showBanner(message) {
  const banner = $("#banner");
  banner.textContent = message;
  banner.hidden = false;
}

function hideBanner() { $("#banner").hidden = true; }

function userHead(user) {
  const head = el("div", "head");
  const avatar = el("img", "avatar");
  avatar.src = user.avatar || "";
  avatar.alt = "";
  head.append(avatar, el("span", "name", user.name));
  return head;
}

function postCard(post, onClick) {
  const card = el("article", "card");
  card.append(userHead(post.author));
  card.append(el("div", "text", post.text));
  if (post.pics.length) {
    const pics = el("div", "pics");
    for (const url of post.pics) {
      const img = el("img");
      img.src = url;
      img.loading = "lazy";
      pics.append(img);
    }
    card.append(pics);
  }
  if (post.retweeted) {
    const box = el("div", "retweet");
    box.append(el("div", "name", "@" + post.retweeted.author.name));
    box.append(el("div", "text", post.retweeted.text));
    card.append(box);
  }
  card.append(el("div", "meta",
    `转发 ${post.reposts} · 评论 ${post.comments} · 赞 ${post.attitudes}`));
  if (onClick) card.addEventListener("click", onClick);
  return card;
}

function commentBody(comment) {
  const box = el("div", "comment");
  const head = el("div", "head");
  const avatar = el("img", "avatar");
  avatar.src = comment.author.avatar || "";
  avatar.alt = "";
  head.append(avatar, el("span", "name", comment.author.name));
  if (comment.target) head.append(el("span", "target", `回复 @${comment.target.name}`));
  if (comment.promoted) head.append(el("span", "tag", "上下文已隐藏"));
  box.append(head);
  box.append(el("div", "text", comment.text));
  return box;
}

async function loadFeed() {
  hideBanner();
  const feed = $("#feed");
  feed.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api("/api/feed");
    feed.innerHTML = "";
    if (!data.items.length) feed.innerHTML = '<div class="loading">没有可显示的内容</div>';
    for (const post of data.items) feed.append(postCard(post, () => openDetail(post.mid)));
  } catch (error) {
    feed.innerHTML = "";
    showBanner(error.message);
  }
}

function setView(view) {
  state.view = view;
  $("#feed").hidden = view !== "feed";
  $("#detail").hidden = view !== "detail";
  $("#back-btn").hidden = view === "feed";
  $("#refresh-btn").hidden = view !== "feed";
  $("#title").textContent = view === "feed" ? "纯净微博" : "帖子详情";
  window.scrollTo(0, 0);
}

async function openDetail(mid) {
  state.mid = mid;
  setView("detail");
  const detail = $("#detail");
  detail.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const [statusData, commentsData] = await Promise.all([
      api(`/api/status/${mid}`),
      api(`/api/status/${mid}/comments`),
    ]);
    renderDetail(statusData.post, commentsData);
  } catch (error) {
    detail.innerHTML = "";
    showBanner(error.message);
  }
}

function renderDetail(post, comments) {
  const detail = $("#detail");
  detail.innerHTML = "";
  detail.append(postCard(post, null));

  const section = el("section", "card");
  section.append(el("h2", null, "评论（只显示你关注的人）"));
  if (!comments.threads.length && !comments.orphans.length) {
    section.append(el("div", "loading", "没有可显示的评论"));
  }
  for (const thread of comments.threads) {
    const box = commentBody(thread);
    if (thread.total_replies > 0) {
      const replies = el("div", "replies");
      replies.hidden = true;
      const button = el("button", "more-btn", `查看 ${thread.total_replies} 条回复`);
      button.type = "button";
      button.addEventListener("click", () => expandReplies(thread.cid, replies, button));
      box.append(button, replies);
    }
    section.append(box);
  }
  if (comments.orphans.length) {
    section.append(el("h2", null, "其他讨论中你关注的人的回复"));
    for (const orphan of comments.orphans) section.append(commentBody(orphan));
  }
  detail.append(section);
}

async function expandReplies(rootCid, container, button) {
  button.disabled = true;
  button.textContent = "加载中…";
  try {
    const data = await api(`/api/comment/${rootCid}/replies?mid=${state.mid}`);
    container.innerHTML = "";
    for (const reply of data.items) container.append(commentBody(reply));
    container.hidden = false;
    button.remove();
  } catch (error) {
    button.disabled = false;
    button.textContent = "加载失败，点击重试";
  }
}

$("#refresh-btn").addEventListener("click", loadFeed);
$("#back-btn").addEventListener("click", () => setView("feed"));
loadFeed();
```

- [ ] **Step 2: 手工验证详情页（服务保持运行，刷新页面）**

验收清单：

- 关注流点开任意帖子：详情显示正文、转发卡片、评论数；
- 评论区只出现关注用户的昵称（可对照原微博：未关注用户的评论不出现）；
- 带回复的楼层显示"查看 N 条回复"，点击后展开，且只显示双方都关注的回复；
- 若某帖子存在"根评论被隐藏、其下有你关注的回复"，应出现在"其他讨论中你关注的人的回复"区域并带"上下文已隐藏"标签（找不到此类帖子可跳过，功能由单测覆盖）；
- 手机模拟（DevTools 设备模式）布局正常，深色模式可读。

- [ ] **Step 3: 提交**

```powershell
git add web/app.js
git commit -m "feat: add post detail with filtered comment tree and orphan replies"
```

---

### Task 8: 文档、运行说明与最终验收

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 在 `README.md` 的"## 7. 里程碑"之前插入 Demo 运行说明**

````markdown
## 6.5 Demo 运行说明（本地）

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# 确保项目根目录存在 cookie.txt（从浏览器复制，格式同 weibo-follows）
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- 电脑访问 `http://127.0.0.1:8000`；手机与电脑同一 Wi-Fi 时访问 `http://<电脑IP>:8000`。
- 测试：`.venv\Scripts\python.exe -m pytest -v`
- Demo 已知限制：只读；只加载关注流最新一页；评论只加载第一页、回复按楼懒加载；无数据库/PWA。

实现计划见 `docs/superpowers/plans/2026-09-13-weibo-clean-demo.md`。
````

- [ ] **Step 2: 全量测试与端到端验收**

```powershell
.venv\Scripts\python.exe -m pytest -v
```

Expected: 19 passed。

再启动服务，完成 Task 6/7 的验收清单；并验证失效 Cookie 场景：

```powershell
Rename-Item cookie.txt cookie.txt.bak
# 刷新页面：应显示红色提示"无法读取 Cookie 文件"或"Cookie 已失效"
Rename-Item cookie.txt.bak cookie.txt
```

- [ ] **Step 3: 提交并打 tag**

```powershell
git add README.md
git commit -m "docs: add demo run instructions and known limitations"
git tag demo-v0.1.0
```

---

## 完成标准（Definition of Done）

- `pytest -v` 全绿（19 个用例）；
- 浏览器可完成：看关注流 → 点开帖子 → 看过滤评论 → 展开楼中楼 → 看到孤儿回复标注；
- 全过程中未关注用户的昵称/评论在页面上不可见；
- Cookie 失效、限流、接口异常都有明确提示；
- `git log` 呈现按任务的渐进式提交，`cookie.txt` 与原始抓包未入库。

# 白名单可见性（v0.2）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **执行方式（已定）**：用户已授权"设计与实现自行完成"，本计划按 superpowers:executing-plans 在本会话内联执行（不派子代理）。

**Goal:** 把可见性判定从"关注"升级为"白名单"（关注 ∪ 手动添加 − 手动移除）：未关注者可手动加入并将其原创帖并入信息流，已关注者可隐藏并在管理页恢复。

**Architecture:** 新增 `WhitelistStore`（JSON 原子持久化"添加/移除"两个覆盖集合）与 `WhitelistPolicy`（统一谓词，替换 filter_engine 里的 `following` 判断）；`WeiboClient` 新增关注列表、单用户资料、单用户时间线抓取；`/api/feed` 合并关注流与手动添加者时间线；前端新增第三个视图"白名单管理"。

**Tech Stack:** Python 3.11 / FastAPI / requests / pytest / 原生 JS（无构建）。

**环境约定：**
- 工作目录：`D:\desktop\weibo-clean`；Python 一律用 `.venv\Scripts\python.exe`（`python` 不在 PATH）。
- 永远不要打印/提交 `cookie.txt` 内容；`fixtures/live/` 已在 .gitignore。
- 每个 Task 结束必须 `git add` 指定文件并 commit（本计划在 `feature/whitelist` 分支上执行）。

**设计依据：** `docs/superpowers/specs/2026-09-13-whitelist-design.md`。

---

### Task 0: 新接口 M0 验证（真实 Cookie，mymblog + profile/info）

**Files:**
- Create: `%TEMP%\opencode\whitelist_m0.py`（临时脚本，不入库）
- Modify: `fixtures/m0-findings.md`（追加"M1 白名单补充验证"小节）
- Output: `fixtures/live/w_mymblog_*.json`、`w_profile_info_unknown.json`（gitignored）

- [ ] **Step 1: 写验证脚本**

```python
import json
import sys
from pathlib import Path

PROJECT = Path(r"D:\desktop\weibo-clean")
sys.path.insert(0, str(PROJECT))

from app.config import load_settings
from app.weibo_client import WeiboClient

settings = load_settings()
cookie = (PROJECT / "cookie.txt").read_text(encoding="utf-8-sig").strip()
client = WeiboClient(cookie, settings)
out = PROJECT / "fixtures" / "live"


def dump(name, payload):
    (out / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


unknown_uid = "3333333333"    # M0 评论者样本，following=false
followed_uid = "2222222222"   # M0 关注样本，following=true

info = client._get("/ajax/profile/info", {"uid": unknown_uid})
dump("w_profile_info_unknown.json", info)
user = ((info.get("data") or {}).get("user")) or {}
print("profile/info:", {k: (k in user) for k in ("idstr", "screen_name", "profile_image_url", "following")})
print("  following =", user.get("following"))

for feature in ("0", "1"):
    data = client._get("/ajax/statuses/mymblog", {"uid": unknown_uid, "page": "1", "feature": feature})
    dump(f"w_mymblog_unknown_f{feature}.json", data)
    items = (data.get("data") or {}).get("list") or []
    print(f"mymblog feature={feature}: ok={data.get('ok')} items={len(items)}")
    if items:
        first = items[0]
        print("  has:", {k: (k in first) for k in ("mid", "created_at", "isAd", "retweeted_status", "user")})
        print("  created_at =", repr(first.get("created_at")))
        print("  is_retweet =", isinstance(first.get("retweeted_status"), dict))
        print("  author_following =", (first.get("user") or {}).get("following"))

data2 = client._get("/ajax/statuses/mymblog", {"uid": followed_uid, "page": "1", "feature": "0"})
dump("w_mymblog_followed_f0.json", data2)
items2 = (data2.get("data") or {}).get("list") or []
print("mymblog followed: items =", len(items2),
      "created_at =", repr(items2[0].get("created_at")) if items2 else None)
```

- [ ] **Step 2: 运行脚本**

Run: `.venv\Scripts\python.exe %TEMP%\opencode\whitelist_m0.py`
Expected:
- `profile/info` 四个字段全部 True，`following = False`（未关注样本）。
- `mymblog feature=0`：`ok=1`、`items > 0`、含 `mid/created_at/user`；`created_at` 为可解析时间串；观察 `retweeted_status` / `isAd` 是否存在。
- 记录 feature=0 与 feature=1 哪个含转发（决定 §6 取哪个值；若 0 不含、1 含，则采用 1）。
- 若 `mymblog` 返回 404/ok!=1 或对未关注账号不可用：依次尝试 `feature` 其他值、`/ajax/statuses/mymblog?uid=..&page=1&since_id=..`、`m.weibo.cn/api/container/getIndex?type=uid&value={uid}`；把最终可用端点、参数与结构写进 findings，后续 Task 4/5 按实际结果微调。

- [ ] **Step 3: 记录结论**

在 `fixtures/m0-findings.md` 末尾追加：

```markdown
## M1 白名单补充验证（2026-09-13）

| 编号 | 项目 | 结论 | 证据文件 |
| --- | --- | --- | --- |
| V8 | 个人时间线（未关注账号） | 待填：端点/参数/可用性 | `live/w_mymblog_unknown_f0.json` |
| V9 | 个人时间线是否含转发 | 待填：feature 取值与结论 | `live/w_mymblog_unknown_f1.json` |
| V10 | 已关注账号抽样一致性 | 待填 | `live/w_mymblog_followed_f0.json` |
| V11 | profile/info 字段复核 | 待填（idstr/screen_name/profile_image_url/following） | `live/w_profile_info_unknown.json` |

补充说明：created_at 格式 = ；isAd 字段 = 。
```

把"待填"替换为实测值后提交。

- [ ] **Step 4: Commit**

```powershell
git add fixtures/m0-findings.md
git commit -m "docs: verify user timeline endpoint for whitelist feature"
```

---

### Task 1: WhitelistStore（存储 + 输入解析）

**Files:**
- Create: `app/whitelist.py`
- Create: `tests/test_whitelist.py`
- Modify: `app/config.py`（加 `whitelist_file`）
- Modify: `.gitignore`（忽略 `whitelist.json`）

- [ ] **Step 1: 写失败测试 `tests/test_whitelist.py`**

```python
import json

import pytest

from app.whitelist import (
    WhitelistEntry,
    WhitelistError,
    WhitelistStore,
    parse_uid_input,
)


def entry(uid: str, name: str = "n") -> WhitelistEntry:
    return WhitelistEntry(uid=uid, name=name, avatar="http://img/a.jpg")


def test_parse_uid_input_accepts_digits():
    assert parse_uid_input(" 123456 ") == "123456"


@pytest.mark.parametrize("text", [
    "https://weibo.com/u/123456",
    "weibo.com/u/123456?from=page",
    "https://m.weibo.cn/u/123456",
    "https://weibo.com/123456",
])
def test_parse_uid_input_accepts_links(text):
    assert parse_uid_input(text) == "123456"


@pytest.mark.parametrize("text", ["", "昵称", "https://weibo.com/n/somebody"])
def test_parse_uid_input_rejects(text):
    with pytest.raises(ValueError):
        parse_uid_input(text)


def test_add_persists_and_removes_from_removed(tmp_path):
    path = tmp_path / "wl.json"
    store = WhitelistStore(path)
    store.hide(entry("1"))
    store.add(entry("1", "新名字"))
    reloaded = WhitelistStore(path)
    assert reloaded.is_added("1") is True
    assert reloaded.is_removed("1") is False
    assert reloaded.added_entries()[0].name == "新名字"


def test_add_stamps_time_when_missing(tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(WhitelistEntry(uid="1"))
    assert store.added_entries()[0].at


def test_hide_moves_added_to_removed(tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(entry("1"))
    store.hide(entry("1"))
    assert store.is_added("1") is False
    assert store.is_removed("1") is True


def test_remove_added_and_restore(tmp_path):
    store = WhitelistStore(tmp_path / "wl.json")
    store.add(entry("1"))
    store.hide(entry("2"))
    store.remove_added("1")
    store.restore("2")
    assert store.added_entries() == []
    assert store.removed_entries() == []


def test_missing_file_starts_empty(tmp_path):
    store = WhitelistStore(tmp_path / "nope.json")
    assert store.added_entries() == []
    assert store.is_added("1") is False


def test_corrupt_file_raises(tmp_path):
    path = tmp_path / "wl.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(WhitelistError):
        WhitelistStore(path).is_added("1")


def test_entries_without_uid_are_skipped(tmp_path):
    path = tmp_path / "wl.json"
    payload = {"version": 1, "added": [{"name": "x"}, vars(entry("1"))]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert [e.uid for e in WhitelistStore(path).added_entries()] == ["1"]


def test_saved_file_is_valid_and_tmp_cleaned(tmp_path):
    path = tmp_path / "wl.json"
    store = WhitelistStore(path)
    store.add(entry("1"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1 and payload["added"][0]["uid"] == "1"
    assert not (tmp_path / "wl.json.tmp").exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_whitelist.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'app.whitelist'`（或 ImportError）。

- [ ] **Step 3: 实现 `app/whitelist.py`**

```python
"""白名单存储：关注为默认基底，手动添加/移除作为覆盖。

生效白名单 = （关注 ∪ added） − removed。
"""

import json
import os
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


class WhitelistError(Exception):
    pass


@dataclass(frozen=True)
class WhitelistEntry:
    uid: str
    name: str = ""
    avatar: str = ""
    at: str = ""


def parse_uid_input(text: str) -> str:
    value = (text or "").strip()
    if not value:
        raise ValueError("请输入主页链接或 UID")
    if value.isdigit():
        return value
    parsed = urlparse(value if "://" in value else "https://" + value)
    segments = [segment for segment in parsed.path.split("/") if segment]
    for index, segment in enumerate(segments[:-1]):
        if segment == "u" and segments[index + 1].isdigit():
            return segments[index + 1]
    for segment in segments:
        if segment.isdigit():
            return segment
    raise ValueError("无法解析 UID，请粘贴形如 weibo.com/u/123456 的主页链接或数字 UID")


class WhitelistStore:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._lock = threading.Lock()
        self._loaded = False
        self._added: dict[str, WhitelistEntry] = {}
        self._removed: dict[str, WhitelistEntry] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise WhitelistError(f"白名单文件无法读取：{exc}") from exc
            if not isinstance(data, dict):
                raise WhitelistError("白名单文件格式异常：顶层必须是对象")
            self._added = self._read_entries(data.get("added"))
            self._removed = self._read_entries(data.get("removed"))
        self._loaded = True

    @staticmethod
    def _read_entries(raw) -> dict[str, WhitelistEntry]:
        entries: dict[str, WhitelistEntry] = {}
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            uid = str(item.get("uid") or "").strip()
            if not uid:
                continue
            entries[uid] = WhitelistEntry(
                uid=uid,
                name=str(item.get("name") or ""),
                avatar=str(item.get("avatar") or ""),
                at=str(item.get("at") or ""),
            )
        return entries

    def _save(self) -> None:
        payload = {
            "version": 1,
            "added": [vars(item) for item in self._added.values()],
            "removed": [vars(item) for item in self._removed.values()],
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.parent / (self._path.name + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        os.replace(tmp_path, self._path)

    @staticmethod
    def _stamp(item: WhitelistEntry) -> WhitelistEntry:
        if item.at:
            return item
        return replace(item, at=datetime.now(timezone.utc).isoformat())

    def is_added(self, uid: str) -> bool:
        with self._lock:
            self._ensure_loaded()
            return uid in self._added

    def is_removed(self, uid: str) -> bool:
        with self._lock:
            self._ensure_loaded()
            return uid in self._removed

    def add(self, item: WhitelistEntry) -> None:
        with self._lock:
            self._ensure_loaded()
            self._removed.pop(item.uid, None)
            self._added[item.uid] = self._stamp(item)
            self._save()

    def hide(self, item: WhitelistEntry) -> None:
        with self._lock:
            self._ensure_loaded()
            self._added.pop(item.uid, None)
            self._removed[item.uid] = self._stamp(item)
            self._save()

    def remove_added(self, uid: str) -> None:
        with self._lock:
            self._ensure_loaded()
            self._added.pop(uid, None)
            self._save()

    def restore(self, uid: str) -> None:
        with self._lock:
            self._ensure_loaded()
            self._removed.pop(uid, None)
            self._save()

    def added_entries(self) -> list[WhitelistEntry]:
        with self._lock:
            self._ensure_loaded()
            return list(self._added.values())

    def removed_entries(self) -> list[WhitelistEntry]:
        with self._lock:
            self._ensure_loaded()
            return list(self._removed.values())
```

- [ ] **Step 4: 改 `app/config.py`**

`Settings` 增加字段（放在 `cookie_file` 之后）：

```python
    whitelist_file: Path = Path("whitelist.json")
```

`load_settings()` 改为：

```python
def load_settings() -> Settings:
    return Settings(
        cookie_file=Path(os.environ.get("WEIBO_COOKIE_FILE", "cookie.txt")),
        whitelist_file=Path(os.environ.get("WEIBO_WHITELIST_FILE", "whitelist.json")),
    )
```

- [ ] **Step 5: 改 `.gitignore`**

在 `# secrets` 段的 `cookie.txt` 后追加：

```
whitelist.json
```

- [ ] **Step 6: 测试通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_whitelist.py -q`
Expected: `11 passed`（参数化展开后数量以实际为准，全部 PASS）。

- [ ] **Step 7: Commit**

```powershell
git add app/whitelist.py tests/test_whitelist.py app/config.py .gitignore
git commit -m "feat: add whitelist store with atomic persistence"
```

---

### Task 2: Post.created_ts（合并排序用时间戳）

**Files:**
- Modify: `app/models.py`（`Post` 加字段）
- Modify: `app/parsing.py`（`parse_created_ts` + `parse_post`）
- Test: `tests/test_parsing.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 `tests/test_parsing.py`）**

```python
from app.parsing import parse_created_ts


def test_parse_created_ts_weibo_format():
    assert parse_created_ts("Sat Sep 13 20:00:00 +0800 2026") > 0


def test_parse_created_ts_iso_format():
    assert parse_created_ts("2026-09-13T20:00:00+08:00") > 0


def test_parse_created_ts_invalid_returns_zero():
    assert parse_created_ts("刚刚") == 0.0
    assert parse_created_ts(None) == 0.0


def test_parse_post_reads_created_ts():
    raw = {"mid": "1", "user": {"idstr": "1"},
           "created_at": "Sat Sep 13 20:00:00 +0800 2026"}
    assert parse_post(raw).created_ts > 0
```

（顶部已有 `from app.parsing import parse_post, ...`，追加导入行即可。）

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_parsing.py -q`
Expected: FAIL / ImportError（`parse_created_ts` 不存在，`created_ts` 属性不存在）。

- [ ] **Step 3: 改 `app/models.py`**

`Post` 在 `created_at: str = ""` 后插入一行：

```python
    created_ts: float = 0.0
```

- [ ] **Step 4: 改 `app/parsing.py`**

顶部加 `from datetime import datetime`，新增函数，并在 `parse_post` 的返回里加 `created_ts=parse_created_ts(raw.get("created_at"))`：

```python
def parse_created_ts(value: Any) -> float:
    text = _s(value).strip()
    if not text:
        return 0.0
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y").timestamp()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0
```

- [ ] **Step 5: 测试通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_parsing.py -q`
Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```powershell
git add app/models.py app/parsing.py tests/test_parsing.py
git commit -m "feat: parse post timestamp for feed merge sorting"
```

---

### Task 3: WhitelistPolicy 替换 filter_engine 的关注判定

**Files:**
- Modify: `app/filter_engine.py`（全量重写）
- Test: `tests/test_filter_engine.py`（全量重写）

- [ ] **Step 1: 全量重写测试 `tests/test_filter_engine.py`**

```python
import pytest

from app.filter_engine import (
    WhitelistPolicy,
    filter_roots,
    is_visible,
    visible_posts,
    visible_replies,
)
from app.models import Comment, Post, User
from app.whitelist import WhitelistEntry, WhitelistStore


def user(uid: str, following: bool) -> User:
    return User(uid=uid, screen_name=f"u{uid}", avatar="", following=following)


def root(cid: str, following: bool, total_replies: int = 0) -> Comment:
    return Comment(cid=cid, author=user(cid, following), text="root",
                   total_replies=total_replies)


def reply(cid: str, author_following: bool, target_following,
          target_uid: str = "t") -> Comment:
    target = None if target_following is None else user(target_uid, target_following)
    return Comment(cid=cid, author=user(cid, author_following), text="reply", target=target)


def post(mid: str, uid: str, following: bool, is_ad: bool = False) -> Post:
    return Post(mid=mid, author=user(uid, following), text="", is_ad=is_ad)


def make_policy(tmp_path, added=(), removed=()) -> WhitelistPolicy:
    store = WhitelistStore(tmp_path / "whitelist.json")
    for uid in added:
        store.add(WhitelistEntry(uid=uid, name=f"u{uid}"))
    for uid in removed:
        store.hide(WhitelistEntry(uid=uid, name=f"u{uid}"))
    return WhitelistPolicy(store)


def test_unfollowed_root_is_hidden(tmp_path):
    policy = make_policy(tmp_path)
    assert is_visible(root("1", following=False), policy) is False
    kept = filter_roots([root("1", False), root("2", True)], policy)
    assert [c.cid for c in kept] == ["2"]


def test_added_user_is_visible_even_if_not_followed(tmp_path):
    policy = make_policy(tmp_path, added={"x"})
    assert is_visible(root("x", following=False), policy) is True


def test_removed_user_is_hidden_even_if_followed(tmp_path):
    policy = make_policy(tmp_path, removed={"x"})
    assert is_visible(root("x", following=True), policy) is False


def test_user_without_uid_is_hidden(tmp_path):
    policy = make_policy(tmp_path)
    anonymous = Comment(cid="1", author=User(uid="", following=True), text="")
    assert is_visible(anonymous, policy) is False


def test_reply_requires_both_sides_whitelisted(tmp_path):
    policy = make_policy(tmp_path, added={"x", "y"})
    comments = [
        reply("10", True, True),      # 双方关注 -> 可见
        reply("11", True, False),     # 目标不在白名单 -> 隐藏
        reply("12", False, True),     # 作者不在白名单 -> 隐藏
        Comment(cid="13", author=user("x", False), text="", target=user("y", False)),
        Comment(cid="14", author=user("x", False), text="", target=user("t", False)),
    ]
    assert [c.cid for c in visible_replies(comments, policy)] == ["10", "13"]


def test_reply_without_target_visible_if_author_allowed(tmp_path):
    policy = make_policy(tmp_path)
    assert [c.cid for c in visible_replies([reply("10", True, None)], policy)] == ["10"]


def test_removed_reply_target_hides_reply(tmp_path):
    policy = make_policy(tmp_path, removed={"t"})
    assert visible_replies([reply("10", True, True, target_uid="t")], policy) == []


def test_promoted_flag_set_for_orphans(tmp_path):
    policy = make_policy(tmp_path)
    kept = visible_replies([reply("10", True, True), reply("11", True, False)],
                           policy, promoted=True)
    assert len(kept) == 1
    assert kept[0].cid == "10" and kept[0].promoted is True


def test_visible_posts_keep_added_and_drop_removed(tmp_path):
    policy = make_policy(tmp_path, added={"x"}, removed={"a"})
    items = visible_posts([
        post("1", "a", True),          # 已隐藏 -> 丢弃
        post("2", "b", False),         # 路人 -> 丢弃
        post("3", "x", False),         # 手动添加 -> 保留
        post("4", "c", True, is_ad=True),  # 广告 -> 丢弃
        post("5", "c", True),          # 关注 -> 保留
    ], policy)
    assert [p.mid for p in items] == ["3", "5"]


def test_promoted_returns_copies_without_mutating_inputs(tmp_path):
    policy = make_policy(tmp_path)
    original = reply("10", True, True)
    kept = visible_replies([original], policy, promoted=True)
    assert original.promoted is False
    assert kept[0] is not original
    assert kept[0].promoted is True


def test_plain_visible_replies_return_originals(tmp_path):
    policy = make_policy(tmp_path)
    original = reply("10", True, True)
    assert visible_replies([original], policy)[0] is original
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_filter_engine.py -q`
Expected: ImportError / TypeError（签名为旧的）。

- [ ] **Step 3: 全量重写 `app/filter_engine.py`**

```python
"""过滤引擎：输入原始模型，输出"只包含白名单成员"的视图。

生效白名单 = （关注 ∪ 手动添加） − 手动移除（白名单存储见 whitelist.py）。

规则：
- R2 一级评论/帖子：作者必须在白名单
- R4 回复：回复者与被回复者都必须在白名单
- 广告/推荐：isAd 丢弃；作者不在白名单也丢弃
"""

from dataclasses import dataclass, replace

from .models import Comment, Post, User
from .whitelist import WhitelistStore


@dataclass(frozen=True)
class WhitelistPolicy:
    store: WhitelistStore

    def allows(self, user: User | None) -> bool:
        if user is None or not user.uid:
            return False
        if self.store.is_removed(user.uid):
            return False
        if user.following:
            return True
        return self.store.is_added(user.uid)


def is_visible(comment: Comment, policy: WhitelistPolicy) -> bool:
    """仅适用于 Comment。target 为 None（一级评论）时只检查作者。"""
    if not policy.allows(comment.author):
        return False
    if comment.target is not None and not policy.allows(comment.target):
        return False
    return True


def filter_roots(roots: list[Comment], policy: WhitelistPolicy) -> list[Comment]:
    return [root for root in roots if is_visible(root, policy)]


def visible_replies(replies: list[Comment], policy: WhitelistPolicy,
                    promoted: bool = False) -> list[Comment]:
    """返回可见回复。promoted=True 时返回标记了"上下文已隐藏"的副本（不修改原对象）。"""
    kept = [reply for reply in replies if is_visible(reply, policy)]
    if promoted:
        return [replace(reply, promoted=True) for reply in kept]
    return kept


def visible_posts(posts: list[Post], policy: WhitelistPolicy) -> list[Post]:
    return [post for post in posts if policy.allows(post.author) and not post.is_ad]
```

- [ ] **Step 4: 测试通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_filter_engine.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```powershell
git add app/filter_engine.py tests/test_filter_engine.py
git commit -m "refactor: replace follow-based visibility with whitelist policy"
```

---

### Task 4: 客户端新增 fetch_following / fetch_user / fetch_user_timeline

**Files:**
- Modify: `app/weibo_client.py`
- Test: `tests/test_client.py`（追加 4 个用例）

- [ ] **Step 1: 追加失败测试到 `tests/test_client.py`**

```python
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
```

> 注：若 Task 0 结论是 `feature=1` 才含转发，则把实现与断言里的 `"0"` 改为 `"1"`，并在本步骤同步修改。

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_client.py -q`
Expected: 4 个新用例 FAIL（AttributeError）。

- [ ] **Step 3: 改 `app/weibo_client.py`**

导入行改为：

```python
from .models import Comment, Post, User
```

在 `fetch_replies` 方法后追加：

```python
    def fetch_following(self) -> list[User]:
        def load() -> list[User]:
            users: dict[str, User] = {}
            page = 1
            while page <= 30:
                data = self._get("/ajax/profile/followContent",
                                 {"sortType": "all", "page": page})
                follows = (data.get("data") or {}).get("follows") or {}
                batch = follows.get("users") or []
                for raw in batch:
                    if not isinstance(raw, dict):
                        continue
                    user = parse_user(raw)
                    if user.uid:
                        users.setdefault(user.uid, user)
                next_cursor = str(follows.get("next_cursor") or "0")
                if not batch or next_cursor in ("", "0"):
                    break
                page += 1
            return list(users.values())

        return self._cache.get_or_set("following", load)

    def fetch_user(self, uid: str) -> User | None:
        data = self._get("/ajax/profile/info", {"uid": uid})
        raw = (data.get("data") or {}).get("user")
        return parse_user(raw) if isinstance(raw, dict) else None

    def fetch_user_timeline(self, uid: str, force: bool = False) -> list[Post]:
        def load() -> list[Post]:
            data = self._get("/ajax/statuses/mymblog",
                             {"uid": uid, "page": "1", "feature": "0"})
            raw_list = (data.get("data") or {}).get("list") or []
            return [parse_post(raw) for raw in raw_list if isinstance(raw, dict)]

        key = f"timeline:{uid}"
        if force:
            self._cache.delete(key)
        return self._cache.get_or_set(key, load)
```

- [ ] **Step 4: 测试通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_client.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```powershell
git add app/weibo_client.py tests/test_client.py
git commit -m "feat: add following list, profile and user timeline fetches"
```

---

### Task 5: API 接口与信息流合并

**Files:**
- Modify: `app/main.py`（全量重写，结构不变）
- Test: `tests/test_api.py`（全量重写）

- [ ] **Step 1: 全量重写 `tests/test_api.py`**

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py -q`
Expected: 多处 FAIL（`/api/whitelist` 404、filter 签名不匹配、merge 未实现）。

- [ ] **Step 3: 全量重写 `app/main.py`**

```python
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
    policy = WhitelistPolicy(store)
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
    policy = WhitelistPolicy(get_store())
    post = client.fetch_status(mid)
    roots = client.fetch_root_comments(mid, post.author.uid)
    threads = [comment_view(root) for root in filter_roots(roots, policy)]
    hidden = [root for root in roots if not is_visible(root, policy) and root.total_replies > 0]
    hidden.sort(key=lambda root: root.total_replies, reverse=True)
    orphans: list[dict] = []
    for root in hidden[: client.settings.max_orphan_threads]:
        replies = client.fetch_replies(root.cid, mid, post.author.uid)
        orphans.extend(comment_view(reply)
                       for reply in visible_replies(replies, policy, promoted=True))
    return {"threads": threads, "orphans": orphans}


@app.get("/api/comment/{root_cid}/replies")
def api_replies(root_cid: str, mid: str):
    client = get_client()
    policy = WhitelistPolicy(get_store())
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
```

- [ ] **Step 4: 测试通过**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py -q`
Expected: 全部 PASS。

- [ ] **Step 5: 全量回归**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS（旧用例已随文件重写更新）。

- [ ] **Step 6: Commit**

```powershell
git add app/main.py tests/test_api.py
git commit -m "feat: whitelist API endpoints and merged feed"
```

---

### Task 6: 前端管理页与白名单标签

**Files:**
- Modify: `web/index.html`（新增按钮与视图容器）
- Modify: `web/style.css`（行、输入框、成功 banner、深色模式）
- Modify: `web/app.js`（全量重写）

- [ ] **Step 1: 改 `web/index.html`**

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
    <button id="whitelist-btn" type="button">白名单</button>
    <button id="refresh-btn" type="button">刷新</button>
  </header>
  <div id="banner" class="banner" hidden></div>
  <main id="feed" class="feed"></main>
  <section id="detail" class="detail" hidden></section>
  <section id="whitelist" class="whitelist" hidden></section>
  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 改 `web/style.css`**

第 12 行选择器改为：

```css
.feed, .detail, .whitelist { max-width: 640px; margin: 0 auto; padding: 8px 8px 48px; }
```

在 `.loading` 规则后追加：

```css
.text-input { width: 100%; padding: 8px 10px; margin: 6px 0; border: 1px solid #d0d3d9;
  border-radius: 6px; font-size: 14px; background: #fff; color: inherit; }
.rows { max-height: 50vh; overflow-y: auto; }
.row { display: flex; align-items: center; gap: 8px; padding: 6px 0;
  border-top: 1px solid #f0f1f3; }
.row .name { flex: 1; }
.row-btn { border: 1px solid #d0d3d9; background: #fff; color: inherit; border-radius: 6px;
  padding: 4px 10px; font-size: 13px; cursor: pointer; }
.hint { color: #86909c; font-size: 13px; padding: 4px 0; }
.banner.ok { background: #e8f5e9; color: #1b5e20; }
```

深色模式块内追加：

```css
  .text-input, .row-btn { background: #232324; border-color: #3a3a3c; }
  .row { border-color: #2e2e30; }
  .banner.ok { background: #1e3a24; color: #7ee2a8; }
```

- [ ] **Step 3: 全量重写 `web/app.js`**

```javascript
const state = { mid: null, view: "feed" };

const TITLES = { feed: "纯净微博", detail: "帖子详情", whitelist: "白名单管理" };

const $ = (selector) => document.querySelector(selector);

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `请求失败（HTTP ${resp.status}）`);
  }
  return resp.json();
}

function post(path, payload) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showBanner(message, ok = false) {
  const banner = $("#banner");
  banner.textContent = message;
  banner.hidden = false;
  banner.classList.toggle("ok", ok);
}

function hideBanner() { $("#banner").hidden = true; }

function avatarImg(url) {
  const avatar = el("img", "avatar");
  avatar.src = url || "";
  avatar.alt = "";
  return avatar;
}

function userHead(user, manual = false) {
  const head = el("div", "head");
  head.append(avatarImg(user.avatar), el("span", "name", user.name));
  if (manual) head.append(el("span", "tag", "白名单"));
  return head;
}

function postCard(post, onClick) {
  const card = el("article", "card");
  card.append(userHead(post.author, post.manual));
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
  head.append(avatarImg(comment.author.avatar), el("span", "name", comment.author.name));
  if (comment.target) head.append(el("span", "target", `回复 @${comment.target.name}`));
  if (comment.promoted) head.append(el("span", "tag", "上下文已隐藏"));
  box.append(head);
  box.append(el("div", "text", comment.text));
  return box;
}

async function loadFeed(force = false) {
  hideBanner();
  const feed = $("#feed");
  feed.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api(force ? "/api/feed?force=1" : "/api/feed");
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
  $("#whitelist").hidden = view !== "whitelist";
  $("#back-btn").hidden = view === "feed";
  $("#refresh-btn").hidden = view !== "feed";
  $("#whitelist-btn").hidden = view !== "feed";
  $("#title").textContent = TITLES[view] || "纯净微博";
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
  section.append(el("h2", null, "评论（只显示白名单内的人）"));
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
    section.append(el("h2", null, "其他讨论中白名单成员的回复"));
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

function whitelistRow(user, actionLabel, action) {
  const row = el("div", "row");
  row.append(avatarImg(user.avatar), el("span", "name", user.name));
  if (actionLabel) {
    const button = el("button", "row-btn", actionLabel);
    button.type = "button";
    button.addEventListener("click", () => action(button));
    row.append(button);
  }
  return row;
}

function section(title) {
  const box = el("section", "card");
  box.append(el("h2", null, title));
  return box;
}

async function whitelistAction(button, path, payload, okMessage) {
  button.disabled = true;
  try {
    await post(path, payload);
    showBanner(okMessage, true);
    await loadWhitelist();
  } catch (error) {
    button.disabled = false;
    showBanner(error.message);
  }
}

function renderWhitelist(data) {
  const page = $("#whitelist");
  page.innerHTML = "";

  const addSection = section("添加白名单");
  const input = el("input", "text-input");
  input.placeholder = "粘贴主页链接或 UID";
  const addButton = el("button", "row-btn", "添加");
  addButton.type = "button";
  const submit = async () => {
    const value = input.value.trim();
    if (!value) {
      showBanner("请输入主页链接或 UID");
      return;
    }
    addButton.disabled = true;
    try {
      const result = await post("/api/whitelist/add", { input: value });
      showBanner(result.following ? "已添加（TA 已在你的关注中）" : `已添加 ${result.name}`, true);
      input.value = "";
      await loadWhitelist();
    } catch (error) {
      addButton.disabled = false;
      showBanner(error.message);
    }
  };
  addButton.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") submit(); });
  addSection.append(input, addButton);
  page.append(addSection);

  const addedSection = section("手动添加");
  if (!data.added.length) addedSection.append(el("div", "hint", "暂无手动添加的人"));
  for (const entry of data.added) {
    addedSection.append(whitelistRow(entry, "移除", (button) =>
      whitelistAction(button, "/api/whitelist/remove", { uid: entry.uid }, "已移除")));
  }
  page.append(addedSection);

  const followingSection = section("关注中");
  const visible = data.following.filter((user) => !user.hidden);
  if (!visible.length) {
    followingSection.append(el("div", "hint", "暂无"));
  } else {
    const filter = el("input", "text-input");
    filter.placeholder = "筛选昵称或 UID";
    const rows = el("div", "rows");
    const renderRows = () => {
      rows.innerHTML = "";
      const keyword = filter.value.trim().toLowerCase();
      const matched = visible.filter((user) =>
        !keyword || user.name.toLowerCase().includes(keyword) || user.uid.includes(keyword));
      if (!matched.length) rows.append(el("div", "hint", "没有匹配的人"));
      for (const user of matched) {
        rows.append(whitelistRow(user, "隐藏", (button) =>
          whitelistAction(button, "/api/whitelist/remove", { uid: user.uid }, "已隐藏")));
      }
    };
    filter.addEventListener("input", renderRows);
    renderRows();
    followingSection.append(filter, rows);
  }
  page.append(followingSection);

  const removedSection = section("已隐藏");
  if (!data.removed.length) removedSection.append(el("div", "hint", "暂无已隐藏的人"));
  for (const entry of data.removed) {
    removedSection.append(whitelistRow(entry, "恢复", (button) =>
      whitelistAction(button, "/api/whitelist/restore", { uid: entry.uid }, "已恢复")));
  }
  page.append(removedSection);
}

async function loadWhitelist() {
  const page = $("#whitelist");
  page.innerHTML = '<div class="loading">加载中…（首次获取关注列表约需几秒）</div>';
  try {
    renderWhitelist(await api("/api/whitelist"));
  } catch (error) {
    page.innerHTML = "";
    showBanner(error.message);
  }
}

$("#refresh-btn").addEventListener("click", () => loadFeed(true));
$("#back-btn").addEventListener("click", () => setView("feed"));
$("#whitelist-btn").addEventListener("click", () => { setView("whitelist"); loadWhitelist(); });
loadFeed();
```

- [ ] **Step 4: 静态语法检查（无构建工具，用 node 若可用；否则跳过）**

Run: `node --check web/app.js`（若 node 不存在则记录"跳过"）
Expected: 无输出（语法通过）。

- [ ] **Step 5: Commit**

```powershell
git add web/index.html web/style.css web/app.js
git commit -m "feat: whitelist management view and manual tag"
```

---

### Task 7: 文档更新

**Files:**
- Modify: `README.md`（规则表、白名单、运行说明）
- Modify: `docs/technical-design.md`（§4 开头加变更说明）

- [ ] **Step 1: 改 `README.md`**

1）第 11~17 行规则表三处替换：

```markdown
| R1 | 首页信息流只显示白名单成员（= 关注 ∪ 手动添加 − 手动移除）**发布或转发**的帖子 | 广告、推荐、热搜、"TA 赞过"卡片全部隐藏 |
| R2 | 帖子评论区只显示**白名单成员**发表的一级评论 | 未在白名单的评论直接不返回 |
| R4 | 楼中楼回复：**回复者与被回复者都在白名单**才显示 | 例：A 回复 B、C；你关注 A、B。只显示 A→B 的回复，A→C 隐藏 |
```

2）第 105 行的"6.5 Demo 运行说明"小节标题后补充一段：

```markdown
白名单（v0.2 新增）：

- 默认白名单 = 你的关注；无需同步，关注变化自动生效。
- 顶栏"白名单"进入管理页：粘贴主页链接/UID 添加未关注的人（其原创帖会并入信息流）；对关注中的人点"隐藏"可移除；"已隐藏"里可恢复。
- 数据只存在本地 `whitelist.json`（已 gitignore），可随时删除重置。
```

3）第 116 行 Demo 已知限制追加："手动添加的人越多，刷新越慢（每人一次抓取，缓存 10 分钟）"。

- [ ] **Step 2: 改 `docs/technical-design.md`**

在 `## 4. 过滤引擎（核心）` 标题下、"```python" 代码块前插入：

```markdown
> **v0.2+ 变更**：R2/R4 的判定依据已从"关注集合"升级为"白名单"（生效白名单 = 关注 ∪ 手动添加 − 手动移除），
> 关注仍是默认基底；设计与存储见 `superpowers/specs/2026-09-13-whitelist-design.md`。
> 下文示例中的 `following` 集合可视为白名单谓词的简化表达。
```

- [ ] **Step 3: Commit**

```powershell
git add README.md docs/technical-design.md
git commit -m "docs: document whitelist feature and run guide"
```

---

### Task 8: 浏览器验收、全量回归与合并

**Files:** 无（验证 + git 操作）

- [ ] **Step 1: 全量测试**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: 全部 PASS（预计 60+）。

- [ ] **Step 2: 启动真实服务并浏览器验收**

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8018
```

用 `agent-browser` 验收（每次操作后 `screenshot` 留档到 `%TEMP%\opencode\`）：

1. 打开 `http://127.0.0.1:8018/`：关注流正常，图片正常（回归）。
2. 点"白名单"：出现"添加白名单 / 手动添加 / 关注中 / 已隐藏"四块；关注中能渲染（数量与账号关注数一致，允许平台过滤差几人）；筛选框输入关键词能过滤。
3. 添加：把 Task 0 验证用过的未关注 uid 粘进输入框 → 提示"已添加 xxx" → 出现在"手动添加"；返回信息流刷新 → 若 TA 有原创帖，卡片出现且名字旁有"白名单"标签。
4. 移除：在"手动添加"点"移除" → 条目消失，信息流恢复。
5. 隐藏/恢复：在"关注中"对任意一人点"隐藏" → 出现在"已隐藏"；信息流刷新后其帖子消失；点"恢复" → 帖子回来。
6. 关闭浏览器与服务进程（`agent-browser close`；`Stop-Process` 清理 uvicorn 及其子进程）。

Expected: 全部通过；任一失败则修复后重跑，不得带病合并。

- [ ] **Step 3: 合并到 master**

```powershell
git switch master
git merge feature/whitelist
.venv\Scripts\python.exe -m pytest -q
git branch -d feature/whitelist
git tag -a demo-v0.2.0 -m "weibo-clean demo v0.2.0: whitelist visibility"
git log --oneline -5
git status --short
```

Expected: fast-forward 合并；测试全绿；工作区干净；tag 建立。

- [ ] **Step 4: 回报用户**

总结：语义变化、新增接口、UI 入口、测试与浏览器验收结果、已知限制（添加者多时刷新慢；mymblog 端点行为来自 M0 实测）。

---

## 自查清单（写计划后核对）

- 设计文档 §3 谓词 → Task 3；§4 存储 → Task 1；§5 关注列表 → Task 4/5；§6 时间线 → Task 4；§7 合并/created_ts → Task 2/5；§8 API → Task 5；§9 UI → Task 6；§11 测试 → Task 1~5；§12 M0 → Task 0；§13 文档 → Task 7。
- 类型一致性：`WhitelistEntry` 字段（uid/name/avatar/at）、`WhitelistPolicy(store)`、`fetch_user_timeline(uid, force)`、`fetch_following()`、`fetch_user(uid)` 在各 Task 中签名一致。
- 无 "TBD/待补" 占位；Task 0 的未知端点采用"测什么、怎么记录、失败备选"的完整验证步骤。

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

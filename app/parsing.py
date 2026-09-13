from datetime import datetime
from typing import Any

from .models import Comment, Post, User


def _s(value: Any) -> str:
    return "" if value is None else str(value)


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
        created_ts=parse_created_ts(raw.get("created_at")),
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

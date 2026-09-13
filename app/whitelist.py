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

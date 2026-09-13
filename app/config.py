import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    cookie_file: Path
    whitelist_file: Path = Path("whitelist.json")
    request_min_delay: float = 1.0
    request_max_delay: float = 2.5
    request_timeout: float = 20.0
    cache_ttl_seconds: float = 600.0
    following_cache_ttl: float = 1800.0
    max_orphan_threads: int = 3
    max_comment_pages: int = 3


def load_settings() -> Settings:
    return Settings(
        cookie_file=Path(os.environ.get("WEIBO_COOKIE_FILE", "cookie.txt")),
        whitelist_file=Path(os.environ.get("WEIBO_WHITELIST_FILE", "whitelist.json")),
        request_min_delay=float(os.environ.get("WEIBO_MIN_DELAY", "1.0")),
        request_max_delay=float(os.environ.get("WEIBO_MAX_DELAY", "2.5")),
    )


def load_cookie(settings: Settings) -> str:
    return settings.cookie_file.read_text(encoding="utf-8-sig").strip()

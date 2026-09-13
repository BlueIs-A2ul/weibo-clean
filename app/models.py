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
    created_ts: float = 0.0
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

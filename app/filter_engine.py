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
    following_uids: frozenset[str] | None = None
    self_uid: str | None = None

    def allows(self, user: User | None) -> bool:
        if user is None or not user.uid:
            return False
        uid = user.uid
        if self.self_uid and uid == self.self_uid:
            return True
        if self.store.is_removed(uid):
            return False
        if user.following:
            return True
        if self.store.is_added(uid):
            return True
        return self.following_uids is not None and uid in self.following_uids


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

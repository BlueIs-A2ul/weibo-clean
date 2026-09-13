"""过滤引擎：输入原始模型，输出"只包含我关注的人"的视图。

规则:
- R2 一级评论/帖子：作者必须被关注
- R4 回复：回复者与被回复者都必须被关注
- 广告/推荐：isAd 或作者未被关注则丢弃
"""

from dataclasses import replace

from .models import Comment, Post


def is_visible(node: Comment) -> bool:
    if not node.author.following:
        return False
    if node.target is not None and not node.target.following:
        return False
    return True


def filter_roots(roots: list[Comment]) -> list[Comment]:
    return [root for root in roots if is_visible(root)]


def visible_replies(replies: list[Comment], promoted: bool = False) -> list[Comment]:
    """返回可见回复。promoted=True 时返回标记了"上下文已隐藏"的副本（不修改原对象）。"""
    kept = [reply for reply in replies if is_visible(reply)]
    if promoted:
        return [replace(reply, promoted=True) for reply in kept]
    return kept


def visible_posts(posts: list[Post]) -> list[Post]:
    return [post for post in posts if post.author.following and not post.is_ad]

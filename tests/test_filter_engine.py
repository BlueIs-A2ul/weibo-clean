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
    anonymous = Comment(cid="1", author=user("", True), text="")
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

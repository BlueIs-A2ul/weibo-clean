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

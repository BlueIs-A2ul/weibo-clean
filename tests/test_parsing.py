from app.parsing import parse_post, parse_reply, parse_root_comment, parse_user


def test_parse_user_reads_following_flag():
    user = parse_user(
        {"idstr": "123", "screen_name": "某人", "profile_image_url": "http://img/x.jpg",
         "following": True}
    )
    assert (user.uid, user.screen_name, user.avatar, user.following) == (
        "123", "某人", "http://img/x.jpg", True)


def test_parse_post_with_retweet():
    raw = {
        "mid": "100",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "转发理由",
        "isAd": False,
        "pic_ids": [],
        "reposts_count": 1,
        "comments_count": 2,
        "attitudes_count": 3,
        "retweeted_status": {
            "mid": "99",
            "user": {"idstr": "2", "screen_name": "B", "following": False},
            "text_raw": "原博",
            "pic_ids": [],
        },
    }
    post = parse_post(raw)
    assert post.mid == "100"
    assert post.author.following is True
    assert post.reposts_count == 1 and post.comments_count == 2 and post.attitudes_count == 3
    assert post.retweeted is not None and post.retweeted.mid == "99"
    assert post.retweeted.author.following is False


def test_parse_post_pics_use_large_url():
    raw = {
        "mid": "100",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "带图",
        "pic_ids": ["p1"],
        "pic_infos": {"p1": {"large": {"url": "http://img/large.jpg"},
                             "bmiddle": {"url": "http://img/mid.jpg"}}},
    }
    post = parse_post(raw)
    assert post.pics == ["http://img/large.jpg"]


def test_parse_root_comment_has_no_target():
    raw = {"id": "555", "user": {"idstr": "1", "screen_name": "A", "following": True},
           "text_raw": "一级评论", "total_number": 3, "like_counts": 4}
    comment = parse_root_comment(raw)
    assert comment.cid == "555"
    assert comment.target is None
    assert comment.total_replies == 3 and comment.like_count == 4


def test_parse_reply_reads_target_user():
    raw = {
        "id": "666",
        "rootid": "555",
        "user": {"idstr": "1", "screen_name": "A", "following": True},
        "text_raw": "回复内容",
        "reply_comment": {"user": {"idstr": "2", "screen_name": "B", "following": False}},
    }
    reply = parse_reply(raw)
    assert reply.cid == "666" and reply.root_cid == "555"
    assert reply.target is not None
    assert reply.target.uid == "2" and reply.target.following is False

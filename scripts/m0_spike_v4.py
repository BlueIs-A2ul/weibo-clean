"""M0 spike v4: 评论链 + 关系交叉验证（weibo.com，只读）。

用法: python scripts/m0_spike_v4.py --cookie fixtures/cookie.txt --out fixtures/live \
      --mid 5000000000000002 --author 6666666666
"""

import argparse
import json
import re
from pathlib import Path

from m0_spike_v3 import (W, Probe, find_comment_with_replies, load_cookie, user_ids)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", default=str(Path(__file__).resolve().parents[1] / "cookie.txt"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "fixtures" / "live"))
    ap.add_argument("--mid", default="5000000000000002")
    ap.add_argument("--author", default="6666666666")
    args = ap.parse_args()
    p = Probe(load_cookie(args.cookie), Path(args.out))
    uid = p.get_home_uid()
    print(f"self_uid={uid}", flush=True)
    out = Path(args.out)

    print("== allGroups（关注流分组）==", flush=True)
    ag = p.get("w_allGroups_fresh", f"{W}/ajax/feed/allGroups", f"{W}/", params={})
    if isinstance(ag, dict):
        groups = ag.get("groups")
        if groups is None and isinstance(ag.get("data"), dict):
            groups = ag["data"].get("groups")
        print("allGroups keys:", list(ag.keys()), flush=True)
        if isinstance(groups, list):
            for g in groups[:10]:
                if isinstance(g, dict):
                    print("   group:", {k: g.get(k) for k in ("id", "name", "title", "list_id", "gid", "type") if k in g}, flush=True)

    print("== V3 一级评论（已知有评论的帖子）==", flush=True)
    c0 = p.get("w_comments_l0_known", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{args.mid}",
               params={"is_reload": "1", "id": args.mid, "is_show_bulletin": "3", "is_mix": "0",
                       "count": "20", "type": "feed", "uid": args.author, "fetch_level": "0",
                       "locale": "zh-CN"})
    cid = find_comment_with_replies(c0) if c0 else None
    print(f"comment_with_replies={cid}", flush=True)

    if cid:
        print("== V4 楼中楼 ==", flush=True)
        p.get("w_comments_l1_known", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{args.mid}",
              params={"is_reload": "1", "id": cid, "is_show_bulletin": "3", "is_mix": "0",
                      "count": "20", "type": "feed", "uid": args.author, "fetch_level": "1",
                      "locale": "zh-CN"})

    # 关注集合（followContent 全部分页的 follows.users）
    follow_set = set()
    for f in sorted(out.glob("w_followcontent_p*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        data = d.get("data") or {}
        users = (data.get("follows") or {}).get("users") or []
        follow_set.update(user_ids({"users": users}))
    follow_samples = [u for u in sorted(follow_set)][:2]
    print(f"follow_set={len(follow_set)} samples={follow_samples}", flush=True)

    commenter_pairs = []
    if c0:
        for item in (c0.get("data") or []):
            u = (item or {}).get("user") or {}
            uu = u.get("idstr") or u.get("id")
            if uu:
                commenter_pairs.append((str(uu), u.get("following")))
    commenter_samples = [u for u, _ in commenter_pairs[:2]]

    print("== V5/V7 关系交叉验证 ==", flush=True)
    for label, samples in (("followed", follow_samples), ("commenters", commenter_samples)):
        for su in samples:
            d = p.get(f"w_profile_{label}_{su}", f"{W}/ajax/profile/info", f"{W}/u/{su}",
                      params={"uid": su})
            u = ((d or {}).get("data") or {}).get("user") if isinstance(d, dict) else {}
            print(f"    {label} uid={su} profile_following={(u or {}).get('following')} "
                  f"in_follow_set={su in follow_set}", flush=True)

    if commenter_pairs:
        cross = [(u, rel, u in follow_set) for u, rel in commenter_pairs]
        print("commenter_cross (uid, comment_following_flag, in_follow_set):", cross[:10], flush=True)

    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

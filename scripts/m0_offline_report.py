"""离线汇总 live/ 与旧 fixtures 的证据，不联网。"""

import json
from pathlib import Path

LIVE = Path(r"D:\desktop\weibo-clean\fixtures\live")
FIX = Path(r"D:\desktop\weibo-clean\fixtures")


def load(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ids_of(users):
    out = []
    for u in users or []:
        i = u.get("idstr") or u.get("id")
        if i:
            out.append(str(i))
    return out


print("=== followContent 分页（只统计 data.follows.users）===")
fc_union = set()
for f in sorted(LIVE.glob("w_followcontent_p*.json")):
    d = load(f)
    if not d:
        continue
    data = d.get("data") or {}
    follows = data.get("follows") or {}
    spec = (data.get("specialAttention") or {}).get("users") or []
    ids = ids_of(follows.get("users"))
    fc_union.update(ids)
    print(f"{f.name}: follows={len(ids)} specialAttention={len(spec)} "
          f"total={follows.get('total_number')} next_cursor={follows.get('next_cursor')}")
print("followContent follows 去重总数:", len(fc_union))

print("\n=== friendships/friends 分页 ===")
fr_union = set()
for f in sorted(LIVE.glob("w_friends_p*.json")):
    d = load(f)
    if not d:
        continue
    users = d.get("users") or []
    fr_union.update(ids_of(users))
    print(f"{f.name}: users={len(users)} total={d.get('total_number')} "
          f"filtered_attentions={d.get('has_filtered_attentions')}")
print("friendships 去重总数:", len(fr_union))

print("\n两接口交集:", len(fc_union & fr_union),
      "followContent独有:", len(fc_union - fr_union),
      "friends独有:", len(fr_union - fc_union))

print("\n=== 新抓的评论响应（为何为空）===")
c = load(LIVE / "w_comments_l0.json")
if c:
    print("keys:", list(c.keys()), "ok:", c.get("ok"), "total_number:", c.get("total_number"),
          "data_len:", len(c.get("data") or []), "tip:", c.get("tip_msg"), "max_id:", c.get("max_id"))

print("\n=== 旧评论样本的用户 following 标记 ===")
for name in ("comments_l0_page1.json", "comments_l1_replies.json"):
    d = load(FIX / name)
    if not d:
        continue
    roots = d.get("data") or []
    n_flags = 0
    true_flags = 0

    def walk(o, depth=0):
        global n_flags, true_flags
        if depth > 14:
            return
        if isinstance(o, dict):
            if isinstance(o.get("following"), bool):
                n_flags += 1
                if o["following"]:
                    true_flags += 1
            for v in o.values():
                walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o:
                walk(v, depth + 1)

    walk(d)
    print(f"{name}: roots={len(roots)} following_flags={n_flags} true={true_flags}")

print("\n=== allGroups（旧 cookie 抓的，看分组结构）===")
ag = load(FIX / "w_allGroups.json")
if ag:
    print("keys:", list(ag.keys()), "ok:", ag.get("ok"))
    data = ag.get("data")
    if isinstance(data, dict):
        print("data_keys:", list(data.keys()))
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                sample = {kk: v[0].get(kk) for kk in ("id", "name", "title", "list_id", "gid")
                          if kk in v[0]}
                print(f"  {k}: {len(v)} items, sample={sample}")
    elif isinstance(data, list):
        print("data list len:", len(data))

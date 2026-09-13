"""结构化分析微博接口响应样本。

只打印结构（键名、类型、小样例），避免输出评论正文等隐私内容。
用法: python scripts/m0_analyze.py fixtures/home_feed_page1.json [...]
"""

import json
import sys
from pathlib import Path

PAGINATION_KEYS = {
    "max_id", "max_id_type", "since_id", "next_cursor", "previous_cursor",
    "total_number", "end_id", "page", "count",
}
RELATION_KEYS = {"following", "follow_me", "followers_count", "follow_count", "followers_count_str"}
AD_HINTS = ("ad", "promot", "recommend", "hot")


def short(v):
    s = str(v)
    return s if len(s) <= 60 else s[:57] + "..."


def find_dicts(obj, predicate, out=None, depth=0, limit=3):
    if out is None:
        out = []
    if depth > 12 or len(out) >= limit:
        return out
    if isinstance(obj, dict):
        if predicate(obj):
            out.append(obj)
        for v in obj.values():
            find_dicts(v, predicate, out, depth + 1, limit)
    elif isinstance(obj, list):
        for v in obj:
            find_dicts(v, predicate, out, depth + 1, limit)
    return out


def find_scalars(obj, keys, out=None, depth=0, limit=6):
    if out is None:
        out = []
    if depth > 12 or len(out) >= limit:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys and not isinstance(v, (dict, list)):
                out.append((k, short(v)))
            find_scalars(v, keys, out, depth + 1, limit)
    elif isinstance(obj, list):
        for v in obj:
            find_scalars(v, keys, out, depth + 1, limit)
    return out


def analyze(path: Path):
    print(f"\n===== {path.name} =====")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        print("top_keys:", list(data.keys()))
        for k in ("ok", "msg", "errno"):
            if k in data:
                print(f"  {k}={short(data[k])}")
        d = data.get("data")
        if isinstance(d, dict):
            print("data_keys:", list(d.keys()))
        elif isinstance(d, list):
            print(f"data=list[{len(d)}]")
    elif isinstance(data, list):
        print(f"top=list[{len(data)}]")

    users = find_dicts(data, lambda x: "screen_name" in x and ("id" in x or "idstr" in x), limit=2)
    if users:
        u = users[0]
        rel = {k: short(v) for k, v in u.items() if k in RELATION_KEYS}
        print("user_keys:", sorted(u.keys()))
        print("user_relation:", rel)

    comments = find_dicts(
        data, lambda x: "text" in x and "user" in x and ("id" in x or "idstr" in x or "id_str" in x), limit=1
    )
    if comments:
        c = comments[0]
        print("comment_keys:", sorted(c.keys()))
        if "reply_comment" in c:
            print("reply_comment_keys:", sorted(c["reply_comment"].keys()) if isinstance(c["reply_comment"], dict) else type(c["reply_comment"]))
        if "reply" in c and isinstance(c["reply"], dict):
            print("reply_keys:", sorted(c["reply"].keys()))

    print("pagination:", find_scalars(data, PAGINATION_KEYS))
    print("relations:", find_scalars(data, {"following", "follow_me"}))

    ads = find_scalars(data, {k for k in {*AD_HINTS} if True})
    hint_fields = []
    if isinstance(data, dict):
        def collect(obj, depth=0, prefix=""):
            if depth > 8:
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if any(h in k.lower() for h in AD_HINTS) and not isinstance(v, (dict, list)):
                        hint_fields.append(f"{prefix}{k}={short(v)}")
                    collect(v, depth + 1, f"{prefix}{k}.")
            elif isinstance(obj, list) and obj:
                collect(obj[0], depth + 1, prefix + "[].")
        collect(data)
    print("ad_like_fields:", hint_fields[:8])


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    for a in args:
        p = Path(a)
        if p.exists():
            try:
                analyze(p)
            except (OSError, json.JSONDecodeError) as exc:
                print(f"{p.name}: ERROR {exc}")
        else:
            print(f"{p.name}: not found")
    return 0


if __name__ == "__main__":
    sys.exit(main())

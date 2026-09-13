"""快速查找: (1) 某条 mid 的作者 uid; (2) 某 uid 在文件中的出现位置。

用法: python scripts/m0_quick.py --mid 5000000000000002 --uid 6666666666 file1.json file2.json
"""

import argparse
import json
from pathlib import Path


def walk_find_mid(obj, mid):
    if isinstance(obj, dict):
        if obj.get("mid") == mid or obj.get("id") == mid or obj.get("idstr") == mid:
            user = obj.get("user") or {}
            uid = user.get("idstr") or user.get("id")
            if uid:
                return str(uid)
        for v in obj.values():
            r = walk_find_mid(v, mid)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = walk_find_mid(v, mid)
            if r:
                return r
    return None


def walk_find_uid(obj, uid, path="", depth=0, found=None):
    if found is None:
        found = []
    if depth > 12 or len(found) >= 5:
        return found
    if isinstance(obj, dict):
        if str(obj.get("idstr") or obj.get("id") or "") == uid:
            keys = [k for k in ("screen_name", "following", "follow_me") if k in obj]
            found.append((path, {k: obj[k] for k in keys}))
        for k, v in obj.items():
            walk_find_uid(v, uid, f"{path}.{k}", depth + 1, found)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:30]):
            walk_find_uid(v, uid, f"{path}[{i}]", depth + 1, found)
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mid")
    ap.add_argument("--uid")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args()
    for f in args.files:
        p = Path(f)
        if not p.exists():
            print(f"{p.name}: not found")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        if args.mid:
            author = walk_find_mid(data, args.mid)
            if author:
                print(f"{p.name}: mid={args.mid} author_uid={author}")
        if args.uid:
            hits = walk_find_uid(data, args.uid)
            for path, info in hits:
                print(f"{p.name}: uid={args.uid} at {path} {info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

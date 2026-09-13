"""检查评论树结构: 根评论 / 内嵌回复 / reply_comment 归属。

用法: python scripts/m0_inspect_comments.py fixtures/comments_l1_replies.json
"""

import json
import sys
from pathlib import Path


def main():
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    roots = data.get("data") if isinstance(data, dict) else None
    if not isinstance(roots, list):
        print("no data[]")
        return 1
    print(f"roots={len(roots)} total_number={data.get('total_number')} max_id={data.get('max_id')}")
    for r in roots[:6]:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        nested = r.get("comments") if isinstance(r.get("comments"), list) else []
        print(f"\n[root] id={rid} total={r.get('total_number')} floor={r.get('floor_number')} "
              f"nested={len(nested)} following={((r.get('user') or {}).get('following'))}")
        for c in nested[:4]:
            if not isinstance(c, dict):
                continue
            rc = c.get("reply_comment")
            rc_uid = None
            if isinstance(rc, dict):
                rc_uid = ((rc.get("user") or {}).get("idstr") or (rc.get("user") or {}).get("id"))
            print(f"  [reply] id={c.get('id')} rootid={c.get('rootid')} total={c.get('total_number')} "
                  f"readtime={c.get('readtimetype')} reply_comment_owner={rc_uid} "
                  f"following={((c.get('user') or {}).get('following'))} "
                  f"max_id={c.get('max_id')}")
            text = c.get("text_raw") or ""
            if "回复@" in text:
                print(f"    text_prefix={text[:40]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""检查 allGroups 分组结构与评论响应细节。"""

import json
from pathlib import Path

LIVE = Path(r"D:\desktop\weibo-clean\fixtures\live")
TARGET = "110011234567890"


def main():
    raw = (LIVE / "w_allGroups_fresh.json").read_text(encoding="utf-8")
    print("list_id_in_file:", TARGET in raw)
    d = json.loads(raw)
    groups = d.get("groups") or []
    print("feed_default:", d.get("feed_default"), "groups:", len(groups))
    for i, g in enumerate(groups[:8]):
        if not isinstance(g, dict):
            continue
        items = g.get("group") or []
        print(f"\n[{i}] title={g.get('title')!r} keys={list(g.keys())} items={len(items)}")
        for it in items[:6]:
            if isinstance(it, dict):
                picked = {k: it.get(k) for k in ("id", "title", "name", "gid", "type", "is_default")
                          if k in it}
                print("    ", picked, "keys=", list(it.keys())[:12])
                if str(it.get("id")) == TARGET:
                    print("     *** TARGET LIST_ID FOUND ***")

    print("\n=== 评论响应细节 ===")
    c = json.loads((LIVE / "w_comments_l0_known.json").read_text(encoding="utf-8"))
    print("top total_number:", c.get("total_number"), "rootComment:", bool(c.get("rootComment")))
    rc = c.get("rootComment")
    if isinstance(rc, dict):
        print("rootComment id:", rc.get("id"), "total:", rc.get("total_number"))
    for i, it in enumerate(c.get("data") or []):
        if not isinstance(it, dict):
            continue
        nested = it.get("comments") if isinstance(it.get("comments"), list) else []
        print(f"data[{i}]: id={it.get('id')} total={it.get('total_number')!r} "
              f"nested={len(nested)} floor={it.get('floor_number')} uid={(it.get('user') or {}).get('idstr')}")
        for j, nc in enumerate(nested[:2]):
            rcf = nc.get("reply_comment") if isinstance(nc, dict) else None
            owner = ((rcf or {}).get("user") or {}).get("idstr") if isinstance(rcf, dict) else None
            print(f"    reply[{j}]: id={nc.get('id')} reply_to={owner} "
                  f"following={((nc.get('user') or {}).get('following'))}")


if __name__ == "__main__":
    main()

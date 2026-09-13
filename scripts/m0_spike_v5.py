"""M0 spike v5: 验证楼中楼展开接口（fetch_level=1）。"""

import argparse
import json
import sys
from pathlib import Path

from m0_spike_v3 import W, Probe, load_cookie

POST_MID = "5000000000000002"
KNOWN_ROOT_CID = "5000000000000001"
KNOWN_ROOT_AUTHOR = "6666666666"


def summarize(name, data, out):
    (out / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if not isinstance(data, dict):
        print(f"{name}: non-dict")
        return
    roots = data.get("data") or []
    rc = data.get("rootComment")
    print(f"{name}: ok={data.get('ok')} data_len={len(roots)} top_total={data.get('total_number')} "
          f"max_id={data.get('max_id')} rootComment={'yes' if isinstance(rc, dict) else 'no'}")
    if isinstance(rc, dict):
        nested = rc.get("comments") if isinstance(rc.get("comments"), list) else []
        print(f"  rootComment id={rc.get('id')} total={rc.get('total_number')} replies={len(nested)}")
        for r in nested[:3]:
            rcf = r.get("reply_comment") if isinstance(r, dict) else None
            owner = ((rcf or {}).get("user") or {}).get("idstr") if isinstance(rcf, dict) else None
            print(f"    reply id={r.get('id')} reply_to={owner} following={((r.get('user') or {}).get('following'))}")
    for i, it in enumerate(roots[:3]):
        if not isinstance(it, dict):
            continue
        nested = it.get("comments") if isinstance(it.get("comments"), list) else []
        print(f"  data[{i}] id={it.get('id')} total={it.get('total_number')} nested={len(nested)}")
        for r in nested[:2]:
            rcf = r.get("reply_comment") if isinstance(r, dict) else None
            owner = ((rcf or {}).get("user") or {}).get("idstr") if isinstance(rcf, dict) else None
            print(f"    reply id={r.get('id')} reply_to={owner} following={((r.get('user') or {}).get('following'))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", default=str(Path(__file__).resolve().parents[1] / "cookie.txt"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "fixtures" / "live"))
    args = ap.parse_args()
    p = Probe(load_cookie(args.cookie), Path(args.out))
    out = Path(args.out)

    print("== fetch_level=1 on post mid ==", flush=True)
    d1 = p.get("w_comments_l1_post", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{POST_MID}",
               params={"is_reload": "1", "id": POST_MID, "is_show_bulletin": "3", "is_mix": "0",
                       "count": "20", "type": "feed", "uid": KNOWN_ROOT_AUTHOR, "fetch_level": "1",
                       "locale": "zh-CN"})
    if d1:
        summarize("w_comments_l1_post", d1, out)

    print("== fetch_level=1 on known root comment ==", flush=True)
    d2 = p.get("w_comments_l1_root", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{POST_MID}",
               params={"is_reload": "1", "id": KNOWN_ROOT_CID, "is_show_bulletin": "3", "is_mix": "0",
                       "count": "20", "type": "feed", "uid": KNOWN_ROOT_AUTHOR, "fetch_level": "1",
                       "locale": "zh-CN"})
    if d2:
        summarize("w_comments_l1_root", d2, out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""M0 spike v2: 使用新 cookie 做只读验证。

覆盖:
- V1 关注流候选接口 (feed/following, feed/friendstimeline)
- V2 帖子详情 (statuses/show)
- V3 评论一级 (statuses/buildComments, fetch_level=0)
- V4 楼中楼 (fetch_level=1 / 内嵌 comments)
- V5 关系标记 following 语义与准确率
- V6 关注列表枚举上限 (profile/followContent 游标分页 + friendships/friends 对照)
- V7 单条关系查询兜底 (profile/info)

只发 GET 请求; 不打印 Cookie。
用法:
    python scripts/m0_spike_v2.py --cookie fixtures/cookie.txt --out fixtures/live
"""

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
W = "https://weibo.com"
M = "https://m.weibo.cn"
NUM_RE = re.compile(r"^\d{6,25}$")


def load_cookie(path: str) -> str:
    return Path(path).read_text(encoding="utf-8-sig").strip()


class Probe:
    def __init__(self, cookie: str, outdir: Path):
        self.cookie = cookie
        self.outdir = outdir
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.summary = []

    def get(self, name, url, referer, params=None, sleep=True):
        if sleep:
            time.sleep(random.uniform(2.0, 4.0))
        headers = {
            "Cookie": self.cookie,
            "User-Agent": UA,
            "Referer": referer,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        }
        record = {"name": name, "url": url, "params": params}
        result = None
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=25)
            record["status"] = resp.status_code
            try:
                data = resp.json()
                (self.outdir / f"{name}.json").write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8"
                )
                record["saved"] = f"{name}.json"
                if isinstance(data, dict):
                    record["ok"] = data.get("ok")
                    record["top_keys"] = list(data.keys())[:12]
                    d = data.get("data")
                    if isinstance(d, dict):
                        record["data_keys"] = list(d.keys())[:15]
                    elif isinstance(d, list):
                        record["data_len"] = len(d)
                result = data
            except ValueError:
                (self.outdir / f"{name}.txt").write_text(resp.text[:3000], encoding="utf-8")
                record["saved"] = f"{name}.txt"
                record["text_head"] = resp.text[:100].replace("\n", " ")
        except requests.RequestException as exc:
            record["error"] = str(exc)
        self.summary.append(record)
        print(json.dumps({k: record.get(k) for k in ("name", "status", "ok", "error", "saved", "data_len")},
                         ensure_ascii=False), flush=True)
        return result

    def save(self):
        (self.outdir / "_m0_summary_v2.json").write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def find_first(obj, keys, depth=0):
    if depth > 14:
        return None
    if isinstance(obj, dict):
        for k in keys:
            v = obj.get(k)
            if isinstance(v, str) and NUM_RE.match(v):
                return v
        for v in obj.values():
            r = find_first(v, keys, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_first(v, keys, depth + 1)
            if r:
                return r
    return None


def find_comment_with_replies(obj, depth=0):
    if depth > 14:
        return None
    if isinstance(obj, dict):
        cid, total = obj.get("id"), obj.get("total_number")
        if isinstance(total, int) and total > 0 and isinstance(cid, str) and NUM_RE.match(cid):
            return cid
        for v in obj.values():
            r = find_comment_with_replies(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_comment_with_replies(v, depth + 1)
            if r:
                return r
    return None


def user_ids(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 14 or len(out) >= 500:
        return out
    if isinstance(obj, dict):
        uid = obj.get("idstr") or obj.get("id_str")
        if uid and obj.get("screen_name") and NUM_RE.match(str(uid)):
            out.append(str(uid))
        for v in obj.values():
            user_ids(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            user_ids(v, out, depth + 1)
    return out


def relation_pairs(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 14:
        return out
    if isinstance(obj, dict):
        uid = obj.get("idstr") or obj.get("id_str") or obj.get("id")
        if isinstance(obj.get("following"), bool) and uid:
            out.append((str(uid), bool(obj["following"])))
        for v in obj.values():
            relation_pairs(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            relation_pairs(v, out, depth + 1)
    return out


def reply_comment_owners(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 16 or len(out) >= 50:
        return out
    if isinstance(obj, dict):
        rc = obj.get("reply_comment")
        if isinstance(rc, dict):
            ru = rc.get("user") or {}
            owner = ru.get("idstr") or ru.get("id")
            cid = obj.get("id")
            out.append((str(cid), str(owner) if owner else None, bool(rc.get("text"))))
        for v in obj.values():
            reply_comment_owners(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            reply_comment_owners(v, out, depth + 1)
    return out


def count_key(obj, name, depth=0):
    if depth > 14:
        return 0
    n = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == name:
                n += 1
            n += count_key(v, name, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            n += count_key(v, name, depth + 1)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookie", default=r"D:\desktop\weibo-clean\fixtures\cookie.txt")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "fixtures" / "live"))
    args = ap.parse_args()
    cookie = load_cookie(args.cookie)
    p = Probe(cookie, Path(args.out))

    cfg = p.get("m_config", f"{M}/api/config", f"{M}/", sleep=False)
    uid = None
    if isinstance(cfg, dict):
        uid = str((cfg.get("data") or {}).get("uid") or "") or None
    print(f"self_uid={uid}", flush=True)
    if not uid:
        print("FATAL: cookie 未登录，请更新 cookie", flush=True)
        p.save()
        return 1

    # V6a: 关注列表 - profile/followContent 游标分页
    url_fc = f"{W}/ajax/profile/followContent"
    fc1 = p.get("w_followcontent_p1", url_fc, f"{W}/u/{uid}", params={"sortType": "all"})
    set1 = user_ids(fc1) if fc1 else []
    print(f"followcontent_p1_users={len(set1)}", flush=True)

    paging_ok = None
    for name, extra in (
        ("w_followcontent_p2_page", {"sortType": "all", "page": "2"}),
        ("w_followcontent_p2_sinceid", {"sortType": "all", "since_id": "50"}),
        ("w_followcontent_p2_cursor", {"sortType": "all", "cursor": "50"}),
        ("w_followcontent_p2_maxid", {"sortType": "all", "max_id": "50"}),
    ):
        r = p.get(name, url_fc, f"{W}/u/{uid}", params=extra)
        ids = user_ids(r) if r else []
        if ids and ids != set1:
            paging_ok = name
            print(f"FOLLOWCONTENT_PAGING_OK={name} users={len(ids)}", flush=True)
            break
        if r is not None and not ids:
            print(f"{name}: empty", flush=True)

    # V6b: 旧接口对照 friendships/friends
    for page in ("1", "11", "21"):
        p.get(f"w_friends_p{page}", f"{W}/ajax/friendships/friends", f"{W}/u/{uid}",
              params={"uid": uid, "page": page})

    # V1: 关注流候选
    p.get("w_feed_following", f"{W}/ajax/feed/following", f"{W}/",
          params={"list_id": "1000", "refresh": "1", "since_id": "0", "count": "10"})
    p.get("w_feed_friendstimeline", f"{W}/ajax/feed/friendstimeline", f"{W}/",
          params={"list_id": "110012345678901", "refresh": "4", "since_id": "0",
                  "count": "25", "fid": "110012345678901"})

    # 选取测试帖子
    mid = None
    for fname in ("w_feed_friendstimeline", "w_feed_following"):
        try:
            data = json.loads((Path(args.out) / f"{fname}.json").read_text(encoding="utf-8"))
            mid = find_first(data, ("mid", "mblogid")) or find_first(data, ("id_str",))
            if mid:
                break
        except (OSError, json.JSONDecodeError):
            continue
    print(f"test_mid={mid}", flush=True)

    if mid:
        # V2
        p.get("w_status_show", f"{W}/ajax/statuses/show", f"{W}/detail/{mid}", params={"id": mid})
        # V3
        c0 = p.get("w_comments_l0", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{mid}",
                   params={"is_reload": "1", "id": mid, "is_show_bulletin": "3", "is_mix": "0",
                           "count": "20", "type": "feed", "uid": uid, "fetch_level": "0",
                           "locale": "zh-CN"})
        cid = find_comment_with_replies(c0) if c0 else None
        print(f"comment_with_replies={cid}", flush=True)
        # V4
        if cid:
            p.get("w_comments_l1", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{mid}",
                  params={"is_reload": "1", "id": cid, "is_show_bulletin": "3", "is_mix": "0",
                          "count": "20", "type": "feed", "uid": uid, "fetch_level": "1",
                          "locale": "zh-CN"})
        p.get("m_hotflow", f"{M}/comments/hotflow", f"{M}/detail/{mid}",
              params={"id": mid, "mid": mid, "max_id_type": "0"})
        # V5/V7: 评论者主页关系
        commenters = user_ids(c0) if c0 else []
        for i, u in enumerate(commenters[:4]):
            p.get(f"w_profile_{i}", f"{W}/ajax/profile/info", f"{W}/u/{u}", params={"uid": u})

    # 汇总
    print("\n== SCAN (live) ==", flush=True)
    report = {}
    for f in sorted(Path(args.out).glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pairs = relation_pairs(data)
        info = {
            "following_true": sum(1 for _, v in pairs if v),
            "following_false": sum(1 for _, v in pairs if not v),
            "reply_comment_key": count_key(data, "reply_comment"),
            "users": len(user_ids(data)),
        }
        report[f.name] = info
        print(f"{f.name}: {info}", flush=True)

    # 关注集合 vs 评论者 following 标记 交叉验证
    try:
        fc1_data = json.loads((Path(args.out) / "w_followcontent_p1.json").read_text(encoding="utf-8"))
        follow_set = set(user_ids(fc1_data))
    except (OSError, json.JSONDecodeError):
        follow_set = set()
    try:
        c0_data = json.loads((Path(args.out) / "w_comments_l0.json").read_text(encoding="utf-8"))
        commenter_pairs = relation_pairs(c0_data)
        cross = [(u, rel, u in follow_set) for u, rel in commenter_pairs]
        print("cross_check (uid, following_flag, in_follow_set_first50):", cross[:10], flush=True)
    except (OSError, json.JSONDecodeError):
        pass
    owners = reply_comment_owners(c0_data) if 'c0_data' in dir() else []
    print("reply_comment_owners_sample:", owners[:5], flush=True)

    (Path(args.out) / "_m0_key_scan_v2.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    p.save()
    print("\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""M0 spike v3 (weibo.com only): 完整只读验证。

流程:
1. 确认登录者 uid (首页 HTML)
2. V6a friendships/friends 分页边界 (页1/11/12/13/14/15/20/21)
3. V6b profile/followContent 游标分页发现 + 全量枚举
4. V1 关注流接口 (friendstimeline / feed/following)
5. V2 帖子详情, V3 一级评论, V4 楼中楼
6. V5/V7 profile/info 关系字段 + 关注集合交叉验证

只发 GET; 不打印 Cookie。
用法: python scripts/m0_spike_v3.py --cookie fixtures/cookie.txt --out fixtures/live
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
NUM_RE = re.compile(r"^\d{6,25}$")


def load_cookie(path):
    return Path(path).read_text(encoding="utf-8-sig").strip()


class Probe:
    def __init__(self, cookie, outdir):
        self.cookie = cookie
        self.outdir = Path(outdir)
        self.outdir.mkdir(parents=True, exist_ok=True)

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
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=25)
            status = resp.status_code
            try:
                data = resp.json()
                (self.outdir / f"{name}.json").write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8")
                ok = data.get("ok") if isinstance(data, dict) else None
            except ValueError:
                data = None
                ok = None
                (self.outdir / f"{name}.txt").write_text(resp.text[:3000], encoding="utf-8")
        except requests.RequestException as exc:
            print(f"  {name}: ERROR {exc}", flush=True)
            return None
        print(f"  {name}: status={status} ok={ok}", flush=True)
        return data

    def get_home_uid(self):
        try:
            r = requests.get(f"{W}/", headers={"Cookie": self.cookie, "User-Agent": UA}, timeout=25)
            m = re.search(r'"uid":(\d{6,20})', r.text)
            return m.group(1) if m else None
        except requests.RequestException:
            return None


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


def find_status_sample(obj, depth=0):
    """找第一个带 mid + user.id 的帖子 dict。"""
    if depth > 14:
        return None
    if isinstance(obj, dict):
        if isinstance(obj.get("mid"), str) and isinstance(obj.get("user"), dict):
            u = obj["user"]
            uid = u.get("idstr") or u.get("id")
            if uid:
                return {"mid": obj["mid"], "author_uid": str(uid),
                        "has_retweeted": "retweeted_status" in obj,
                        "retweeted_mid": (obj.get("retweeted_status") or {}).get("mid")
                        if isinstance(obj.get("retweeted_status"), dict) else None}
        for v in obj.values():
            r = find_status_sample(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_status_sample(v, depth + 1)
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
    if depth > 14 or len(out) >= 2000:
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
    ap.add_argument("--cookie", default=str(Path(__file__).resolve().parents[1] / "cookie.txt"))
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "fixtures" / "live"))
    args = ap.parse_args()
    p = Probe(load_cookie(args.cookie), args.out)

    print("== 0. 登录者 uid ==", flush=True)
    uid = p.get_home_uid()
    print(f"self_uid={uid}", flush=True)
    if not uid:
        print("FATAL: 无法确定登录者 uid")
        return 1

    print("== V6a. friendships/friends 分页边界 ==", flush=True)
    seen_first = {}
    for page in (1, 11, 12, 13, 14, 15, 20, 21):
        d = p.get(f"w_friends_p{page}", f"{W}/ajax/friendships/friends", f"{W}/u/{uid}",
                  params={"uid": uid, "page": str(page)})
        if isinstance(d, dict):
            users = d.get("users") or []
            first = str((users[0] or {}).get("idstr") or "") if users else None
            seen_first[page] = first
            print(f"    page={page} users={len(users)} total={d.get('total_number')} first={first}",
                  flush=True)
    print(f"    first_uid_repeats={seen_first}", flush=True)

    print("== V6b. profile/followContent 游标分页 ==", flush=True)
    url_fc = f"{W}/ajax/profile/followContent"
    fc1 = p.get("w_followcontent_p1", url_fc, f"{W}/u/{uid}", params={"sortType": "all"})
    ids1 = user_ids(fc1) if fc1 else []
    param_used = None
    for name, extra in (
        ("p2_page", {"sortType": "all", "page": "2"}),
        ("p2_since_id", {"sortType": "all", "since_id": "50"}),
        ("p2_cursor", {"sortType": "all", "cursor": "50"}),
        ("p2_max_id", {"sortType": "all", "max_id": "50"}),
        ("p2_page_next", {"sortType": "all", "page": "2", "since_id": "50"}),
    ):
        r = p.get(f"w_followcontent_{name}", url_fc, f"{W}/u/{uid}", params=extra)
        ids = user_ids(r) if r else []
        if ids and ids != ids1:
            param_used = extra
            print(f"    PAGING_OK name={name} extra={extra} users={len(ids)}", flush=True)
            break
    if param_used:
        all_ids = list(ids1)
        page = 3
        while page <= 8:
            extra = dict(param_used)
            key = "page" if "page" in extra else ("since_id" if "since_id" in extra else "cursor")
            extra[key] = str(int(param_used.get(key, "1")) + (page - 2) if key == "page" else 50 * (page - 1))
            r = p.get(f"w_followcontent_p{page}", url_fc, f"{W}/u/{uid}", params=extra)
            ids = user_ids(r) if r else []
            if not ids or set(ids) <= set(all_ids):
                break
            all_ids.extend(ids)
            page += 1
        uniq = list(dict.fromkeys(all_ids))
        print(f"    followcontent_unique_users={len(uniq)}", flush=True)
        (Path(args.out) / "_follow_set.json").write_text(
            json.dumps(uniq, ensure_ascii=False), encoding="utf-8")

    print("== V1. 关注流 ==", flush=True)
    p.get("w_feed_friendstimeline", f"{W}/ajax/feed/friendstimeline", f"{W}/",
          params={"list_id": "110011234567890", "refresh": "4", "since_id": "0",
                  "count": "25", "fid": "110011234567890"})
    p.get("w_feed_following", f"{W}/ajax/feed/following", f"{W}/",
          params={"list_id": "1000", "refresh": "1", "since_id": "0", "count": "10"})

    post = None
    for fname in ("w_feed_friendstimeline", "w_feed_following"):
        fp = Path(args.out) / f"{fname}.json"
        if fp.exists():
            try:
                post = find_status_sample(json.loads(fp.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                post = None
            if post:
                break
    print(f"test_post={post}", flush=True)

    if post:
        mid, author = post["mid"], post["author_uid"]
        print("== V2. 帖子详情 ==", flush=True)
        p.get("w_status_show", f"{W}/ajax/statuses/show", f"{W}/detail/{mid}", params={"id": mid})

        print("== V3. 一级评论 ==", flush=True)
        c0 = p.get("w_comments_l0", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{mid}",
                   params={"is_reload": "1", "id": mid, "is_show_bulletin": "3", "is_mix": "0",
                           "count": "20", "type": "feed", "uid": author, "fetch_level": "0",
                           "locale": "zh-CN"})
        cid = find_comment_with_replies(c0) if c0 else None
        print(f"comment_with_replies={cid}", flush=True)

        print("== V4. 楼中楼 ==", flush=True)
        if cid:
            p.get("w_comments_l1", f"{W}/ajax/statuses/buildComments", f"{W}/detail/{mid}",
                  params={"is_reload": "1", "id": cid, "is_show_bulletin": "3", "is_mix": "0",
                          "count": "20", "type": "feed", "uid": author, "fetch_level": "1",
                          "locale": "zh-CN"})

        print("== V5/V7. 评论者关系 ==", flush=True)
        commenters = []
        if c0:
            commenters = list(dict.fromkeys(user_ids(c0)))
        for i, cu in enumerate(commenters[:4]):
            p.get(f"w_profile_{i}_{cu}", f"{W}/ajax/profile/info", f"{W}/u/{cu}",
                  params={"uid": cu})

    print("== 汇总扫描 ==", flush=True)
    report = {}
    for f in sorted(Path(args.out).glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pairs = relation_pairs(data)
        report[f.name] = {
            "users": len(user_ids(data)),
            "following_true": sum(1 for _, v in pairs if v),
            "following_false": sum(1 for _, v in pairs if not v),
            "reply_comment_key": count_key(data, "reply_comment"),
        }
        print(f"  {f.name}: {report[f.name]}", flush=True)
    (Path(args.out) / "_m0_key_scan_v3.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 交叉验证: 关注集合 vs 评论者 following 标记
    follow_set = set()
    fs = Path(args.out) / "_follow_set.json"
    if fs.exists():
        follow_set = set(json.loads(fs.read_text(encoding="utf-8")))
    if not follow_set:
        try:
            follow_set = set(user_ids(json.loads(
                (Path(args.out) / "w_followcontent_p1.json").read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            pass
    try:
        c0_data = json.loads((Path(args.out) / "w_comments_l0.json").read_text(encoding="utf-8"))
        cross = [(u, rel, u in follow_set) for u, rel in relation_pairs(c0_data)]
        print(f"cross_check follow_set={len(follow_set)}: {cross[:12]}", flush=True)
    except (OSError, json.JSONDecodeError):
        pass
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""M0 spike: 只读接口验证。

- 只发 GET 请求，不执行关注/取关/点赞/评论等任何写操作。
- 绝不打印 Cookie。
- 响应保存到 fixtures/ 供后续过滤引擎单测使用。

用法:
    .venv\\Scripts\\python.exe scripts\\m0_spike.py
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
                    d = data.get("data")
                    if isinstance(d, dict):
                        record["data_keys"] = list(d.keys())[:15]
                    record["top_keys"] = list(data.keys())[:10]
                result = data
            except ValueError:
                (self.outdir / f"{name}.txt").write_text(
                    resp.text[:3000], encoding="utf-8"
                )
                record["saved"] = f"{name}.txt"
                record["text_head"] = resp.text[:100].replace("\n", " ")
        except requests.RequestException as exc:
            record["error"] = str(exc)
        self.summary.append(record)
        brief = {k: record.get(k) for k in ("name", "status", "ok", "error", "saved")}
        print(json.dumps(brief, ensure_ascii=False), flush=True)
        return result

    def save_summary(self):
        path = self.outdir / "_m0_summary.json"
        path.write_text(
            json.dumps(self.summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def find_first(obj, keys, depth=0):
    if depth > 12:
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
    if depth > 12:
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


def scan_relation_pairs(obj, pairs=None, depth=0):
    if pairs is None:
        pairs = []
    if depth > 12:
        return pairs
    if isinstance(obj, dict):
        uid = obj.get("idstr") or obj.get("id_str") or obj.get("id")
        if isinstance(obj.get("following"), bool):
            pairs.append((str(uid), obj["following"]))
        for v in obj.values():
            scan_relation_pairs(v, pairs, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            scan_relation_pairs(v, pairs, depth + 1)
    return pairs


def count_key(obj, name, depth=0):
    if depth > 12:
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


def find_user_uids(obj, out=None, depth=0):
    if out is None:
        out = []
    if depth > 12 or len(out) >= 20:
        return out
    if isinstance(obj, dict):
        uid = obj.get("idstr") or obj.get("id_str")
        if uid and obj.get("screen_name") and NUM_RE.match(str(uid)):
            out.append(str(uid))
        for v in obj.values():
            find_user_uids(v, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            find_user_uids(v, out, depth + 1)
    return out


def scan_files(outdir: Path):
    print("\n== KEY SCAN ==", flush=True)
    report = {}
    for f in sorted(outdir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pairs = scan_relation_pairs(data)
        reply_count = count_key(data, "reply_comment")
        info = {
            "following_pairs": len(pairs),
            "following_true": sum(1 for _, v in pairs if v),
            "following_false": sum(1 for _, v in pairs if not v),
            "reply_comment_key": reply_count,
        }
        report[f.name] = info
        print(f"{f.name}: {info}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cookie", default=r"D:\desktop\weibo\cookie.txt")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "fixtures"),
    )
    args = parser.parse_args()

    cookie = load_cookie(args.cookie)
    outdir = Path(args.out)
    probe = Probe(cookie, outdir)

    # V2 前置: 登录状态与自己的 uid
    cfg = probe.get("m_config", f"{M}/api/config", f"{M}/", sleep=False)
    uid = None
    login = None
    if isinstance(cfg, dict):
        d = cfg.get("data") or {}
        login = d.get("login")
        uid = str(d.get("uid") or "") or None
    print(f"login={login} uid={uid}", flush=True)

    # V1: 关注流候选
    probe.get("w_allGroups", f"{W}/ajax/feed/allGroups", f"{W}/")
    feed = probe.get("w_home_following", f"{W}/ajax/feed/following", f"{W}/",
                     params={"list_id": "1000", "count": "10", "refresh": "1"})
    mid = find_first(feed, ("mid", "mblogid", "id_str")) if feed else None
    if not mid and uid:
        myblog = probe.get("w_mymblog", f"{W}/ajax/statuses/mymblog", f"{W}/u/{uid}",
                           params={"uid": uid, "page": "1", "feature": "0"})
        mid = find_first(myblog, ("mid", "mblogid", "id_str"))
    print(f"test_mid={mid}", flush=True)

    # V2/V3/V4: 帖子详情与评论
    if mid:
        probe.get("w_status_show", f"{W}/ajax/statuses/show", f"{W}/detail/{mid}",
                  params={"id": mid})
        c0 = probe.get("w_comments_l0", f"{W}/ajax/comments/buildComments",
                       f"{W}/detail/{mid}",
                       params={"is_reload": "1", "id": mid, "is_show_bulletin": "2",
                               "is_mix": "0", "count": "20", "fetch_level": "0"})
        if uid:
            pass  # uid 已可用于后续请求参数
        cid = find_comment_with_replies(c0) if c0 else None
        print(f"comment_with_replies={cid}", flush=True)
        if cid:
            probe.get("w_comments_l1", f"{W}/ajax/comments/buildComments",
                      f"{W}/detail/{mid}",
                      params={"is_reload": "1", "id": cid, "fetch_level": "1",
                              "count": "20"})
            probe.get("m_hotFlowChild", f"{M}/comments/hotFlowChild",
                      f"{M}/detail/{mid}",
                      params={"id": cid, "mid": mid, "max_id_type": "0"})
        probe.get("m_hotflow", f"{M}/comments/hotflow", f"{M}/detail/{mid}",
                  params={"id": mid, "mid": mid, "max_id_type": "0"})
        # V5: 评论者主页关系标记
        commenter_uids = find_user_uids(c0) if c0 else []
        for i, u in enumerate(commenter_uids[:3]):
            probe.get(f"w_profile_{i}", f"{W}/ajax/profile/info", f"{W}/u/{u}",
                      params={"uid": u})
    else:
        print("WARN: 未找到测试帖子 mid", flush=True)

    # V6: 关注名单枚举上限（自己的账号 + 历史上报 237 的账号）
    targets = []
    if uid:
        targets.append((uid, "self"))
    if "7777777777" not in [t[0] for t in targets]:
        targets.append(("7777777777", "t237"))
    for tu, label in targets:
        probe.get(f"w_follows_{label}_p1", f"{W}/ajax/friendships/friends",
                  f"{W}/u/{tu}", params={"uid": tu, "page": "1"})
        probe.get(f"w_follows_{label}_p11", f"{W}/ajax/friendships/friends",
                  f"{W}/u/{tu}", params={"uid": tu, "page": "11"})
    probe.get("m_selffollowed_p1", f"{M}/api/container/getIndex", f"{M}/",
              params={"containerid": "231093_-_selffollowed", "page": "1"})

    report = scan_files(outdir)
    (outdir / "_m0_key_scan.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    probe.save_summary()
    print("\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

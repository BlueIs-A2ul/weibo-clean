"""诊断 cookie 状态: 只打印 cookie 的键名（不打印值）与各接口登录结果。"""

import json
import sys
from pathlib import Path

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def cookie_keys(raw: str):
    keys = []
    for part in raw.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        keys.append(part.split("=", 1)[0].strip())
    return keys


def get(cookie, url, referer, params=None):
    headers = {
        "Cookie": cookie,
        "User-Agent": UA,
        "Referer": referer,
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=25)
    except requests.RequestException as exc:
        return {"_error": str(exc)}
    try:
        return r.json()
    except ValueError:
        return {"_status": r.status_code, "_text": r.text[:200]}


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r"D:\desktop\weibo-clean\cookie.txt"
    raw = Path(path).read_text(encoding="utf-8-sig").strip()
    print("cookie_keys:", cookie_keys(raw))
    print("has_SUB:", "SUB=" in raw, "has_SUBP:", "SUBP=" in raw, "len:", len(raw))

    cfg = get(raw, "https://m.weibo.cn/api/config", "https://m.weibo.cn/")
    d = cfg.get("data") if isinstance(cfg, dict) else {}
    print("m_config: ok=%s login=%s uid=%s" % (
        cfg.get("ok") if isinstance(cfg, dict) else None,
        (d or {}).get("login"),
        (d or {}).get("uid"),
    ))

    info = get(raw, "https://weibo.com/ajax/profile/info", "https://weibo.com/")
    user = ((info or {}).get("data") or {}).get("user") if isinstance(info, dict) else {}
    print("w_profile_info: ok=%s uid=%s screen=%s following=%s" % (
        (info or {}).get("ok") if isinstance(info, dict) else None,
        (user or {}).get("idstr") or (user or {}).get("id"),
        (user or {}).get("screen_name"),
        (user or {}).get("following"),
    ))

    import re

    try:
        r = requests.get(
            "https://weibo.com/",
            headers={"Cookie": raw, "User-Agent": UA},
            timeout=25,
        )
        html = r.text
        print("home_html: status=%s len=%s" % (r.status_code, len(html)))
        for pat in (r"CONFIG\['uid'\]='(\d+)'", r'"uid":"(\d{6,20})"', r'"uid":(\d{6,20})',
                    r'"idstr":"(\d{6,20})"'):
            m = re.search(pat, html)
            print("  pattern %s -> %s" % (pat, m.group(1) if m else None))
    except requests.RequestException as exc:
        print("home_html error:", exc)

    import re
    import urllib.parse

    uor = None
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "UOR":
            uor = v
    if uor:
        dec = urllib.parse.unquote_plus(uor)
        m = re.search(r"uid[\"=:]+(\d{6,20})", dec)
        print("UOR_decoded_uid:", m.group(1) if m else None)

    for cand, label in ((1234567890, "home_regex"),):
        for page in ("1", "11", "21"):
            fr = get(raw, "https://weibo.com/ajax/friendships/friends",
                     "https://weibo.com/u/%d" % cand,
                     {"uid": cand, "page": page})
            if isinstance(fr, dict):
                print("w_friendships uid=%s(%s) page=%s: ok=%s users=%s total=%s" % (
                    cand, label, page, fr.get("ok"), len(fr.get("users") or []),
                    fr.get("total_number")))

    for tu in (6666666666,):
        pinfo = get(raw, "https://weibo.com/ajax/profile/info", "https://weibo.com/u/%d" % tu,
                    {"uid": tu})
        pu = ((pinfo or {}).get("data") or {}).get("user") if isinstance(pinfo, dict) else {}
        print("w_profile_info uid=%s: ok=%s following=%s screen=%s keys_data=%s" % (
            tu, (pinfo or {}).get("ok") if isinstance(pinfo, dict) else None,
            (pu or {}).get("following"), (pu or {}).get("screen_name"),
            list(((pinfo or {}).get("data") or {}).keys())[:10] if isinstance(pinfo, dict) else None,
        ))

    fc = get(raw, "https://weibo.com/ajax/profile/followContent", "https://weibo.com/",
             {"sortType": "all"})
    if isinstance(fc, dict):
        data = fc.get("data") or {}
        follows = (data.get("follows") or {}) if isinstance(data, dict) else {}
        print("w_followContent: ok=%s total=%s next_cursor=%s users=%s" % (
            fc.get("ok"), follows.get("total_number") if isinstance(follows, dict) else None,
            follows.get("next_cursor") if isinstance(follows, dict) else None,
            len(follows.get("users") or []) if isinstance(follows, dict) else None,
        ))
    else:
        print("w_followContent: non-json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# 纯净微博 技术方案（v0.2，接口已验证）

配套文档：根目录 `../README.md`（现状与用法）、`feasibility.md`（历史可行性分析与需求规则 R1~R5）、`../fixtures/m0-findings.md`（M0 实测结论）。
状态说明：【已验证】= 2026-09-13 实账号只读实测通过；【待实现】= 属于我们自己的代码，尚未编写。

## 1. 系统组成

```
┌──────────────────────────────────────────────────────┐
│ 前端 PWA（React/Vue + Vite，移动端优先，深色模式）      │
│  - 关注流   /                                        │
│  - 帖子详情 /status/:mid（正文 + 过滤评论树）          │
│  - 设置     /settings（Cookie、同步、策略开关）        │
└───────────────▲──────────────────────────────────────┘
                │ 本项目 REST API (JSON)
┌───────────────┴──────────────────────────────────────┐
│ 后端 FastAPI + SQLite                                 │
│  ┌────────────┐ ┌────────────┐ ┌───────────────────┐ │
│  │ weibo 客户端│ │ 缓存/仓储   │ │ 过滤引擎（纯函数） │ │
│  │ 限速/重试   │ │ SQLite     │ │ filter_threads()  │ │
│  └────────────┘ └────────────┘ └───────────────────┘ │
└───────────────▲──────────────────────────────────────┘
                │ 带登录 Cookie 的 GET 请求
              weibo.com 内部接口
```

后端职责：持有 Cookie、拉取原始数据、缓存、过滤，前端只拿过滤后的数据（对应规则 R5）。
所有数据源统一定在 weibo.com；m.weibo.cn 不识别当前 Cookie（实测未登录），不作为数据源。

## 2. 数据源接口（M0 已验证）

### 2.1 关注流

```
GET https://weibo.com/ajax/feed/friendstimeline
    ?list_id={gid}&fid={gid}&refresh=4&since_id=0&count=25
```

- `gid` 运行时从 `GET /ajax/feed/allGroups` 解析，选 `title=全部关注` 的分组（本账号 `100012345678901`，type=1）。不要硬编码。
- 响应：`statuses[]`、`total_number`、`since_id`/`max_id` 翻页游标。
- 实测：24 条/页；含转发（`retweeted_status`）；作者 `user.following` 全为 true；广告标记 `status.isAd`、用户 status 里 `ad_marked`。
- 其他分组（原创/特别关注/视频）可用同一接口，gid 不同。

### 2.2 帖子详情

```
GET https://weibo.com/ajax/statuses/show?id={mid}
```

### 2.3 评论与楼中楼【已验证】

```
GET https://weibo.com/ajax/statuses/buildComments
```

一级评论（fetch_level=0）：

```
is_reload=1&id={mid}&is_show_bulletin=3&is_mix=0&count=20&type=feed&uid={帖子作者uid}&fetch_level=0&locale=zh-CN
```

- `data[]`：评论列表；响应级 `total_number`、`max_id` 用于翻页。
- 单条评论关键字段：`id`、`total_number`（回复数）、`max_id`（该评论的回复翻页游标）、`comments[]`（回复预览）、`floor_number`、`like_counts`、`user.following`。

楼中楼（fetch_level=1，`id` 换成根评论 id）：

```
is_reload=1&id={根评论id}&...&fetch_level=1&locale=zh-CN
```

- `data[]` 为该根评论下的回复（扁平列表）。
- 回复关键字段：`rootid`（所属根评论）、`readtimetype=comment_reply`、`reply_comment.user.idstr`（被回复者 uid，R4 的配对依据）、`user.following`。
- 回复多时用根评论的 `max_id` 继续翻页。

### 2.4 关注名单【已验证】

```
主：GET https://weibo.com/ajax/profile/followContent?sortType=all&page={n}
备：GET https://weibo.com/ajax/friendships/friends?uid={uid}&page={n}
```

- followContent：50/页；`data.follows.users`、`total_number`、`next_cursor`（实为 offset）；`data.specialAttention` 每页重复出现，统计时排除。
- friendships：20/页；实测可达第 14 页（258/263），未复现旧的约 200 条硬上限；后段页面 `has_filtered_attentions=true`。
- 少量用户被平台过滤无法枚举（差 5~9 属正常），UI 不提示，仅日志记录。
- 同步策略：优先 followContent 全量；与 friendships 结果取并集后写库；同步后与 `total_number` 校验。
- Demo 实现：followContent 结果写入本地 `following_cache.json`（30 分钟 TTL）；进程启动/重启直接读本地，过期后由后台线程静默刷新，避免每 10 分钟在请求路径上重新拉 6 页。

### 2.5 单条关系判断【已验证】

```
数据自带：任意用户对象 .following（true=我关注 TA）
单条兜底：GET https://weibo.com/ajax/profile/info?uid={uid} → data.user.following
```

- 注意：`following` 字段**仅信息流/用户主页数据可信**；`buildComments`（一级评论与楼中楼）返回的 `following` 恒为 `false`（已关注用户也如此，实测见 `fixtures/m0-findings.md` 勘误），评论可见性判定必须使用本地关注集合。
- 实测交叉验证：关注用户 profile/info=true 且在实时 followContent 集合内；关注用户的评论对象 following=false（字段不可信的直接证据）。
- 评论翻页：根评论与楼中楼均支持 `max_id`，每页实际返回 2~5 条，客户端最多抓 3 页。

### 2.6 登录者身份

- 请求头带 Cookie，不需要请求签名即可 GET。
- 登录者 uid 从 `https://weibo.com/` 首页 HTML 的 `"uid":(\d+)` 解析（实测得到真实 uid）。
- Cookie 失效判定：接口返回 `ok:0`/`errno:-100` 或 HTML 无 uid → 提示重新导入。

## 3. 数据模型（SQLite）

```sql
CREATE TABLE follow (
  uid TEXT PRIMARY KEY,
  screen_name TEXT,
  updated_at TEXT
);
CREATE TABLE post (
  mid TEXT PRIMARY KEY,
  author_uid TEXT,
  retweeted_mid TEXT,        -- 转发原博，无则 NULL
  raw_json TEXT NOT NULL,
  fetched_at TEXT
);
CREATE TABLE comment (
  cid TEXT PRIMARY KEY,
  mid TEXT,                  -- 所属帖子
  root_cid TEXT,             -- 所属根评论（一级评论为 NULL）
  target_uid TEXT,           -- 被回复者（reply_comment.user.idstr）
  author_uid TEXT,
  raw_json TEXT NOT NULL,
  fetched_at TEXT
);
CREATE TABLE relation_cache (
  target_uid TEXT PRIMARY KEY,
  following INTEGER,
  checked_at TEXT
);
CREATE TABLE setting (k TEXT PRIMARY KEY, v TEXT);
```

设计要点：

- 原始 JSON 落库，过滤视图不落库；关注名单变化时只需重算视图，不必重新抓取。
- TTL：关注流 10 分钟、帖子详情 1 小时、评论 30 分钟（可配置）。
- 请求时优先用数据里的 `following` 标记；只有缺失时才查 `relation_cache` / 调 `profile/info`。

## 4. 过滤引擎（核心）

> **v0.2+ 变更**：R2/R4 的判定依据已从"关注集合"升级为"白名单"（生效白名单 = 关注 ∪ 手动添加 − 手动移除），
> 关注仍是默认基底；设计与存储见 `superpowers/specs/2026-09-13-whitelist-design.md`。
> 下文示例中的 `following` 集合可视为白名单谓词的简化表达。

```python
def visible_comments(roots, following: set[str]) -> list[Node]:
    return [n for n in (walk(r, following) for r in roots) if n]

def walk(node, following):
    if node.author_uid not in following:
        return None                          # R2：作者未关注
    if node.is_reply:
        if node.target_uid is None or node.target_uid not in following:
            return None                      # R4：被回复者未关注/无法确认
    node.children = [c for c in (walk(x, following) for x in node.children) if c]
    return node
```

### 4.1 被回复者 uid 的解析顺序

1. `reply_comment.user.idstr`——已实测直出，**主路径**。
2. 本地关注集合匹配评论 HTML 锚点 `@昵称` 的 href（`/u/{uid}`）。
3. 文本 `回复@昵称:` 与关注名单昵称匹配；重名或无法确认时按配置策略（默认隐藏）。

### 4.2 孤儿回复策略

场景：B 回复了未关注的 C（该条隐藏），A 又回复了 B（A、B 均关注）。按 R4，A→B 可见，但父节点已被剪掉。

- 默认：提升到顶层显示，标注"回复 @B（上下文已隐藏）"。
- 可选：严格模式直接隐藏（设置项）。
- 实现：walk 剪枝时，把通过配对检查的节点提升到当前可见层级，而不是丢弃。

### 4.3 帖子流过滤

- 丢弃：作者 uid 不在关注集合中的卡片；`isAd` / `ad_marked` 等促销标记；"TA 赞过"类卡片。
- 保留：关注用户的原创帖；关注用户的转发帖（卡片作者 ∈ 关注集合即可），原博内容照常展示（R3）。
- 实测关注流第一页 24 条均为关注用户发布/转发，过滤后仍会剔除广告与个别推荐位。

### 4.4 单测（过滤引擎不联微博）

用 `fixtures/` 里的真实 JSON 构造用例：

| 用例 | 输入 | 期望 |
|---|---|---|
| 一级评论过滤 | B（关注）、C（未关注）评论 A 的帖子 | 只留 B |
| 楼中楼配对 | A 回复 B（均关注）、A 回复 C（C 未关注） | 只留 A→B |
| 双方反向 | C 回复 A（C 未关注） | 隐藏 |
| 孤儿提升 | A→B 合法但父节点被剪 | 提升并标注 |
| 转发帖 | 关注的人转发未关注用户的原博 | 保留卡片 |
| 广告卡片 | `isAd=true` / `ad_marked=true` | 丢弃 |
| 昵称解析 | `reply_comment` 缺失，HTML 锚点可解析 | 正确取到 uid |
| 重名/无法解析 | 目标无法确认 | 按配置策略（默认隐藏） |

## 5. 本项目 REST API（前端只调这些）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/feed?cursor=` | 过滤后的关注流，分页 |
| GET | `/api/status/{mid}` | 帖子详情（含转发原博展开） |
| GET | `/api/status/{mid}/comments?cursor=` | 过滤后的评论（返回 post + threads，首屏不等待孤儿楼） |
| GET | `/api/status/{mid}/orphans` | 其他讨论中可见的孤儿回复（前端评论渲染后后台加载） |
| GET | `/api/settings` / `PUT /api/settings` | 过滤开关（R3 原博显示、孤儿策略、TTL） |
| POST | `/api/auth/cookie` | 更新 Cookie（格式同 weibo-follows 的 cookie.txt） |
| GET | `/api/auth/status` | Cookie 是否有效 |
| POST | `/api/follows/sync` | 手动同步关注名单，返回进度与差异 |
| GET | `/api/follows/status` | 名单数量、上次同步时间、过滤缺失数 |

错误约定（沿用现有项目）：Cookie 失效 → 401 + 明确文案；风控/限流 → 429 + 建议稍后再试；接口结构变化 → 502 + 记录原始响应片段到日志。

## 6. 前端页面

1. **关注流**：大卡片列表（头像、昵称、正文/配图、转发卡片）、下拉刷新、无限滚动、顶部同步状态条（Cookie 失效时提示）。
2. **帖子详情**：正文 + 互动数 + 评论树。只渲染过滤后的数据；孤儿回复按提升策略标注；隐藏评论不占位。
3. **设置**：Cookie 粘贴/更新、关注同步按钮与状态、策略开关、缓存清理、退出。

移动端优先：单列布局、底部安全区、深色模式、图片懒加载。PWA manifest + Service Worker 做静态缓存；HTTPS 提示见 README 第 5 节。

## 7. 请求预算与限流

- 关注流：翻页 1 次/页，缓存 10 分钟；下拉刷新才重新请求。
- 评论：默认只拉一级评论第一页 + 可见评论的楼中楼；"加载更多"才翻页；不后台预抓全量。
- 关系判断：优先用响应里的 `following` 字段，几乎不产生额外请求；缺失时才查缓存/`profile/info`。
- 所有请求随机延时 ≥2 秒（实测 28 次请求无风控）、指数退避重试 ≤3 次、异常后进入冷却（如 10 分钟）。

## 8. 部署

1. 本机运行：`uvicorn` 监听 `0.0.0.0:8000`，手机同 Wi-Fi 访问 `http://<电脑IP>:8000`。
2. 外网访问：Tailscale（推荐，自带 HTTPS）或 VPS（注意 Cookie 安全，建议只放自己可控机器）。
3. Cookie 文件权限收紧，仅本机可读；日志禁止打印 Cookie；数据库文件不进 Git。
4. 项目根目录 `cookie.txt` 与 `fixtures/` 属敏感目录，后续 git init 时务必加入 `.gitignore`。

## 9. 与 weibo-follows 的代码复用

| 现有组件 | 复用方式 |
|---|---|
| `weibo_client.py` 的请求头/Cookie/重试/错误分类 | 抽成公共 weibo client 模块（复制后演进，不动原项目） |
| `models.py` 的 `FollowedUser` | 关注名单导入 |
| CLI 退出码约定（1 Cookie 失效 / 2 风控 / 3 其他） | 后端错误分类沿用 |
| `data/follows_*.json` 导出 | 作为关注名单初始数据导入 |

另：`weibo-follows` README 中"约 200 条平台上限"的说法已被本 M0 实测推翻，建议后续更新其文档。

## 10. 后续（2.0+，暂不做）

写操作（评论/转发/点赞）、消息中心过滤、原生 App 壳、多账号、关注名单定时同步、孤儿回复的更多展示样式。

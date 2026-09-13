# 纯净微博 · 白名单可见性（v0.2）设计

- 日期：2026-09-13
- 状态：定稿（用户授权自主设计与实施）
- 关联文档：`docs/technical-design.md`、`fixtures/m0-findings.md`、`docs/superpowers/plans/2026-09-13-weibo-clean-demo.md`

## 1. 背景与目标

原可见性规则基于"关注"：R2（帖子/一级评论作者必须被关注）、R4（回复双方都必须被关注）。
本设计将其替换为基于"白名单"：

```
生效白名单 = （关注 ∪ 手动添加） − 手动移除
```

- 默认行为与现状一致：关注的人自动可见。
- **手动添加未关注者**：其原创微博并入首页信息流，其评论/回复不再被过滤。
- **手动移除已关注者**：其帖子（含转发）、评论、回复全部隐藏，并可在管理页恢复。
- 添加入口：粘贴微博主页链接或纯数字 UID（用户明确选择，不做昵称搜索、不做内容内快捷添加）。

## 2. 非目标

- 昵称搜索添加、从帖子/评论处快捷添加。
- 修改微博侧关注关系（不代用户关注/取关）。
- 用微博分组/特别关注等远程状态存白名单。
- 信息流分页/加载更多（维持单页抓取）。
- ~~登录账号自身内容的特殊可见性（与现状一致，不做特判）。~~ v0.2.2 修正：登录者自己始终可见（见 §3），uid 从 `https://weibo.com/` 首页 HTML 解析并缓存。
- 手动添加者的转发内容：若验证发现个人时间线接口天然包含转发则包含，否则只取原创（见 §12）。

## 3. 判定语义

谓词 `allows(user) = True` 当且仅当：

0. `user.uid == self_uid`（登录者自己，v0.2.2）：无条件可见，优先于移除集合；`self_uid` 由首页 HTML 解析、10 分钟缓存，解析失败时退化为 `None`（仅影响自己内容的可见性，不影响鉴权错误上抛）。
1. `user.uid` 非空；
2. `uid ∉ removed`；
3. `user.following == True`（信息流/主页数据可信；评论接口的该字段恒为 false，见 `fixtures/m0-findings.md` 勘误）；或
4. `uid ∈ added`；或
5. `uid ∈ following_uids`（本地关注集合，v0.2.1 起用于评论/楼中楼判定）。

替换点：

- R2：帖子作者、一级评论作者必须 `allows`。
- R4：回复作者与目标用户（`target` 存在时）都必须 `allows`。
- 不变：广告规则（`isAd` 丢弃）、转发嵌套内容整体展示、孤儿楼（隐藏根楼中可见回复）逻辑。
- 不变量：`added ∩ removed = ∅`；再次添加即自动移出 `removed`（复活）。
- 过滤不依赖本地关注集合：微博响应中的 `following` 布尔已覆盖帖子/评论/回复目标场景（M0 已验证）。

## 4. 存储

新增 `app/whitelist.py`（`WhitelistStore`），持久化到 `whitelist.json`：

```json
{
  "version": 1,
  "added":   [{"uid": "123", "name": "张三", "avatar": "https://...", "at": "2026-09-13T12:00:00+00:00"}],
  "removed": [{"uid": "456", "name": "李四", "avatar": "https://...", "at": "2026-09-13T12:00:00+00:00"}]
}
```

- 存 `name`/`avatar` 用于管理页展示，避免逐条请求；`avatar` 存原始 URL，展示时再走图片代理。
- 写入：线程锁 + 临时文件 + `os.replace` 原子替换（Windows 兼容）。
- 读取：懒加载一次；顶层结构损坏抛 `WhitelistError`；条目缺 `uid` 则跳过。
- 路径：`Settings.whitelist_file`，默认 `whitelist.json`，可用环境变量 `WEIBO_WHITELIST_FILE` 覆盖；加入 `.gitignore`。
- 接口：`is_added(uid)`、`is_removed(uid)`、`add(entry)`、`hide(entry)`、`remove_added(uid)`、`restore(uid)`、`added_entries()`、`removed_entries()`。

## 5. 关注列表（仅管理页用）

- `WeiboClient.fetch_following()`：`GET /ajax/profile/followContent?sortType=all&page=N`（50/页），按 `data.next_cursor`（实为 offset）翻页直至用户列表为空 / 游标不前进 / 上限 30 页保险；按 uid 去重后返回 `list[User]`。
- 缓存键 `following`，沿用 `TTLCache`（v0.2.4 起 1800 秒）并持久化到本地 `following_cache.json`：启动即读本地、过期后台刷新，避免阻塞评论首屏。
- 管理页"关注中"列表 = `fetch_following()` 结果中 `uid ∉ removed` 的条目；"已隐藏"直接取 `store.removed_entries()`。

## 6. 手动添加者的个人时间线

- 新端点（待 §12 验证）：`GET /ajax/statuses/mymblog?uid={uid}&page=1&feature=0`；不可用则尝试 `m.weibo.cn/api/container/getIndex?type=uid&value={uid}` 等备选。
- `WeiboClient.fetch_user_timeline(uid, force=False)`：解析复用 `parse_post`；缓存键 `timeline:{uid}`，600 秒；`force=True` 时先删缓存。
- 失败隔离：单个用户抓取失败（网络/限流等非鉴权错误）时跳过该用户，不影响整体信息流；`WeiboAuthError` 正常上抛。

## 7. 信息流合并

- `GET /api/feed` 数据 = `fetch_feed(force)` ＋ Σ `fetch_user_timeline(uid, force)`（`uid ∈ added`）。
- 合并：按 `mid` 去重（关注流优先）、按 `created_ts` 降序、截断 60 条。
- `Post` 新增 `created_ts: float`：解析层将微博时间串（`%a %b %d %H:%M:%S %z %Y`）或 ISO 串归一为时间戳，失败为 `0.0`；仅用于排序，UI 不展示。
- `post_view` 增加 `manual` 布尔（作者 uid ∈ added），前端据此打"白名单"标签。
- 过滤发生在响应阶段（缓存存原始帖），白名单增删改即时生效，无需强制刷新；`force=1` 时同时清 `feed` 与全部 `timeline:{uid}` 缓存。

## 8. API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/feed?force=` | 合并后的白名单信息流 |
| GET | `/api/whitelist` | `{following: [{uid,name,avatar,hidden}], added: [Entry], removed: [Entry]}`，avatar 走代理 |
| POST | `/api/whitelist/add` | body `{"input": "链接或UID"}`；解析 uid → `profile/info?uid=` 取 name/avatar/following → `store.add`；返回 `{uid,name,following}` |
| POST | `/api/whitelist/remove` | body `{"uid": "..."}`；若在 added 中则删除条目，否则记入 removed |
| POST | `/api/whitelist/restore` | body `{"uid": "..."}`；移出 removed |

- 输入解析：去掉空白后为纯数字 → uid；否则取 URL 路径中 `/u/<数字>` 或首个全数字路径段；均不匹配 → 400 `{"error": "请粘贴主页链接或数字 UID"}`。
- `profile/info` 查无此人 → 404；`WhitelistError` → 500；鉴权/限流/网络错误沿用现有 401/429/502 映射。
- 写操作持 store 锁串行执行。
- `remove` 的 name/avatar：优先取 added 条目，其次从 `fetch_following()` 缓存中查，兜底 `profile/info`。

## 9. UI

- 顶栏新增"白名单"按钮（信息流视图可见）→ 第三个视图"白名单管理"（复用现有 back/title 切换机制）。
- 管理页结构：
  - 添加区：输入框（占位符"粘贴主页链接或 UID"）+ 添加按钮 + 结果反馈（banner）。
  - 手动添加（added）：头像 + 昵称 + "移除"。
  - 关注中（following，排除已隐藏）：头像 + 昵称 + "隐藏"；顶部客户端筛选框（纯前端过滤，不请求接口）。
  - 已隐藏（removed）：头像 + 昵称 + "恢复"。
- 信息流卡片：`manual` 作者名旁加"白名单"小标签。
- 评论区标题文案由"只显示你关注的人"改为"只显示白名单内的人"。
- 管理页各列表加载中显示占位文案；关注列表冷启动约 10 秒，需明确 loading 反馈。
- `app.js` 增加 POST 辅助函数与三个视图渲染；远程文本继续走 `textContent`（无 XSS 面）。

## 10. 错误处理

沿用现有异常映射（401/429/502），新增 400（输入非法）、404（用户不存在）、500（白名单文件损坏）。所有错误响应统一 `{"error": "..."}`，前端 banner 展示。

## 11. 测试策略

- `tests/test_whitelist.py`（新）：store 增删/复活/恢复、原子写、损坏文件、输入解析（纯数字、`weibo.com/u/123`、`m.weibo.cn/u/123?x=1`、非法串）。
- `tests/test_filter_engine.py`：谓词组合（following/added/removed/无 uid）、R4 四种组合、广告与转发不变。
- `tests/test_client.py`：`fetch_following` 翻页/去重/缓存；`fetch_user_timeline` 解析、缓存、force、失败隔离。
- `tests/test_api.py`：GET/POST 白名单接口与错误码、feed 合并去重与 `manual` 标签、`created_ts` 排序、图片代理回归。
- 前端：真实 cookie + 本地 stub 浏览器验收（管理页增删改、标签、"隐藏后再现/消失"）。
- 旧测试全部保持通过（涉及过滤函数签名的用例同步更新）。

## 12. M0 验证项（实施第一步，真实 cookie）

1. `mymblog` 对**未关注**账号可用性、返回结构（`data.list`）、是否包含转发、`feature` 取值（0/1）、`created_at` 格式、`isAd` 字段。
2. 同一端点对已关注账号的一致性抽样。
3. `profile/info?uid=` 的 `screen_name`/`profile_image_url`/`following` 字段复核。
4. 原始响应存 `fixtures/live/`（gitignored），结论补入 `fixtures/m0-findings.md`。

若 `mymblog` 不可用：依次尝试备选端点；全部失败则降级为"仅评论/回复放宽 + 管理页可用"，并回报用户。

## 13. 影响文件

- 新增：`app/whitelist.py`、`tests/test_whitelist.py`、`docs/superpowers/specs/2026-09-13-whitelist-design.md`
- 修改：`app/config.py`、`app/models.py`、`app/parsing.py`、`app/filter_engine.py`、`app/weibo_client.py`、`app/main.py`、`web/index.html`、`web/style.css`、`web/app.js`、`tests/test_parsing.py`、`tests/test_filter_engine.py`、`tests/test_client.py`、`tests/test_api.py`、`README.md`、`.gitignore`

## 14. 风险

- `mymblog` 行为不确定 → 有备选与降级路径（§12）。
- 手动添加用户较多时刷新变慢（每人 1 次请求、1.0–2.5 秒随机限速）→ 缓存 600 秒兜底；个人量级可接受。
- `followContent` 游标语义依赖 M0 实测结论（6 页可达、去重后 254 人），已记录。

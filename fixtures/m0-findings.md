# M0 验证结果（最终）

- 日期：2026-09-13
- 账号：uid 1234567890（关注 263 人，实测）
- 方式：weibo.com 内部接口 + 浏览器 Cookie，纯只读 GET（脚本见 `scripts/`，Cookie 已移至项目根目录 `cookie.txt`）
- 结论：**V1~V7 全部通过**。原 checklist 中"约 200 条关注上限"在本账号未复现。

## 结论汇总

| 编号 | 验证项 | 结论 | 证据 | 备注 |
|---|---|---|---|---|
| V1 | 关注流接口 | 通过 | `live/w_feed_all.json` | `ajax/feed/friendstimeline`，gid 来自 allGroups；24 条/页，含转发，作者 following 全为 true |
| V2 | 帖子详情接口 | 通过 | `live/w_status_show.json` | `ajax/statuses/show?id={mid}` |
| V3 | 一级评论接口 | 通过 | `live/w_comments_l0_known.json`、旧样本 `comments_l0_page1.json` | `ajax/statuses/buildComments` fetch_level=0 |
| V4 | 楼中楼与被回复者 | 通过 | `live/w_comments_l1_root.json` | `reply_comment.user.idstr` 直出被回复者 uid；`rootid` 指向根评论 |
| V5 | 关系标记 following | 通过 | `live/w_followcontent_p*.json`、`w_comments_*.json` | 用户对象自带 `following` 布尔；关注用户=true、路人=false，与关注集合交叉验证一致 |
| V6 | 关注名单上限 | 通过 | `live/w_friends_p*.json`、`live/w_followcontent_p*.json` | friends 可达第 14 页（258/263），followContent 6 页去重 254；无 200 硬上限 |
| V7 | 单条关系查询兜底 | 通过 | `live/w_profile_followed_*.json`、`w_profile_commenters_*.json` | `ajax/profile/info?uid=` 返回 `data.user.following` |

## 已验证接口清单

### 1. 关注流（首页时间线）

```
GET https://weibo.com/ajax/feed/friendstimeline
    ?list_id={gid}&fid={gid}&refresh=4&since_id=0&count=25
```

- `gid` 从 `GET /ajax/feed/allGroups` 中取 `title=全部关注` 的分组（本账号 `100011234567890`，type=1）。
- 响应：`statuses[]`、`total_number`（本账号 2000）、`since_id/max_id` 翻页游标。
- 实测：单页 24 条，其中 4 条转发（含 `retweeted_status`）；作者 `user.following` 全为 true；帖子自带 `isAd`，用户 status 里有 `ad_marked`，可用于广告过滤。
- 注意：`/ajax/feed/following` 不存在（404）；不要硬编码 gid，运行时从 allGroups 解析。

### 2. 帖子详情

```
GET https://weibo.com/ajax/statuses/show?id={mid}
```

### 3. 评论

```
GET https://weibo.com/ajax/statuses/buildComments
```

一级评论参数：

```
is_reload=1&id={mid}&is_show_bulletin=3&is_mix=0&count=20&type=feed&uid={帖子作者uid}&fetch_level=0&locale=zh-CN
```

- 响应：`data[]`（评论列表）、`total_number`、`max_id`（翻页）、`rootComment`（部分场景）。
- 每条评论字段：`id`、`total_number`（回复数）、`max_id`（该评论的回复翻页游标）、`comments[]`（回复预览）、`floor_number`、`like_counts`、`user`（含 `following`）。

楼中楼参数（把 id 换成根评论 id）：

```
is_reload=1&id={根评论id}&...&fetch_level=1&locale=zh-CN
```

- 响应 `data[]` 为该根评论下的回复（扁平结构）。
- 每条回复：`rootid`（根评论 id）、`readtimetype=comment_reply`、`reply_comment.user.idstr`（**被回复者 uid，R4 配对依据**）、`user.following`。
- 回复过多时用该根评论的 `max_id` 继续翻页。

### 4. 关注名单（两条路径）

```
主：GET https://weibo.com/ajax/profile/followContent?sortType=all&page={n}
备：GET https://weibo.com/ajax/friendships/friends?uid={uid}&page={n}
```

- followContent：50/页，`data.follows.users`、`next_cursor`（实为 offset）、`total_number`；注意 `data.specialAttention` 每页重复出现（本账号固定 1 人），统计时必须排除。
- friendships：20/页，可达末页；后期页面 `has_filtered_attentions=true`。
- 实测：263 关注 → friendships 14 页共 258 人；followContent 去重 254 人；与 total_number 差 5~9（平台过滤/注销账号，正常）。
- 结论：原 weibo-follows 工具的"约 200 条上限"在当前接口上不成立，建议同步后做数量校验即可。

### 5. 关系判断

```
数据自带：任意用户对象 .following（true=我关注 TA）
单条兜底：GET https://weibo.com/ajax/profile/info?uid={uid} → data.user.following
```

双向验证：2 个关注用户 profile 返回 true 且在关注集合内；4 个评论者 profile 返回 false 且不在集合内，与评论数据里的 `following` 标记完全一致。

### 6. 分组信息

```
GET https://weibo.com/ajax/feed/allGroups
```

- 响应 `groups[].group[]`，每项含 `gid/title/type`；"全部关注"（type=1）、"特别关注"、"原创"、"视频"等。

## 对过滤引擎的影响

- "是否关注"不再需要额外请求：评论、帖子、流数据里的 `user.following` 直接可用；本地关注集合用于批量与离线场景，profile/info 作为兜底。
- R4 配对：回复条目的 `reply_comment.user.idstr`（被回复者）+ 双方 `following`；被回复者不在当前响应内时用关注集合判断。
- 广告/推荐过滤：`isAd`、`ad_marked` 等字段。
- 关注流 gid 运行时解析，避免硬编码。

## 遗留与注意事项

- Cookie 会过期（依赖 SUB）；失效时后端需明确提示重新导入。
- `has_filtered_attentions` 导致少量关注不可枚举，属平台行为，无法绕过；UI 不提示，仅日志记录。
- 请求频率保持人类节奏（≥2s 间隔），高频有风控风险。
- weibo.com Cookie 不适用于 m.weibo.cn（m 站接口返回未登录），客户端统一走 weibo.com。

## M1 白名单补充验证（2026-09-13）

| 编号 | 项目 | 结论 | 证据文件 |
|---|---|---|---|
| V8 | 个人时间线（未关注账号） | 通过：`GET /ajax/statuses/mymblog?uid={uid}&page=1&feature=0` 对未关注账号可用，`data.list[]` 28 条 | `live/w_mymblog_unknown_f0.json` |
| V9 | 个人时间线是否含转发 | `feature=0`（全部）= 含转发（28 条中 4 条带 `retweeted_status`）；`feature=1`（原创）= 不含转发（19 条） | `live/w_mymblog_unknown_f1.json` |
| V10 | 已关注账号抽样一致性 | 通过：同一端点对已关注账号同样可用 | `live/w_mymblog_followed_f0.json` |
| V11 | profile/info 字段复核 | 通过：`idstr`/`screen_name`/`profile_image_url`/`following` 均存在 | `live/w_profile_info_unknown.json` |

补充说明：

- `created_at` 格式为 `%a %b %d %H:%M:%S %z %Y`（如 `Sun Sep 13 03:25:05 +0800 2026`），解析器已按此实现，ISO 作为兜底。
- 列表首条可能是置顶帖（`isTop: 1`，日期较旧），合并进信息流后按时间倒序自然下沉，无需特殊处理。
- 帖子自带 `isAd`；`user.following` 对未关注作者为 `false`（白名单判定依赖 added 集合）。
- 客户端实现采用 `feature=0`（与 friendstimeline 一致，含转发）。

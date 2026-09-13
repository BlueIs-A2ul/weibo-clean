# 纯净微博 · weibo-clean

自托管的"纯净版微博"阅读器：只显示**白名单成员**（默认就是你关注的人）发布或转发的帖子与评论，广告、推荐和路人的内容在服务端就被过滤掉，前端拿不到被隐藏的数据。

- **服务端过滤**：不是渲染后遮挡，被隐藏的帖子和评论根本不会下发到浏览器。
- **白名单完全可控**：关注自动生效；支持手动添加未关注的人、隐藏已关注的人，随时恢复。
- **数据只在本地**：Cookie、白名单、缓存都只存在你自己的机器上。

> ⚠️ 本项目通过微博网页版**非官方接口**读取数据，仅适合个人自用。使用前请阅读文末[免责声明](#免责声明)。

## 功能

| 功能 | 说明 |
|---|---|
| 白名单信息流 | 只显示白名单成员发布/转发的帖子；`isAd` 广告一律丢弃 |
| 无限下滑 | 基于 `max_id` 游标分页，滚到底自动加载更早的帖子 |
| 评论过滤 | 一级评论只显示白名单成员的发言；楼中楼要求回复双方都在白名单（R2/R4） |
| 自己始终可见 | 你自己的帖子、评论、回复不参与过滤 |
| 添加未关注者 | 粘贴主页链接或 UID，其帖子并入信息流第一页，并在评论中可见 |
| 隐藏 / 恢复 | 对关注中的人一键隐藏；"已隐藏"列表可随时恢复 |
| 孤儿回复 | 被隐藏楼里"双方都可见"的回复提升展示，标注"上下文已隐藏" |
| 图片代理 | 后端带 `Referer` 代理新浪图床图片，绕过防盗链导致的 403 |
| 本地缓存 | 关注名单缓存 30 分钟并落盘（重启秒读、后台刷新）；帖子/评论 10 分钟 TTL |
| 移动端 UI | 单列卡片、深色模式、图片懒加载 |

## 快速开始

要求：Python 3.10+。

```bash
git clone https://github.com/BlueIs-A2ul/weibo-clean.git
cd weibo-clean
python -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS / Linux
# source .venv/bin/activate && pip install -r requirements.txt

# 准备 Cookie：把浏览器里 weibo.com 请求的完整 Cookie 值存到项目根目录 cookie.txt
# 启动
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打开 `http://127.0.0.1:8000`；手机与电脑同一 Wi-Fi 时访问 `http://<电脑IP>:8000`。

<details>
<summary>如何获取 Cookie</summary>

1. 浏览器登录 weibo.com；
2. 开发者工具 → Network，随便找一个发往 `weibo.com` 的请求；
3. 复制 Request Headers 里的完整 `Cookie` 值，存为项目根目录的 `cookie.txt`（只放这一行）；
4. 文件支持带 BOM 的 UTF-8；Cookie 过期后会收到 401 提示，重新导入即可。
</details>

## 使用

- **信息流**：点卡片进详情；滚到底自动加载更早内容；右上角"刷新"拉取最新。
- **白名单管理**（顶栏"白名单"）：
  - 添加：粘贴 `https://weibo.com/u/1234567890` 形式的链接或纯数字 UID；
  - 隐藏：在"关注中"点"隐藏"（仍然关注，只是本应用不再显示）；
  - 恢复：在"已隐藏"点"恢复"；
  - 关注列表支持昵称/UID 筛选。

### 可见性规则

生效白名单 = （你的关注 ∪ 手动添加） − 手动移除，关注变化自动生效。

| 编号 | 规则 |
|---|---|
| R1 | 信息流只显示白名单成员发布或转发的帖子；广告/推荐位丢弃 |
| R2 | 一级评论只显示白名单成员发表的评论 |
| R3 | 白名单成员转发的原博照常显示（原作者可以不在白名单） |
| R4 | 楼中楼回复：回复者与被回复者都在白名单才显示 |
| R5 | 过滤全部发生在服务端，前端拿不到被隐藏的数据 |
| R6 | 你自己始终可见，不参与过滤 |

## 配置

环境变量（全部可选）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `WEIBO_COOKIE_FILE` | `cookie.txt` | Cookie 文件路径 |
| `WEIBO_WHITELIST_FILE` | `whitelist.json` | 白名单存储路径 |
| `WEIBO_FOLLOWING_CACHE_FILE` | `following_cache.json` | 关注名单本地缓存路径 |
| `WEIBO_MIN_DELAY` / `WEIBO_MAX_DELAY` | `1.0` / `2.5` | 每个微博请求前的随机间隔（秒），调低有风控风险 |

本地数据文件（均已 gitignore）：`cookie.txt`（凭证）、`whitelist.json`（手动添加/隐藏）、`following_cache.json`（关注名单缓存）。删除缓存文件可强制重新拉取。

## 工作原理

```
浏览器（原生 JS 单页，无构建）
   │  /api/*（只返回过滤后的数据）
   ▼
FastAPI 后端
   ├─ 白名单引擎：关注 ∪ 添加 − 隐藏（filter_engine.py）
   ├─ 微博客户端：Cookie、限速、错误分类、TTL 缓存（weibo_client.py）
   ├─ 关注名单：followContent 分页 → 内存 + 本地文件缓存（30 分钟）
   ├─ 评论：buildComments 分页，白名单双方判定（R4）
   └─ 图片代理：带 Referer 转发新浪图床
   ▼
weibo.com 网页版内部接口（只读 GET）
```

- 信息流按 `max_id` 游标分页；手动添加者的时间线（`mymblog`）只在第一页合并，按时间倒序去重。
- 所有微博调用集中在 `weibo_client.py`（单点修改即可应对接口变动），请求带 1.0~2.5 秒随机间隔并做结果缓存。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/feed?cursor=&force=` | 白名单信息流，游标分页 |
| GET | `/api/status/{mid}` | 帖子详情 |
| GET | `/api/status/{mid}/comments` | 帖子 + 过滤后的一级评论 |
| GET | `/api/status/{mid}/orphans` | 孤儿回复（前端渲染评论后后台加载） |
| GET | `/api/comment/{cid}/replies?mid=` | 楼中楼回复 |
| GET | `/api/whitelist` | 关注 / 添加 / 隐藏三组名单 |
| POST | `/api/whitelist/add` | `{"input": "主页链接或UID"}` |
| POST | `/api/whitelist/remove` | `{"uid": "..."}`：添加的移除，关注的隐藏 |
| POST | `/api/whitelist/restore` | `{"uid": "..."}`：恢复已隐藏 |
| GET | `/api/image?url=` | 新浪图床图片代理（仅 `*.sinaimg.cn`） |

错误约定：Cookie 失效 → 401；风控/限流 → 429；接口异常 → 502；输入非法 → 400；白名单文件损坏 → 500。响应统一 `{"error": "..."}`。

## 项目结构

```
app/
  main.py           FastAPI 路由、视图序列化、图片代理
  weibo_client.py   微博接口客户端（限速 / 错误分类 / 缓存 / 分页）
  filter_engine.py  白名单谓词与过滤函数（R1~R4）
  whitelist.py      白名单存储（添加 / 隐藏 / 恢复，原子写）
  parsing.py        接口响应 → 领域模型
  models.py         领域模型
  config.py         配置（环境变量）
  cache.py          线程安全 TTL 缓存
web/                原生 JS 前端（index.html / app.js / style.css）
tests/              pytest 单元与 API 测试（97 个）
docs/               技术方案、可行性分析、设计与实现计划（历史）
fixtures/           M0 接口验证结论（原始抓包不入库）
scripts/            M0 验证脚本（历史工具）
```

## 测试

```bash
.venv\Scripts\python.exe -m pytest -q
```

## 已知限制

- 只读：不支持发帖、评论、点赞等写操作。
- 评论最多抓取前 3 页（每页由微博决定，约 2~5 条）；楼中楼按需加载。
- 手动添加的人越多，刷新越慢（每人一次请求，缓存 10 分钟）。
- 关注名单受平台过滤影响，可能漏掉个别账号（实测可枚举约 96%）。
- 图片是微博签名 URL，签名过期后需要刷新页面重新获取。
- 无数据库、无 PWA；单账号、单实例。

## 免责声明

- 本项目使用微博网页版**非官方接口**，仅供个人学习与自用；请遵守微博服务条款，不要用于批量抓取、公开分发或商业用途。
- 使用非官方接口存在**账号被风控或限制**的风险；请控制请求频率，并自行承担使用后果。
- Cookie 只保存在本机文件、不会外传；请勿将 `cookie.txt` 提交到任何仓库（本项目已将其加入 `.gitignore`）。
- 接口随时可能变更，可能导致部分功能失效；欢迎提交 issue 反馈。

## 开发文档

- [可行性分析（历史）](docs/feasibility.md)
- [技术方案](docs/technical-design.md)
- [M0 接口验证结论](fixtures/m0-findings.md)
- [白名单设计](docs/superpowers/specs/2026-09-13-whitelist-design.md)
- [Demo 实现计划](docs/superpowers/plans/2026-09-13-weibo-clean-demo.md) ｜ [白名单实现计划](docs/superpowers/plans/2026-09-13-whitelist.md)

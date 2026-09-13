const state = { mid: null, view: "feed" };

const TITLES = { feed: "纯净微博", detail: "帖子详情", whitelist: "白名单管理" };

const $ = (selector) => document.querySelector(selector);

async function api(path, options) {
  const resp = await fetch(path, options);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `请求失败（HTTP ${resp.status}）`);
  }
  return resp.json();
}

function post(path, payload) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showBanner(message, ok = false) {
  const banner = $("#banner");
  banner.textContent = message;
  banner.hidden = false;
  banner.classList.toggle("ok", ok);
}

function hideBanner() { $("#banner").hidden = true; }

function avatarImg(url) {
  const avatar = el("img", "avatar");
  avatar.src = url || "";
  avatar.alt = "";
  return avatar;
}

function userHead(user, manual = false) {
  const head = el("div", "head");
  head.append(avatarImg(user.avatar), el("span", "name", user.name));
  if (manual) head.append(el("span", "tag", "白名单"));
  return head;
}

function postCard(post, onClick) {
  const card = el("article", "card");
  card.append(userHead(post.author, post.manual));
  card.append(el("div", "text", post.text));
  if (post.pics.length) {
    const pics = el("div", "pics");
    for (const url of post.pics) {
      const img = el("img");
      img.src = url;
      img.loading = "lazy";
      pics.append(img);
    }
    card.append(pics);
  }
  if (post.retweeted) {
    const box = el("div", "retweet");
    box.append(el("div", "name", "@" + post.retweeted.author.name));
    box.append(el("div", "text", post.retweeted.text));
    card.append(box);
  }
  card.append(el("div", "meta",
    `转发 ${post.reposts} · 评论 ${post.comments} · 赞 ${post.attitudes}`));
  if (onClick) card.addEventListener("click", onClick);
  return card;
}

function commentBody(comment) {
  const box = el("div", "comment");
  const head = el("div", "head");
  head.append(avatarImg(comment.author.avatar), el("span", "name", comment.author.name));
  if (comment.target) head.append(el("span", "target", `回复 @${comment.target.name}`));
  if (comment.promoted) head.append(el("span", "tag", "上下文已隐藏"));
  box.append(head);
  box.append(el("div", "text", comment.text));
  return box;
}

async function loadFeed(force = false) {
  hideBanner();
  const feed = $("#feed");
  feed.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api(force ? "/api/feed?force=1" : "/api/feed");
    feed.innerHTML = "";
    if (!data.items.length) feed.innerHTML = '<div class="loading">没有可显示的内容</div>';
    for (const post of data.items) feed.append(postCard(post, () => openDetail(post.mid)));
  } catch (error) {
    feed.innerHTML = "";
    showBanner(error.message);
  }
}

function setView(view) {
  state.view = view;
  $("#feed").hidden = view !== "feed";
  $("#detail").hidden = view !== "detail";
  $("#whitelist").hidden = view !== "whitelist";
  $("#back-btn").hidden = view === "feed";
  $("#refresh-btn").hidden = view !== "feed";
  $("#whitelist-btn").hidden = view !== "feed";
  $("#title").textContent = TITLES[view] || "纯净微博";
  window.scrollTo(0, 0);
}

async function openDetail(mid) {
  state.mid = mid;
  setView("detail");
  const detail = $("#detail");
  detail.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api(`/api/status/${mid}/comments`);
    renderDetail(data.post, data.threads);
    loadOrphans(mid);
  } catch (error) {
    detail.innerHTML = "";
    showBanner(error.message);
  }
}

function renderDetail(post, threads) {
  const detail = $("#detail");
  detail.innerHTML = "";
  detail.append(postCard(post, null));

  const section = el("section", "card");
  section.append(el("h2", null, "评论（只显示白名单内的人）"));
  if (!threads.length) {
    section.append(el("div", "loading", "没有可显示的评论"));
  }
  for (const thread of threads) {
    const box = commentBody(thread);
    if (thread.total_replies > 0) {
      const replies = el("div", "replies");
      replies.hidden = true;
      const button = el("button", "more-btn", `查看 ${thread.total_replies} 条回复`);
      button.type = "button";
      button.addEventListener("click", () => expandReplies(thread.cid, replies, button));
      box.append(button, replies);
    }
    section.append(box);
  }
  detail.append(section);
}

async function loadOrphans(mid) {
  const detail = $("#detail");
  const hint = el("div", "loading", "正在检查其他讨论…");
  detail.append(hint);
  try {
    const data = await api(`/api/status/${mid}/orphans`);
    hint.remove();
    if (!data.items.length) return;
    const section = el("section", "card");
    section.append(el("h2", null, "其他讨论中白名单成员的回复"));
    for (const orphan of data.items) section.append(commentBody(orphan));
    detail.append(section);
  } catch (error) {
    hint.remove();
    showBanner(error.message);
  }
}

async function expandReplies(rootCid, container, button) {
  button.disabled = true;
  button.textContent = "加载中…";
  try {
    const data = await api(`/api/comment/${rootCid}/replies?mid=${state.mid}`);
    container.innerHTML = "";
    for (const reply of data.items) container.append(commentBody(reply));
    container.hidden = false;
    button.remove();
  } catch (error) {
    button.disabled = false;
    button.textContent = "加载失败，点击重试";
  }
}

function whitelistRow(user, actionLabel, action) {
  const row = el("div", "row");
  row.append(avatarImg(user.avatar), el("span", "name", user.name));
  if (actionLabel) {
    const button = el("button", "row-btn", actionLabel);
    button.type = "button";
    button.addEventListener("click", () => action(button));
    row.append(button);
  }
  return row;
}

function section(title) {
  const box = el("section", "card");
  box.append(el("h2", null, title));
  return box;
}

async function whitelistAction(button, path, payload, okMessage) {
  button.disabled = true;
  try {
    await post(path, payload);
    showBanner(okMessage, true);
    await loadWhitelist();
  } catch (error) {
    button.disabled = false;
    showBanner(error.message);
  }
}

function renderWhitelist(data) {
  const page = $("#whitelist");
  page.innerHTML = "";

  const addSection = section("添加白名单");
  const input = el("input", "text-input");
  input.placeholder = "粘贴主页链接或 UID";
  const addButton = el("button", "row-btn", "添加");
  addButton.type = "button";
  const submit = async () => {
    const value = input.value.trim();
    if (!value) {
      showBanner("请输入主页链接或 UID");
      return;
    }
    addButton.disabled = true;
    try {
      const result = await post("/api/whitelist/add", { input: value });
      showBanner(result.following ? "已添加（TA 已在你的关注中）" : `已添加 ${result.name}`, true);
      input.value = "";
      await loadWhitelist();
    } catch (error) {
      addButton.disabled = false;
      showBanner(error.message);
    }
  };
  addButton.addEventListener("click", submit);
  input.addEventListener("keydown", (event) => { if (event.key === "Enter") submit(); });
  addSection.append(input, addButton);
  page.append(addSection);

  const addedSection = section("手动添加");
  if (!data.added.length) addedSection.append(el("div", "hint", "暂无手动添加的人"));
  for (const entry of data.added) {
    addedSection.append(whitelistRow(entry, "移除", (button) =>
      whitelistAction(button, "/api/whitelist/remove", { uid: entry.uid }, "已移除")));
  }
  page.append(addedSection);

  const followingSection = section("关注中");
  const visible = data.following.filter((user) => !user.hidden);
  if (!visible.length) {
    followingSection.append(el("div", "hint", "暂无"));
  } else {
    const filter = el("input", "text-input");
    filter.placeholder = "筛选昵称或 UID";
    const rows = el("div", "rows");
    const renderRows = () => {
      rows.innerHTML = "";
      const keyword = filter.value.trim().toLowerCase();
      const matched = visible.filter((user) =>
        !keyword || user.name.toLowerCase().includes(keyword) || user.uid.includes(keyword));
      if (!matched.length) rows.append(el("div", "hint", "没有匹配的人"));
      for (const user of matched) {
        rows.append(whitelistRow(user, "隐藏", (button) =>
          whitelistAction(button, "/api/whitelist/remove", { uid: user.uid }, "已隐藏")));
      }
    };
    filter.addEventListener("input", renderRows);
    renderRows();
    followingSection.append(filter, rows);
  }
  page.append(followingSection);

  const removedSection = section("已隐藏");
  if (!data.removed.length) removedSection.append(el("div", "hint", "暂无已隐藏的人"));
  for (const entry of data.removed) {
    removedSection.append(whitelistRow(entry, "恢复", (button) =>
      whitelistAction(button, "/api/whitelist/restore", { uid: entry.uid }, "已恢复")));
  }
  page.append(removedSection);
}

async function loadWhitelist() {
  const page = $("#whitelist");
  page.innerHTML = '<div class="loading">加载中…（首次获取关注列表约需几秒）</div>';
  try {
    renderWhitelist(await api("/api/whitelist"));
  } catch (error) {
    page.innerHTML = "";
    showBanner(error.message);
  }
}

$("#refresh-btn").addEventListener("click", () => loadFeed(true));
$("#back-btn").addEventListener("click", () => setView("feed"));
$("#whitelist-btn").addEventListener("click", () => { setView("whitelist"); loadWhitelist(); });
loadFeed();

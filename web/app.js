const state = { mid: null, view: "feed" };

const $ = (selector) => document.querySelector(selector);

async function api(path) {
  const resp = await fetch(path);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || `请求失败（HTTP ${resp.status}）`);
  }
  return resp.json();
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showBanner(message) {
  const banner = $("#banner");
  banner.textContent = message;
  banner.hidden = false;
}

function hideBanner() { $("#banner").hidden = true; }

function userHead(user) {
  const head = el("div", "head");
  const avatar = el("img", "avatar");
  avatar.src = user.avatar || "";
  avatar.alt = "";
  head.append(avatar, el("span", "name", user.name));
  return head;
}

function postCard(post, onClick) {
  const card = el("article", "card");
  card.append(userHead(post.author));
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
  const avatar = el("img", "avatar");
  avatar.src = comment.author.avatar || "";
  avatar.alt = "";
  head.append(avatar, el("span", "name", comment.author.name));
  if (comment.target) head.append(el("span", "target", `回复 @${comment.target.name}`));
  if (comment.promoted) head.append(el("span", "tag", "上下文已隐藏"));
  box.append(head);
  box.append(el("div", "text", comment.text));
  return box;
}

async function loadFeed() {
  hideBanner();
  const feed = $("#feed");
  feed.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const data = await api("/api/feed");
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
  $("#back-btn").hidden = view === "feed";
  $("#refresh-btn").hidden = view !== "feed";
  $("#title").textContent = view === "feed" ? "纯净微博" : "帖子详情";
  window.scrollTo(0, 0);
}

async function openDetail(mid) {
  state.mid = mid;
  setView("detail");
  const detail = $("#detail");
  detail.innerHTML = '<div class="loading">加载中…</div>';
  try {
    const [statusData, commentsData] = await Promise.all([
      api(`/api/status/${mid}`),
      api(`/api/status/${mid}/comments`),
    ]);
    renderDetail(statusData.post, commentsData);
  } catch (error) {
    detail.innerHTML = "";
    showBanner(error.message);
  }
}

function renderDetail(post, comments) {
  const detail = $("#detail");
  detail.innerHTML = "";
  detail.append(postCard(post, null));

  const section = el("section", "card");
  section.append(el("h2", null, "评论（只显示你关注的人）"));
  if (!comments.threads.length && !comments.orphans.length) {
    section.append(el("div", "loading", "没有可显示的评论"));
  }
  for (const thread of comments.threads) {
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
  if (comments.orphans.length) {
    section.append(el("h2", null, "其他讨论中你关注的人的回复"));
    for (const orphan of comments.orphans) section.append(commentBody(orphan));
  }
  detail.append(section);
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

$("#refresh-btn").addEventListener("click", loadFeed);
$("#back-btn").addEventListener("click", () => setView("feed"));
loadFeed();

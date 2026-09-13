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

function openDetail(mid) {
  state.mid = mid;
  setView("detail");
  $("#detail").innerHTML = '<div class="loading">详情页将在下一个任务实现</div>';
}

$("#refresh-btn").addEventListener("click", loadFeed);
$("#back-btn").addEventListener("click", () => setView("feed"));
loadFeed();

const $ = (id) => document.getElementById(id);
const state = { file: null, jobId: null, poll: null, refinePoll: null, downloadWhich: "result", lang: "en" };

const LANG_BADGE = { auto: "AUTO", en: "EN", pt: "PT", zh: "ZH" };

// ---- i18n ----------------------------------------------------------------
// Static UI text is translated via [data-i18n]/[data-i18n-ph] attributes in the
// HTML; dynamic strings built in JS go through t(). Function-valued entries take
// arguments (e.g. page numbers). The user's choice is remembered in the browser.
const I18N = {
  en: {
    historyTitle: "Translation History",
    history: "History",
    dropLead: "Drag & drop a PDF here, or ",
    browse: "browse",
    from: "From",
    to: "To",
    engine: "Engine",
    apiKey: "API Key",
    optAuto: "Auto-detect",
    optEn: "English",
    optZh: "Chinese (Simplified)",
    optPt: "Portuguese",
    engGoogle: "Google Translate",
    engClaude: "Claude",
    engOpenai: "OpenAI",
    keyPlaceholder: "Paste your API key…",
    keyPlaceholderSaved: "Key saved in this browser — enter a new one to replace",
    save: "Save",
    keyNote: "Your key is sent securely and used only for your translation — never stored on our server. For maximum privacy, use the desktop app.",
    translate: "Translate",
    ready: "Ready to translate",
    complete: "Translation complete",
    download: "Download translated PDF",
    retry: "Retry",
    refine: "Get refined version",
    refining: (p) => `Refining… page ${p}`,
    refineStarting: "Refining… (LLM + OCR, slower)",
    refineNeedsKey: "Pick Claude or OpenAI and add your API key to get the refined version.",
    refineReady: "Refined version ready ✓ — showing it",
    refineFailed: "Refined version failed.",
    original: "ORIGINAL",
    translated: "TRANSLATED",
    langName: "中文",
    starting: "Starting…",
    translatingPage: (p, c) => `Translating page ${p} of ${c}…`,
    previewUnavailable: "Preview unavailable.",
    noPages: "No pages to preview.",
    errChoosePdfFirst: "Please choose a PDF first.",
    errChoosePdf: "Please choose a PDF file.",
    errNetUpload: "Network error during upload.",
    errUpload: "Upload failed.",
    errTranslateFailed: "Translation failed.",
    keyEnterFirst: "Enter a key first.",
    keySaved: (label) => `${label} key saved in your browser ✓`,
    keyCleared: "Key removed from this browser.",
    addKeyFirst: (label) => `Add your ${label} API key first.`,
  },
  zh: {
    historyTitle: "翻译历史",
    history: "历史",
    dropLead: "拖放 PDF 到此处，或",
    browse: "浏览",
    from: "源语言",
    to: "目标语言",
    engine: "翻译引擎",
    apiKey: "API 密钥",
    optAuto: "自动检测",
    optEn: "英语",
    optZh: "简体中文",
    optPt: "葡萄牙语",
    engGoogle: "谷歌翻译",
    engClaude: "Claude",
    engOpenai: "OpenAI",
    keyPlaceholder: "粘贴你的 API 密钥…",
    keyPlaceholderSaved: "密钥已保存在此浏览器 — 输入新密钥可替换",
    save: "保存",
    keyNote: "你的密钥通过加密连接发送，仅用于本次翻译 — 绝不存储在我们的服务器上。如需最高隐私保护，请使用桌面版应用。",
    translate: "翻译",
    ready: "准备就绪",
    complete: "翻译完成",
    download: "下载翻译后的 PDF",
    retry: "重试",
    refine: "获取精修版",
    refining: (p) => `精修中…第 ${p} 页`,
    refineStarting: "精修中…（大模型 + OCR，较慢）",
    refineNeedsKey: "请选择 Claude 或 OpenAI 并添加 API 密钥以生成精修版。",
    refineReady: "精修版已就绪 ✓ — 正在显示",
    refineFailed: "精修版生成失败。",
    original: "原文",
    translated: "译文",
    langName: "EN",
    starting: "正在开始…",
    translatingPage: (p, c) => `正在翻译第 ${p} / ${c} 页…`,
    previewUnavailable: "无法预览。",
    noPages: "没有可预览的页面。",
    errChoosePdfFirst: "请先选择一个 PDF 文件。",
    errChoosePdf: "请选择 PDF 文件。",
    errNetUpload: "上传时发生网络错误。",
    errUpload: "上传失败。",
    errTranslateFailed: "翻译失败。",
    keyEnterFirst: "请先输入密钥。",
    keySaved: (label) => `${label} 密钥已保存到浏览器 ✓`,
    keyCleared: "已从此浏览器移除密钥。",
    addKeyFirst: (label) => `请先添加你的 ${label} API 密钥。`,
  },
};

function t(key, ...args) {
  const dict = I18N[state.lang] || I18N.en;
  const v = dict[key] !== undefined ? dict[key] : I18N.en[key];
  return typeof v === "function" ? v(...args) : v;
}

function applyLang(lng) {
  state.lang = I18N[lng] ? lng : "en";
  const dict = I18N[state.lang];
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const v = dict[el.getAttribute("data-i18n")];
    if (typeof v === "string") el.textContent = v;
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    const v = dict[el.getAttribute("data-i18n-ph")];
    if (typeof v === "string") el.placeholder = v;
  });
  const label = $("langToggleLabel");
  if (label) label.textContent = dict.langName;
  try { localStorage.setItem("pdftx_lang", state.lang); } catch {}
  // Re-derive any text the engine UI sets dynamically (e.g. key placeholder).
  refreshEngineUi();
}

function toggleLang() {
  applyLang(state.lang === "en" ? "zh" : "en");
}

// ---- bring-your-own-key (browser-local) ----------------------------------
const keyStoreId = (engine) => `pdftx_key_${engine}`;
function getStoredKey(engine) {
  try { return localStorage.getItem(keyStoreId(engine)) || ""; } catch { return ""; }
}
function storeKey(engine, value) {
  try {
    if (value) localStorage.setItem(keyStoreId(engine), value);
    else localStorage.removeItem(keyStoreId(engine));
  } catch {}
}

function showStatus(which) {
  for (const id of ["statusIdle", "statusProgress", "statusDone", "statusError"]) {
    const el = $(id);
    if (el) el.classList.toggle("hidden", id !== which);
  }
  // statusBar has no hidden class by default — always visible
}

function setBadges() {
  $("origBadge").textContent = LANG_BADGE[$("from").value] || "AUTO";
  $("transBadge").textContent = LANG_BADGE[$("to").value] || "ZH";
}

function humanSize(n) {
  if (n >= 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
  return n + " B";
}

function setFile(f) {
  if (!f) return;
  const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) { showError(t("errChoosePdf")); return; }
  state.file = f;
  // #fileMeta contains an icon SVG + child spans; set spans individually, never
  // overwrite textContent on the parent (that destroys the icon and the spans).
  $("fileMetaName").textContent = f.name;
  $("fileMetaInfo").textContent = humanSize(f.size);
  $("fileMeta").classList.remove("hidden");
  $("translateBtn").disabled = false;
}

function showError(msg) {
  $("errorText").textContent = msg;
  showStatus("statusError");
}

async function safeDetail(res) {
  try { return (await res.json()).detail; } catch { return null; }
}

// ---- engine menu + key ----
function refreshEngineUi() {
  const engine = $("engine").value;
  const needsKey = engine === "claude" || engine === "openai";
  clearKeyStatus();
  $("apiKeyWrap").classList.toggle("hidden", !needsKey);
  if (needsKey) {
    $("apiKey").placeholder = getStoredKey(engine) ? t("keyPlaceholderSaved") : t("keyPlaceholder");
  }
}

function showKeyStatus(msg, ok) {
  const el = $("keyStatus");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden", "ok", "err");
  el.classList.add(ok ? "ok" : "err");
}

function clearKeyStatus() {
  const el = $("keyStatus");
  if (el) el.classList.add("hidden");
}

// Keys are stored ONLY in this browser (localStorage) and sent with each
// translation request — never persisted on the server.
function saveKey() {
  const engine = $("engine").value;
  const key = $("apiKey").value.trim();
  if (!key) { showKeyStatus(t("keyEnterFirst"), false); return; }
  storeKey(engine, key);
  $("apiKey").value = "";
  refreshEngineUi();
  const label = engine === "claude" ? "Claude" : "OpenAI";
  showKeyStatus(t("keySaved", label), true);
}

// ---- translate ----
async function startTranslate() {
  if (!state.file) { showError(t("errChoosePdfFirst")); return; }
  const engine = $("engine").value;
  const needsKey = engine === "claude" || engine === "openai";
  const key = needsKey ? getStoredKey(engine) : "";
  if (needsKey && !key) {
    showError(t("addKeyFirst", engine === "claude" ? "Claude" : "OpenAI"));
    return;
  }

  $("origView").innerHTML = "";
  $("transView").innerHTML = "";
  $("translateBtn").disabled = true;
  resetRefineUi();
  showStatus("statusProgress");
  setProgress(0, 0);

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("source", $("from").value);
  fd.append("target", $("to").value);
  fd.append("engine", engine);
  if (key) fd.append("api_key", key);

  let res;
  try { res = await fetch("/api/translate", { method: "POST", body: fd }); }
  catch { return fail(t("errNetUpload")); }
  if (!res.ok) return fail((await safeDetail(res)) || t("errUpload"));

  const data = await res.json();
  state.jobId = data.job_id;
  loadPages("original", "origView");
  pollStatus();
}

function setProgress(page, count) {
  // #progressBar is the TRACK <div>; the FILL is its child .progress-bar-fill.
  // Setting style.width on #progressBar itself does nothing visible.
  const fill = document.querySelector("#progressBar .progress-bar-fill");
  const pct = count > 0 ? Math.round((page / count) * 100) : 6;
  if (fill) fill.style.width = pct + "%";
  $("progressText").textContent = count ? t("translatingPage", page, count) : t("starting");
}

function fail(msg) {
  if (state.poll) { clearInterval(state.poll); state.poll = null; }
  $("translateBtn").disabled = false;
  showError(msg);
}

function pollStatus() {
  if (state.poll) clearInterval(state.poll);
  state.poll = setInterval(async () => {
    let res;
    try { res = await fetch(`/api/jobs/${state.jobId}`); } catch { return; }
    if (!res.ok) return;
    const s = await res.json();
    if (s.status === "running") {
      setProgress(s.page, s.page_count);
      // Enrich file meta with page count as soon as it's known
      if (s.page_count) {
        const pages = s.page_count;
        $("fileMetaInfo").textContent =
          humanSize(state.file.size) + ` · ${pages} page${pages !== 1 ? "s" : ""}`;
      }
    } else if (s.status === "done") {
      clearInterval(state.poll); state.poll = null;
      // Enrich page count on done too (in case it resolved before first running poll)
      if (s.page_count) {
        const pages = s.page_count;
        $("fileMetaInfo").textContent =
          humanSize(state.file.size) + ` · ${pages} page${pages !== 1 ? "s" : ""}`;
      }
      await loadPages("result", "transView");
      state.downloadWhich = "result";
      resetRefineUi();
      showStatus("statusDone");
      $("translateBtn").disabled = false;
      refreshHistory();
    } else if (s.status === "error") {
      fail(s.error || t("errTranslateFailed"));
    }
  }, 1000);
}

// ---- page-image panes ----
// Render the ACTUAL PDF pages as images (original layout, images, fonts all
// preserved) by pointing at the per-page render endpoints. This shows the
// format-preserved document, not a text transcription.
async function loadPages(which, viewId) {
  const view = $(viewId);
  view.innerHTML = "";
  let res;
  try { res = await fetch(`/api/jobs/${state.jobId}/pages?which=${which}`); }
  catch { view.textContent = t("previewUnavailable"); return; }
  if (!res.ok) { view.textContent = t("previewUnavailable"); return; }
  const { pages } = await res.json();
  if (!pages) { view.textContent = t("noPages"); return; }
  for (let i = 0; i < pages; i++) {
    const img = document.createElement("img");
    img.className = "pdfpage";
    img.loading = "lazy";
    img.alt = `${which} page ${i + 1}`;
    img.src = `/api/jobs/${state.jobId}/page/${which}/${i}`;
    view.appendChild(img);
  }
}

// ---- history (session-only) ----
async function refreshHistory() {
  let res;
  try { res = await fetch("/api/jobs"); } catch { return; }
  if (!res.ok) return;
  const jobs = await res.json();
  const list = $("historyList");
  list.innerHTML = "";
  // #historyList is a <ul>; wrap each entry in <li>
  jobs.forEach((j) => {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.className = "historyitem";
    const engineLabel = { google: "Google", claude: "Claude", openai: "OpenAI" }[j.engine] || j.engine || "";
    const langs = `${(j.source || "auto").toUpperCase()}→${(j.target || "").toUpperCase()}`;
    btn.textContent = `${j.filename} · ${langs} · ${engineLabel} · ${j.status}`;
    btn.addEventListener("click", () => openHistory(j.id));
    li.appendChild(btn);
    list.appendChild(li);
  });
}

async function openHistory(jobId) {
  state.jobId = jobId;
  $("historyPanel").classList.add("hidden");
  await loadPages("original", "origView");
  const s = await (await fetch(`/api/jobs/${jobId}`)).json();
  if (s.status === "done") {
    await loadPages("result", "transView");
    state.downloadWhich = "result";
    resetRefineUi();
    showStatus("statusDone");
  }
}

// ---- refined version (LLM + OCR, on demand) ----
function showRefineStatus(msg, kind) {
  const el = $("refineStatus");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden", "ok", "err");
  if (kind) el.classList.add(kind);
}

function resetRefineUi() {
  if (state.refinePoll) { clearInterval(state.refinePoll); state.refinePoll = null; }
  const btn = $("refineBtn");
  if (btn) btn.disabled = false;
  const el = $("refineStatus");
  if (el) el.classList.add("hidden");
}

async function startRefine() {
  const engine = $("engine").value;
  const key = (engine === "claude" || engine === "openai") ? getStoredKey(engine) : "";
  if (!key) { showRefineStatus(t("refineNeedsKey"), "err"); return; }
  if (!state.jobId) return;

  const fd = new FormData();
  fd.append("engine", engine);
  fd.append("api_key", key);
  let res;
  try { res = await fetch(`/api/jobs/${state.jobId}/refine`, { method: "POST", body: fd }); }
  catch { showRefineStatus(t("errNetUpload"), "err"); return; }
  if (!res.ok) { showRefineStatus((await safeDetail(res)) || t("refineFailed"), "err"); return; }

  $("refineBtn").disabled = true;
  showRefineStatus(t("refineStarting"), null);
  if (state.refinePoll) clearInterval(state.refinePoll);
  state.refinePoll = setInterval(async () => {
    let r;
    try { r = await fetch(`/api/jobs/${state.jobId}`); } catch { return; }
    if (!r.ok) return;
    const s = await r.json();
    if (s.refined_status === "running") {
      showRefineStatus(s.refined_page ? t("refining", s.refined_page) : t("refineStarting"), null);
    } else if (s.refined_status === "done") {
      clearInterval(state.refinePoll); state.refinePoll = null;
      await loadPages("refined", "transView");
      state.downloadWhich = "refined";
      showRefineStatus(t("refineReady"), "ok");
    } else if (s.refined_status === "error") {
      clearInterval(state.refinePoll); state.refinePoll = null;
      $("refineBtn").disabled = false;
      showRefineStatus(s.refined_error || t("refineFailed"), "err");
    }
  }, 1000);
}

function swapLangs() {
  const from = $("from"), to = $("to");
  // 'auto' has no slot in To; fall back to 'en' when swapping an auto source
  const newTo = from.value === "auto" ? "en" : from.value;
  const newFrom = to.value;
  from.value = newFrom;
  to.value = newTo;
  setBadges();
}

function wireUp() {
  const drop = $("dropzone");
  drop.addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", (e) => setFile(e.target.files[0]));
  ["dragover", "dragenter"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

  $("from").addEventListener("change", setBadges);
  $("to").addEventListener("change", setBadges);
  $("swapBtn").addEventListener("click", swapLangs);
  $("engine").addEventListener("change", refreshEngineUi);
  $("saveKeyBtn").addEventListener("click", saveKey);
  $("translateBtn").addEventListener("click", startTranslate);
  if ($("retryBtn")) $("retryBtn").addEventListener("click", startTranslate);
  if ($("langToggle")) $("langToggle").addEventListener("click", toggleLang);
  if ($("refineBtn")) $("refineBtn").addEventListener("click", startRefine);
  // #downloadBtn is a <button>; download the currently-shown version (fast or
  // refined). ?download=1 makes the server send it as an attachment.
  if ($("downloadBtn")) {
    $("downloadBtn").addEventListener("click", () => {
      if (state.jobId) {
        window.location.href =
          `/api/jobs/${state.jobId}/result?which=${state.downloadWhich || "result"}&download=1`;
      }
    });
  }
  $("historyBtn").addEventListener("click", () => {
    $("historyPanel").classList.toggle("hidden");
    if (!$("historyPanel").classList.contains("hidden")) refreshHistory();
  });
  if ($("historyClose")) {
    $("historyClose").addEventListener("click", () => $("historyPanel").classList.add("hidden"));
  }
  // Esc closes the history panel
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("historyPanel").classList.add("hidden");
  });

  // Language priority: explicit ?lang= override, then remembered choice, then EN.
  let saved = "en";
  try {
    const q = new URLSearchParams(location.search).get("lang");
    saved = (q && I18N[q] && q) || localStorage.getItem("pdftx_lang") || "en";
  } catch {}
  applyLang(saved);
  setBadges();
  showStatus("statusIdle");
}

document.addEventListener("DOMContentLoaded", wireUp);

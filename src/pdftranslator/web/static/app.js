const $ = (id) => document.getElementById(id);
const state = { file: null, jobId: null, poll: null, downloadUrl: null };

const LANG_BADGE = { auto: "AUTO", en: "EN", pt: "PT", zh: "ZH" };

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
  if (!isPdf) { showError("Please choose a PDF file."); return; }
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
async function refreshEngineUi() {
  const engine = $("engine").value;
  const needsKey = engine === "claude" || engine === "openai";
  $("apiKeyWrap").classList.toggle("hidden", !needsKey);
  if (needsKey) {
    try {
      const s = await (await fetch("/api/settings")).json();
      $("apiKey").placeholder = s[engine] ? "Key saved — enter a new one to replace" : "Paste your API key";
    } catch {}
  }
}

async function saveKey() {
  const engine = $("engine").value;
  const key = $("apiKey").value.trim();
  if (!key) return;
  const fd = new FormData();
  fd.append("engine", engine);
  fd.append("api_key", key);
  const res = await fetch("/api/settings", { method: "POST", body: fd });
  if (res.ok) { $("apiKey").value = ""; refreshEngineUi(); }
  else showError((await safeDetail(res)) || "Could not save key.");
}

// ---- translate ----
async function startTranslate() {
  if (!state.file) return;
  $("origView").innerHTML = "";
  $("transView").innerHTML = "";
  $("translateBtn").disabled = true;
  showStatus("statusProgress");
  setProgress(0, 0);

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("source", $("from").value);
  fd.append("target", $("to").value);
  fd.append("engine", $("engine").value);

  let res;
  try { res = await fetch("/api/translate", { method: "POST", body: fd }); }
  catch { return fail("Network error during upload."); }
  if (!res.ok) return fail((await safeDetail(res)) || "Upload failed.");

  const data = await res.json();
  state.jobId = data.job_id;
  loadText("original", "origView");
  pollStatus();
}

function setProgress(page, count) {
  // #progressBar is the TRACK <div>; the FILL is its child .progress-bar-fill.
  // Setting style.width on #progressBar itself does nothing visible.
  const fill = document.querySelector("#progressBar .progress-bar-fill");
  const pct = count > 0 ? Math.round((page / count) * 100) : 6;
  if (fill) fill.style.width = pct + "%";
  $("progressText").textContent = count ? `Translating page ${page} of ${count}…` : "Starting…";
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
      await loadText("result", "transView");
      // #downloadBtn is a <button>, not <a> — store URL and trigger via click handler
      state.downloadUrl = `/api/jobs/${state.jobId}/result`;
      showStatus("statusDone");
      $("translateBtn").disabled = false;
      refreshHistory();
    } else if (s.status === "error") {
      fail(s.error || "Translation failed.");
    }
  }, 1000);
}

// ---- text-reader panes ----
async function loadText(which, viewId) {
  const view = $(viewId);
  view.innerHTML = "";
  let res;
  try { res = await fetch(`/api/jobs/${state.jobId}/text?which=${which}`); }
  catch { view.textContent = "Preview unavailable."; return; }
  if (!res.ok) { view.textContent = "Preview unavailable."; return; }
  const { pages } = await res.json();
  pages.forEach((text, i) => {
    if (i > 0) {
      const marker = document.createElement("div");
      marker.className = "pagemarker";
      marker.textContent = which === "result" ? `第 ${i + 1} 页` : `PAGE ${i + 1}`;
      view.appendChild(marker);
    }
    const p = document.createElement("div");
    p.className = "pagetext";
    p.textContent = text;
    view.appendChild(p);
  });
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
    btn.textContent = `${j.filename} · ${(j.source || "auto").toUpperCase()}→${(j.target || "").toUpperCase()} · ${j.status}`;
    btn.addEventListener("click", () => openHistory(j.id));
    li.appendChild(btn);
    list.appendChild(li);
  });
}

async function openHistory(jobId) {
  state.jobId = jobId;
  $("historyPanel").classList.add("hidden");
  await loadText("original", "origView");
  const s = await (await fetch(`/api/jobs/${jobId}`)).json();
  if (s.status === "done") {
    await loadText("result", "transView");
    state.downloadUrl = `/api/jobs/${jobId}/result`;
    showStatus("statusDone");
  }
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
  // #downloadBtn is a <button>; navigate to the stored download URL on click
  if ($("downloadBtn")) {
    $("downloadBtn").addEventListener("click", () => {
      if (state.downloadUrl) window.location.href = state.downloadUrl;
    });
  }
  $("historyBtn").addEventListener("click", () => {
    $("historyPanel").classList.toggle("hidden");
    refreshHistory();
  });

  setBadges();
  refreshEngineUi();
  showStatus("statusIdle");
}

document.addEventListener("DOMContentLoaded", wireUp);

const state = { file: null, jobId: null, poll: null };
const $ = (id) => document.getElementById(id);

function showError(msg) { const e = $("error"); e.textContent = msg; e.classList.remove("hidden"); }
function clearError() { $("error").classList.add("hidden"); }
function stopPoll() { if (state.poll) { clearInterval(state.poll); state.poll = null; } }
function fail(msg) { stopPoll(); $("progressWrap").classList.add("hidden"); $("translateBtn").disabled = false; showError(msg); }

function setProgress(page, count, text) {
  $("progressWrap").classList.remove("hidden");
  const pct = count > 0 ? Math.round((page / count) * 100) : 5;
  $("progressBar").style.width = pct + "%";
  $("progressText").textContent = text;
}

function setFile(f) {
  if (!f) return;
  const isPdf = f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) { showError("Please choose a PDF file."); return; }
  clearError();
  state.file = f;
  $("filename").textContent = f.name;
  $("translateBtn").disabled = false;
}

async function safeDetail(res) {
  try { const j = await res.json(); return j.detail; } catch { return null; }
}

async function startTranslate() {
  if (!state.file) return;
  clearError();
  $("download").classList.add("hidden");
  $("transFrame").removeAttribute("src");
  $("translateBtn").disabled = true;
  setProgress(0, 0, "Uploading…");

  const fd = new FormData();
  fd.append("file", state.file);
  fd.append("source", $("from").value);
  fd.append("target", $("to").value);

  let res;
  try { res = await fetch("/api/translate", { method: "POST", body: fd }); }
  catch { return fail("Network error during upload."); }
  if (!res.ok) { return fail((await safeDetail(res)) || "Upload failed."); }

  const { job_id } = await res.json();
  state.jobId = job_id;
  $("origFrame").src = `/api/jobs/${job_id}/original`;
  pollStatus();
}

function pollStatus() {
  stopPoll();
  state.poll = setInterval(async () => {
    let res;
    try { res = await fetch(`/api/jobs/${state.jobId}`); } catch { return; }
    if (!res.ok) return;
    const s = await res.json();
    if (s.status === "running") {
      setProgress(s.page, s.page_count, s.page_count ? `Translating page ${s.page} / ${s.page_count}…` : "Starting…");
    } else if (s.status === "done") {
      stopPoll();
      setProgress(1, 1, "Done");
      const url = `/api/jobs/${state.jobId}/result`;
      $("transFrame").src = url;
      const dl = $("download");
      dl.href = url;
      dl.classList.remove("hidden");
      $("translateBtn").disabled = false;
    } else if (s.status === "error") {
      fail(s.error || "Translation failed.");
    }
  }, 1000);
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
  $("translateBtn").addEventListener("click", startTranslate);
}

document.addEventListener("DOMContentLoaded", wireUp);

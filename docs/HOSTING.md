# Hosting pdfTranslator online

Run the translator as a public website — visitors use it in their browser with
nothing to download. It's the same FastAPI app, served from a cloud host.

## Key handling on a public site (important)

The hosted build runs in **bring-your-own-key (BYOK)** mode
(`PDFTRANSLATOR_BYOK_ONLY=1`, already set in `render.yaml` and the `Dockerfile`):

- The free **Google** engine needs no key and works for everyone.
- For **Claude / ChatGPT**, each visitor pastes their *own* key. It's kept only
  in their browser (`localStorage`), sent over HTTPS with each translation, and
  **never written to or read from the server**. The server also refuses to
  persist any key in this mode.
- This keeps your costs at zero and means one visitor can't spend another's
  quota. Tell users to use a scoped key with a spending limit and to rotate it
  afterward. The desktop app remains the most private option (key never leaves
  their machine).

Always serve over **HTTPS** so keys are encrypted in transit — every option
below does this automatically.

## Option 1 — Render (easiest, free tier)

1. Push this repo to GitHub (already done for the standalone repo).
2. On [render.com](https://render.com): **New → Blueprint**, select the repo.
   Render reads `render.yaml` and provisions the service.
3. Deploy. You get a public `https://<name>.onrender.com` URL.

Free instances sleep after ~15 min idle, so the first visit after a lull takes
~30–60 s to wake (cold start). Upgrade to a paid instance to keep it always-on.

## Option 2 — Any container host (Docker)

The `Dockerfile` runs anywhere containers do — Fly.io, Railway, Google Cloud
Run, a VPS, etc.:

```bash
docker build -t pdftranslator .
docker run -p 8000:8000 pdftranslator
# open http://localhost:8000
```

Platforms that inject a `$PORT` are handled automatically.

## Notes & limits

- **Jobs are in-memory.** Translation jobs (and their history) live in the
  server's RAM and are cleared on restart/redeploy. Fine for on-demand use; the
  app needs no database.
- **Single instance.** The in-memory job store assumes one instance. Don't scale
  to multiple replicas without moving jobs to shared storage first.
- **Memory.** PyMuPDF renders pages to images for the preview; small/medium PDFs
  fit comfortably in a 512 MB free instance.
- **Private deployment.** For a trusted single-user/internal deploy where saving
  a key on the server is acceptable, set `PDFTRANSLATOR_BYOK_ONLY=0`.

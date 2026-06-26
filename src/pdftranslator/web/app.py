import io
import os
import secrets
import sys
from pathlib import Path

import fitz
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import settings
from ..core import lang, providers
from .jobs import JobStore


def _static_dir() -> Path:
    """Locate the bundled static assets, whether running from source or frozen.

    PyInstaller extracts data files under sys._MEIPASS; when running normally
    __file__ resolves the package directory. Both place the assets at the same
    relative path (pdftranslator/web/static).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / "pdftranslator" / "web" / "static"
    return Path(__file__).parent / "static"


STATIC_DIR = _static_dir()
PREVIEW_DPI = 110


def _byok_only() -> bool:
    """Hosted (public) mode: keys are bring-your-own, sent per request and never
    stored server-side. Set PDFTRANSLATOR_BYOK_ONLY=1 on a shared deployment so
    no key is ever written to (or read from) the server's config file. Off by
    default, which keeps the local desktop convenience of a machine-saved key.
    """
    return os.environ.get("PDFTRANSLATOR_BYOK_ONLY", "").lower() in ("1", "true", "yes")


_SID_COOKIE = "pdftx_sid"


def _client_id(request: Request, response: Response) -> str:
    """Anonymous per-browser session id, used to keep each user's translation
    history private. Issued as an httpOnly cookie on first contact; no login.
    """
    sid = request.cookies.get(_SID_COOKIE)
    if not sid:
        sid = secrets.token_urlsafe(16)
        response.set_cookie(
            _SID_COOKIE, sid, max_age=60 * 60 * 24 * 30,
            httponly=True, samesite="lax",
        )
    return sid


def _page_texts(path: Path) -> list[str]:
    doc = fitz.open(path)
    try:
        return [doc[i].get_text("text") for i in range(doc.page_count)]
    finally:
        doc.close()


def create_app(store: JobStore | None = None) -> FastAPI:
    app = FastAPI(title="PDF Translator")
    app.state.store = store or JobStore()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def _get_owned(job_id: str, owner: str):
        """Fetch a job only if it belongs to this user; otherwise 404 (we never
        reveal that another user's job exists)."""
        job = app.state.store.get(job_id)
        if job is None or job.owner != owner:
            raise HTTPException(status_code=404, detail="unknown job")
        return job

    @app.get("/", response_class=HTMLResponse)
    def index(owner: str = Depends(_client_id)) -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.post("/api/translate")
    async def translate(
        file: UploadFile = File(...),
        source: str = Form(...),
        target: str = Form(...),
        engine: str = Form("google"),
        # Bring-your-own-key: sent with the request, used only to build the
        # provider for this translation, and never stored or logged.
        api_key: str | None = Form(None),
        owner: str = Depends(_client_id),
    ) -> dict:
        try:
            lang.validate_source(source)
            lang.validate_target(target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        key = None
        if engine in ("claude", "openai"):
            key = (api_key or "").strip()
            # Fall back to a machine-saved key only in local desktop mode.
            if not key and not _byok_only():
                key = settings.get_key(engine) or ""
            if not key:
                label = "Claude" if engine == "claude" else "OpenAI"
                raise HTTPException(status_code=400, detail=f"Add your {label} API key first.")
        try:
            provider = providers.build_provider(engine, api_key=key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty file")
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="not a PDF file")
        try:
            doc = fitz.open(stream=data, filetype="pdf")
            page_count = doc.page_count
            doc.close()
        except Exception:
            raise HTTPException(status_code=400, detail="could not read PDF")

        job = app.state.store.create(
            data, source, target,
            engine=engine, provider=provider,
            filename=file.filename or "document.pdf", page_count=page_count,
            owner=owner,
        )
        return {"job_id": job.id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str, owner: str = Depends(_client_id)) -> dict:
        job = _get_owned(job_id, owner)
        return {
            "status": job.status,
            "page": job.page,
            "page_count": job.page_count,
            "error": job.error,
            "filename": job.filename,
            "size_bytes": job.size_bytes,
            "source": job.source,
            "target": job.target,
            "engine": job.engine,
        }

    @app.get("/api/jobs/{job_id}/original")
    def job_original(job_id: str, owner: str = Depends(_client_id)):
        job = _get_owned(job_id, owner)
        # Inline so the browser renders it in the preview iframe (not download).
        return FileResponse(
            job.input_path, media_type="application/pdf",
            filename="original.pdf", content_disposition_type="inline",
        )

    @app.get("/api/jobs/{job_id}/result")
    def job_result(job_id: str, owner: str = Depends(_client_id)):
        job = _get_owned(job_id, owner)
        if job.status != "done":
            raise HTTPException(status_code=404, detail="result not ready")
        # Inline so it renders in the preview iframe; the Download button's
        # anchor carries `download`, which forces a save when clicked.
        return FileResponse(
            job.output_path, media_type="application/pdf",
            filename="translated.pdf", content_disposition_type="inline",
        )

    def _pdf_path(job, which: str) -> Path:
        # Resolve which document to preview. Rendering to images (below) avoids
        # the browser's PDF-in-iframe download behavior entirely.
        if which == "original":
            return job.input_path
        if which == "result":
            if job.status != "done":
                raise HTTPException(status_code=404, detail="result not ready")
            return job.output_path
        raise HTTPException(status_code=400, detail="invalid document")

    @app.get("/api/jobs/{job_id}/pages")
    def job_pages(job_id: str, which: str = "result", owner: str = Depends(_client_id)) -> dict:
        job = _get_owned(job_id, owner)
        path = _pdf_path(job, which)
        doc = fitz.open(path)
        try:
            return {"pages": doc.page_count}
        finally:
            doc.close()

    @app.get("/api/jobs/{job_id}/page/{which}/{n}")
    def job_page(job_id: str, which: str, n: int, owner: str = Depends(_client_id)):
        job = _get_owned(job_id, owner)
        path = _pdf_path(job, which)
        doc = fitz.open(path)
        try:
            if n < 0 or n >= doc.page_count:
                raise HTTPException(status_code=404, detail="no such page")
            png = doc[n].get_pixmap(dpi=PREVIEW_DPI).tobytes("png")
        finally:
            doc.close()
        return Response(content=png, media_type="image/png")

    @app.get("/api/jobs")
    def jobs_list(owner: str = Depends(_client_id)) -> list:
        return [
            {
                "id": j.id,
                "filename": j.filename,
                "source": j.source,
                "target": j.target,
                "engine": j.engine,
                "status": j.status,
                "page_count": j.page_count,
                "created_at": j.created_at,
            }
            for j in app.state.store.list(owner=owner)
        ]

    @app.get("/api/jobs/{job_id}/text")
    def job_text(job_id: str, which: str = "result", owner: str = Depends(_client_id)) -> dict:
        job = _get_owned(job_id, owner)
        if which == "original":
            path = job.input_path
        elif which == "result":
            if job.status != "done":
                raise HTTPException(status_code=404, detail="result not ready")
            path = job.output_path
        else:
            raise HTTPException(status_code=400, detail="invalid document")
        return {"pages": _page_texts(path)}

    @app.get("/api/settings")
    def get_settings() -> dict:
        return {"claude": settings.has_key("claude"), "openai": settings.has_key("openai")}

    @app.post("/api/settings")
    def save_settings(engine: str = Form(...), api_key: str = Form(...)) -> dict:
        if _byok_only():
            # Public deployment: refuse to persist any key on the server.
            raise HTTPException(
                status_code=403,
                detail="Server-side key storage is disabled. Your key stays in your browser.",
            )
        try:
            settings.set_key(engine, api_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    return app


app = create_app()

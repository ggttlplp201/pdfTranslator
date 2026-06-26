from pathlib import Path

import fitz
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from ..core import lang
from .jobs import JobStore

STATIC_DIR = Path(__file__).parent / "static"
PREVIEW_DPI = 110


def create_app(store: JobStore | None = None) -> FastAPI:
    app = FastAPI(title="PDF Translator")
    app.state.store = store or JobStore()
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.post("/api/translate")
    async def translate(
        file: UploadFile = File(...),
        source: str = Form(...),
        target: str = Form(...),
    ) -> dict:
        try:
            lang.validate_source(source)
            lang.validate_target(target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty file")
        # Magic-byte sniff (not full validation — just rejects obvious non-PDFs)
        if not data.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail="not a PDF file")
        job = app.state.store.create(data, source, target)
        return {"job_id": job.id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict:
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return {
            "status": job.status,
            "page": job.page,
            "page_count": job.page_count,
            "error": job.error,
        }

    @app.get("/api/jobs/{job_id}/original")
    def job_original(job_id: str):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        # Inline so the browser renders it in the preview iframe (not download).
        return FileResponse(
            job.input_path, media_type="application/pdf",
            filename="original.pdf", content_disposition_type="inline",
        )

    @app.get("/api/jobs/{job_id}/result")
    def job_result(job_id: str):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
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
    def job_pages(job_id: str, which: str = "result") -> dict:
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        path = _pdf_path(job, which)
        doc = fitz.open(path)
        try:
            return {"pages": doc.page_count}
        finally:
            doc.close()

    @app.get("/api/jobs/{job_id}/page/{which}/{n}")
    def job_page(job_id: str, which: str, n: int):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        path = _pdf_path(job, which)
        doc = fitz.open(path)
        try:
            if n < 0 or n >= doc.page_count:
                raise HTTPException(status_code=404, detail="no such page")
            png = doc[n].get_pixmap(dpi=PREVIEW_DPI).tobytes("png")
        finally:
            doc.close()
        return Response(content=png, media_type="image/png")

    return app


app = create_app()

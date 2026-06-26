from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..core import lang
from .jobs import JobStore

STATIC_DIR = Path(__file__).parent / "static"


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
        if not data[:5].startswith(b"%PDF"):
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
        return FileResponse(job.input_path, media_type="application/pdf", filename="original.pdf")

    @app.get("/api/jobs/{job_id}/result")
    def job_result(job_id: str):
        job = app.state.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="unknown job")
        if job.status != "done":
            raise HTTPException(status_code=404, detail="result not ready")
        return FileResponse(job.output_path, media_type="application/pdf", filename="translated.pdf")

    return app


app = create_app()

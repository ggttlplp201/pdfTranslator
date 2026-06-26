import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import engine


@dataclass
class Job:
    id: str
    source: str
    target: str
    engine: str
    filename: str
    size_bytes: int
    page_count: int
    input_path: Path
    output_path: Path
    tmpdir: Path
    provider: object = None
    created_at: float = 0.0
    status: str = "running"
    page: int = 0
    error: Optional[str] = None
    owner: str = ""  # anonymous per-browser session id; isolates one user's history
    thread: Optional[threading.Thread] = field(default=None, repr=False, compare=False)


class JobStore:
    def __init__(self, max_jobs: int = 20, runner: Optional[Callable[[Job], None]] = None):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._max_jobs = max_jobs
        self._runner = runner or self._translate

    def create(self, data: bytes, source: str, target: str, *, engine: str = "google",
               provider: object = None, filename: str = "document.pdf",
               page_count: int = 0, owner: str = "") -> Job:
        job_id = uuid.uuid4().hex
        tmpdir = Path(tempfile.mkdtemp(prefix="pdftr-"))
        input_path = tmpdir / "input.pdf"
        output_path = tmpdir / "output.pdf"
        input_path.write_bytes(data)
        job = Job(
            id=job_id, source=source, target=target, engine=engine,
            filename=filename, size_bytes=len(data), page_count=page_count,
            input_path=input_path, output_path=output_path, tmpdir=tmpdir,
            provider=provider, created_at=time.time(), owner=owner,
        )
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._evict_locked()
        thread = threading.Thread(target=self._execute, args=(job,), daemon=True)
        job.thread = thread
        thread.start()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, owner: Optional[str] = None) -> list[Job]:
        with self._lock:
            jobs = [self._jobs[i] for i in reversed(self._order) if i in self._jobs]
        # Only return the requesting user's own jobs (history is private per user).
        if owner is not None:
            jobs = [j for j in jobs if j.owner == owner]
        return jobs

    def _evict_locked(self) -> None:
        while len(self._order) > self._max_jobs:
            victim_id = None
            for jid in self._order:
                j = self._jobs.get(jid)
                if j is None or j.status != "running":
                    victim_id = jid
                    break
            if victim_id is None:
                break
            self._order.remove(victim_id)
            old = self._jobs.pop(victim_id, None)
            if old is not None:
                shutil.rmtree(old.tmpdir, ignore_errors=True)

    def _execute(self, job: Job) -> None:
        try:
            self._runner(job)
            job.status = "done"
        except Exception as exc:  # surfaced to the user as a job error
            job.status = "error"
            job.error = f"Translation failed: {exc}"

    def _translate(self, job: Job) -> None:
        if job.provider is None:
            raise RuntimeError("no translation provider configured")

        def progress(index: int, count: int) -> None:
            job.page = index + 1

        engine.translate_pdf(
            str(job.input_path), str(job.output_path),
            source=job.source, target=job.target,
            provider=job.provider, progress=progress,
        )

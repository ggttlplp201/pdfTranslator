import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..core import engine, providers


@dataclass
class Job:
    id: str
    source: str
    target: str
    provider_name: str
    input_path: Path
    output_path: Path
    tmpdir: Path
    status: str = "running"
    page: int = 0
    page_count: int = 0
    error: Optional[str] = None
    thread: Optional[threading.Thread] = field(default=None, repr=False, compare=False)


class JobStore:
    def __init__(self, max_jobs: int = 20, runner: Optional[Callable[[Job], None]] = None):
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._max_jobs = max_jobs
        self._runner = runner or self._translate

    def create(self, data: bytes, source: str, target: str, provider_name: str = "google") -> Job:
        job_id = uuid.uuid4().hex
        tmpdir = Path(tempfile.mkdtemp(prefix="pdftr-"))
        input_path = tmpdir / "input.pdf"
        output_path = tmpdir / "output.pdf"
        input_path.write_bytes(data)
        job = Job(
            id=job_id, source=source, target=target, provider_name=provider_name,
            input_path=input_path, output_path=output_path, tmpdir=tmpdir,
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

    def _evict_locked(self) -> None:
        while len(self._order) > self._max_jobs:
            old_id = self._order.pop(0)
            old = self._jobs.pop(old_id, None)
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
        provider = providers.build_provider(job.provider_name)

        def progress(index: int, count: int) -> None:
            job.page = index + 1
            job.page_count = count

        engine.translate_pdf(
            str(job.input_path), str(job.output_path),
            source=job.source, target=job.target,
            provider=provider, progress=progress,
        )

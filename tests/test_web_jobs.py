import time

import requests
from pdftranslator.web.jobs import JobStore


def test_job_runs_to_done_with_metadata():
    def fake_runner(job):
        job.page = job.page_count

    store = JobStore(runner=fake_runner)
    job = store.create(
        b"%PDF-1.4 data", "auto", "zh",
        engine="google", filename="report.pdf", page_count=3,
    )
    job.thread.join(timeout=5)

    got = store.get(job.id)
    assert got.status == "done"
    assert got.filename == "report.pdf"
    assert got.size_bytes == len(b"%PDF-1.4 data")
    assert got.page_count == 3
    assert got.engine == "google"
    assert got.created_at > 0


def test_runner_failure_sets_error():
    def boom(job):
        raise requests.RequestException("rate limited")

    store = JobStore(runner=boom)
    job = store.create(b"%PDF", "auto", "en")
    job.thread.join(timeout=5)
    assert store.get(job.id).status == "error"
    assert "rate limited" in store.get(job.id).error


def test_default_runner_requires_provider():
    # No runner injected and no provider → the job ends in error, not a crash.
    store = JobStore()
    job = store.create(b"%PDF", "auto", "en", provider=None)
    job.thread.join(timeout=5)
    assert store.get(job.id).status == "error"


def test_list_returns_newest_first():
    def fake_runner(job):
        job.page = 1

    store = JobStore(runner=fake_runner)
    a = store.create(b"%PDF", "auto", "en", filename="a.pdf")
    b = store.create(b"%PDF", "auto", "en", filename="b.pdf")
    a.thread.join(timeout=5)
    b.thread.join(timeout=5)
    names = [j.filename for j in store.list()]
    assert names[0] == "b.pdf" and names[1] == "a.pdf"


def test_store_evicts_oldest_terminal_and_removes_tmpdir():
    def fake_runner(job):
        job.page = 1

    store = JobStore(max_jobs=2, runner=fake_runner)
    jobs = [store.create(b"%PDF", "auto", "en") for _ in range(3)]
    for j in jobs:
        j.thread.join(timeout=5)
    assert store.get(jobs[0].id) is None
    assert not jobs[0].tmpdir.exists()
    assert store.get(jobs[2].id) is not None

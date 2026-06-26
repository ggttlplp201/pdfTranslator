import threading

import requests
from pdftranslator.web.jobs import JobStore


def test_job_runs_to_done_and_records_progress():
    def fake_runner(job):
        job.page_count = 2
        job.page = 2

    store = JobStore(runner=fake_runner)
    job = store.create(b"%PDF-1.4 fake", "auto", "en")
    job.thread.join(timeout=5)

    got = store.get(job.id)
    assert got.status == "done"
    assert got.page == 2 and got.page_count == 2
    assert job.input_path.read_bytes() == b"%PDF-1.4 fake"


def test_job_runner_failure_sets_error():
    def boom(job):
        raise requests.RequestException("rate limited")

    store = JobStore(runner=boom)
    job = store.create(b"%PDF", "auto", "en")
    job.thread.join(timeout=5)

    got = store.get(job.id)
    assert got.status == "error"
    assert "rate limited" in got.error


def test_store_evicts_oldest_and_removes_tmpdir():
    """Oldest terminal job is evicted when the cap is exceeded."""
    def fake_runner(job):
        job.page_count = 1
        job.page = 1

    store = JobStore(max_jobs=2, runner=fake_runner)
    jobs = []
    for _ in range(3):
        j = store.create(b"%PDF", "auto", "en")
        j.thread.join(timeout=5)  # ensure terminal before next job triggers eviction
        jobs.append(j)

    assert store.get(jobs[0].id) is None
    assert not jobs[0].tmpdir.exists()
    assert store.get(jobs[2].id) is not None


def test_store_keeps_running_jobs_over_cap():
    """Running jobs are never evicted even when the store exceeds its cap."""
    gate = threading.Event()

    def blocking_runner(job):
        gate.wait()  # block until released

    store = JobStore(max_jobs=2, runner=blocking_runner)
    jobs = []
    try:
        for _ in range(3):
            jobs.append(store.create(b"%PDF", "auto", "en"))

        # Oldest job is still running — must NOT have been evicted
        assert store.get(jobs[0].id) is not None, "running job should not be evicted"
    finally:
        gate.set()  # release all blocked threads so they can finish
        for j in jobs:
            j.thread.join(timeout=5)

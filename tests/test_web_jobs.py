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
    def fake_runner(job):
        job.page_count = 1
        job.page = 1

    store = JobStore(max_jobs=2, runner=fake_runner)
    jobs = [store.create(b"%PDF", "auto", "en") for _ in range(3)]
    for j in jobs:
        j.thread.join(timeout=5)

    assert store.get(jobs[0].id) is None
    assert not jobs[0].tmpdir.exists()
    assert store.get(jobs[2].id) is not None

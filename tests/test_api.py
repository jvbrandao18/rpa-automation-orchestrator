def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_echo_job_runs_asynchronously_in_eager_mode(client):
    response = client.post(
        "/jobs",
        json={
            "name": "Echo invoice metadata",
            "task_type": "echo",
            "payload": {"message": "invoice captured", "invoice_id": "INV-100"},
            "max_retries": 0,
            "timeout_seconds": 5,
        },
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "success"
    assert job["attempt"] == 1
    assert job["result"]["message"] == "invoice captured"

    list_response = client.get("/jobs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_get_job_by_id(client):
    create_response = client.post(
        "/jobs",
        json={
            "name": "Fetch customer record",
            "task_type": "echo",
            "payload": {"customer_id": "C-100"},
        },
    )
    created_job = create_response.json()

    response = client.get(f"/jobs/{created_job['id']}")

    assert response.status_code == 200
    job = response.json()
    assert job["id"] == created_job["id"]
    assert job["name"] == "Fetch customer record"
    assert job["status"] == "success"


def test_get_unknown_job_returns_404(client):
    response = client.get("/jobs/not-a-real-job")

    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"


def test_failed_job_retries_until_max_retries_is_exhausted(client):
    response = client.post(
        "/jobs",
        json={
            "name": "Submit portal form",
            "task_type": "fail",
            "payload": {"error": "portal returned validation error"},
            "max_retries": 2,
            "timeout_seconds": 5,
        },
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "failed"
    assert job["attempt"] == 3
    assert job["max_retries"] == 2
    assert "validation error" in job["error"]


def test_timeout_is_enforced(client):
    response = client.post(
        "/jobs",
        json={
            "name": "Wait for download",
            "task_type": "sleep",
            "payload": {"duration": 1.5},
            "max_retries": 0,
            "timeout_seconds": 1,
        },
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "failed"
    assert job["attempt"] == 1
    assert "timeout" in job["error"]
    assert "exceeded timeout" in job["error"]


def test_timeout_retries_until_max_retries_is_exhausted(client):
    response = client.post(
        "/jobs",
        json={
            "name": "Retry slow download",
            "task_type": "sleep",
            "payload": {"duration": 1.5},
            "max_retries": 2,
            "timeout_seconds": 1,
        },
    )

    assert response.status_code == 201
    job = response.json()
    assert job["status"] == "failed"
    assert job["attempt"] == 3
    assert job["max_retries"] == 2
    assert "timeout" in job["error"]


def test_atomic_claim_allows_only_one_worker():
    from app.database import SessionLocal
    from app.job_service import claim_job_for_execution, dumps
    from app.models import Job, JobStatus, TaskType

    with SessionLocal() as db:
        job = Job(
            name="Atomic claim",
            task_type=TaskType.ECHO.value,
            payload=dumps({"message": "run once"}),
            status=JobStatus.PENDING.value,
        )
        db.add(job)
        db.commit()
        job_id = job.id

    with SessionLocal() as db:
        claimed = claim_job_for_execution(db, job_id, "task-1")

    with SessionLocal() as db:
        duplicate = claim_job_for_execution(db, job_id, "task-2")
        stored = db.get(Job, job_id)

    assert claimed is not None
    assert claimed.status == "running"
    assert claimed.attempt == 1
    assert duplicate is None
    assert stored.status == "running"
    assert stored.attempt == 1
    assert stored.celery_task_id == "task-1"


def test_manual_retry_requeues_terminal_job(client):
    create_response = client.post(
        "/jobs",
        json={
            "name": "Retry failed export",
            "task_type": "fail",
            "payload": {"error": "export button not found"},
            "max_retries": 0,
            "timeout_seconds": 5,
        },
    )
    failed_job = create_response.json()
    assert failed_job["status"] == "failed"

    retry_response = client.post(f"/jobs/{failed_job['id']}/retry", json={"max_retries": 1})

    assert retry_response.status_code == 200
    retried_job = retry_response.json()
    assert retried_job["status"] == "failed"
    assert retried_job["attempt"] == 2
    assert retried_job["max_retries"] == 1


def test_worker_skips_terminal_jobs(client):
    from app.tasks import run_job

    create_response = client.post(
        "/jobs",
        json={
            "name": "Already complete",
            "task_type": "echo",
            "payload": {"message": "done"},
        },
    )
    completed_job = create_response.json()
    assert completed_job["status"] == "success"

    result = run_job.apply(args=[completed_job["id"]]).get()
    response = client.get(f"/jobs/{completed_job['id']}")

    assert result["skipped"] is True
    assert response.json()["status"] == "success"
    assert response.json()["attempt"] == 1


def test_retry_unknown_job_returns_404(client):
    response = client.post("/jobs/not-a-real-job/retry", json={})

    assert response.status_code == 404
    assert response.json()["detail"] == "job not found"


def test_retry_rejects_non_terminal_job(client, monkeypatch):
    def skip_enqueue(_job_id):
        return "queued-but-not-run"

    monkeypatch.setattr("app.main.enqueue_job", skip_enqueue)

    create_response = client.post(
        "/jobs",
        json={
            "name": "Pending approval",
            "task_type": "echo",
            "payload": {"document": "PO-100"},
        },
    )
    pending_job = create_response.json()

    response = client.post(f"/jobs/{pending_job['id']}/retry", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "job is already pending"


def test_list_jobs_can_filter_by_status(client):
    client.post("/jobs", json={"name": "A", "task_type": "echo", "payload": {}})
    client.post("/jobs", json={"name": "B", "task_type": "fail", "payload": {}, "max_retries": 0})

    response = client.get("/jobs", params={"status": "success"})

    assert response.status_code == 200
    jobs = response.json()
    assert len(jobs) == 1
    assert jobs[0]["name"] == "A"


def test_create_job_validates_payload(client):
    response = client.post(
        "/jobs",
        json={
            "name": "",
            "task_type": "unknown",
            "payload": {},
            "max_retries": -1,
            "timeout_seconds": 0,
        },
    )

    assert response.status_code == 422


def test_create_job_returns_503_when_queue_is_unavailable(client, monkeypatch):
    def fail_enqueue(_job_id):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr("app.main.enqueue_job", fail_enqueue)

    response = client.post("/jobs", json={"name": "Queue outage", "task_type": "echo", "payload": {}})

    assert response.status_code == 503
    assert response.json()["detail"] == "job queue is unavailable"

    jobs = client.get("/jobs").json()
    assert jobs[0]["status"] == "failed"
    assert "queue unavailable" in jobs[0]["error"]

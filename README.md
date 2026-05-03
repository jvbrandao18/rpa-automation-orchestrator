# RPA Automation Orchestrator

RPA Automation Orchestrator is a FastAPI backend that accepts automation jobs, queues them with Celery and Redis, executes them asynchronously, and tracks job state in SQLite.

## What is it?

It is a small job orchestration API for simulated automation tasks.

The API can:

- create and enqueue automation jobs
- list jobs and filter them by status
- retrieve a single job
- retry terminal jobs
- track lifecycle states such as `pending`, `running`, `success`, `failed`, and `retrying`
- expose a basic monitoring dashboard
- expose a health check

The automation work is intentionally simulated. The project focuses on orchestration, queueing, retries, timeouts, persistence, and observability.

## Why was it built?

RPA and back-office automation workflows often need more than a direct HTTP request. They need queued execution, worker processing, retry behavior, timeout handling, and a way to inspect what happened after a job starts.

This project was built to demonstrate those backend patterns in a local, understandable system. It shows API-driven job orchestration, worker-backed execution, explicit state transitions, durable job tracking, structured logging, Docker Compose setup, and test coverage for the API and worker behavior.

## How does it work?

A client sends a job with `name`, `task_type`, `payload`, `max_retries`, and `timeout_seconds`.

The API stores the job in SQLite and publishes work to Redis. A Celery worker consumes the queued job, claims it, runs the simulated automation task, and updates the job record as it moves through its lifecycle.

Workers avoid executing jobs that are already terminal or already running. Retry behavior is bounded by `max_retries`, and timeout exhaustion is recorded as a failed terminal result.

### Main technologies

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- SQLite
- Celery
- Redis
- Pytest
- Docker Compose

### API endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/jobs` | Create and enqueue a job |
| `GET` | `/jobs` | List jobs, optionally filtered by status |
| `GET` | `/jobs/{job_id}` | Retrieve a single job |
| `POST` | `/jobs/{job_id}/retry` | Retry a terminal job |
| `GET` | `/dashboard` | Basic job monitoring dashboard |
| `GET` | `/docs` | Swagger API documentation |

### Task types

| Task type | Behavior |
| --- | --- |
| `echo` | Returns the provided payload and succeeds |
| `sleep` | Sleeps for `payload.duration` seconds and fails if it exceeds `timeout_seconds` |
| `fail` | Raises a simulated automation error for retry testing |

### Example usage

```bash
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Submit vendor portal form",
    "task_type": "fail",
    "payload": {
      "error": "portal returned validation error"
    },
    "max_retries": 2,
    "timeout_seconds": 10
  }'
```

### Project structure

```text
app/
  automation.py       Simulated automation task execution
  celery_app.py       Celery configuration
  config.py           Environment-based settings
  database.py         SQLAlchemy engine and session setup
  job_service.py      Job serialization and state transitions
  logging_config.py   Structured JSON logging
  main.py             FastAPI routes and dashboard
  models.py           SQLAlchemy models and enums
  schemas.py          Pydantic request and response schemas
  tasks.py            Celery worker task and retry scheduling
tests/
  conftest.py
  test_api.py
docker-compose.yml
Dockerfile
requirements.txt
pytest.ini
```

## How do I run it?

### Run with Docker Compose

```bash
docker compose up --build
```

Open:

- Dashboard: `http://localhost:8000/dashboard`
- Swagger docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

Stop the stack:

```bash
docker compose down
```

Reset persisted job data:

```bash
docker compose down -v
```

### Run locally

Local execution requires Redis to be running and reachable through `REDIS_URL`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

In another terminal, start the worker:

```bash
celery -A app.celery_app.celery_app worker --loglevel=info --concurrency=2
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Tests and validation

```bash
pytest
```

The test suite runs Celery in eager mode, so Redis is not required for tests.

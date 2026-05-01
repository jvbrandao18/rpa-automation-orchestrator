# RPA Automation Orchestrator

A production-oriented automation orchestrator built with FastAPI, Celery, Redis, and SQLite.

The project demonstrates how to accept automation jobs through an API, enqueue them for asynchronous execution, process them with distributed workers, and track job lifecycle state with retries, timeout handling, structured logging, and a lightweight monitoring dashboard.

## Features

- Create, list, inspect, and retry automation jobs
- Asynchronous job execution through Celery workers
- Redis-backed job queue
- SQLite-backed job persistence
- Lifecycle tracking for `pending`, `running`, `success`, `failed`, and `retrying`
- Configurable `max_retries` and `timeout_seconds`
- Timeout exhaustion is recorded as a failed job with a timeout error
- Safe retry behavior for terminal jobs
- Structured JSON logs for API and worker events
- Basic dashboard at `/dashboard`
- Swagger documentation at `/docs`
- Docker Compose setup for local execution
- Docker healthchecks for Redis and the API
- GitHub Actions CI for pytest on push and pull request
- Pytest suite with Celery eager-mode testing

## Architecture

```text
Client / Dashboard
        |
        v
FastAPI API
        |
        | create / read / update jobs
        v
SQLite
        ^
        | state transitions
        |
Celery Worker
        ^
        |
Redis Queue
        ^
        |
FastAPI API
```

The API stores jobs in SQLite and publishes work to Redis. Celery workers consume queued jobs, execute the simulated automation task, and update the job record as it moves through its lifecycle.

Workers claim jobs atomically before execution, so duplicate task deliveries do not execute terminal or already-running jobs.

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/health` | Health check |
| `POST` | `/jobs` | Create and enqueue a job |
| `GET` | `/jobs` | List jobs, optionally filtered by status |
| `GET` | `/jobs/{job_id}` | Get a single job |
| `POST` | `/jobs/{job_id}/retry` | Retry a terminal job |
| `GET` | `/dashboard` | Job monitoring dashboard |
| `GET` | `/docs` | Swagger API documentation |

## Example Request

Create a job that fails and retries twice:

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

Example response:

```json
{
  "id": "7b2a3d1e-2d2b-4e2f-95d7-0c7f2c6fd123",
  "name": "Submit vendor portal form",
  "task_type": "fail",
  "payload": {
    "error": "portal returned validation error"
  },
  "status": "retrying",
  "attempt": 1,
  "max_retries": 2,
  "timeout_seconds": 10,
  "celery_task_id": "a4b8f8b9-6e4d-4722-b8d8-1f2a8f0e16b7",
  "error": "portal returned validation error",
  "result": null,
  "created_at": "2026-05-01T12:00:00Z",
  "updated_at": "2026-05-01T12:00:01Z",
  "started_at": "2026-05-01T12:00:01Z",
  "finished_at": null
}
```

## Task Types

| Task type | Behavior |
| --- | --- |
| `echo` | Returns the provided payload and succeeds |
| `sleep` | Sleeps for `payload.duration` seconds and fails with a timeout error if it exceeds `timeout_seconds` |
| `fail` | Raises a simulated automation error for retry testing |

## Setup

Start the full stack:

```bash
docker compose up --build
```

Open:

- Dashboard: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
- Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health check: [http://localhost:8000/health](http://localhost:8000/health)

Stop the stack:

```bash
docker compose down
```

Reset persisted job data:

```bash
docker compose down -v
```

## Running Tests

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

Tests run Celery in eager mode, so Redis is not required for the test suite.

## Project Structure

```text
app/
  automation.py       # Simulated automation task execution
  celery_app.py       # Celery configuration
  config.py           # Environment-based settings
  database.py         # SQLAlchemy engine and session setup
  job_service.py      # Job serialization and state transitions
  logging_config.py   # Structured JSON logging
  main.py             # FastAPI routes and dashboard
  models.py           # SQLAlchemy models and enums
  schemas.py          # Pydantic request/response schemas
  tasks.py            # Celery worker task and retry scheduling
tests/
  conftest.py
  test_api.py
.github/workflows/
  ci.yml
docker-compose.yml
Dockerfile
requirements.txt
pytest.ini
```

## Key Concepts Demonstrated

- API-driven job orchestration
- Asynchronous background processing
- Queue-based worker execution
- Distributed worker architecture
- Durable job state tracking
- Explicit lifecycle state transitions
- Retry handling with bounded attempts
- Timeout enforcement as a failed terminal outcome
- Atomic worker job claiming
- Operational visibility through logs and dashboard
- Local-first development with Docker Compose

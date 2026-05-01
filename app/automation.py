import time
from typing import Any

from app.models import TaskType


class AutomationTimeoutError(TimeoutError):
    pass


def run_automation(task_type: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + timeout_seconds

    if task_type == TaskType.ECHO.value:
        return {
            "message": payload.get("message", "ok"),
            "payload": payload,
        }

    if task_type == TaskType.FAIL.value:
        raise RuntimeError(str(payload.get("error", "simulated automation failure")))

    if task_type == TaskType.SLEEP.value:
        duration = float(payload.get("duration", 1))
        elapsed = 0.0
        while elapsed < duration:
            if time.monotonic() >= deadline:
                raise AutomationTimeoutError(f"job exceeded timeout of {timeout_seconds}s")
            time.sleep(min(0.1, duration - elapsed))
            elapsed = time.monotonic() - started
        return {"slept_seconds": round(duration, 3)}

    raise ValueError(f"unsupported task type: {task_type}")

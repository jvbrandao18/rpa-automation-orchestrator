from dataclasses import dataclass
import os


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "RPA Automation Orchestrator")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/jobs.db")
    redis_url: str = os.getenv("REDIS_URL", "redis://redis:6379/0")
    celery_task_always_eager: bool = _bool_env("CELERY_TASK_ALWAYS_EAGER", False)
    celery_task_eager_propagates: bool = _bool_env("CELERY_TASK_EAGER_PROPAGATES", True)


settings = Settings()

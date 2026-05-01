import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "1"
os.environ["CELERY_TASK_EAGER_PROPAGATES"] = "1"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine, init_db
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

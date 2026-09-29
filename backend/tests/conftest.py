import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


test_dir = Path(tempfile.mkdtemp(prefix="parts-catalogue-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{test_dir / 'test.db'}"
os.environ["STORAGE_DIR"] = str(test_dir / "uploads")

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as api:
        yield api

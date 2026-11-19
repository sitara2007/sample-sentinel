from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import get_engine, init_engine
from app.models import Base


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("THRESHOLD", "0.95")
    get_settings.cache_clear()
    init_engine(get_settings().database_url)
    Base.metadata.drop_all(bind=get_engine())
    Base.metadata.create_all(bind=get_engine())

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()

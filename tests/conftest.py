import os

os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5433/shop_test"
os.environ["CHECKPOINT_URL"] = "postgresql://postgres:postgres@localhost:5433/shop_test"
os.environ["FAKE_LLM"] = "1"
os.environ["AUTO_SYNC"] = "0"
os.environ["EMBED_MODE"] = "hash"
os.environ["SYNC_MODE"] = "inprocess"
os.environ["REDIS_URL"] = ""
os.environ["LANGSMITH_TEST_TRACKING"] = "false"

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from api.catalog.sync import release_lock, sync_catalog, sync_categories
from api.db.engine import db_session, ensure_database, init_db, reset_engine

FIXTURE = json.loads(Path("tests/fixtures/products.json").read_text())


@pytest.fixture(scope="session", autouse=True)
def database():
    ensure_database(os.environ["DATABASE_URL"])
    reset_engine()
    init_db()
    yield
    reset_engine()


@pytest.fixture(autouse=True)
def clean_rows():
    session = db_session()
    session.execute(text("TRUNCATE products, categories, conversations, catalog_meta RESTART IDENTITY CASCADE"))
    session.commit()
    session.close()
    release_lock()
    yield
    release_lock()


@pytest.fixture
def catalog_client():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/products/categories"):
            return httpx.Response(200, json=FIXTURE["categories"])
        skip = int(request.url.params.get("skip", 0))
        limit = int(request.url.params.get("limit", 100))
        modified = request.url.params.get("modifiedAfter")
        products = FIXTURE["products"]
        if modified:
            products = [item for item in products if item["meta"]["updatedAt"] > modified]
        page = products[skip : skip + limit]
        return httpx.Response(200, json={"products": page, "total": len(products), "skip": skip, "limit": limit})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="https://catalog.test")
    yield client
    client.close()


@pytest.fixture
def seeded(catalog_client):
    report = sync_catalog(client=catalog_client, base_url="https://catalog.test", page_size=2, incremental=False)
    sync_categories(client=catalog_client, base_url="https://catalog.test")
    return report

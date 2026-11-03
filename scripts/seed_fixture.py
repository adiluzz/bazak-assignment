"""Load the fixture catalog into shop_test so Playwright has products to find.

The app catalog lives in `shop`. This script never writes there.
"""

import json
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5433/shop_test"
os.environ["CHECKPOINT_URL"] = "postgresql://postgres:postgres@localhost:5433/shop_test"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import text

from api.catalog.sync import sync_catalog, sync_categories
from api.db.engine import db_session, ensure_database, init_db

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "products.json").read_text())


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/products/categories"):
        return httpx.Response(200, json=FIXTURE["categories"])
    skip = int(request.url.params.get("skip", 0))
    limit = int(request.url.params.get("limit", 100))
    products = FIXTURE["products"]
    page = products[skip : skip + limit]
    return httpx.Response(200, json={"products": page, "total": len(products), "skip": skip, "limit": limit})


def main() -> None:
    ensure_database(os.environ["DATABASE_URL"])
    init_db()
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://catalog.test")
    sync_catalog(client=client, base_url="https://catalog.test", incremental=False)
    sync_categories(client=client, base_url="https://catalog.test")
    session = db_session()
    session.execute(text("TRUNCATE conversations RESTART IDENTITY CASCADE"))
    session.commit()
    session.close()
    client.close()


if __name__ == "__main__":
    main()

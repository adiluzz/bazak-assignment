from sqlalchemy import text

from api.catalog.mapping import embed_text_for
from api.catalog.search import catalog_facts, search_products
from api.catalog.sync import force_hold_lock, release_lock, sync_catalog
from api.db.engine import db_session
from api.worker.scheduler import build_scheduler
from api.worker.tasks import run_sync_job


def test_sync_pages_and_upserts(catalog_client):
    report = sync_catalog(client=catalog_client, base_url="https://catalog.test", page_size=2, incremental=False)
    assert report.pages == 7
    assert report.upserted == 14
    session = db_session()
    count = session.execute(text("SELECT count(*) FROM products")).scalar()
    missing_brand = session.execute(text("SELECT brand FROM products WHERE id = 1")).scalar()
    stored = session.execute(
        text("SELECT embed_text, embedding IS NOT NULL FROM products WHERE id = 1")
    ).one()
    session.close()
    assert count == 14
    assert missing_brand is None
    assert "Lovely" not in stored[0]
    assert stored[1] is True


def test_sync_is_idempotent(catalog_client):
    sync_catalog(client=catalog_client, base_url="https://catalog.test", page_size=4, incremental=False)
    again = sync_catalog(client=catalog_client, base_url="https://catalog.test", page_size=4, incremental=False)
    session = db_session()
    count = session.execute(text("SELECT count(*) FROM products")).scalar()
    session.close()
    assert count == 14
    assert again.changed_ids == []


def test_embed_text_without_brand():
    text_value = embed_text_for({"title": "Essence Mascara", "description": "A light mascara.", "category": "beauty", "brand": None, "tags": ["beauty"], "reviews": [{"comment": "Lovely."}]})
    assert "None" not in text_value
    assert "Essence Mascara" in text_value
    assert "Lovely." not in text_value


def test_incremental_sync_uses_modified_after(catalog_client):
    sync_catalog(client=catalog_client, base_url="https://catalog.test", page_size=10, incremental=False)
    seen = {}

    def handler(request):
        seen["modified"] = request.url.params.get("modifiedAfter")
        return httpx_response(request)

    import httpx

    def httpx_response(request):
        return httpx.Response(200, json={"products": [], "total": 0, "skip": 0, "limit": 10})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://catalog.test")
    sync_catalog(client=client, base_url="https://catalog.test", page_size=10, incremental=True)
    client.close()
    assert seen["modified"]


def test_only_changed_rows_reembed(catalog_client, seeded):
    payload = {
        "products": [
            {**__import__("json").loads(open("tests/fixtures/products.json").read())["products"][0], "description": "A reformulated mascara."}
        ],
        "total": 1,
        "skip": 0,
        "limit": 10,
    }
    import httpx

    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)),
        base_url="https://catalog.test",
    )
    report = sync_catalog(client=client, base_url="https://catalog.test", incremental=False)
    client.close()
    assert report.changed_ids == [1]


def test_overlapping_sync_skipped(catalog_client):
    force_hold_lock()
    report = sync_catalog(client=catalog_client, base_url="https://catalog.test", incremental=False)
    release_lock()
    assert report.skipped is True


def test_worker_copies_the_whole_catalog(monkeypatch):
    seen = {}

    def fake_sync(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr("api.worker.tasks.sync_catalog", fake_sync)
    run_sync_job()
    assert seen["incremental"] is False


def test_inprocess_mode_runs_same_job():
    scheduler = build_scheduler()
    job = scheduler.get_job("sync_catalog")
    assert job.func is run_sync_job


def test_price_ceiling_respected(seeded):
    session = db_session()
    products, _note = search_products(session, query="phone", categories=["smartphones"], price_max=500)
    session.close()
    assert products
    assert all(item["price"] <= 500 for item in products)
    assert all(item["availabilityStatus"] != "Out of Stock" for item in products)


def test_empty_filter_does_not_backfill(seeded):
    session = db_session()
    products, _note = search_products(session, query="phone", price_max=0.01)
    session.close()
    assert products == []


def test_phone_typo_does_not_return_unrelated(seeded):
    session = db_session()
    products, _note = search_products(session, query="I'm looking for a phhone")
    session.close()
    assert products
    assert all(item["category"] == "smartphones" for item in products)
    assert "Sunglasses" not in [item["title"] for item in products]


def test_review_comment_is_not_searched(seeded):
    session = db_session()
    products, _note = search_products(session, query="waterproof")
    session.close()
    assert products == []


def test_catalog_facts_lists_real_categories(seeded):
    session = db_session()
    facts = catalog_facts(session)
    session.close()
    slugs = {item["slug"] for item in facts["categories"]}
    assert "smartphones" in slugs
    assert "home-decoration" in slugs
    assert facts["in_stock"] >= 1
    assert facts["price_min"] is not None
    assert facts["highest_rated"]["title"]


def test_guard_drops_unknown_id():
    from api.catalog.search import apply_shortlist_guard

    groups = [{"label": "x", "products": [{"id": 2, "title": "Galaxy Budget"}, {"id": 99999, "title": "Ghost"}]}]
    cleaned = apply_shortlist_guard(groups, {2})
    assert [item["id"] for item in cleaned[0]["products"]] == [2]

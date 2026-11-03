import json
import threading
from dataclasses import dataclass, field

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.catalog.embed import embed_texts
from api.catalog.mapping import content_hash, embed_text_for, parse_updated_at
from api.db.engine import db_session
from api.settings import get_settings

_memory_lock = threading.Lock()
_memory_held = False


@dataclass
class SyncReport:
    upserted: int = 0
    changed_ids: list[int] = field(default_factory=list)
    skipped: bool = False
    pages: int = 0


def try_acquire_lock() -> bool:
    global _memory_held
    settings = get_settings()
    if settings.redis_url and settings.sync_mode == "celery":
        try:
            import redis

            client = redis.Redis.from_url(settings.redis_url)
            return bool(client.set("catalog_sync_lock", "1", nx=True, ex=300))
        except Exception:
            return False
    with _memory_lock:
        if _memory_held:
            return False
        _memory_held = True
        return True


def release_lock() -> None:
    global _memory_held
    settings = get_settings()
    if settings.redis_url and settings.sync_mode == "celery":
        try:
            import redis

            redis.Redis.from_url(settings.redis_url).delete("catalog_sync_lock")
        except Exception:
            return
        return
    with _memory_lock:
        _memory_held = False


def force_hold_lock() -> None:
    """Test helper: pretend a sync is already running."""
    global _memory_held
    with _memory_lock:
        _memory_held = True


def fetch_products(client: httpx.Client, base_url: str, page_size: int, modified_after: str | None) -> tuple[list[dict], int]:
    products: list[dict] = []
    skip = 0
    pages = 0
    total = None
    while True:
        params: dict[str, str | int] = {"limit": page_size, "skip": skip}
        if modified_after:
            params["modifiedAfter"] = modified_after
        response = client.get(f"{base_url.rstrip('/')}/products", params=params)
        response.raise_for_status()
        payload = response.json()
        pages += 1
        batch = payload.get("products") or []
        products.extend(batch)
        total = payload.get("total", len(products))
        skip += len(batch)
        if not batch or skip >= total:
            break
    return products, pages


def upsert_products(session: Session, products: list[dict]) -> list[int]:
    changed: list[int] = []
    for product in products:
        text_value = embed_text_for(product)
        digest = content_hash(text_value)
        existing = session.execute(
            text("SELECT embed_hash FROM products WHERE id = :id"),
            {"id": product["id"]},
        ).scalar()
        if existing != digest:
            changed.append(product["id"])
        updated = parse_updated_at(product)
        session.execute(
            text(
                """
                INSERT INTO products (
                    id, title, description, category, price, discount_percentage, rating, stock,
                    availability_status, brand, sku, tags, weight, dimensions, warranty_information,
                    shipping_information, return_policy, minimum_order_quantity, reviews, thumbnail,
                    images, source_updated_at, embed_text, embed_hash, search_tsv
                ) VALUES (
                    :id, :title, :description, :category, :price, :discount_percentage, :rating, :stock,
                    :availability_status, :brand, :sku, :tags, :weight, CAST(:dimensions AS jsonb),
                    :warranty_information, :shipping_information, :return_policy, :minimum_order_quantity,
                    CAST(:reviews AS jsonb), :thumbnail, :images, :source_updated_at, :embed_text, :embed_hash,
                    to_tsvector('english', :embed_text)
                )
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    price = EXCLUDED.price,
                    discount_percentage = EXCLUDED.discount_percentage,
                    rating = EXCLUDED.rating,
                    stock = EXCLUDED.stock,
                    availability_status = EXCLUDED.availability_status,
                    brand = EXCLUDED.brand,
                    sku = EXCLUDED.sku,
                    tags = EXCLUDED.tags,
                    weight = EXCLUDED.weight,
                    dimensions = EXCLUDED.dimensions,
                    warranty_information = EXCLUDED.warranty_information,
                    shipping_information = EXCLUDED.shipping_information,
                    return_policy = EXCLUDED.return_policy,
                    minimum_order_quantity = EXCLUDED.minimum_order_quantity,
                    reviews = EXCLUDED.reviews,
                    thumbnail = EXCLUDED.thumbnail,
                    images = EXCLUDED.images,
                    source_updated_at = EXCLUDED.source_updated_at,
                    embed_text = EXCLUDED.embed_text,
                    embed_hash = EXCLUDED.embed_hash,
                    search_tsv = EXCLUDED.search_tsv,
                    embedding = CASE
                        WHEN products.embed_hash IS DISTINCT FROM EXCLUDED.embed_hash THEN NULL
                        ELSE products.embedding
                    END
                """
            ),
            {
                "id": product["id"],
                "title": product.get("title") or "",
                "description": product.get("description") or "",
                "category": product.get("category") or "",
                "price": product.get("price") or 0,
                "discount_percentage": product.get("discountPercentage") or 0,
                "rating": product.get("rating") or 0,
                "stock": product.get("stock") or 0,
                "availability_status": product.get("availabilityStatus") or "In Stock",
                "brand": product.get("brand"),
                "sku": product.get("sku") or "",
                "tags": product.get("tags") or [],
                "weight": product.get("weight") or 0,
                "dimensions": json.dumps(product.get("dimensions") or {}),
                "warranty_information": product.get("warrantyInformation") or "",
                "shipping_information": product.get("shippingInformation") or "",
                "return_policy": product.get("returnPolicy") or "",
                "minimum_order_quantity": product.get("minimumOrderQuantity") or 1,
                "reviews": json.dumps(product.get("reviews") or []),
                "thumbnail": product.get("thumbnail") or "",
                "images": product.get("images") or [],
                "source_updated_at": updated,
                "embed_text": text_value,
                "embed_hash": digest,
            },
        )
    session.commit()
    return changed


def upsert_categories(session: Session, categories: list[dict]) -> None:
    for category in categories:
        session.execute(
            text(
                """
                INSERT INTO categories (slug, name, url)
                VALUES (:slug, :name, :url)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name, url = EXCLUDED.url
                """
            ),
            {
                "slug": category["slug"],
                "name": category.get("name") or category["slug"],
                "url": category.get("url") or "",
            },
        )
    session.commit()
    from api.catalog.search import refresh_known_categories

    refresh_known_categories(session)


def ensure_vectors() -> int:
    """Rewrite vectors when the embedder changes, and fill any missing ones."""
    settings = get_settings()
    session = db_session()
    try:
        stored = get_meta(session, "embed_mode")
        if stored != settings.embed_mode:
            session.execute(text("UPDATE products SET embedding = NULL"))
            session.commit()
        written = embed_products(session)
        if stored != settings.embed_mode:
            session.execute(text("REINDEX INDEX products_embedding_idx"))
            session.commit()
            set_meta(session, "embed_mode", settings.embed_mode)
        return written
    finally:
        session.close()


def embed_products(session: Session, ids: list[int] | None = None) -> int:
    settings = get_settings()
    if ids is None:
        rows = session.execute(
            text("SELECT id, embed_text FROM products WHERE embedding IS NULL")
        ).all()
    else:
        if not ids:
            return 0
        rows = session.execute(
            text("SELECT id, embed_text FROM products WHERE id = ANY(:ids)"),
            {"ids": ids},
        ).all()
    if not rows:
        return 0
    vectors = embed_texts([row.embed_text for row in rows], settings.embed_mode)
    for row, vector in zip(rows, vectors):
        session.execute(
            text("UPDATE products SET embedding = CAST(:embedding AS vector) WHERE id = :id"),
            {"id": row.id, "embedding": "[" + ",".join(str(value) for value in vector) + "]"},
        )
    session.commit()
    return len(rows)


def latest_source_update(session: Session) -> str | None:
    value = session.execute(text("SELECT max(source_updated_at) FROM products")).scalar()
    if value is None:
        return None
    return value.isoformat()


def set_meta(session: Session, key: str, value: str) -> None:
    session.execute(
        text(
            """
            INSERT INTO catalog_meta (key, value) VALUES (:key, :value)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """
        ),
        {"key": key, "value": value},
    )
    session.commit()


def get_meta(session: Session, key: str) -> str | None:
    return session.execute(text("SELECT value FROM catalog_meta WHERE key = :key"), {"key": key}).scalar()


def sync_catalog(
    *,
    client: httpx.Client | None = None,
    base_url: str | None = None,
    page_size: int | None = None,
    incremental: bool = False,
    respect_lock: bool = True,
) -> SyncReport:
    if respect_lock and not try_acquire_lock():
        return SyncReport(skipped=True)
    settings = get_settings()
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        session = db_session()
        try:
            modified_after = latest_source_update(session) if incremental else None
            products, pages = fetch_products(
                client,
                base_url or settings.catalog_source_url,
                page_size or settings.page_size,
                modified_after,
            )
            changed = upsert_products(session, products)
            slugs = sorted({product.get("category") for product in products if product.get("category")})
            if slugs:
                upsert_categories(
                    session,
                    [{"slug": slug, "name": slug.replace("-", " ").title(), "url": ""} for slug in slugs],
                )
            embed_products(session, changed)
            embed_products(session)
            from datetime import datetime, timezone

            set_meta(session, "last_sync_at", datetime.now(timezone.utc).isoformat())
            return SyncReport(upserted=len(products), changed_ids=changed, pages=pages)
        finally:
            session.close()
    finally:
        if respect_lock:
            release_lock()
        if owns_client:
            client.close()


def sync_categories(client: httpx.Client | None = None, base_url: str | None = None) -> int:
    settings = get_settings()
    owns_client = client is None
    client = client or httpx.Client(timeout=30)
    try:
        response = client.get(f"{(base_url or settings.catalog_source_url).rstrip('/')}/products/categories")
        response.raise_for_status()
        categories = response.json()
        session = db_session()
        try:
            upsert_categories(session, categories)
            return len(categories)
        finally:
            session.close()
    finally:
        if owns_client:
            client.close()

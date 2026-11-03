import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.catalog.embed import embed_query
from api.settings import get_settings

KNOWN_CATEGORIES: set[str] = set()

_STOP_WORDS = {
    "the", "and", "for", "you", "your", "looking", "look", "find", "show", "want",
    "need", "get", "buy", "something", "please", "that", "will", "this", "with",
    "what", "can", "are", "recommend", "recommendation", "good", "from", "have",
    "about", "just", "like", "would", "could", "should", "into", "over", "under",
}


def _fold_token(token: str) -> str:
    return re.sub(r"(.)\1+", r"\1", token)


def content_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+", query.lower()):
        if len(token) < 3 or token in _STOP_WORDS:
            continue
        variants = [token]
        folded = _fold_token(token)
        if folded != token and len(folded) >= 4 and folded not in _STOP_WORDS:
            variants.append(folded)
        for variant in variants:
            if variant not in tokens:
                tokens.append(variant)
    return tokens


def refresh_known_categories(session: Session) -> None:
    rows = session.execute(text("SELECT slug FROM categories")).all()
    KNOWN_CATEGORIES.clear()
    KNOWN_CATEGORIES.update(row[0] for row in rows)


def list_categories(session: Session) -> list[dict]:
    rows = session.execute(text("SELECT slug, name FROM categories ORDER BY name")).all()
    return [{"slug": row.slug, "name": row.name} for row in rows]


def _filters(categories: list[str], price_min: float | None, price_max: float | None, include_out_of_stock: bool) -> tuple[str, dict]:
    clauses = ["TRUE"]
    params: dict = {}
    if categories:
        clauses.append("category = ANY(:categories)")
        params["categories"] = categories
    if price_min is not None:
        clauses.append("price >= :price_min")
        params["price_min"] = price_min
    if price_max is not None:
        clauses.append("price <= :price_max")
        params["price_max"] = price_max
    if not include_out_of_stock:
        clauses.append("availability_status <> 'Out of Stock'")
    return " AND ".join(clauses), params


def _store_filter(
    categories: list[str],
    price_min: float | None,
    price_max: float | None,
    include_out_of_stock: bool,
) -> dict | None:
    clauses: list[dict] = []
    if categories:
        clauses.append({"category": {"$in": categories}})
    if price_min is not None:
        clauses.append({"price": {"$gte": price_min}})
    if price_max is not None:
        clauses.append({"price": {"$lte": price_max}})
    if not include_out_of_stock:
        clauses.append({"availability_status": {"$ne": "Out of Stock"}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _card_from_document(document) -> dict:
    meta = document.metadata
    return {
        "id": int(document.id),
        "title": meta.get("title") or "",
        "description": meta.get("description") or "",
        "category": meta.get("category") or "",
        "price": meta.get("price") or 0,
        "discountPercentage": meta.get("discount_percentage") or 0,
        "rating": meta.get("rating") or 0,
        "stock": meta.get("stock") or 0,
        "availabilityStatus": meta.get("availability_status") or "",
        "brand": meta.get("brand"),
        "thumbnail": meta.get("thumbnail") or "",
    }


def _lexical_rows(
    session: Session,
    query: str,
    categories: list[str],
    price_min: float | None,
    price_max: float | None,
    include_out_of_stock: bool,
    limit: int,
):
    tokens = content_tokens(query)
    if not tokens:
        return []
    likes = []
    params: dict = {"limit": max(limit, 8), "query": " ".join(tokens)}
    for index, token in enumerate(tokens):
        params[f"token_{index}"] = f"%{token}%"
        likes.append(
            "("
            f"title ILIKE :token_{index} OR description ILIKE :token_{index} "
            f"OR category ILIKE :token_{index} OR embed_text ILIKE :token_{index}"
            ")"
        )
    where, filter_params = _filters(categories, price_min, price_max, include_out_of_stock)
    params.update(filter_params)
    sql = f"""
        SELECT id, title, description, category, price, discount_percentage, rating, stock,
               availability_status, brand, thumbnail
        FROM products
        WHERE ({" OR ".join(likes)}) AND {where}
        ORDER BY ts_rank(search_tsv, plainto_tsquery('english', :query)) DESC, rating DESC
        LIMIT :limit
    """
    return session.execute(text(sql), params).mappings().all()


def _hybrid_search(
    session: Session,
    query: str,
    categories: list[str],
    price_min: float | None,
    price_max: float | None,
    include_out_of_stock: bool,
    limit: int,
) -> tuple[list[dict], str]:
    from api.catalog.vectorstore import get_store, hybrid_config

    used_categories = categories
    rows = _lexical_rows(session, query, categories, price_min, price_max, include_out_of_stock, limit)
    note = ""
    if not rows and categories:
        rows = _lexical_rows(session, query, [], price_min, price_max, include_out_of_stock, limit)
        if rows:
            used_categories = []
            note = "No matches in that category, so the category filter was dropped."
    if not rows:
        if used_categories and price_min is None and price_max is None:
            aisle = _category_rows(session, used_categories, include_out_of_stock, limit)
            if aisle:
                return [_card(row) for row in aisle][:4], "No title matched, so these are the products in that category."
        vector_rows = _vector_hits(session, query, used_categories, price_min, price_max, include_out_of_stock, limit)
        if vector_rows:
            return [_card(row) for row in vector_rows][:4], note
        return [], note
    allowed = [row["id"] for row in rows]
    store = get_store()
    found = store.similarity_search(
        query or "product",
        k=32,
        filter=_store_filter(used_categories, price_min, price_max, include_out_of_stock),
        hybrid_search_config=hybrid_config(query),
    )
    ordered: list[dict] = []
    seen: set[int] = set()
    allowed_ids = set(allowed)
    for document in found:
        product_id = int(document.id)
        if product_id in allowed_ids and product_id not in seen:
            ordered.append(_card_from_document(document))
            seen.add(product_id)
    for row in rows:
        if row["id"] not in seen:
            ordered.append(_card(row))
            seen.add(row["id"])
    return ordered[:4], note


def search_products(
    session: Session,
    *,
    query: str,
    categories: list[str] | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    sort: str = "relevance",
    limit: int = 10,
    include_out_of_stock: bool = False,
) -> tuple[list[dict], str]:
    categories = categories or []
    if sort == "relevance":
        return _hybrid_search(session, query, categories, price_min, price_max, include_out_of_stock, limit)
    where, params = _filters(categories, price_min, price_max, include_out_of_stock)
    params["limit"] = limit
    params["query"] = query or ""
    settings = get_settings()
    vector = embed_query(query or "product", settings.embed_mode)
    params["embedding"] = "[" + ",".join(str(value) for value in vector) + "]"
    order = {
        "price_asc": "price ASC",
        "price_desc": "price DESC",
        "rating": "rating DESC",
        "relevance": "(0.7 * COALESCE(1 - (embedding <=> CAST(:embedding AS vector)), 0) + 0.3 * ts_rank(search_tsv, plainto_tsquery('english', :query))) DESC",
    }.get(sort, "rating DESC")
    sql = f"""
        SELECT id, title, description, category, price, discount_percentage, rating, stock,
               availability_status, brand, thumbnail,
               COALESCE(1 - (embedding <=> CAST(:embedding AS vector)), 0) AS vec_score
        FROM products
        WHERE {where}
        ORDER BY {order}
        LIMIT :limit
    """
    rows = session.execute(text(sql), params).mappings().all()
    note = ""
    if not rows and categories:
        where, params = _filters([], price_min, price_max, include_out_of_stock)
        params["limit"] = limit
        params["query"] = query or ""
        params["embedding"] = "[" + ",".join(str(value) for value in vector) + "]"
        sql = f"""
            SELECT id, title, description, category, price, discount_percentage, rating, stock,
                   availability_status, brand, thumbnail,
                   COALESCE(1 - (embedding <=> CAST(:embedding AS vector)), 0) AS vec_score
            FROM products
            WHERE {where}
            ORDER BY {order}
            LIMIT :limit
        """
        rows = session.execute(text(sql), params).mappings().all()
        note = "No matches in that category, so the category filter was dropped."
    products = [_card(row) for row in rows][:4]
    return products, note


def _category_rows(session: Session, categories: list[str], include_out_of_stock: bool, limit: int) -> list:
    where, params = _filters(categories, None, None, include_out_of_stock)
    params["limit"] = limit
    return session.execute(
        text(
            f"""
            SELECT id, title, description, category, price, discount_percentage, rating, stock,
                   availability_status, brand, thumbnail
            FROM products
            WHERE {where}
            ORDER BY rating DESC, price ASC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()


def _vector_hits(
    session: Session,
    query: str,
    categories: list[str],
    price_min: float | None,
    price_max: float | None,
    include_out_of_stock: bool,
    limit: int,
) -> list:
    """Nearest embedded rows when the words themselves miss. Hash mode stays lexical.

    Only a clear neighbor is kept. A vague sentence stays empty so the reply can ask
    from the catalog instead of showing a weak match.
    """
    settings = get_settings()
    if settings.embed_mode != "fastembed" or not (query or "").strip() or price_min is not None or price_max is not None:
        return []
    where, params = _filters(categories, None, None, include_out_of_stock)
    vector = embed_query(query, settings.embed_mode)
    params["embedding"] = "[" + ",".join(str(value) for value in vector) + "]"
    params["limit"] = max(limit, 8)
    rows = session.execute(
        text(
            f"""
            SELECT id, title, description, category, price, discount_percentage, rating, stock,
                   availability_status, brand, thumbnail,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS vec_score
            FROM products
            WHERE {where} AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()
    if not rows or float(rows[0]["vec_score"] or 0) < 0.75:
        return []
    best = float(rows[0]["vec_score"])
    return [row for row in rows if best - float(row["vec_score"] or 0) <= 0.05]


def catalog_facts(session: Session) -> dict:
    """Categories, prices, and a standout product the model can talk about."""
    totals = session.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE availability_status <> 'Out of Stock') AS in_stock,
                   min(price) FILTER (WHERE availability_status <> 'Out of Stock') AS price_min,
                   max(price) FILTER (WHERE availability_status <> 'Out of Stock') AS price_max
            FROM products
            """
        )
    ).mappings().one()
    categories = session.execute(
        text(
            """
            SELECT p.category AS slug,
                   COALESCE(c.name, initcap(replace(p.category, '-', ' '))) AS name,
                   count(*) FILTER (WHERE p.availability_status <> 'Out of Stock') AS in_stock,
                   min(p.price) FILTER (WHERE p.availability_status <> 'Out of Stock') AS min_price,
                   max(p.price) FILTER (WHERE p.availability_status <> 'Out of Stock') AS max_price
            FROM products p
            LEFT JOIN categories c ON c.slug = p.category
            GROUP BY p.category, c.name
            ORDER BY in_stock DESC, p.category
            """
        )
    ).mappings().all()
    highlight = session.execute(
        text(
            """
            SELECT title, category, price, rating
            FROM products
            WHERE availability_status <> 'Out of Stock'
            ORDER BY rating DESC, price ASC
            LIMIT 1
            """
        )
    ).mappings().first()
    return {
        "in_stock": int(totals["in_stock"] or 0),
        "price_min": float(totals["price_min"]) if totals["price_min"] is not None else None,
        "price_max": float(totals["price_max"]) if totals["price_max"] is not None else None,
        "highest_rated": dict(highlight) if highlight else None,
        "categories": [
            {
                "slug": row["slug"],
                "name": row["name"],
                "in_stock": int(row["in_stock"] or 0),
                "min_price": float(row["min_price"]) if row["min_price"] is not None else None,
                "max_price": float(row["max_price"]) if row["max_price"] is not None else None,
            }
            for row in categories
            if int(row["in_stock"] or 0) > 0
        ],
    }


def _card(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "category": row["category"],
        "price": row["price"],
        "discountPercentage": row["discount_percentage"],
        "rating": row["rating"],
        "stock": row["stock"],
        "availabilityStatus": row["availability_status"],
        "brand": row["brand"],
        "thumbnail": row["thumbnail"],
    }


def apply_shortlist_guard(groups: list[dict], allowed_ids: set[int]) -> list[dict]:
    cleaned = []
    for group in groups:
        products = [product for product in group.get("products", []) if product.get("id") in allowed_ids]
        if products:
            cleaned.append({**group, "products": products})
    return cleaned

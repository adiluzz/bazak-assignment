from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from api.settings import Settings, get_settings

_engine = None
_Session = None


def engine_for(settings: Settings | None = None):
    global _engine, _Session
    settings = settings or get_settings()
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
        _Session = sessionmaker(bind=_engine)
    return _engine


def session_factory() -> sessionmaker[Session]:
    engine_for()
    assert _Session is not None
    return _Session


def db_session() -> Session:
    return session_factory()()


def reset_engine() -> None:
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


def ensure_database(url: str) -> None:
    """Create the named database when it is missing. Tests use this so they never share `shop`."""
    from sqlalchemy.engine import make_url

    parsed = make_url(url)
    name = parsed.database or ""
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Refusing to create database {name!r}")
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        admin.dispose()


def init_db(settings: Settings | None = None) -> None:
    engine = engine_for(settings)
    statements = [
        "CREATE EXTENSION IF NOT EXISTS vector",
        """
        CREATE TABLE IF NOT EXISTS categories (
            slug TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL,
            price DOUBLE PRECISION NOT NULL,
            discount_percentage DOUBLE PRECISION NOT NULL DEFAULT 0,
            rating DOUBLE PRECISION NOT NULL DEFAULT 0,
            stock INTEGER NOT NULL DEFAULT 0,
            availability_status TEXT NOT NULL DEFAULT 'In Stock',
            brand TEXT,
            sku TEXT NOT NULL DEFAULT '',
            tags TEXT[] NOT NULL DEFAULT '{}',
            weight DOUBLE PRECISION NOT NULL DEFAULT 0,
            dimensions JSONB NOT NULL DEFAULT '{}',
            warranty_information TEXT NOT NULL DEFAULT '',
            shipping_information TEXT NOT NULL DEFAULT '',
            return_policy TEXT NOT NULL DEFAULT '',
            minimum_order_quantity INTEGER NOT NULL DEFAULT 1,
            reviews JSONB NOT NULL DEFAULT '[]',
            thumbnail TEXT NOT NULL DEFAULT '',
            images TEXT[] NOT NULL DEFAULT '{}',
            source_updated_at TIMESTAMPTZ,
            embed_text TEXT NOT NULL DEFAULT '',
            embed_hash TEXT NOT NULL DEFAULT '',
            embedding vector(384),
            search_tsv tsvector
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS catalog_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS products_category_idx ON products (category)",
        "CREATE INDEX IF NOT EXISTS products_price_idx ON products (price)",
        "CREATE INDEX IF NOT EXISTS products_rating_idx ON products (rating)",
        "CREATE INDEX IF NOT EXISTS products_availability_idx ON products (availability_status)",
        "CREATE INDEX IF NOT EXISTS products_brand_idx ON products (brand)",
        "CREATE INDEX IF NOT EXISTS products_tags_idx ON products USING GIN (tags)",
        "CREATE INDEX IF NOT EXISTS products_search_idx ON products USING GIN (search_tsv)",
        """
        CREATE INDEX IF NOT EXISTS products_embedding_idx
        ON products USING hnsw (embedding vector_cosine_ops)
        """,
        """
        UPDATE products
        SET search_tsv = to_tsvector('english', coalesce(embed_text, ''))
        WHERE search_tsv IS NULL AND embed_text <> ''
        """,
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def database_reachable() -> bool:
    try:
        with engine_for().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

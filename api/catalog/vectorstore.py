from langchain_core.embeddings import Embeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_postgres.v2.hybrid_search_config import HybridSearchConfig, reciprocal_rank_fusion

from api.catalog.embed import embed_query, embed_texts
from api.settings import get_settings

METADATA_COLUMNS = [
    "title",
    "description",
    "category",
    "price",
    "discount_percentage",
    "rating",
    "stock",
    "availability_status",
    "brand",
    "thumbnail",
]

_store: PGVectorStore | None = None


class LocalEmbeddings(Embeddings):
    """Same vectors the worker writes. Hash mode in tests, FastEmbed when configured."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(list(texts), get_settings().embed_mode)

    def embed_query(self, text: str) -> list[float]:
        return embed_query(text, get_settings().embed_mode)


def get_store() -> PGVectorStore:
    global _store
    if _store is None:
        engine = PGEngine.from_connection_string(get_settings().database_url)
        _store = PGVectorStore.create_sync(
            engine=engine,
            embedding_service=LocalEmbeddings(),
            table_name="products",
            content_column="embed_text",
            embedding_column="embedding",
            metadata_columns=METADATA_COLUMNS,
            id_column="id",
            metadata_json_column="langchain_metadata",
            hybrid_search_config=HybridSearchConfig(
                tsv_column="search_tsv",
                tsv_lang="pg_catalog.english",
                fusion_function=reciprocal_rank_fusion,
                primary_top_k=32,
                secondary_top_k=32,
            ),
        )
    return _store


def hybrid_config(query: str) -> HybridSearchConfig:
    return HybridSearchConfig(
        tsv_column="search_tsv",
        tsv_lang="pg_catalog.english",
        fts_query=query or "product",
        fusion_function=reciprocal_rank_fusion,
        primary_top_k=32,
        secondary_top_k=32,
    )

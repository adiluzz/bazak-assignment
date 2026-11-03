import json

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from pydantic import BaseModel, Field, field_validator
from typing_extensions import Annotated

from api.agent.review import review_products
from api.catalog.search import KNOWN_CATEGORIES, catalog_facts, list_categories, search_products
from api.db.engine import db_session


class SearchArgs(BaseModel):
    query: str = ""
    categories: list[str] = Field(default_factory=list)
    price_min: float | None = None
    price_max: float | None = None
    sort: str = "relevance"
    limit: int = 10

    @field_validator("categories")
    @classmethod
    def known_categories(cls, value: list[str]) -> list[str]:
        if not KNOWN_CATEGORIES:
            return value
        unknown = [item for item in value if item not in KNOWN_CATEGORIES]
        if unknown:
            raise ValueError(f"Unknown category: {', '.join(unknown)}")
        return value


def _writer(payload: dict) -> None:
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(payload)
    except Exception:
        return


def _shopper_text(state: dict | None) -> str:
    text = ""
    for message in (state or {}).get("messages") or []:
        if getattr(message, "type", None) != "human":
            continue
        content = getattr(message, "content", "")
        if isinstance(content, str):
            text = content
    return text


def _finish(tool_call_id: str, payload: dict, group: dict | None) -> Command:
    if group and group.get("products"):
        _writer({"type": "status", "text": f"Looking at {len(group['products'])} matches"})
        _writer({"type": "products", "group": group})
    update: dict = {"messages": [ToolMessage(content=json.dumps(payload), tool_call_id=tool_call_id)]}
    if group and group.get("products"):
        update["product_groups"] = [group]
    return Command(update=update)


@tool("search_products", args_schema=SearchArgs)
def search_products_tool(
    query: str = "",
    categories: list[str] | None = None,
    price_min: float | None = None,
    price_max: float | None = None,
    sort: str = "relevance",
    limit: int = 10,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict, InjectedState] = None,
) -> Command:
    """Search the local catalog. Use one call per product.
    If the shopper names a place or a use, query the product type and category that fit, not their exact sentence.
    The result includes catalog facts: categories, prices, and the highest-rated item.
    """
    _writer({"type": "status", "text": "Searching the catalog"})
    session = db_session()
    try:
        products, note = search_products(
            session,
            query=query,
            categories=categories or [],
            price_min=price_min,
            price_max=price_max,
            sort=sort if sort in {"relevance", "price_asc", "price_desc", "rating"} else "relevance",
            limit=limit,
        )
        facts = catalog_facts(session)
    finally:
        session.close()
    if products:
        _writer({"type": "status", "text": "Checking whether these answer the question"})
        products, review_note = review_products(_shopper_text(state), query, products)
        if review_note:
            note = f"{note} {review_note}".strip()
    found = {product.get("category") for product in products if product.get("category")}
    label = next(iter(found)).replace("-", " ").title() if len(found) == 1 else (query or "Products")
    group = {"label": label, "products": products, "note": note}
    return _finish(tool_call_id, {"products": products, "note": note, "catalog": facts}, group if products else None)


@tool("list_categories")
def list_categories_tool(tool_call_id: Annotated[str, InjectedToolCallId] = "") -> Command:
    """List catalog categories."""
    session = db_session()
    try:
        categories = list_categories(session)
    finally:
        session.close()
    return _finish(tool_call_id, {"categories": categories}, None)


TOOLS = [search_products_tool, list_categories_tool]

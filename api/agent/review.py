import logging

from api.settings import get_settings

logger = logging.getLogger(__name__)

# Probability that the product is the kind of thing the shopper asked for.
# Price was already applied by search, so this is not a price check.
_ANSWER_THRESHOLD = 0.5


def review_products(shopper: str, query: str, products: list[dict]) -> tuple[list[dict], str]:
    """Keep products that answer the shopper's question.

    The scripted test model leaves the search result as it is. The live model
    scores each candidate. A failed call leaves the search result as it is.
    """
    if not products or get_settings().fake_llm:
        return products, ""
    try:
        scores = _ask_model(shopper or query, query, products)
    except Exception:
        logger.exception("product answer check failed")
        return products, ""
    return _apply(products, scores)


def _apply(products: list[dict], scores: dict[int, float] | None) -> tuple[list[dict], str]:
    if not scores:
        return products, ""
    kept = []
    for product in products:
        score = scores.get(int(product["id"]))
        if score is None or score >= _ANSWER_THRESHOLD:
            kept.append(product)
            continue
        logger.info("dropped product %s score=%.2f", product["id"], score)
    if kept:
        return kept, ""
    return [], "None of these products answer the question."


def _ask_model(shopper: str, query: str, products: list[dict]) -> dict[int, float]:
    from langchain_openai.decisions import OpenAIDecisions, Predicate

    settings = get_settings()
    questions = {}
    ids: dict[str, int] = {}
    for product in products:
        key = f"p{int(product['id'])}"
        ids[key] = int(product["id"])
        questions[key] = Predicate(
            instructions=(
                "True only if this product directly answers what the shopper asked for. "
                "Something they might merely own or use is not enough. "
                "Price and stock were already filtered, so ignore price. "
                f"Shopper: {shopper}. Search words: {query}. "
                f"Product: {product.get('title') or ''} [{product.get('category') or ''}] {product.get('description') or ''}. "
                "False when the only connection is a shared word or letters inside another word."
            )
        )
    client = OpenAIDecisions(model="gpt-6-luna", api_key=settings.openai_api_key or None)
    response = client.invoke({"input": shopper, "questions": questions})
    scores: dict[int, float] = {}
    for key, verdict in response.predicates.items():
        if key in ids:
            scores[ids[key]] = float(verdict.probability)
    return scores

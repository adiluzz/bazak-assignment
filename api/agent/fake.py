import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


def classify_route(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("flight", "tokyo", "hotel")):
        return "off_catalog"
    if "thanks" in lowered or lowered.strip() in {"hi", "hello", "hey"}:
        return "chat"
    if "cheap" in lowered and "cool" in lowered:
        return "clarify"
    return "search"


class ScriptedChatModel(BaseChatModel):
    """Deterministic stand-in for gpt-6-luna. Chooses tools from the latest user text."""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=self._decide(messages))])

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._decide(messages)
        if message.tool_calls:
            chunk = AIMessageChunk(
                content="",
                tool_call_chunks=[
                    {
                        "name": call["name"],
                        "args": json.dumps(call["args"]),
                        "id": call["id"],
                        "index": index,
                    }
                    for index, call in enumerate(message.tool_calls)
                ],
            )
            yield ChatGenerationChunk(message=chunk)
            return
        text = message.content if isinstance(message.content, str) else ""
        for character in text:
            yield ChatGenerationChunk(message=AIMessageChunk(content=character))

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        human = ""
        turn: list[BaseMessage] = []
        for message in messages:
            if isinstance(message, HumanMessage):
                human = message.content if isinstance(message.content, str) else ""
                turn = []
            else:
                turn.append(message)
        tool_messages = [message for message in turn if isinstance(message, ToolMessage)]
        lowered = human.lower()
        route = classify_route(human)
        if route == "off_catalog":
            return AIMessage(content="We don't sell flights. This shop carries beauty, phones, laptops, watches, groceries, and outdoor gear.")
        if route == "chat":
            return AIMessage(content="You're welcome. Ask whenever you want to look at products.")
        if "laptop" in lowered and "watch" in lowered:
            if len(tool_messages) == 0:
                return AIMessage(
                    content="",
                    tool_calls=[_call("search_products", {"query": "laptop", "categories": ["laptops"]}, "call_laptop")],
                )
            if len(tool_messages) == 1:
                return AIMessage(
                    content="",
                    tool_calls=[_call("search_products", {"query": "watch", "categories": ["mens-watches"]}, "call_watch")],
                )
        if tool_messages:
            titles = _titles(tool_messages)
            if route == "clarify":
                names = _catalog_names(tool_messages)
                found = f" I found {titles}." if titles else ""
                shop = names or "beauty, phones, laptops, and home decoration"
                return AIMessage(content=f"What should I look through? The shop has {shop}.{found}")
            return AIMessage(content=f"I'd start with {titles}." if titles else "I couldn't find a match.")
        if "cheaper" in lowered:
            return AIMessage(
                content="",
                tool_calls=[_call("search_products", {"query": "cheaper option", "sort": "price_asc"}, "call_cheaper")],
            )
        if route == "clarify":
            return AIMessage(
                content="",
                tool_calls=[_call("search_products", {"query": human}, "call_clarify_search")],
            )
        price_max = _price_max(lowered)
        folded = re.sub(r"(.)\1+", r"\1", lowered)
        categories = ["smartphones"] if any(word in folded for word in ("phone", "iphone", "smartphone", "mobile")) else []
        return AIMessage(
            content="",
            tool_calls=[
                _call(
                    "search_products",
                    {"query": human, "categories": categories, **({"price_max": price_max} if price_max is not None else {})},
                    "call_search",
                )
            ],
        )


def _call(name: str, args: dict, call_id: str) -> dict:
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def _price_max(text: str) -> float | None:
    match = re.search(r"under\s+\$?(\d+)", text)
    if match:
        return float(match.group(1))
    return None


def _catalog_names(messages: list[ToolMessage]) -> str:
    names: list[str] = []
    for message in messages:
        try:
            payload = json.loads(message.content if isinstance(message.content, str) else "{}")
        except json.JSONDecodeError:
            continue
        for category in (payload.get("catalog") or {}).get("categories") or []:
            name = category.get("name") or category.get("slug")
            if name and name not in names:
                names.append(name)
    return ", ".join(names[:4])


def _titles(messages: list[ToolMessage]) -> str:
    titles: list[str] = []
    for message in messages:
        try:
            payload = json.loads(message.content if isinstance(message.content, str) else "{}")
        except json.JSONDecodeError:
            continue
        for product in payload.get("products", []):
            titles.append(product["title"])
    return ", ".join(titles[:4])

import json
import logging
from typing import Annotated, Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.messages import SystemMessage, ToolMessage
from typing_extensions import NotRequired

from api.agent.fake import classify_route
from api.agent.prompts import CHAT, CLARIFY, OFF_CATALOG, SYSTEM
from api.catalog.search import apply_shortlist_guard
from api.settings import get_settings

logger = logging.getLogger(__name__)


def _add_groups(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    return [*(left or []), *(right or [])]


class ShopState(AgentState):
    product_groups: NotRequired[Annotated[list[dict], _add_groups]]
    route: NotRequired[str]


def _is_new_shopper_turn(messages: list[Any]) -> bool:
    return bool(messages) and getattr(messages[-1], "type", None) == "human"


def _latest_human(messages: list[Any]) -> str:
    text = ""
    for message in messages:
        if getattr(message, "type", None) == "human":
            content = message.content
            text = content if isinstance(content, str) else ""
    return text


def _tool_name(tool: Any) -> str:
    if isinstance(tool, dict):
        function = tool.get("function") or {}
        return str(tool.get("name") or function.get("name") or "")
    return str(getattr(tool, "name", "") or "")


def _tools_named(tools: list[Any], names: set[str]) -> list[Any]:
    return [tool for tool in tools if _tool_name(tool) in names]


def _current_turn(messages: list[Any]) -> list[Any]:
    turn: list[Any] = []
    for message in messages:
        if getattr(message, "type", None) == "human":
            turn = []
        else:
            turn.append(message)
    return turn


def _tool_already_ran(messages: list[Any], name: str) -> bool:
    pending: set[str] = set()
    for message in _current_turn(messages):
        for call in getattr(message, "tool_calls", None) or []:
            if call.get("name") == name and call.get("id"):
                pending.add(call["id"])
        if isinstance(message, ToolMessage) and (message.name == name or message.tool_call_id in pending):
            return True
    return False


def _shape_request(request, route: str | None):
    if route == "off_catalog":
        return request.override(tools=[], system_message=SystemMessage(content=OFF_CATALOG), tool_choice=None)
    if route == "chat":
        return request.override(tools=[], system_message=SystemMessage(content=CHAT), tool_choice=None)
    search_tools = _tools_named(request.tools or [], {"search_products", "list_categories"})
    searched = _tool_already_ran(request.messages or [], "search_products")
    if route == "clarify":
        if searched:
            return request.override(tools=[], system_message=SystemMessage(content=CLARIFY), tool_choice=None)
        return request.override(
            tools=_tools_named(search_tools, {"search_products"}) or search_tools,
            system_message=SystemMessage(content=CLARIFY),
            tool_choice="search_products",
        )
    return request.override(
        tools=search_tools or list(request.tools or []),
        system_message=SystemMessage(content=SYSTEM),
        tool_choice=None if searched else "search_products",
    )


def _allowed_ids(messages: list[Any]) -> set[int]:
    allowed: set[int] = set()
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        raw = message.content if isinstance(message.content, str) else ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for product in payload.get("products") or []:
            if "id" in product:
                allowed.add(int(product["id"]))
    return allowed


class RouteMiddleware(AgentMiddleware):
    state_schema = ShopState

    def before_model(self, state, runtime):
        messages = state.get("messages") or []
        if not _is_new_shopper_turn(messages):
            return None
        if get_settings().fake_llm:
            route = classify_route(_latest_human(messages))
            logger.warning("route=%s source=fake", route)
            return {"route": route}
        return {"route": _decisions_route(messages)}

    async def abefore_model(self, state, runtime):
        messages = state.get("messages") or []
        if not _is_new_shopper_turn(messages):
            return None
        if get_settings().fake_llm:
            route = classify_route(_latest_human(messages))
            logger.warning("route=%s source=fake", route)
            return {"route": route}
        return {"route": await _adecisions_route(messages)}

    def wrap_model_call(self, request, handler):
        route = (request.state or {}).get("route")
        return handler(_shape_request(request, route))

    async def awrap_model_call(self, request, handler):
        route = (request.state or {}).get("route")
        return await handler(_shape_request(request, route))


class ShortlistGuard(AgentMiddleware):
    state_schema = ShopState

    def after_model(self, state, runtime):
        allowed = _allowed_ids(state.get("messages") or [])
        groups = state.get("product_groups") or []
        cleaned = apply_shortlist_guard(groups, allowed)
        if len(cleaned) != len(groups) or any(
            len(left.get("products", [])) != len(right.get("products", [])) for left, right in zip(groups, cleaned)
        ):
            logger.info("shortlist guard dropped products outside the tool results")
        return None

    async def aafter_model(self, state, runtime):
        return self.after_model(state, runtime)


def _decision_request(messages: list[Any]) -> dict:
    from langchain_openai.decisions import Choice, Predicate

    transcript = []
    for message in messages[-6:]:
        content = getattr(message, "content", "")
        if isinstance(content, str) and content:
            transcript.append(content)
    return {
        "input": "\n".join(transcript),
        "questions": {
            "route": Choice(
                instructions="What kind of shopper message is this?",
                choices={
                    "search": "They named a product, or a place or use this store can shop for, such as a phone, a lamp, a kitchen, an office, or a living room.",
                    "clarify": "They want something but named no product and no place or use. A gift, something cheap, or something cool is clarify.",
                    "off_catalog": "They want something this store does not sell, such as a flight or a hotel.",
                    "chat": "Greeting or thanks, with no product request.",
                },
            ),
            "concrete_product": Predicate(
                instructions="True when the shopper names a product type or a place or use, such as a phone, a lamp, a living room, a kitchen, or an office. False for a gift, something cheap, or something cool with no place and no product.",
            ),
        },
    }


def _decisions_client():
    from langchain_openai.decisions import OpenAIDecisions

    settings = get_settings()
    return OpenAIDecisions(model="gpt-6-luna", api_key=settings.openai_api_key or None)


def _route_from_decision(response) -> str:
    route = str(response.choices["route"].choice)
    concrete = float(response.predicates["concrete_product"].probability)
    logger.warning(
        "decisions route=%s confidence=%.2f concrete_product=%.2f",
        route,
        float(response.choices["route"].confidence),
        concrete,
    )
    if route == "search" and concrete < 0.5:
        logger.warning("route overridden to clarify: search without a concrete product")
        return "clarify"
    if route not in {"search", "clarify", "off_catalog", "chat"}:
        return "clarify"
    return route


def _decisions_route(messages: list[Any]) -> str:
    response = _decisions_client().invoke(_decision_request(messages))
    return _route_from_decision(response)


async def _adecisions_route(messages: list[Any]) -> str:
    response = await _decisions_client().ainvoke(_decision_request(messages))
    return _route_from_decision(response)

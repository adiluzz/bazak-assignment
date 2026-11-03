import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import text

from api.catalog.search import apply_shortlist_guard
from api.db.engine import db_session


def thread_config(conversation_id: str) -> dict:
    return {"configurable": {"thread_id": conversation_id}}


def _allowed_ids(messages) -> set[int]:
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


def _groups_in_tool_message(message: ToolMessage) -> int:
    raw = message.content if isinstance(message.content, str) else ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    return 1 if payload.get("products") else 0


def message_text(message) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
            continue
        if isinstance(block, dict) and block.get("type") in {"text", "output_text"} and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def public_messages(state_values: dict) -> list[dict]:
    messages = state_values.get("messages") or []
    groups = apply_shortlist_guard(state_values.get("product_groups") or [], _allowed_ids(messages))
    items: list[dict] = []
    pending = 0
    cursor = 0
    for message in messages:
        if isinstance(message, HumanMessage):
            items.append({"id": message.id, "role": "user", "content": message_text(message), "groups": []})
        elif isinstance(message, ToolMessage):
            pending += _groups_in_tool_message(message)
        elif isinstance(message, AIMessage) and not message.tool_calls:
            content = message_text(message)
            if not content:
                continue
            take = min(pending, max(len(groups) - cursor, 0))
            attached = groups[cursor : cursor + take]
            cursor += take
            pending = 0
            status = (message.additional_kwargs or {}).get("status", "complete")
            items.append(
                {"id": message.id, "role": "assistant", "content": content, "groups": attached, "status": status}
            )
    return items


async def run_turn(agent, conversation_id: str, text_value: str, *, stream: bool = False) -> AsyncIterator[dict]:
    config = thread_config(conversation_id)
    yield {"type": "status", "text": "Looking through the catalog"}
    if not stream:
        result = await agent.ainvoke({"messages": [HumanMessage(content=text_value)]}, config)
        for item in _events_from_state(result):
            yield item
        yield {"type": "done", "message_id": _last_ai_id(result)}
        return
    async for mode, data in _stream(agent, text_value, config):
        if mode == "custom" and isinstance(data, dict):
            yield data
        elif mode == "messages":
            chunk, meta = data
            node = (meta or {}).get("langgraph_node", "")
            if "model" in node and not getattr(chunk, "tool_call_chunks", None):
                delta = message_text(chunk)
                if delta:
                    yield {"type": "token", "delta": delta}
    state = await agent.aget_state(config)
    yield {"type": "done", "message_id": _last_ai_id(state.values)}


async def _stream(agent, text_value: str, config: dict):
    async for item in agent.astream(
        {"messages": [HumanMessage(content=text_value)]},
        config,
        stream_mode=["messages", "custom"],
    ):
        if isinstance(item, tuple) and len(item) == 2:
            yield item


def _events_from_state(result: dict) -> list[dict]:
    events = []
    for group in result.get("product_groups") or []:
        if group.get("products"):
            events.append({"type": "products", "group": group})
    reply = ""
    for message in reversed(result.get("messages") or []):
        if isinstance(message, AIMessage) and not message.tool_calls:
            reply = message_text(message)
            break
    if reply:
        events.append({"type": "token", "delta": reply})
    return events


def _last_ai_id(values: dict) -> str | None:
    for message in reversed(values.get("messages") or []):
        if isinstance(message, AIMessage) and message_text(message) and not message.tool_calls:
            return message.id
    return None


def touch_title(conversation_id: str, user_text: str) -> None:
    title = user_text.strip().replace("\n", " ")[:60] or "New chat"
    session = db_session()
    try:
        current = session.execute(
            text("SELECT title FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        ).scalar()
        if current in (None, "", "New chat"):
            session.execute(
                text("UPDATE conversations SET title = :title, updated_at = now() WHERE id = :id"),
                {"title": title, "id": conversation_id},
            )
        else:
            session.execute(
                text("UPDATE conversations SET updated_at = now() WHERE id = :id"),
                {"id": conversation_id},
            )
        session.commit()
    finally:
        session.close()


def conversation_exists(conversation_id: str) -> bool:
    session = db_session()
    try:
        found = session.execute(
            text("SELECT 1 FROM conversations WHERE id = :id"),
            {"id": conversation_id},
        ).scalar()
        return bool(found)
    finally:
        session.close()


class RunRegistry:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._queues: dict[str, asyncio.Queue] = {}

    def start(self, conversation_id: str, agent, text_value: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[conversation_id] = queue

        async def worker():
            try:
                if not conversation_exists(conversation_id):
                    await queue.put({"type": "error", "text": "That conversation is gone."})
                    return
                touch_title(conversation_id, text_value)
                partial = ""
                async for event in run_turn(agent, conversation_id, text_value, stream=True):
                    if event.get("type") == "token":
                        partial += event.get("delta") or ""
                    worker.partial = partial
                    await queue.put(event)
            except asyncio.CancelledError:
                partial = getattr(worker, "partial", "")
                if partial:
                    from langchain_core.messages import AIMessage

                    await agent.aupdate_state(
                        thread_config(conversation_id),
                        {"messages": [AIMessage(content=partial, additional_kwargs={"status": "incomplete"})]},
                    )
                await queue.put({"type": "error", "text": "Stopped."})
                raise
            except Exception as exc:
                await queue.put({"type": "error", "text": str(exc)})
            finally:
                await queue.put(None)

        self._tasks[conversation_id] = asyncio.create_task(worker())
        return queue

    def cancel(self, conversation_id: str) -> bool:
        task = self._tasks.get(conversation_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


def new_id() -> str:
    return uuid.uuid4().hex

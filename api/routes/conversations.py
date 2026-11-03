import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from api.agent.runs import conversation_exists, new_id, public_messages, run_turn, thread_config, touch_title
from api.db.engine import db_session

router = APIRouter()


class CreateBody(BaseModel):
    title: str | None = None


class TurnBody(BaseModel):
    text: str


class RenameBody(BaseModel):
    title: str


def _require(conversation_id: str) -> None:
    if not conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.get("/conversations")
def list_conversations():
    session = db_session()
    try:
        rows = session.execute(
            text("SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC")
        ).mappings().all()
        return {"conversations": [dict(row) for row in rows]}
    finally:
        session.close()


@router.post("/conversations")
def create_conversation(body: CreateBody | None = None):
    conversation_id = new_id()
    title = ((body.title if body and body.title else None) or "New chat")[:60]
    session = db_session()
    try:
        session.execute(
            text("INSERT INTO conversations (id, title) VALUES (:id, :title)"),
            {"id": conversation_id, "title": title},
        )
        session.commit()
    finally:
        session.close()
    return {"id": conversation_id, "title": title}


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, body: RenameBody):
    _require(conversation_id)
    session = db_session()
    try:
        session.execute(
            text("UPDATE conversations SET title = :title, updated_at = now() WHERE id = :id"),
            {"title": body.title[:60], "id": conversation_id},
        )
        session.commit()
    finally:
        session.close()
    return {"id": conversation_id, "title": body.title[:60]}


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    _require(conversation_id)
    session = db_session()
    try:
        session.execute(text("DELETE FROM conversations WHERE id = :id"), {"id": conversation_id})
        session.commit()
    finally:
        session.close()
    return {"ok": True}


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: str, request: Request):
    _require(conversation_id)
    agent = request.app.state.agent
    state = await agent.aget_state(thread_config(conversation_id))
    values = state.values if state else {}
    return {"messages": public_messages(values or {})}


@router.post("/conversations/{conversation_id}/turn")
async def turn(conversation_id: str, body: TurnBody, request: Request):
    _require(conversation_id)
    touch_title(conversation_id, body.text)
    agent = request.app.state.agent
    events = []
    async for event in run_turn(agent, conversation_id, body.text, stream=False):
        events.append(event)
    state = await agent.aget_state(thread_config(conversation_id))
    messages = public_messages(state.values or {})
    assistant = next((item for item in reversed(messages) if item["role"] == "assistant"), None)
    return {
        "reply": assistant["content"] if assistant else "",
        "groups": assistant["groups"] if assistant else [],
        "route": (state.values or {}).get("route"),
        "events": events,
    }


@router.post("/conversations/{conversation_id}/stream")
async def stream(conversation_id: str, body: TurnBody, request: Request):
    _require(conversation_id)
    queue = request.app.state.runs.start(conversation_id, request.app.state.agent, body.text)

    async def generate():
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.delete("/conversations/{conversation_id}/runs/current")
async def abort(conversation_id: str, request: Request):
    _require(conversation_id)
    cancelled = request.app.state.runs.cancel(conversation_id)
    return {"cancelled": cancelled}

"""Thin web wrapper around the agent built by agent.build_agent().

This file does not change any agent/tool logic — it only constructs the
agent (its composition root, same as main_agent.py's CLI entrypoint) and
exposes it over a small HTTP API so a browser-based frontend can talk to it.
The request/response contract mirrors exactly what the CLI loop already does:
    master_agent.invoke({"messages": [{"role": ..., "content": ...}, ...]})
    -> result["messages"][-1].content
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import build_agent

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Business RAG Assistant")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

master_agent = build_agent()

_lock = Lock()
_conversations: dict[str, dict] = {}


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str


def _new_conversation() -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {"id": str(uuid.uuid4()), "title": "New chat", "created_at": now, "messages": []}


def _summary(conv: dict) -> dict:
    return {"id": conv["id"], "title": conv["title"], "created_at": conv["created_at"]}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/conversations")
def list_conversations() -> list[dict]:
    with _lock:
        convs = sorted(_conversations.values(), key=lambda c: c["created_at"], reverse=True)
        return [_summary(c) for c in convs]


@app.post("/api/conversations")
def create_conversation() -> dict:
    conv = _new_conversation()
    with _lock:
        _conversations[conv["id"]] = conv
    return _summary(conv)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    with _lock:
        conv = _conversations.get(conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"id": conv["id"], "title": conv["title"], "messages": conv["messages"]}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict:
    with _lock:
        _conversations.pop(conversation_id, None)
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")

    with _lock:
        conv = _conversations.get(payload.conversation_id) if payload.conversation_id else None
        if conv is None:
            conv = _new_conversation()
            _conversations[conv["id"]] = conv

        conv["messages"].append({"role": "user", "content": message})
        if conv["title"] == "New chat":
            conv["title"] = message[:40]
        history = list(conv["messages"])

    try:
        result = master_agent.invoke({"messages": history})
        ai_message = result["messages"][-1]
        reply = getattr(ai_message, "content", str(ai_message))
    except Exception as exc:  # noqa: BLE001 - surface agent errors to the chat UI
        reply = f"Error: {exc}"

    with _lock:
        conv["messages"].append({"role": "assistant", "content": reply})

    return ChatResponse(conversation_id=conv["id"], reply=reply)

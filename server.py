"""Thin web wrapper around the agent built by agent.build_agent().

This file does not change any agent/tool logic — it only constructs the
agent (its composition root, same as main_agent.py's CLI entrypoint) and
exposes it over a small HTTP API so a browser-based frontend can talk to it.
The request/response contract mirrors exactly what the CLI loop already does:
    master_agent.invoke({"messages": [{"role": ..., "content": ...}, ...]})
    -> result["messages"][-1].content
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from agent import build_agent
from config import MAX_MESSAGE_LENGTH

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Business RAG Assistant")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

master_agent = build_agent()

_lock = Lock()
_conversations: dict[str, dict] = {}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


class ChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message must not be empty or whitespace-only.")
        return stripped


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
def get_conversation(conversation_id: uuid.UUID) -> dict:
    with _lock:
        conv = _conversations.get(str(conversation_id))
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return {"id": conv["id"], "title": conv["title"], "messages": conv["messages"]}


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: uuid.UUID) -> dict:
    with _lock:
        _conversations.pop(str(conversation_id), None)
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    conversation_id = str(payload.conversation_id) if payload.conversation_id else None

    with _lock:
        conv = _conversations.get(conversation_id) if conversation_id else None
        if conv is None:
            conv = _new_conversation()
            _conversations[conv["id"]] = conv

        conv["messages"].append({"role": "user", "content": payload.message})
        if conv["title"] == "New chat":
            conv["title"] = payload.message[:40]
        history = list(conv["messages"])

    try:
        result = master_agent.invoke({"messages": history})
        ai_message = result["messages"][-1]
        reply = getattr(ai_message, "content", str(ai_message))
    except Exception:
        logger.exception("Agent invocation failed for conversation_id=%s", conv["id"])
        reply = "Sorry, I couldn't process that request right now. Please try again."

    with _lock:
        conv["messages"].append({"role": "assistant", "content": reply})

    return ChatResponse(conversation_id=conv["id"], reply=reply)

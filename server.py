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
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from agent import build_agent
from config import CONVERSATIONS_DB_PATH, MAX_HISTORY_MESSAGES, MAX_MESSAGE_LENGTH
from conversation_store import ConversationStore, SqliteConversationStore

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Business RAG Assistant")
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")

master_agent = build_agent()
conversation_store: ConversationStore = SqliteConversationStore(CONVERSATIONS_DB_PATH)


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/conversations")
def list_conversations() -> list[dict]:
    return conversation_store.list_summaries()


@app.post("/api/conversations")
def create_conversation() -> dict:
    return conversation_store.create()


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: uuid.UUID) -> dict:
    conv = conversation_store.get(str(conversation_id))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: uuid.UUID) -> dict:
    conversation_store.delete(str(conversation_id))
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    conversation_id = str(payload.conversation_id) if payload.conversation_id else None
    conv = conversation_store.get_or_create(conversation_id)

    conversation_store.add_message(conv["id"], "user", payload.message)
    history = conversation_store.get_history(conv["id"], limit=MAX_HISTORY_MESSAGES)

    try:
        result = master_agent.invoke({"messages": history})
        ai_message = result["messages"][-1]
        reply = getattr(ai_message, "content", str(ai_message))
    except Exception:
        logger.exception("Agent invocation failed for conversation_id=%s", conv["id"])
        reply = "Sorry, I couldn't process that request right now. Please try again."

    conversation_store.add_message(conv["id"], "assistant", reply)

    return ChatResponse(conversation_id=conv["id"], reply=reply)

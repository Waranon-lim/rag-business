"""Thin web wrapper around the agent built by agent.build_agent().

This file does not change any agent/tool logic — it only constructs the
agent (its composition root, same as main_agent.py's CLI entrypoint) and
exposes it over a small HTTP API so a browser-based frontend can talk to it.
The non-streaming contract mirrors exactly what the CLI loop already does:
    master_agent.invoke({"messages": [{"role": ..., "content": ...}, ...]})
    -> result["messages"][-1].content

/api/chat/stream additionally drives master_agent.astream(..., stream_mode=
"messages"), filtered to langgraph_node == "model" chunks with non-empty
content — that filter is what excludes tool-call bookkeeping and the SQL
tool's own internal LLM reasoning from what the client sees, verified by
comparing an assembled filtered stream against a plain .invoke() reply for
the same question.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
    # Only honored by /api/chat/stream: if set, deletes this message and
    # everything after it in the conversation before adding `message` as its
    # replacement — the server side of "edit a past message and regenerate."
    edit_message_id: int | None = None

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


class RenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Title must not be empty or whitespace-only.")
        return stripped


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


@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: uuid.UUID, payload: RenameRequest) -> dict:
    updated = conversation_store.rename(str(conversation_id), payload.title)
    if updated is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


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


async def _stream_chat_response(payload: ChatRequest):
    conversation_id = str(payload.conversation_id) if payload.conversation_id else None
    conv = conversation_store.get_or_create(conversation_id)

    if payload.edit_message_id is not None:
        conversation_store.delete_messages_from(conv["id"], payload.edit_message_id)

    user_message_id = conversation_store.add_message(conv["id"], "user", payload.message)
    history = conversation_store.get_history(conv["id"], limit=MAX_HISTORY_MESSAGES)

    yield (
        json.dumps(
            {"type": "start", "conversation_id": conv["id"], "message_id": user_message_id}
        )
        + "\n"
    )

    assembled = ""
    stream_failed = False
    try:
        async for chunk, meta in master_agent.astream(
            {"messages": history}, stream_mode="messages"
        ):
            if meta.get("langgraph_node") == "model" and chunk.content:
                assembled += chunk.content
                yield json.dumps({"type": "delta", "content": chunk.content}) + "\n"
    except Exception:
        # Also covers the client disconnecting (Stop Generating / navigating
        # away): Starlette cancels this generator, which surfaces here as
        # asyncio.CancelledError — NOT caught by `except Exception`, so it
        # still propagates after the `finally` below persists whatever was
        # generated so far, matching ChatGPT's "keep the partial answer"
        # behavior on stop.
        logger.exception("Streaming agent invocation failed for conversation_id=%s", conv["id"])
        stream_failed = True
        if not assembled:
            assembled = "Sorry, I couldn't process that request right now. Please try again."
        yield json.dumps({"type": "error", "content": assembled}) + "\n"
    finally:
        if assembled:
            conversation_store.add_message(conv["id"], "assistant", assembled)

    if not stream_failed:
        yield json.dumps({"type": "done", "conversation_id": conv["id"]}) + "\n"


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_stream_chat_response(payload), media_type="application/x-ndjson")

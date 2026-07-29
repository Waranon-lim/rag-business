"""Conversation persistence abstraction.

ConversationStore defines the contract server.py depends on. Swapping the
backing implementation (SQLite today, Postgres/Redis tomorrow) should never
require changing the HTTP layer — only which store gets constructed.
"""

import sqlite3
import uuid
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone

_NEW_CHAT_TITLE = "New chat"


class ConversationStore(ABC):
    """Persistence contract for conversations and their message history."""

    @abstractmethod
    def create(self) -> dict:
        """Create a new, empty conversation and return its summary."""

    @abstractmethod
    def get_or_create(self, conversation_id: str | None) -> dict:
        """Return the summary for conversation_id, or create a new conversation
        if conversation_id is None or unknown."""

    @abstractmethod
    def list_summaries(self) -> list[dict]:
        """Return all conversation summaries, most recently created first."""

    @abstractmethod
    def get(self, conversation_id: str) -> dict | None:
        """Return the full conversation (id, title, messages) or None if missing."""

    @abstractmethod
    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        """Append a message and return its id. Auto-titles the conversation
        from the first user message."""

    @abstractmethod
    def get_history(self, conversation_id: str, limit: int | None = None) -> list[dict]:
        """Return up to the most recent `limit` messages (oldest first), for
        feeding to the agent. Pass limit=None for the full history."""

    @abstractmethod
    def delete(self, conversation_id: str) -> None:
        """Delete a conversation and its messages. No-op if it doesn't exist."""

    @abstractmethod
    def delete_messages_from(self, conversation_id: str, message_id: int) -> None:
        """Delete the message with id=message_id and every message after it
        in that conversation. Used to discard the old continuation when a
        past message is edited and regenerated. No-op if message_id doesn't
        belong to that conversation."""

    @abstractmethod
    def rename(self, conversation_id: str, title: str) -> dict | None:
        """Set the conversation's title explicitly (unlike auto-titling, this
        always overwrites). Returns the updated summary, or None if the
        conversation doesn't exist."""


class SqliteConversationStore(ConversationStore):
    """SQLite-backed ConversationStore.

    Opens a short-lived connection per call rather than sharing one connection
    across threads: FastAPI's sync routes run on a thread pool, and SQLite
    connections aren't safe to share across threads. Every method here is a
    single atomic SQL statement (the title update is one conditional UPDATE,
    not a read-then-write), so SQLite's own file locking — helped by WAL mode,
    which lets readers proceed without waiting on a writer — is sufficient for
    correctness without any additional application-level locking.
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id)"
            )

    def create(self) -> dict:
        conversation_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, created_at) VALUES (?, ?, ?)",
                (conversation_id, _NEW_CHAT_TITLE, created_at),
            )
        return {"id": conversation_id, "title": _NEW_CHAT_TITLE, "created_at": created_at}

    def get_or_create(self, conversation_id: str | None) -> dict:
        if conversation_id:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT id, title, created_at FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
            if row is not None:
                return dict(row)
        return self.create()

    def list_summaries(self) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at FROM conversations ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, conversation_id: str) -> dict | None:
        with self._connection() as conn:
            conv_row = conn.execute(
                "SELECT id, title, created_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conv_row is None:
                return None
            message_rows = conn.execute(
                "SELECT id, role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        return {
            "id": conv_row["id"],
            "title": conv_row["title"],
            "messages": [dict(row) for row in message_rows],
        }

    def add_message(self, conversation_id: str, role: str, content: str) -> int:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, created_at),
            )
            message_id = cursor.lastrowid
            if role == "user":
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE id = ? AND title = ?",
                    (content[:40], conversation_id, _NEW_CHAT_TITLE),
                )
        return message_id

    def get_history(self, conversation_id: str, limit: int | None = None) -> list[dict]:
        with self._connection() as conn:
            if limit is None:
                rows = conn.execute(
                    "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                    (conversation_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT role, content FROM (
                        SELECT role, content, id FROM messages
                        WHERE conversation_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                    )
                    ORDER BY id ASC
                    """,
                    (conversation_id, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, conversation_id: str) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

    def delete_messages_from(self, conversation_id: str, message_id: int) -> None:
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND id >= ?",
                (conversation_id, message_id),
            )

    def rename(self, conversation_id: str, title: str) -> dict | None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ?",
                (title, conversation_id),
            )
            row = conn.execute(
                "SELECT id, title, created_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row is not None else None

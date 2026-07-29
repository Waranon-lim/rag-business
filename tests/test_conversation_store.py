"""Conversation persistence tests for SqliteConversationStore.

Every test gets its own tmp_path-scoped SQLite file — no shared state
between tests, and the real project's conversations.db is never touched.
"""

import sqlite3
import threading

import pytest

from conversation_store import SqliteConversationStore


@pytest.fixture
def store(tmp_path):
    return SqliteConversationStore(str(tmp_path / "conversations.db"))


def test_create_returns_new_chat_summary(store):
    conv = store.create()

    assert conv["title"] == "New chat"
    assert conv["id"]
    assert conv["created_at"]


def test_create_mints_distinct_ids(store):
    first = store.create()
    second = store.create()

    assert first["id"] != second["id"]


def test_get_or_create_with_none_creates_new(store):
    conv = store.get_or_create(None)

    assert store.get(conv["id"]) is not None


def test_get_or_create_with_existing_id_returns_same_conversation(store):
    created = store.create()

    fetched = store.get_or_create(created["id"])

    assert fetched["id"] == created["id"]


def test_get_or_create_with_unknown_id_creates_a_new_conversation(store):
    """Matches the pre-SQLite dict-store behavior: a stale/unknown id is not
    an error, it silently becomes a brand new conversation."""
    unknown_id = "11111111-1111-1111-1111-111111111111"

    conv = store.get_or_create(unknown_id)

    assert conv["id"] != unknown_id
    assert store.get(conv["id"]) is not None


def test_get_returns_none_for_unknown_id(store):
    assert store.get("11111111-1111-1111-1111-111111111111") is None


def test_add_message_appends_in_order(store):
    conv = store.create()

    store.add_message(conv["id"], "user", "first")
    store.add_message(conv["id"], "assistant", "second")

    messages = store.get(conv["id"])["messages"]
    assert [m["content"] for m in messages] == ["first", "second"]
    assert [m["role"] for m in messages] == ["user", "assistant"]


def test_first_user_message_sets_title(store):
    conv = store.create()

    store.add_message(conv["id"], "user", "What are my top products this quarter?")

    assert store.get(conv["id"])["title"] == "What are my top products this quarter?"[:40]


def test_later_user_messages_do_not_override_title(store):
    conv = store.create()

    store.add_message(conv["id"], "user", "first question")
    store.add_message(conv["id"], "assistant", "an answer")
    store.add_message(conv["id"], "user", "a completely different second question")

    assert store.get(conv["id"])["title"] == "first question"


def test_assistant_message_never_sets_title(store):
    conv = store.create()

    store.add_message(conv["id"], "assistant", "an unsolicited assistant message")

    assert store.get(conv["id"])["title"] == "New chat"


def test_get_history_returns_full_history_without_limit(store):
    conv = store.create()
    for i in range(5):
        store.add_message(conv["id"], "user", f"msg-{i}")

    history = store.get_history(conv["id"])

    assert len(history) == 5


def test_get_history_truncates_to_most_recent_messages_in_order(store):
    conv = store.create()
    for i in range(30):
        role = "user" if i % 2 == 0 else "assistant"
        store.add_message(conv["id"], role, f"msg-{i}")

    truncated = store.get_history(conv["id"], limit=5)

    assert [m["content"] for m in truncated] == [f"msg-{i}" for i in range(25, 30)]


def test_get_still_returns_full_untruncated_history_for_display(store):
    conv = store.create()
    for i in range(30):
        store.add_message(conv["id"], "user", f"msg-{i}")

    full = store.get(conv["id"])

    assert len(full["messages"]) == 30


def test_list_summaries_orders_most_recent_first(store):
    first = store.create()
    second = store.create()

    summaries = store.list_summaries()

    assert [s["id"] for s in summaries] == [second["id"], first["id"]]


def test_delete_removes_conversation(store):
    conv = store.create()

    store.delete(conv["id"])

    assert store.get(conv["id"]) is None


def test_delete_cascades_to_messages(store):
    conv = store.create()
    store.add_message(conv["id"], "user", "hello")

    store.delete(conv["id"])

    # A fresh conversation created afterward proves the store still works
    # and isn't left in a broken state by the cascade delete.
    other = store.create()
    assert store.get(other["id"]) is not None
    assert store.list_summaries() == [
        {"id": other["id"], "title": other["title"], "created_at": other["created_at"]}
    ]


def test_delete_unknown_id_is_a_safe_noop(store):
    store.delete("11111111-1111-1111-1111-111111111111")  # must not raise


def test_get_includes_message_ids(store):
    conv = store.create()
    store.add_message(conv["id"], "user", "hello")

    messages = store.get(conv["id"])["messages"]

    assert isinstance(messages[0]["id"], int)


def test_add_message_returns_the_new_message_id(store):
    conv = store.create()

    message_id = store.add_message(conv["id"], "user", "hello")

    stored = store.get(conv["id"])["messages"][0]
    assert stored["id"] == message_id


def test_delete_messages_from_removes_target_and_everything_after(store):
    conv = store.create()
    ids = [store.add_message(conv["id"], "user" if i % 2 == 0 else "assistant", f"msg-{i}") for i in range(5)]

    store.delete_messages_from(conv["id"], ids[2])

    remaining = store.get(conv["id"])["messages"]
    assert [m["content"] for m in remaining] == ["msg-0", "msg-1"]


def test_delete_messages_from_is_scoped_to_its_own_conversation(store):
    conv_a = store.create()
    conv_b = store.create()
    a_message_id = store.add_message(conv_a["id"], "user", "a-message")
    store.add_message(conv_b["id"], "user", "b-message")

    # Deleting from conv_b using conv_a's (lower) message id: without the
    # conversation_id scoping clause, "id >= a_message_id" would also match
    # (and delete) conv_a's own message, since ids increase globally across
    # every conversation's messages.
    store.delete_messages_from(conv_b["id"], a_message_id)

    assert [m["content"] for m in store.get(conv_a["id"])["messages"]] == ["a-message"]
    assert store.get(conv_b["id"])["messages"] == []


def test_rename_updates_the_title(store):
    conv = store.create()

    store.rename(conv["id"], "My custom title")

    assert store.get(conv["id"])["title"] == "My custom title"


def test_rename_overrides_even_an_already_auto_titled_conversation(store):
    conv = store.create()
    store.add_message(conv["id"], "user", "first question sets the auto title")

    store.rename(conv["id"], "Renamed by user")

    assert store.get(conv["id"])["title"] == "Renamed by user"


def test_rename_returns_the_updated_summary(store):
    conv = store.create()

    updated = store.rename(conv["id"], "New title")

    assert updated["id"] == conv["id"]
    assert updated["title"] == "New title"


def test_rename_unknown_conversation_returns_none(store):
    result = store.rename("11111111-1111-1111-1111-111111111111", "New title")

    assert result is None


def test_write_failure_rolls_back_instead_of_partially_committing(store):
    """add_message on a conversation_id that doesn't exist violates the
    messages.conversation_id foreign key — the transaction must roll back
    cleanly (and re-raise) rather than leaving a partial write committed."""
    with pytest.raises(sqlite3.IntegrityError):
        store.add_message("11111111-1111-1111-1111-111111111111", "user", "orphaned message")


def test_concurrent_writes_to_the_same_conversation_lose_nothing(store):
    """Regression test for removing the process-wide lock: SQLite's own
    locking must be sufficient without any application-level lock."""
    conv = store.create()
    n_threads = 10
    n_messages_per_thread = 10
    errors = []

    def worker(thread_id):
        try:
            for i in range(n_messages_per_thread):
                store.add_message(conv["id"], "user", f"t{thread_id}-m{i}")
        except Exception as exc:  # pragma: no cover - only hit on real failure
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(store.get(conv["id"])["messages"]) == n_threads * n_messages_per_thread

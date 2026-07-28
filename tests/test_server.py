"""API endpoint and error-handling tests for server.py.

The `client`/`server_module`/`fake_agent` fixtures (see conftest.py) ensure
master_agent is a fully mocked stand-in and the conversation store is backed
by a tmp_path-scoped SQLite file — no network call, no real project files
touched.
"""

from unittest.mock import MagicMock

from conftest import make_ai_message


def test_index_serves_the_frontend(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_chat_creates_new_conversation_when_no_id_given(client, fake_agent):
    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "fake reply"
    assert body["conversation_id"]


def test_chat_continues_an_existing_conversation(client, fake_agent):
    first = client.post("/api/chat", json={"message": "hello"}).json()

    second = client.post(
        "/api/chat",
        json={"conversation_id": first["conversation_id"], "message": "follow-up"},
    ).json()

    assert second["conversation_id"] == first["conversation_id"]


def test_chat_persists_both_user_and_assistant_messages(client, server_module):
    conv_id = client.post("/api/chat", json={"message": "hello"}).json()["conversation_id"]

    full = client.get(f"/api/conversations/{conv_id}").json()

    assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
    assert full["messages"][0]["content"] == "hello"
    assert full["messages"][1]["content"] == "fake reply"


def test_chat_calls_get_history_with_the_configured_limit(client, server_module):
    import config as config_module

    spy = MagicMock(wraps=server_module.conversation_store.get_history)
    server_module.conversation_store.get_history = spy

    client.post("/api/chat", json={"message": "hello"})

    assert spy.call_args.kwargs["limit"] == config_module.MAX_HISTORY_MESSAGES


def test_list_conversations_is_empty_initially(client):
    assert client.get("/api/conversations").json() == []


def test_list_conversations_after_chat(client):
    client.post("/api/chat", json={"message": "hello"})

    listing = client.get("/api/conversations").json()

    assert len(listing) == 1
    assert listing[0]["title"] == "hello"


def test_create_conversation_endpoint(client):
    response = client.post("/api/conversations")

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New chat"
    assert body["id"]


def test_get_conversation_returns_404_for_unknown_id(client):
    response = client.get("/api/conversations/11111111-1111-1111-1111-111111111111")

    assert response.status_code == 404


def test_get_conversation_returns_422_for_malformed_uuid(client):
    response = client.get("/api/conversations/not-a-uuid")

    assert response.status_code == 422


def test_delete_conversation(client):
    conv_id = client.post("/api/conversations").json()["id"]

    delete_response = client.delete(f"/api/conversations/{conv_id}")
    get_response = client.get(f"/api/conversations/{conv_id}")

    assert delete_response.status_code == 200
    assert delete_response.json() == {"ok": True}
    assert get_response.status_code == 404


def test_delete_unknown_conversation_is_a_safe_noop(client):
    response = client.delete("/api/conversations/11111111-1111-1111-1111-111111111111")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_chat_rejects_empty_message(client):
    response = client.post("/api/chat", json={"message": ""})

    assert response.status_code == 422


def test_chat_rejects_whitespace_only_message(client):
    response = client.post("/api/chat", json={"message": "   "})

    assert response.status_code == 422


def test_chat_rejects_oversized_message(client):
    import config as config_module

    response = client.post("/api/chat", json={"message": "a" * (config_module.MAX_MESSAGE_LENGTH + 1)})

    assert response.status_code == 422


def test_chat_accepts_message_at_the_length_limit(client):
    import config as config_module

    response = client.post("/api/chat", json={"message": "a" * config_module.MAX_MESSAGE_LENGTH})

    assert response.status_code == 200


def test_chat_rejects_malformed_conversation_id(client):
    response = client.post("/api/chat", json={"message": "hi", "conversation_id": "not-a-uuid"})

    assert response.status_code == 422


def test_chat_with_unknown_but_valid_conversation_id_starts_a_new_conversation(client):
    unknown_id = "11111111-1111-1111-1111-111111111111"

    response = client.post("/api/chat", json={"conversation_id": unknown_id, "message": "hi"})

    assert response.status_code == 200
    assert response.json()["conversation_id"] != unknown_id


def test_chat_agent_failure_returns_generic_reply_not_the_raw_exception(client, fake_agent):
    fake_agent.invoke.side_effect = RuntimeError("leaked internal path: /etc/secret_config")

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert "leaked internal path" not in body["reply"]
    assert body["reply"] == "Sorry, I couldn't process that request right now. Please try again."


def test_chat_failure_still_persists_the_user_message(client, fake_agent):
    fake_agent.invoke.side_effect = RuntimeError("boom")

    conv_id = client.post("/api/chat", json={"message": "hello"}).json()["conversation_id"]

    full = client.get(f"/api/conversations/{conv_id}").json()
    assert full["messages"][0]["content"] == "hello"


def test_unhandled_exception_returns_generic_500_not_a_traceback(client, server_module):
    server_module.conversation_store.list_summaries = MagicMock(
        side_effect=RuntimeError("db file corrupted at /secret/path.db")
    )

    response = client.get("/api/conversations")

    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "Internal server error."}
    assert "secret/path.db" not in response.text


def test_agent_receives_message_objects_with_content_attribute(client, fake_agent):
    """Guards the getattr(ai_message, 'content', str(ai_message)) fallback path."""
    fake_agent.invoke.return_value = {"messages": [make_ai_message("a fresh reply")]}

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.json()["reply"] == "a fresh reply"

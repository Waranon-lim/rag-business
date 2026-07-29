"""Shared pytest fixtures.

All fixtures here that touch server.py or agent.py are careful to patch
config/agent BEFORE importing (or reloading) server.py, since both
master_agent construction and conversation store construction are real,
module-level side effects that happen at import time. No test in this suite
makes a real network call to OpenAI or Tavily.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def make_ai_message(content: str) -> SimpleNamespace:
    """Build a minimal stand-in for the LangChain message objects the real
    agent returns — only `.content` is ever read via getattr() by our code."""
    return SimpleNamespace(content=content)


def make_streaming_astream(pieces, node="model"):
    """Build an .astream() replacement yielding (chunk, meta) tuples for each
    piece of text, tagged with the given langgraph_node. A plain MagicMock
    isn't async-iterable, so tests that need to control streaming behavior
    reassign `fake_agent.astream` to a function built by this helper."""

    async def _astream(payload, stream_mode="messages"):
        for piece in pieces:
            yield make_ai_message(piece), {"langgraph_node": node}

    return _astream


def make_failing_astream(exc, pieces_before_failure=()):
    """An .astream() replacement that yields any given pieces, then raises."""

    async def _astream(payload, stream_mode="messages"):
        for piece in pieces_before_failure:
            yield make_ai_message(piece), {"langgraph_node": "model"}
        raise exc

    return _astream


@pytest.fixture
def fake_agent():
    """A stand-in for master_agent: no LLM, no network, fully scripted.

    .invoke is a MagicMock (existing tests configure it via
    .return_value/.side_effect/.assert_not_called()). .astream is a plain
    async generator function, not a MagicMock, since MagicMock instances
    aren't async-iterable — reassign it directly (see make_streaming_astream
    above) in tests that need specific streaming behavior.
    """
    agent = MagicMock(name="fake_master_agent")
    agent.invoke.return_value = {"messages": [make_ai_message("fake reply")]}
    agent.astream = make_streaming_astream(["fake ", "reply"])
    return agent


@pytest.fixture
def server_module(monkeypatch, tmp_path, fake_agent):
    """Import (or reload) server.py with build_agent() and the conversation
    store's DB path patched, so no real OpenAI/Tavily client or real
    conversations.db file is ever touched by a test."""
    import agent as agent_module
    import config

    monkeypatch.setattr(agent_module, "build_agent", MagicMock(return_value=fake_agent))
    monkeypatch.setattr(config, "CONVERSATIONS_DB_PATH", str(tmp_path / "conversations.db"))

    import server

    importlib.reload(server)
    return server


@pytest.fixture
def client(server_module):
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False: we want to test our own global exception
    # handler's response, not have TestClient re-raise the original error.
    return TestClient(server_module.app, raise_server_exceptions=False)

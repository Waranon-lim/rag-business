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


@pytest.fixture
def fake_agent():
    """A stand-in for master_agent: no LLM, no network, fully scripted."""
    agent = MagicMock(name="fake_master_agent")
    agent.invoke.return_value = {"messages": [make_ai_message("fake reply")]}
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

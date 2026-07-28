"""Tool factory tests.

build_sql_database does real (but tiny, tmp_path-scoped) file I/O — no
network, no LLM — so its read-only/scoping guarantees are tested for real
rather than mocked. build_sql_tool/build_search_tool wrap external clients
(the LangChain SQL agent, Tavily), which are mocked here; nothing in this
file makes a real OpenAI or Tavily API call.
"""

import logging
import sqlite3

import pandas as pd
import pytest

import tools as tools_module
from tools import build_search_tool, build_sql_database, build_sql_tool


@pytest.fixture
def sample_xlsx(tmp_path):
    path = tmp_path / "orders.xlsx"
    pd.DataFrame(
        {
            "product_name": ["Widget", "Gadget", "Widget"],
            "quantity": [2, 1, 3],
        }
    ).to_excel(path, index=False)
    return path


def test_build_sql_database_loads_rows_from_spreadsheet(tmp_path, sample_xlsx):
    db_path = tmp_path / "test.db"

    db = build_sql_database(str(sample_xlsx), str(db_path), "orders")

    result = db.run("SELECT COUNT(*) FROM orders")
    assert "3" in result


def test_build_sql_database_is_read_only(tmp_path, sample_xlsx):
    db_path = tmp_path / "test.db"

    db = build_sql_database(str(sample_xlsx), str(db_path), "orders")

    with pytest.raises(Exception, match="readonly database"):
        db.run("DELETE FROM orders")


def test_build_sql_database_scopes_to_the_target_table(tmp_path, sample_xlsx):
    db_path = tmp_path / "test.db"

    # Seed an unrelated table directly, before build_sql_database creates "orders".
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE secrets (value TEXT)")
    conn.execute("INSERT INTO secrets VALUES ('should not be visible to the agent')")
    conn.commit()
    conn.close()

    db = build_sql_database(str(sample_xlsx), str(db_path), "orders")

    assert db.get_usable_table_names() == ["orders"]


def test_build_sql_tool_has_expected_name_and_description(monkeypatch):
    monkeypatch.setattr(tools_module, "create_sql_agent", lambda *a, **k: object())

    tool_ = build_sql_tool(llm=object(), db=object())

    assert tool_.name == "query_sales_database"
    assert "internal company sales database" in tool_.description


def test_build_sql_tool_returns_executor_output_on_success(monkeypatch):
    fake_executor = type("FakeExecutor", (), {"invoke": lambda self, payload: {"output": "42 orders"}})()
    monkeypatch.setattr(tools_module, "create_sql_agent", lambda *a, **k: fake_executor)

    tool_ = build_sql_tool(llm=object(), db=object())

    assert tool_.invoke({"query": "how many orders?"}) == "42 orders"


def test_build_sql_tool_stringifies_non_dict_executor_responses(monkeypatch):
    fake_executor = type("FakeExecutor", (), {"invoke": lambda self, payload: ["not", "a", "dict"]})()
    monkeypatch.setattr(tools_module, "create_sql_agent", lambda *a, **k: fake_executor)

    tool_ = build_sql_tool(llm=object(), db=object())

    assert tool_.invoke({"query": "how many orders?"}) == str(["not", "a", "dict"])


def test_build_sql_tool_returns_generic_message_and_logs_on_error(monkeypatch, caplog):
    class FailingExecutor:
        def invoke(self, payload):
            raise RuntimeError("syntax error near DROP")

    monkeypatch.setattr(tools_module, "create_sql_agent", lambda *a, **k: FailingExecutor())

    tool_ = build_sql_tool(llm=object(), db=object())

    with caplog.at_level(logging.ERROR):
        result = tool_.invoke({"query": "bad query"})

    assert result == "I couldn't complete that database query right now."
    assert "syntax error near DROP" not in result
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_build_search_tool_has_expected_name_and_description(monkeypatch):
    monkeypatch.setattr(tools_module, "TavilySearch", lambda max_results: object())

    tool_ = build_search_tool(max_results=3)

    assert tool_.name == "search_internet"
    assert "internet" in tool_.description.lower()


def test_build_search_tool_returns_results_on_success(monkeypatch):
    fake_search = type("FakeSearch", (), {"invoke": lambda self, query: {"results": ["a", "b"]}})()
    monkeypatch.setattr(tools_module, "TavilySearch", lambda max_results: fake_search)

    tool_ = build_search_tool(max_results=3)

    assert tool_.invoke({"query": "latest retail trends"}) == str({"results": ["a", "b"]})


def test_build_search_tool_returns_generic_message_and_logs_on_error(monkeypatch, caplog):
    class FailingSearch:
        def invoke(self, query):
            raise RuntimeError("Tavily API key invalid: sk-secret-123")

    monkeypatch.setattr(tools_module, "TavilySearch", lambda max_results: FailingSearch())

    tool_ = build_search_tool(max_results=3)

    with caplog.at_level(logging.ERROR):
        result = tool_.invoke({"query": "bad query"})

    assert result == "I couldn't complete that internet search right now."
    assert "sk-secret-123" not in result
    assert any(record.levelno == logging.ERROR for record in caplog.records)

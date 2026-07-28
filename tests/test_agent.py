"""Agent construction tests — agent.build_agent() wiring, fully mocked.

No real ChatOpenAI/SQL/Tavily/LangChain agent object is ever constructed
here; only the wiring logic (who gets called, with what, in what order) is
under test.
"""

from unittest.mock import MagicMock, call

import agent as agent_module
from agent import build_agent
from prompts import SYSTEM_PROMPT


def _patch_agent_collaborators(monkeypatch):
    fake_llm = MagicMock(name="fake_llm")
    fake_db = MagicMock(name="fake_db")
    fake_sql_tool = MagicMock(name="fake_sql_tool")
    fake_search_tool = MagicMock(name="fake_search_tool")
    fake_agent = MagicMock(name="fake_agent")

    chat_openai = MagicMock(return_value=fake_llm)
    build_sql_database = MagicMock(return_value=fake_db)
    build_sql_tool = MagicMock(return_value=fake_sql_tool)
    build_search_tool = MagicMock(return_value=fake_search_tool)
    create_agent = MagicMock(return_value=fake_agent)

    monkeypatch.setattr(agent_module, "ChatOpenAI", chat_openai)
    monkeypatch.setattr(agent_module, "build_sql_database", build_sql_database)
    monkeypatch.setattr(agent_module, "build_sql_tool", build_sql_tool)
    monkeypatch.setattr(agent_module, "build_search_tool", build_search_tool)
    monkeypatch.setattr(agent_module, "create_agent", create_agent)

    return {
        "llm": fake_llm,
        "db": fake_db,
        "sql_tool": fake_sql_tool,
        "search_tool": fake_search_tool,
        "agent": fake_agent,
        "ChatOpenAI": chat_openai,
        "build_sql_database": build_sql_database,
        "build_sql_tool": build_sql_tool,
        "build_search_tool": build_search_tool,
        "create_agent": create_agent,
    }


def test_build_agent_constructs_llm_with_defaults(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    build_agent()

    mocks["ChatOpenAI"].assert_called_once_with(model="gpt-4o", temperature=0)


def test_build_agent_constructs_llm_with_overrides(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    build_agent(llm_model="gpt-4o-mini", llm_temperature=0.5)

    mocks["ChatOpenAI"].assert_called_once_with(model="gpt-4o-mini", temperature=0.5)


def test_build_agent_loads_sql_database_with_given_paths(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    build_agent(xlsx_path="custom.xlsx", db_path="custom.db", table_name="custom_table")

    mocks["build_sql_database"].assert_called_once_with("custom.xlsx", "custom.db", "custom_table")


def test_build_agent_wires_sql_tool_with_llm_and_db(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    build_agent()

    mocks["build_sql_tool"].assert_called_once_with(mocks["llm"], mocks["db"])


def test_build_agent_wires_search_tool_with_max_results(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    build_agent(tavily_max_results=7)

    mocks["build_search_tool"].assert_called_once_with(7)


def test_build_agent_passes_both_tools_and_system_prompt_to_create_agent(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    build_agent()

    mocks["create_agent"].assert_called_once_with(
        model=mocks["llm"],
        tools=[mocks["sql_tool"], mocks["search_tool"]],
        system_prompt=SYSTEM_PROMPT,
    )


def test_build_agent_returns_create_agent_result(monkeypatch):
    mocks = _patch_agent_collaborators(monkeypatch)

    result = build_agent()

    assert result is mocks["agent"]


def test_build_agent_construction_order(monkeypatch):
    """The SQL database must be built before the SQL tool wraps it."""
    mocks = _patch_agent_collaborators(monkeypatch)
    manager = MagicMock()
    manager.attach_mock(mocks["build_sql_database"], "build_sql_database")
    manager.attach_mock(mocks["build_sql_tool"], "build_sql_tool")

    build_agent()

    assert manager.mock_calls.index(
        call.build_sql_database("retail_orders.xlsx", "business_data.db", "orders")
    ) < manager.mock_calls.index(call.build_sql_tool(mocks["llm"], mocks["db"]))

"""Tool factories for the business AI agent.

Each build_* function performs its I/O (reading the spreadsheet, rebuilding
the SQLite table, constructing API clients) only when called — never as a
side effect of importing this module.
"""

import logging
import sqlite3

import pandas as pd
from langchain.tools import tool
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_tavily import TavilySearch

from config import DB_PATH, TABLE_NAME, TAVILY_MAX_RESULTS, XLSX_PATH

logger = logging.getLogger(__name__)


def _load_orders_table(xlsx_path: str, db_path: str, table_name: str) -> None:
    """Bootstrap the SQLite table from the spreadsheet via a read-write connection.

    This is the only place the database is opened read-write. Everything the
    LLM-driven SQL agent touches afterward goes through a read-only handle
    (see build_sql_database) so a generated query cannot mutate the data —
    that boundary is enforced by SQLite itself, not just a prompt instruction.
    """
    df = pd.read_excel(xlsx_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    try:
        df.to_sql(table_name, conn, if_exists="replace", index=False)
    finally:
        conn.close()


def build_sql_database(
    xlsx_path: str = XLSX_PATH,
    db_path: str = DB_PATH,
    table_name: str = TABLE_NAME,
) -> SQLDatabase:
    """Load the retail orders spreadsheet into SQLite, then return a READ-ONLY SQLDatabase handle."""
    _load_orders_table(xlsx_path, db_path, table_name)
    readonly_uri = f"sqlite:///file:{db_path}?mode=ro&uri=true"
    return SQLDatabase.from_uri(readonly_uri, include_tables=[table_name])


def build_sql_tool(llm, db: SQLDatabase):
    """Build the Internal_Sales_Database tool, backed by a LangChain SQL agent."""
    sql_agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=False)

    def run_sql_query(query: str) -> str:
        try:
            response = sql_agent_executor.invoke({"input": query})
            if isinstance(response, dict):
                return response.get("output", str(response))
            return str(response)
        except Exception:
            logger.exception("SQL tool failed for query: %r", query)
            return "I couldn't complete that database query right now."

    @tool
    def Internal_Sales_Database(query: str) -> str:
        """Query the internal company sales database."""
        return run_sql_query(query)

    return Internal_Sales_Database


def build_search_tool(max_results: int = TAVILY_MAX_RESULTS):
    """Build the Internet_Search tool, backed by Tavily."""
    tavily_search = TavilySearch(max_results=max_results)

    def run_internet_search(query: str) -> str:
        try:
            results = tavily_search.invoke(query)
            return str(results)
        except Exception:
            logger.exception("Internet search tool failed for query: %r", query)
            return "I couldn't complete that internet search right now."

    @tool
    def Internet_Search(query: str) -> str:
        """Search the internet for news and general information."""
        return run_internet_search(query)

    return Internet_Search

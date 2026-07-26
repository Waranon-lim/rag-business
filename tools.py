"""Tool factories for the business AI agent.

Each build_* function performs its I/O (reading the spreadsheet, rebuilding
the SQLite table, constructing API clients) only when called — never as a
side effect of importing this module.
"""

import sqlite3

import pandas as pd
from langchain.tools import tool
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_tavily import TavilySearch

from config import DB_PATH, TABLE_NAME, TAVILY_MAX_RESULTS, XLSX_PATH


def build_sql_database(
    xlsx_path: str = XLSX_PATH,
    db_path: str = DB_PATH,
    table_name: str = TABLE_NAME,
) -> SQLDatabase:
    """Load the retail orders spreadsheet into SQLite and return a SQLDatabase handle."""
    df = pd.read_excel(xlsx_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    df.to_sql(table_name, conn, if_exists="replace", index=False)
    return SQLDatabase.from_uri(f"sqlite:///{db_path}")


def build_sql_tool(llm, db: SQLDatabase):
    """Build the Internal_Sales_Database tool, backed by a LangChain SQL agent."""
    sql_agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=False)

    def run_sql_query(query: str) -> str:
        try:
            response = sql_agent_executor.invoke({"input": query})
            if isinstance(response, dict):
                return response.get("output", str(response))
            return str(response)
        except Exception as e:
            return f"Database query error: {e}"

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
        except Exception as e:
            return f"Internet search error: {e}"

    @tool
    def Internet_Search(query: str) -> str:
        """Search the internet for news and general information."""
        return run_internet_search(query)

    return Internet_Search

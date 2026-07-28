"""Agent construction for the business AI assistant.

build_agent() is the single factory that wires the LLM, tools, and system
prompt together. Nothing in this module runs at import time — callers
(the CLI entrypoint, the web server) must invoke build_agent() explicitly.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from config import (
    DB_PATH,
    LLM_MODEL,
    LLM_TEMPERATURE,
    TABLE_NAME,
    TAVILY_MAX_RESULTS,
    XLSX_PATH,
)
from prompts import SYSTEM_PROMPT
from tools import build_search_tool, build_sql_database, build_sql_tool


def build_agent(
    xlsx_path: str = XLSX_PATH,
    db_path: str = DB_PATH,
    table_name: str = TABLE_NAME,
    llm_model: str = LLM_MODEL,
    llm_temperature: float = LLM_TEMPERATURE,
    tavily_max_results: int = TAVILY_MAX_RESULTS,
):
    """Construct the master business agent: LLM + SQL tool + internet search tool + system prompt."""
    llm = ChatOpenAI(model=llm_model, temperature=llm_temperature)
    db = build_sql_database(xlsx_path, db_path, table_name)

    tools = [
        build_sql_tool(llm, db),
        build_search_tool(tavily_max_results),
    ]

    return create_agent(model=llm, tools=tools, system_prompt=SYSTEM_PROMPT)

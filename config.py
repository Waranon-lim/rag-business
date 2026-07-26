"""Environment loading and configuration constants for the business AI agent.

Loading environment variables is the one exception to "no side effects on
import" in this codebase: it is cheap, idempotent, and every module that
touches API keys needs it, so it is done once here rather than repeated
(or forgotten) elsewhere.
"""

from dotenv import load_dotenv

load_dotenv()

XLSX_PATH = "retail_orders.xlsx"
DB_PATH = "business_data.db"
TABLE_NAME = "orders"

LLM_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0

TAVILY_MAX_RESULTS = 3

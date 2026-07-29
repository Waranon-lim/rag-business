"""Environment loading and configuration constants for the business AI agent.

Loading environment variables and configuring logging are the exceptions to
"no side effects on import" in this codebase: both are cheap, idempotent,
and every module that touches API keys or reports errors needs them, so
they are done once here rather than repeated (or forgotten) elsewhere.
"""

import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

XLSX_PATH = "retail_orders.xlsx"
DB_PATH = "business_data.db"
TABLE_NAME = "orders"

# Separate from DB_PATH on purpose: business data (read-only, agent-facing)
# and conversation state (read-write, app-owned) shouldn't share a file.
CONVERSATIONS_DB_PATH = "conversations.db"

LLM_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0

TAVILY_MAX_RESULTS = 3

# Hard cap on incoming chat message size — protects against oversized
# payloads being forwarded straight into the LLM (cost/DoS surface).
MAX_MESSAGE_LENGTH = 4000

# Only the most recent N messages are sent to the agent per turn, so token
# cost/latency stay bounded as a conversation grows. The full history is
# still persisted and returned to the UI — only the model's input is capped.
MAX_HISTORY_MESSAGES = 20

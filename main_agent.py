import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_tavily import TavilySearch
from langchain_core.tools import Tool
from langchain.agents import create_agent

# 1. Load Environment Variables
load_dotenv()

# 2. Prepare SQLite Database from your Excel file
df = pd.read_excel('retail_orders.xlsx')
conn = sqlite3.connect("business_data.db", check_same_thread=False)
df.to_sql("orders", conn, if_exists="replace", index=False)

# 3. Initialize Main LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 4. Tool 1: SQL Agent for internal sales and order data
db = SQLDatabase.from_uri("sqlite:///business_data.db")
sql_agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=False)

def run_sql_query(query: str) -> str:
    """Useful for querying internal company database (retail_orders.xlsx) to get sales figures, product details, order quantities, and statistics."""
    try:
        response = sql_agent_executor.invoke({"input": query})
        if isinstance(response, dict):
            return response.get("output", str(response))
        return str(response)
    except Exception as e:
        return f"Database query error: {e}"

# 5. Tool 2: Tavily Search for external information / internet
tavily_search = TavilySearch(max_results=3)

def run_internet_search(query: str) -> str:
    """Useful for searching external information, news, market trends, or general knowledge from the internet."""
    try:
        results = tavily_search.invoke(query)
        return str(results)
    except Exception as e:
        return f"Internet search error: {e}"

# 6. Combine Tools
from langchain.tools import tool

@tool
def Internal_Sales_Database(query: str) -> str:
    """Query the internal company sales database."""
    return run_sql_query(query)

@tool
def Internet_Search(query: str) -> str:
    """Search the internet for news and general information."""
    return run_internet_search(query)

tools = [Internal_Sales_Database, Internet_Search]

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=(
        "You are a professional AI business assistant. "
        "Always choose Internal_Sales_Database for questions about company orders, revenue, products, or sales. "
        "Choose Internet_Search only for external news, trends, competitors, or general knowledge. "
        "Strict Rules: "
        "1. When querying rankings or top sellers, if multiple products share the exact same sales volume (ties), you must list all of them completely instead of truncating. "
        "2. If a user asks questions completely unrelated to business, sales, finance, or commerce (such as personal life, romance, or random trivia), you must politely refuse to answer and redirect them back to business topics. "
        "3. **Self-Introduction & Capabilities:** If the user asks what this system is, who you are, or what you can do, you must explain clearly and professionally in Thai that you are an AI Business Assistant. Detail your capabilities: querying internal sales and order databases, analyzing product trends, and searching external market data on the internet. "
        "4. **Formatting Output:** Whenever you present data, lists, rankings, or answers in Thai, you must format them cleanly using Markdown (such as bullet points, bold text, or tables where appropriate) to ensure the output is structured, neat, and easy to read."
    ),
)

master_agent = agent

# 8. Interactive Chat
if __name__ == "__main__":
    print("🤖 AI Business Assistant is ready!")
    print("Type 'exit' or 'quit' to stop.\n")

    # เก็บประวัติการสนทนา
    chat_history = []

    while True:
        try:
            # รับคำถามจากผู้ใช้
            user_input = input("User: ").strip()

            # ออกจากโปรแกรม
            if user_input.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            # ถ้าไม่ได้พิมพ์อะไร
            if not user_input:
                continue

            # เพิ่มข้อความของผู้ใช้เข้า History
            chat_history.append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            # ส่งข้อความทั้งหมดให้ Agent
            result = master_agent.invoke(
                {
                    "messages": chat_history,
                }
            )

            # ดึงข้อความล่าสุดของ AI
            ai_message = result["messages"][-1]
            ai_response = getattr(ai_message, "content", str(ai_message))

            print(f"\nAI: {ai_response}\n")

            # บันทึกคำตอบของ AI ลง History
            chat_history.append(
                {
                    "role": "assistant",
                    "content": ai_response,
                }
            )

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break

        except Exception as e:
            print(f"\n❌ Error: {e}\n")
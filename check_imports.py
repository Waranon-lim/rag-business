import sys

print("Checking environment and package availability...")

try:
    import openai
    print("✅ openai is ready")
    
    from langchain_openai import ChatOpenAI
    print("✅ langchain_openai is ready")
    
    from langchain_community.utilities import SQLDatabase
    print("✅ langchain_community (SQLDatabase) is ready")
    
    from langchain_community.agent_toolkits import create_sql_agent
    print("✅ langchain_community (SQL Agent) is ready")
    
    from langchain_tavily import TavilySearch
    print("✅ langchain_tavily is ready")
    
    from langchain_core.tools import Tool
    print("✅ langchain_core.tools is ready")
    
    
    print("✅ langchain.agents (create_tool_calling_agent) is ready")
    print("✅ langchain.chains (AgentExecutor) is ready")
    
    import pandas as pd
    import sqlite3
    print("✅ pandas and sqlite3 are ready")
    
    print("\n🎉 Success! All required libraries are installed and ready to use.")

except ImportError as e:
    print(f"\n❌ Error: Missing library or incorrect import path -> {e}")
    sys.exit(1)
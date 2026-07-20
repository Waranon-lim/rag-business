import sqlite3
import pandas as pd
from dotenv import load_dotenv # เพิ่ม
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent
from langchain_openai import ChatOpenAI

load_dotenv() # เพิ่ม

# 1. โหลดข้อมูล
df = pd.read_excel('retail_orders.xlsx')
conn = sqlite3.connect("business_data.db")
df.to_sql("orders", conn, if_exists="replace", index=False)
conn.close() # เพิ่ม

# 2. เชื่อมต่อ
db = SQLDatabase.from_uri("sqlite:///business_data.db")
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 3. สร้าง Agent
agent_executor = create_sql_agent(llm, db=db, agent_type="openai-tools", verbose=True)

# 4. ทดสอบ
response = agent_executor.invoke({"input": "ช่วยสรุปยอดขายรวมของสินค้าในหมวด Electronics ให้หน่อย"})
print(response["output"])
"""Interactive CLI entrypoint for the business AI assistant.

Run this file directly to chat with the agent from the terminal:
    python main_agent.py

Importing this module has no side effects — the agent is only constructed
when the CLI loop below actually runs.
"""

from agent import build_agent

if __name__ == "__main__":
    master_agent = build_agent()

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

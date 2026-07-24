import os
from dotenv import load_dotenv
from langchain_tavily import TavilySearch

# โหลดค่าจากไฟล์ .env
load_dotenv()

# สร้างเครื่องมือค้นหาแบบใหม่
search = TavilySearch(max_results=3)

def search_internet(query: str):
    """ฟังก์ชันสำหรับค้นหาข้อมูลจากอินเทอร์เน็ต"""
    try:
        results = search.invoke(query)
        return results
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการค้นหา: {e}"

if __name__ == "__main__":
    test_query = "เทรนด์ธุรกิจและเทคโนโลยีปี 2026"
    print(f"กำลังค้นหา: {test_query}...\n")
    
    results = search_internet(test_query)
    
    # วนลูปจัดรูปแบบให้สวยงาม
    for i, item in enumerate(results, 1):
        print(f"--- ผลลัพธ์ที่ {i} ---")
        print(f"หัวข้อ/ลิงก์: {item.get('url')}")
        print(f"เนื้อหา: {item.get('content')}\n")
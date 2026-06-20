# from __future__ import annotations

# import hashlib
# import os
# from io import BytesIO
# from typing import Iterable

# from langfuse.langchain import CallbackHandler
# import pandas as pd
# import streamlit as st
# from dotenv import load_dotenv
# from langchain_community.vectorstores import FAISS
# from langchain_core.documents import Document
# from langchain_core.messages import AIMessage
# from langchain_core.prompts import ChatPromptTemplate
# from langchain_openai import ChatOpenAI, OpenAIEmbeddings
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# from pypdf import PdfReader
# from pypdf.errors import PdfReadError
# from pydantic import SecretStr


# load_dotenv()

# LLM_MODEL = "gpt-4o-mini"
# EMBEDDING_MODEL = "text-embedding-3-small"
# DECLINE_MESSAGE = (
#     "I am sorry, but I cannot assist with this topic. My system is strictly limited to "
#     "summarizing sales, order metrics, and business strategy development based on your documents. "
#     "For other general questions, creative writing, or technical help, please try searching on Google "
#     "or consulting a general-purpose AI chatbot like ChatGPT or Claude."
# )

# CHUNK_SIZE = 1000
# CHUNK_OVERLAP = 150
# TOP_K = 20

# def configure_ui() -> None:
#     st.set_page_config(page_title="Business RAG Assistant", layout="centered")
#     st.markdown(
#         """
#         <style>
#         .stApp {
#             background-color: #0f1117;
#             color: #e6e6e6;
#         }
#         h1, h2, h3, h4 {
#             color: #e6e6e6;
#         }
#         .stChatMessage {
#             border-radius: 12px;
#             padding: 8px 12px;
#         }
#         div[data-testid="stChatInput"] textarea {
#             background-color: #1a1f2b;
#             border-radius: 12px;
#             border: 1px solid #2a3245;
#             color: #e6e6e6;
#         }
#         button[kind="secondary"], button[kind="primary"] {
#             border-radius: 10px;
#         }
#         </style>
#         """,
#         unsafe_allow_html=True,
#     )
#     st.markdown(
#         "<h2 style='text-align:center;'>Business RAG Assistant</h2>",
#         unsafe_allow_html=True,
#     )


# def init_session_state() -> None:
#     st.session_state.setdefault("chat_history", [])
#     st.session_state.setdefault("vector_store", None)
#     st.session_state.setdefault("doc_fingerprint", None)
#     st.session_state.setdefault("doc_errors", [])


# def decode_text(file_bytes: bytes) -> str:
#     try:
#         return file_bytes.decode("utf-8")
#     except UnicodeDecodeError:
#         return file_bytes.decode("latin-1")


# def load_pdf_documents(filename: str, file_bytes: bytes) -> list[Document]:
#     reader = PdfReader(BytesIO(file_bytes))
#     documents: list[Document] = []
#     for page_index, page in enumerate(reader.pages, start=1):
#         text = page.extract_text() or ""
#         if text.strip():
#             documents.append(
#                 Document(
#                     page_content=text,
#                     metadata={"source": filename, "page": page_index},
#                 )
#             )
#     return documents


# def row_to_text(row: pd.Series) -> str:
#     parts = [f"{col}: {row[col]}" for col in row.index]
#     return " | ".join(parts)


# def load_csv_documents(filename: str, file_bytes: bytes) -> list[Document]:
#     df = pd.read_csv(BytesIO(file_bytes))
#     documents: list[Document] = []
#     for row_index, (_, row) in enumerate(df.iterrows(), start=1):
#         documents.append(
#             Document(
#                 page_content=row_to_text(row),
#                 metadata={"source": filename, "row": row_index},
#             )
#         )
#     return documents


# def load_xlsx_documents(filename: str, file_bytes: bytes) -> list[Document]:
#     sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
#     documents: list[Document] = []
#     for sheet_name, sheet_df in sheets.items():
#         for row_index, (_, row) in enumerate(sheet_df.iterrows(), start=1):
#             documents.append(
#                 Document(
#                     page_content=row_to_text(row),
#                     metadata={
#                         "source": filename,
#                         "sheet": sheet_name,
#                         "row": row_index,
#                     },
#                 )
#             )
#     return documents


# def load_documents_from_uploads(
#     file_payloads: tuple[tuple[str, bytes], ...],
# ) -> tuple[list[Document], list[str]]:
#     documents: list[Document] = []
#     errors: list[str] = []
#     for filename, file_bytes in file_payloads:
#         extension = filename.lower().rsplit(".", 1)[-1]
#         try:
#             if extension == "pdf":
#                 documents.extend(load_pdf_documents(filename, file_bytes))
#             elif extension == "txt":
#                 text = decode_text(file_bytes)
#                 if text.strip():
#                     documents.append(
#                         Document(
#                             page_content=text,
#                             metadata={"source": filename},
#                         )
#                     )
#             elif extension == "csv":
#                 documents.extend(load_csv_documents(filename, file_bytes))
#             elif extension in {"xlsx", "xls"}:
#                 documents.extend(load_xlsx_documents(filename, file_bytes))
#         except (PdfReadError, ValueError, pd.errors.ParserError) as exc:
#             errors.append(f"{filename}: {exc}")
#     return documents, errors


# def split_documents(documents: Iterable[Document]) -> list[Document]:
#     splitter = RecursiveCharacterTextSplitter(
#         chunk_size=CHUNK_SIZE,
#         chunk_overlap=CHUNK_OVERLAP,
#         add_start_index=True,
#     )
#     return splitter.split_documents(list(documents))


# def build_vector_store(
#     file_payloads: tuple[tuple[str, bytes], ...],
#     api_key: str | None = None,
# ) -> tuple[FAISS | None, list[str]]:
#     documents, errors = load_documents_from_uploads(file_payloads)
#     if not documents:
#         return None, errors
#     chunks = split_documents(documents)
 
#     if api_key:
#         embeddings = OpenAIEmbeddings(
#             model=EMBEDDING_MODEL, 
#             api_key=SecretStr(api_key)
#         )
#     else:
#         embeddings = OpenAIEmbeddings(
#             model=EMBEDDING_MODEL
#         )

#     langfuse_handler = CallbackHandler()

#     return FAISS.from_documents(
#         chunks, 
#         embeddings, 
#     ), errors


# def build_context(chunks: list[Document]) -> str:
#     context_blocks = []
#     for chunk in chunks:
#         meta = chunk.metadata
#         source_parts = [meta.get("source", "unknown")]
#         if meta.get("page"):
#             source_parts.append(f"page {meta['page']}")
#         if meta.get("sheet"):
#             source_parts.append(f"sheet {meta['sheet']}")
#         if meta.get("row"):
#             source_parts.append(f"row {meta['row']}")
#         label = " | ".join(source_parts)
#         context_blocks.append(f"Source: {label}\nContent: {chunk.page_content}")
#     return "\n\n".join(context_blocks)

# def build_llm(api_key: str | None = None) -> ChatOpenAI:
#     kwargs = {"model": LLM_MODEL, "temperature": 0.2}
#     if api_key:
#         kwargs["api_key"] = SecretStr(api_key)
        
#     return ChatOpenAI(**kwargs)

# def normalize_llm_content(content: object) -> str:
#     if isinstance(content, str):
#         return content
#     if isinstance(content, list):
#         parts: list[str] = []
#         for item in content:
#             if isinstance(item, str):
#                 parts.append(item)
#             elif isinstance(item, dict):
#                 text = item.get("text")
#                 if isinstance(text, str):
#                     parts.append(text)
#         return "\n".join(parts)
#     return str(content)

# def answer_question(question: str, chunks: list[Document], api_key: str | None = None) -> str:
#     system_prompt = (
#         "You are a business analytics assistant. Your ONLY purpose is to "
#         "summarize and analyze financial metrics, sales figures, order volumes, "
#         "and to assist in generating business/marketing strategies based on the "
#         "provided data. If a user asks anything outside this scope, respond with "
#         f"exactly: {DECLINE_MESSAGE} "
#         "\n\nIMPORTANT RESPONSE GUIDELINES:\n"
#         "1. Be concise: Provide only the exact number/metric and 1-2 sentences of relevant context.\n"
#         "2. Do NOT show tables or detailed breakdowns unless explicitly requested.\n"
#         "3. When data is partial: Calculate what IS available and clearly state what is missing.\n"
#         "   Example: 'June sales total $X,XXX (data from 3 days). March data is not available in the documents.'\n"
#         "4. Do not include citations or sources in your response; they are shown separately in the UI."
#     )
#     prompt = ChatPromptTemplate.from_messages(
#         [
#             ("system", system_prompt),
#             (
#                 "human",
#                 "Question: {question}\n\nContext:\n{context}",
#             ),
#         ]
#     )
#     llm = build_llm(api_key)
#     messages = prompt.format_messages(
#         question=question,
#         context=build_context(chunks),
#     )
    
#     # 🎯 1. ประกาศตัวแปรเรียกใช้ Handler แบบคลีนๆ (ไม่มีพารามิเตอร์ข้างในเพื่อไม่ให้เอ๋อ)
#     langfuse_handler = CallbackHandler()
    
#     # 🎯 2. ส่ง langfuse_handler เข้าไปใน config ของ invoke เพื่อเริ่มส่งข้อมูลไป Docker
#     response: AIMessage = llm.invoke(
#         messages, 
#         config={
#             "callbacks": [langfuse_handler],
#             "metadata": {"project_name": "business_rag_chat"} # ใส่ชื่อกลุ่มโปรเจกต์ไว้ตรงนี้แทน
#         }
#     )
#     return normalize_llm_content(response.content).strip()


# def fingerprint_payloads(file_payloads: tuple[tuple[str, bytes], ...]) -> tuple:
#     fingerprint = []
#     for filename, file_bytes in file_payloads:
#         digest = hashlib.sha256(file_bytes).hexdigest()
#         fingerprint.append((filename, len(file_bytes), digest))
#     return tuple(fingerprint)


# def format_sources(chunks: list[Document]) -> list[dict[str, str]]:
#     formatted = []
#     for chunk in chunks:
#         meta = chunk.metadata
#         parts = [meta.get("source", "unknown")]
#         if meta.get("page"):
#             parts.append(f"page {meta['page']}")
#         if meta.get("sheet"):
#             parts.append(f"sheet {meta['sheet']}")
#         if meta.get("row"):
#             parts.append(f"row {meta['row']}")
#         label = " | ".join(parts)
#         snippet = " ".join(chunk.page_content.split())
#         if len(snippet) > 500:
#             snippet = f"{snippet[:500]}..."
#         formatted.append({"label": label, "snippet": snippet})
#     return formatted


# def render_sources(sources: list[dict[str, str]]) -> None:
#     if not sources:
#         st.write("No source references available.")
#         return
#     for index, source in enumerate(sources, start=1):
#         st.markdown(f"**{index}. {source['label']}**")
#         st.code(source["snippet"])


# def main() -> None:
#     configure_ui()
#     init_session_state()

#     with st.sidebar:
#         st.header("Documents")
#         uploaded_files = st.file_uploader(
#             "Upload PDF, TXT, CSV, or XLSX files",
#             type=["pdf", "txt", "csv", "xlsx", "xls"],
#             accept_multiple_files=True,
#         )
#         if st.button("Clear Chat"):
#             st.session_state.pop("chat_history", None)
#             st.session_state.pop("vector_store", None)
#             st.session_state.pop("doc_fingerprint", None)
#             st.session_state.pop("doc_errors", None)
#             st.rerun()

#     try:
#         api_key = st.secrets.get("OPENAI_API_KEY")
#     except Exception:
#         api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         st.info("Set OPENAI_API_KEY to enable embeddings and answers.")

#     file_payloads: tuple[tuple[str, bytes], ...] = tuple(
#         (uploaded_file.name, uploaded_file.getvalue())
#         for uploaded_file in (uploaded_files or [])
#     )

#     if file_payloads:
#         current_fingerprint = fingerprint_payloads(file_payloads)
#         if st.session_state.get("doc_fingerprint") != current_fingerprint:
#             if not api_key:
#                 st.session_state["vector_store"] = None
#                 st.session_state["doc_errors"] = []
#             else:
#                 # FIXED: Added api_key injection argument to properly initialize the target model instances
#                 vector_store, errors = build_vector_store(file_payloads, api_key=api_key)
#                 st.session_state["vector_store"] = vector_store
#                 st.session_state["doc_errors"] = errors
#             st.session_state["doc_fingerprint"] = current_fingerprint

#     if st.session_state.get("doc_errors"):
#         st.sidebar.warning("Some files could not be processed:")
#         for error in st.session_state["doc_errors"]:
#             st.sidebar.write(f"- {error}")

#     for message in st.session_state["chat_history"]:
#         with st.chat_message(message["role"]):
#             st.markdown(message["content"])
#             if message["role"] == "assistant" and message.get("sources"):
#                 with st.expander("View Source References"):
#                     render_sources(message["sources"])

#     question = st.chat_input("Ask about your financial or sales data")
#     if question:
#         st.session_state["chat_history"].append(
#             {"role": "user", "content": question}
#         )
#         with st.chat_message("user"):
#             st.markdown(question)

#         vector_store: FAISS | None = st.session_state.get("vector_store")
#         if not vector_store:
#             assistant_text = "Upload at least one document to start analyzing."
#             with st.chat_message("assistant"):
#                 st.markdown(assistant_text)
#             st.session_state["chat_history"].append(
#                 {"role": "assistant", "content": assistant_text, "sources": []}
#             )
#             return

#         chunks = vector_store.similarity_search(question, k=TOP_K)
#         answer = answer_question(question, chunks, api_key)
#         sources = format_sources(chunks)

#         with st.chat_message("assistant"):
#             st.markdown(answer)
#             with st.expander("View Source References"):
#                 render_sources(sources)

#         st.session_state["chat_history"].append(
#             {"role": "assistant", "content": answer, "sources": sources}
#         )


# if __name__ == "__main__":
#     main()

from __future__ import annotations

import hashlib
import os
from io import BytesIO

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import SecretStr
from langfuse.langchain import CallbackHandler
from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent


load_dotenv()

LLM_MODEL = "gpt-4o-mini"
DECLINE_MESSAGE = (
    "I am sorry, but I cannot assist with this topic. My system is strictly limited to "
    "summarizing sales, order metrics, and business strategy development based on your documents. "
    "For other general questions, creative writing, or technical help, please try searching on Google "
    "or consulting a general-purpose AI chatbot like ChatGPT or Claude."
)


def configure_ui() -> None:
    st.set_page_config(page_title="Business Data Agent", layout="centered")
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #0f1117;
            color: #e6e6e6;
        }
        h1, h2, h3, h4 {
            color: #e6e6e6;
        }
        .stChatMessage {
            border-radius: 12px;
            padding: 8px 12px;
        }
        div[data-testid="stChatInput"] textarea {
            background-color: #1a1f2b;
            border-radius: 12px;
            border: 1px solid #2a3245;
            color: #e6e6e6;
        }
        button[kind="secondary"], button[kind="primary"] {
            border-radius: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        "<h2 style='text-align:center;'>Business Data Agent</h2>",
        unsafe_allow_html=True,
    )


def init_session_state() -> None:
    st.session_state.setdefault("chat_history", [])
    st.session_state.setdefault("current_df", None)
    st.session_state.setdefault("doc_fingerprint", None)


def build_llm(api_key: str | None = None) -> ChatOpenAI:
    kwargs = {"model": LLM_MODEL, "temperature": 0.2}
    if api_key:
        kwargs["api_key"] = SecretStr(api_key)
    return ChatOpenAI(**kwargs)


def load_data_as_dataframe(file_payloads: tuple[tuple[str, bytes], ...]) -> pd.DataFrame | None:
    df_list = []
    for filename, file_bytes in file_payloads:
        extension = filename.lower().rsplit(".", 1)[-1]
        try:
            if extension == "csv":
                df_list.append(pd.read_csv(BytesIO(file_bytes)))
            elif extension in {"xlsx", "xls"}:
                sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
                for _, sheet_df in sheets.items():
                    df_list.append(sheet_df)
        except Exception as e:
            st.sidebar.error(f"Error loading {filename}: {e}")
            
    if not df_list:
        return None
    return pd.concat(df_list, ignore_index=True)
def ask_agent_question(question: str, df: pd.DataFrame, api_key: str | None = None) -> str:
    langfuse_handler = CallbackHandler()
    llm = build_llm(api_key)
    
    # 1. เขียนคำสั่งอธิบายบทบาทสั้นๆ กระชับ วางไว้ด้านบนสุดเพื่อให้บอทไม่สับสน
    system_instruction = (
        f"You are an expert business analytics assistant. Answer the user's question by analyzing the dataframe 'df'. "
        f"If the question is completely irrelevant to the data or business analytics, reply with exactly: {DECLINE_MESSAGE}\n\n"
    )
    
    # 2. บิวต์ Agent ตามสเปกเวอร์ชันล่าสุดของคุณ
    agent = create_pandas_dataframe_agent(
        llm,
        df,
        verbose=True,
        agent_type="openai-tools",  
        allow_dangerous_code=True,
    )
    
    # 3. ส่งคำสั่งคู่กับคำถามไปให้ Agent
    response = agent.invoke(
        {"input": f"{system_instruction}User Question: {question}"},
        config={
            "callbacks": [langfuse_handler],
            "metadata": {"project_name": "business_data_agent"}
        }
    )
    return str(response.get("output", response))


def fingerprint_payloads(file_payloads: tuple[tuple[str, bytes], ...]) -> tuple:
    fingerprint = []
    for filename, file_bytes in file_payloads:
        digest = hashlib.sha256(file_bytes).hexdigest()
        fingerprint.append((filename, len(file_bytes), digest))
    return tuple(fingerprint)


def main() -> None:
    configure_ui()
    init_session_state()

    with st.sidebar:
        st.header("Documents")
        uploaded_files = st.file_uploader(
            "Upload CSV or XLSX files",
            type=["csv", "xlsx", "xls"],
            accept_multiple_files=True,
        )
        if st.button("Clear Chat"):
            st.session_state.pop("chat_history", None)
            st.session_state.pop("current_df", None)
            st.session_state.pop("doc_fingerprint", None)
            st.rerun()

    try:
        api_key = st.secrets.get("OPENAI_API_KEY")
    except Exception:
        api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.info("Set OPENAI_API_KEY to enable analytics.")

    file_payloads: tuple[tuple[str, bytes], ...] = tuple(
        (uploaded_file.name, uploaded_file.getvalue())
        for uploaded_file in (uploaded_files or [])
    )

    if file_payloads:
        current_fingerprint = fingerprint_payloads(file_payloads)
        if st.session_state.get("doc_fingerprint") != current_fingerprint:
            if not api_key:
                st.session_state["current_df"] = None
            else:
                st.session_state["current_df"] = load_data_as_dataframe(file_payloads)
            st.session_state["doc_fingerprint"] = current_fingerprint

    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("Ask about your financial or sales data")
    if question:
        st.session_state["chat_history"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        df = st.session_state.get("current_df")
        if df is None:
            assistant_text = "Upload at least one document to start analyzing."
            with st.chat_message("assistant"):
                st.markdown(assistant_text)
            st.session_state["chat_history"].append(
                {"role": "assistant", "content": assistant_text}
            )
            return

        # รัน Agent คำนวณหาผลลัพธ์ผ่าน Pandas โค้ดอัตโนมัติ
        answer = ask_agent_question(question, df, api_key)

        with st.chat_message("assistant"):
            st.markdown(answer)

        st.session_state["chat_history"].append(
            {"role": "assistant", "content": answer}
        )


if __name__ == "__main__":
    main()
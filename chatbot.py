"""
chatbot.py — LangGraph conversational chatbot with RAG support.
"""

import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

from langchain_groq import ChatGroq
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import HumanMessage, AIMessage, SystemMessage

from database import save_message, get_messages, update_session_title


# ── LLM ───────────────────────────────────────────────────────────────────────
def get_llm():
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        temperature=0.7,
    )


def get_embeddings():
    return GoogleGenerativeAIEmbeddings(
        model="models/embedding-001",
        google_api_key=GEMINI_API_KEY,
    )


# ── Vector store cache ─────────────────────────────────────────────────────────
_vector_stores = {}


def load_pdf_to_vectorstore(session_id: str, pdf_path: str):
    loader     = PyPDFLoader(pdf_path)
    pages      = loader.load()
    splitter   = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks     = splitter.split_documents(pages)
    embeddings = get_embeddings()
    vs = FAISS.from_documents(chunks, embeddings)
    _vector_stores[session_id] = vs
    return len(chunks)


def query_vectorstore(session_id: str, query: str, k: int = 4) -> str:
    vs = _vector_stores.get(session_id)
    if not vs:
        return ""
    docs = vs.similarity_search(query, k=k)
    return "\n\n".join(d.page_content for d in docs)


def has_vectorstore(session_id: str) -> bool:
    return session_id in _vector_stores


# ── Chat function (LangGraph imported lazily) ──────────────────────────────────
def _run_langgraph(lc_messages, context):
    """Import LangGraph lazily to avoid conflicts with Gradio."""
    from typing import Annotated
    from typing_extensions import TypedDict
    from langgraph.graph import StateGraph, END
    from langgraph.graph.message import add_messages

    class ChatState(TypedDict):
        messages: Annotated[list, add_messages]
        context:  str

    def chat_node(state):
        llm     = get_llm()
        context = state.get("context", "")
        system_content = """You are a helpful, knowledgeable, and friendly AI assistant.
You have persistent memory of the conversation and can answer follow-up questions.
Be concise but thorough. Use markdown formatting where appropriate."""
        if context:
            system_content += f"\n\nRelevant context from uploaded documents:\n{context}"
        messages = [SystemMessage(content=system_content)] + list(state["messages"])
        response = get_llm().invoke(messages)
        return {"messages": [response], "context": context}

    graph = StateGraph(ChatState)
    graph.add_node("chat", chat_node)
    graph.set_entry_point("chat")
    graph.add_edge("chat", END)
    compiled = graph.compile()

    result = compiled.invoke({
        "messages": lc_messages,
        "context":  context,
    })
    return result["messages"][-1].content


# ── Public API ─────────────────────────────────────────────────────────────────
def chat(session_id: str, user_message: str, history: list) -> tuple:
    if not user_message.strip():
        return history, ""

    try:
        context = query_vectorstore(session_id, user_message) if has_vectorstore(session_id) else ""

        lc_messages = []
        for pair in history:
            if isinstance(pair, (list, tuple)) and len(pair) == 2:
                human, assistant = pair
                if human:
                    lc_messages.append(HumanMessage(content=str(human)))
                if assistant:
                    lc_messages.append(AIMessage(content=str(assistant)))
        lc_messages.append(HumanMessage(content=user_message))

        assistant_message = _run_langgraph(lc_messages, context)

        save_message(session_id, "human", user_message)
        save_message(session_id, "assistant", assistant_message)

        if len(history) == 0:
            title = user_message[:50] + ("..." if len(user_message) > 50 else "")
            update_session_title(session_id, title)

        history = history + [[user_message, assistant_message]]
        return history, ""

    except Exception as e:
        import traceback
        traceback.print_exc()
        history = history + [[user_message, f"❌ Error: {str(e)}"]]
        return history, ""


def load_session_history(session_id: str) -> list:
    messages = get_messages(session_id)
    history  = []
    i = 0
    while i < len(messages):
        if messages[i]["role"] == "human":
            human     = messages[i]["content"]
            assistant = messages[i + 1]["content"] if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant" else ""
            history.append([human, assistant])
            i += 2
        else:
            i += 1
    return history


def process_pdf(session_id: str, pdf_file) -> str:
    if pdf_file is None:
        return "No file uploaded."
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(open(pdf_file.name, "rb").read())
            tmp_path = tmp.name
        chunks = load_pdf_to_vectorstore(session_id, tmp_path)
        from database import save_document
        save_document(session_id, os.path.basename(pdf_file.name))
        return f"✅ PDF indexed! {chunks} chunks created. Ask me anything about it."
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ Error processing PDF: {e}"
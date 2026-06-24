"""
app.py — Flask UI for LangGraph Conversational Chatbot
"""

import os
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from database import init_db, create_session, get_all_sessions, delete_session
from chatbot import chat, load_session_history, process_pdf

load_dotenv()
init_db()

app = Flask(__name__)

_session_id = create_session("Default Chat")
_history = []

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>🤖 LangGraph Chatbot</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', sans-serif; background: #0f1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; }
        header { background: #161b22; border-bottom: 1px solid #21262d; padding: 16px 24px; }
        header h1 { color: #58a6ff; font-size: 1.3rem; }
        header p  { color: #8b949e; font-size: 0.85rem; margin-top: 4px; }
        .container { display: flex; flex: 1; overflow: hidden; }
        .sidebar { width: 260px; background: #161b22; border-right: 1px solid #21262d; padding: 16px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
        .sidebar button { width: 100%; padding: 8px; border-radius: 8px; border: none; cursor: pointer; font-size: 0.85rem; }
        .btn-primary { background: #1f6feb; color: white; }
        .btn-danger  { background: #da3633; color: white; }
        .btn-secondary { background: #21262d; color: #c9d1d9; border: 1px solid #30363d !important; }
        .session-item { padding: 8px; background: #21262d; border-radius: 8px; font-size: 0.8rem; color: #8b949e; cursor: pointer; word-break: break-word; }
        .session-item:hover { background: #30363d; }
        .chat-area { flex: 1; display: flex; flex-direction: column; padding: 16px; gap: 12px; overflow: hidden; }
        #chat-box { flex: 1; background: #161b22; border: 1px solid #21262d; border-radius: 12px; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
        .msg-user { background: #1f6feb; color: white; border-radius: 18px 18px 4px 18px; padding: 10px 14px; max-width: 70%; align-self: flex-end; }
        .msg-bot  { background: #21262d; color: #c9d1d9; border-radius: 18px 18px 18px 4px; padding: 10px 14px; max-width: 70%; align-self: flex-start; }
        .input-row { display: flex; gap: 8px; }
        #msg-input { flex: 1; padding: 10px 14px; background: #161b22; border: 1px solid #30363d; border-radius: 10px; color: #c9d1d9; font-size: 0.95rem; outline: none; }
        #send-btn { padding: 10px 20px; background: #1f6feb; color: white; border: none; border-radius: 10px; cursor: pointer; font-size: 0.95rem; }
        .upload-area { display: flex; flex-direction: column; gap: 6px; }
        #upload-status { font-size: 0.8rem; color: #3fb950; min-height: 20px; }
        label { font-size: 0.8rem; color: #8b949e; }
        input[type=file] { font-size: 0.8rem; color: #8b949e; }
        .thinking { color: #8b949e; font-style: italic; font-size: 0.85rem; }
    </style>
</head>
<body>
<header>
    <h1>🤖 LangGraph Conversational Chatbot</h1>
    <p>Groq LLaMA 3.3 · Gemini Embeddings · RAG · Persistent Memory</p>
</header>
<div class="container">
    <div class="sidebar">
        <button class="btn-primary" onclick="newChat()">➕ New Chat</button>
        <button class="btn-danger"  onclick="deleteChat()">🗑️ Delete Chat</button>
        <div style="border-top:1px solid #21262d;padding-top:10px;">
            <label>📄 Upload PDF for RAG</label>
            <div class="upload-area" style="margin-top:6px;">
                <input type="file" id="pdf-input" accept=".pdf">
                <button class="btn-secondary" onclick="uploadPdf()">📤 Index PDF</button>
                <div id="upload-status"></div>
            </div>
        </div>
        <div style="border-top:1px solid #21262d;padding-top:10px;">
            <label>💬 Previous Chats</label>
            <div id="sessions-list" style="margin-top:6px;display:flex;flex-direction:column;gap:6px;"></div>
        </div>
    </div>
    <div class="chat-area">
        <div id="chat-box">
            <div class="msg-bot">👋 Hello! I'm your AI assistant. How can I help you today?</div>
        </div>
        <div class="input-row">
            <input type="text" id="msg-input" placeholder="Type your message and press Enter…" onkeydown="if(event.key==='Enter') sendMessage()">
            <button id="send-btn" onclick="sendMessage()">Send 🚀</button>
        </div>
    </div>
</div>
<script>
let currentSession = null;

async function init() {
    const r = await fetch('/new_chat', {method:'POST'});
    const d = await r.json();
    currentSession = d.session_id;
    loadSessions();
}

async function newChat() {
    const r = await fetch('/new_chat', {method:'POST'});
    const d = await r.json();
    currentSession = d.session_id;
    document.getElementById('chat-box').innerHTML = '<div class="msg-bot">👋 New chat started! How can I help?</div>';
    loadSessions();
}

async function deleteChat() {
    if (!currentSession) return;
    await fetch('/delete_chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: currentSession})});
    await newChat();
}

async function loadSessions() {
    const r = await fetch('/sessions');
    const d = await r.json();
    const list = document.getElementById('sessions-list');
    list.innerHTML = '';
    d.sessions.forEach(s => {
        const div = document.createElement('div');
        div.className = 'session-item';
        div.textContent = '💬 ' + s.title.substring(0, 35);
        div.onclick = () => loadChat(s.session_id);
        list.appendChild(div);
    });
}

async function loadChat(sid) {
    currentSession = sid;
    const r = await fetch('/load_chat', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({session_id: sid})});
    const d = await r.json();
    const box = document.getElementById('chat-box');
    box.innerHTML = '';
    d.history.forEach(([human, assistant]) => {
        box.innerHTML += '<div class="msg-user">' + human + '</div>';
        box.innerHTML += '<div class="msg-bot">'  + assistant + '</div>';
    });
    box.scrollTop = box.scrollHeight;
}

async function sendMessage() {
    const input = document.getElementById('msg-input');
    const msg   = input.value.trim();
    if (!msg) return;
    input.value = '';

    const box = document.getElementById('chat-box');
    box.innerHTML += '<div class="msg-user">' + msg + '</div>';
    box.innerHTML += '<div class="msg-bot thinking" id="thinking">🤔 Thinking…</div>';
    box.scrollTop  = box.scrollHeight;

    const r = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: msg, session_id: currentSession})
    });
    const d = await r.json();

    document.getElementById('thinking').remove();
    box.innerHTML += '<div class="msg-bot">' + d.response + '</div>';
    box.scrollTop  = box.scrollHeight;
    loadSessions();
}

async function uploadPdf() {
    const fileInput = document.getElementById('pdf-input');
    if (!fileInput.files.length) { document.getElementById('upload-status').textContent = '⚠️ No file selected.'; return; }
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('session_id', currentSession);
    document.getElementById('upload-status').textContent = '⏳ Indexing…';
    const r = await fetch('/upload_pdf', {method:'POST', body: formData});
    const d = await r.json();
    document.getElementById('upload-status').textContent = d.status;
}

init();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/new_chat", methods=["POST"])
def new_chat():
    global _session_id, _history
    _session_id = create_session("New Chat")
    _history = []
    return jsonify({"session_id": _session_id})


@app.route("/delete_chat", methods=["POST"])
def delete_chat_route():
    data = request.json
    delete_session(data["session_id"])
    return jsonify({"ok": True})


@app.route("/sessions")
def sessions():
    all_sessions = get_all_sessions()
    return jsonify({"sessions": all_sessions})


@app.route("/load_chat", methods=["POST"])
def load_chat_route():
    global _session_id, _history
    data = request.json
    _session_id = data["session_id"]
    _history = load_session_history(_session_id)
    return jsonify({"history": _history})


@app.route("/chat", methods=["POST"])
def chat_route():
    global _history
    data    = request.json
    msg     = data.get("message", "")
    sid     = data.get("session_id", _session_id)
    _history, _ = chat(sid, msg, _history)
    response = _history[-1][1] if _history else "Sorry, something went wrong."
    return jsonify({"response": response})


@app.route("/upload_pdf", methods=["POST"])
def upload_pdf_route():
    if "file" not in request.files:
        return jsonify({"status": "No file uploaded."})
    file       = request.files["file"]
    session_id = request.form.get("session_id", _session_id)
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    class FakeFile:
        name = tmp_path

    status = process_pdf(session_id, FakeFile())
    return jsonify({"status": status})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7860, debug=False)
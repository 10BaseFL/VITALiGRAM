
import json
import sqlite3
from datetime import datetime
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.responses import HTMLResponse

app = FastAPI()
DB_NAME = "chat_history.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, tag TEXT, text TEXT, timestamp TEXT)''')
    # секретный ключ для уникальности ника и тега
    cursor.execute('''CREATE TABLE IF NOT EXISTS profiles 
        (tag TEXT PRIMARY KEY, name TEXT, about TEXT, avatar TEXT, secret TEXT)''')
    conn.commit()
    conn.close()

def save_profile(tag, name, about, avatar, secret):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Проверяем существует ли тег
    cursor.execute('SELECT secret FROM profiles WHERE tag = ?', (tag,))
    res = cursor.fetchone()
    
    if res and res[0] != secret:
        conn.close()
        return False # Тег занят другим человеком
    
    cursor.execute('''INSERT OR REPLACE INTO profiles (tag, name, about, avatar, secret) 
                      VALUES (?, ?, ?, ?, ?)''', (tag, name, about, avatar, secret))
    conn.commit()
    conn.close()
    return True

def get_profile(tag):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT name, avatar FROM profiles WHERE tag = ?', (tag,))
    res = cursor.fetchone()
    conn.close()
    if res:
        return {"name": res[0], "avatar": res[1]}
    return {"name": tag, "avatar": "https://cdn-icons-png.flaticon.com/512/149/149071.png"}

def save_message(tag, text, timestamp):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO messages (tag, text, timestamp) VALUES (?, ?, ?)', (tag, text, timestamp))
    conn.commit()
    conn.close()

def get_history(limit=50):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT tag, text, timestamp FROM messages ORDER BY id DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    history = []
    for r in reversed(rows):
        prof = get_profile(r[0])
        history.append({"tag": r[0], "text": r[1], "timestamp": r[2], "user": prof['name'], "avatar": prof['avatar']})
    return history

init_db()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        for msg in get_history():
            await websocket.send_text(json.dumps(msg))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

html_template = """
<!DOCTYPE html>
<html>
    <head>
        <title>VITALiGRAM Media</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: 'Segoe UI', sans-serif; margin: 0; background: #0f0f0f; color: #e0e0e0; display: flex; flex-direction: column; height: 100vh; }
            header { background: #181818; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #2ecc71; }
            h1 { color: #2ecc71; margin: 0; font-size: 1.2rem; }
            
            #messages { flex-grow: 1; list-style: none; padding: 15px; margin: 0; overflow-y: auto; overflow-x: hidden; }
            .msg-item { display: flex; gap: 12px; margin-bottom: 20px; align-items: flex-start; max-width: 100%; }
            .avatar { width: 45px; height: 45px; border-radius: 50%; object-fit: cover; border: 2px solid #2ecc71; flex-shrink: 0; }
            
            .msg-content { 
                background: #1e1e1e; padding: 10px 15px; border-radius: 0 15px 15px 15px; 
                max-width: 75%; /* Ограничение ширины */
                box-shadow: 0 2px 5px rgba(0,0,0,0.3);
                overflow-wrap: anywhere; /* ИСПРАВЛЕНИЕ ВЫХОДА ЗА РАМКИ */
                word-break: break-word;
            }
            
            .name { color: #2ecc71; font-weight: bold; font-size: 0.95rem; margin-right: 5px; }
            .tag { color: #555; font-size: 0.8rem; }
            .text { font-size: 1rem; color: #f0f0f0; margin-top: 5px; }
            .time { color: #444; font-size: 0.7rem; margin-top: 8px; display: block; text-align: right; }

            /* Стили для медиа */
            .media-content { max-width: 100%; border-radius: 8px; margin-top: 8px; display: block; border: 1px solid #333; }

            footer { padding: 15px; background: #181818; border-top: 1px solid #222; }
            .input-area { display: flex; gap: 10px; max-width: 1000px; margin: 0 auto; }
            input, textarea { background: #252525; border: 1px solid #333; color: white; padding: 12px; border-radius: 10px; outline: none; font-size: 1rem; }
            input:focus { border-color: #2ecc71; }
            #messageText { flex-grow: 1; }
            
            button { background: #2ecc71; color: #000; border: none; padding: 10px 20px; border-radius: 10px; font-weight: bold; cursor: pointer; transition: 0.2s; }
            button:hover { background: #27ae60; }
            .btn-profile { background: transparent; color: #2ecc71; border: 1px solid #2ecc71; }

            #profileModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.9); justify-content: center; align-items: center; z-index: 1000; }
            .modal-content { background: #181818; padding: 30px; border-radius: 20px; width: 90%; max-width: 400px; display: flex; flex-direction: column; gap: 15px; border: 1px solid #2ecc71; }
        </style>
    </head>
    <body>
        <header>
            <h1>VITALiGRAM</h1>
            <button class="btn-profile" onclick="toggleProfile()">ПРОФИЛЬ</button>
        </header>

        <ul id='messages'></ul>

        <footer>
            <div class="input-area">
                <input type="text" id="messageText" placeholder="Сообщение или ссылка на фото/видео..." autocomplete="off">
                <button onclick="sendChat()">➤</button>
            </div>
        </footer>

        <div id="profileModal">
            <div class="modal-content">
                <h2 style="color:#2ecc71; margin-top:0;">Настройки</h2>
                <input type="text" id="p_tag" placeholder="@тег (уникальный)">
                <input type="text" id="p_name" placeholder="Имя">
                <input type="text" id="p_avatar" placeholder="URL аватарки">
                <button onclick="saveProfile()">СОХРАНИТЬ</button>
                <button style="background:#333; color:white;" onclick="toggleProfile()">ОТМЕНА</button>
            </div>
        </div>

        <script>
            var ws = new WebSocket((window.location.protocol === "https:" ? "wss://" : "ws://") + window.location.host + "/ws");
            
            // Генерация или получение секретного ключа для защиты ника
            let mySecret = localStorage.getItem('chat_secret');
            if(!mySecret) {
                mySecret = Math.random().toString(36).substring(2) + Date.now().toString(36);
                localStorage.setItem('chat_secret', mySecret);
            }
            
            let myTag = localStorage.getItem('chat_tag') || 'user' + Math.floor(Math.random()*1000);

            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                
                if(data.type === "error") {
                    alert(data.text);
                    return;
                }

                const li = document.createElement('li');
                li.className = 'msg-item';
                
                // Функция для превращения ссылок в картинки/видео
                const contentHtml = parseMedia(data.text);

                li.innerHTML = `
                    <img src="${data.avatar}" class="avatar">
                    <div class="msg-content">
                        <div class="msg-header">
                            <span class="name">${data.user}</span>
                            <span class="tag">@${data.tag}</span>
                        </div>
                        <div class="text">${contentHtml}</div>
                        <span class="time">${data.timestamp}</span>
                    </div>
                `;
                document.getElementById('messages').appendChild(li);
                document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
            };

            function parseMedia(text) {
                const imgRegex = /(https?:\/\/.*\.(?:png|jpg|jpeg|gif|webp))/i;
                const vidRegex = /(https?:\/\/.*\.(?:mp4|webm|ogg|mov))/i;
                const ytRegex = /(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?(.+)/i;

                if (imgRegex.test(text)) {
                    return `${text}<br><img src="${text}" class="media-content">`;
                }
                if (vidRegex.test(text)) {
                    return `${text}<br><video src="${text}" class="media-content" controls></video>`;
                }
                return text.replace(/[<>]/g, ''); // Защита от XSS
            }

            function sendChat() {
                const input = document.getElementById("messageText");
                if (input.value) {
                    ws.send(JSON.stringify({ type: "chat", tag: myTag, text: input.value }));
                    input.value = '';
                }
            }

            function saveProfile() {
                const tag = document.getElementById('p_tag').value.replace('@','').trim();
                const name = document.getElementById('p_name').value.trim();
                const avatar = document.getElementById('p_avatar').value.trim();

                if(!tag) return alert("Тег обязателен!");

                ws.send(JSON.stringify({
                    type: "profile",
                    tag: tag,
                    name: name || tag,
                    avatar: avatar || "https://cdn-icons-png.flaticon.com/512/149/149071.png",
                    secret: mySecret
                }));
                
                myTag = tag;
                localStorage.setItem('chat_tag', tag);
                toggleProfile();
            }

            function toggleProfile() {
                const m = document.getElementById("profileModal");
                m.style.display = m.style.display === "flex" ? "none" : "flex";
                document.getElementById('p_tag').value = myTag;
            }

            document.getElementById('messageText').addEventListener('keypress', (e) => { if(e.key === 'Enter') sendChat(); });
        </script>
    </body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html_template)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            raw_data = await websocket.receive_text()
            data = json.loads(raw_data)
            
            if data['type'] == "profile":
                success = save_profile(data['tag'], data['name'], "", data['avatar'], data['secret'])
                if not success:
                    await websocket.send_text(json.dumps({
                        "type": "error", 
                        "text": "Этот тег уже занят другим пользователем!"
                    }))
                
            elif data['type'] == "chat":
                tag = data['tag']
                prof = get_profile(tag)
                ts = datetime.now().strftime("%H:%M")
                save_message(tag, data['text'], ts)
                await manager.broadcast(json.dumps({
                    "type": "chat", "tag": tag, "user": prof['name'], 
                    "avatar": prof['avatar'], "text": data['text'], "timestamp": ts
                }))
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__": # порт сюдымы
    import uvicorn
    uvicorn.run(app, host="192.168.1.12", port=8090)

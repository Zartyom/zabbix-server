from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

DATABASE_FILE = 'zabbix_messages.db'

# ⬇️ СНАЧАЛА ОПРЕДЕЛЯЕМ ФУНКЦИЮ
def init_database():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host_name TEXT,
            problem_name TEXT,
            severity TEXT,
            message_text TEXT,
            timestamp DATETIME,
            is_read INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ База данных создана")

# ⬇️ ПОТОМ ВЫЗЫВАЕМ
init_database()

# ⬇️ ПОТОМ ВСЕ МАРШРУТЫ
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "message": "Zabbix Server работает на Timeweb Cloud!",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/api/zabbix-webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f"📨 Получено: {data}")
        
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (host_name, problem_name, severity, message_text, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            data.get('host_name', 'Unknown'),
            data.get('problem_name', 'Unknown'),
            data.get('severity', 'Unknown'),
            data.get('message', ''),
            datetime.now()
        ))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/messages', methods=['GET'])
def get_messages():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, host_name, problem_name, severity, message_text, timestamp FROM messages ORDER BY timestamp DESC LIMIT 50')
    messages = []
    for row in cursor.fetchall():
        messages.append({
            "id": row[0],
            "host_name": row[1],
            "problem_name": row[2],
            "severity": row[3],
            "message": row[4],
            "timestamp": row[5]
        })
    conn.close()
    return jsonify({"success": True, "messages": messages})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

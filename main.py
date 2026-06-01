import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import bcrypt
import secrets
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ===== ПАРАМЕТРЫ ПОДКЛЮЧЕНИЯ К БД (ЗАМЕНИТЕ НА ВАШИ) =====
DB_HOST = os.environ.get('DB_HOST', '192.168.0.4')   # ваш приватный IP кластера
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'pc_monitor_db')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASS = os.environ.get('DB_PASS', 'ваш_пароль')

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=5
    )

# ===== ТЕСТОВЫЙ МАРШРУТ =====
@app.route('/api/test_db')
def test_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        return jsonify({"status": "DB connected"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== АВТОРИЗАЦИЯ =====
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, password_hash, role FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            token = secrets.token_hex(32)
            cur.execute("UPDATE users SET token = %s WHERE id = %s", (token, user['id']))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({'success': True, 'token': token, 'user_id': user['id'], 'role': user['role']})
        cur.close()
        conn.close()
        return jsonify({'error': 'Неверный логин или пароль'}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== ПРОВЕРКА ТОКЕНА =====
@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, role FROM users WHERE token = %s", (token,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            return jsonify({'success': True, 'user_id': user['id'], 'role': user['role']})
        return jsonify({'error': 'Unauthorized'}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===== ОСТАЛЬНЫЕ МАРШРУТЫ (get_messages, mark_read, get_tasks, complete_task, restore_task, stats, админка) =====
# ... добавьте их из предыдущей полной версии сервера

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

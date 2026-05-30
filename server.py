from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import bcrypt
import secrets
import os
from datetime import datetime
import sqlite3

app = Flask(__name__)
CORS(app)

# === Параметры подключения к PostgreSQL (ваши данные) ===
DB_HOST = '192.168.0.4'        # приватный IP вашего кластера
DB_PORT = 5432
DB_NAME = 'pc_monitor_db'      # имя вашей базы данных (может быть default_db, уточните)
DB_USER = 'gen_user'
DB_PASS = 'mlas2024'

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

# === Инициализация таблиц (если не существуют) ===
def init_postgres_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Проверяем, есть ли таблица users (достаточно одной)
        cur.execute("SELECT 1 FROM users LIMIT 1")
    except psycopg2.ProgrammingError:
        # Таблицы нет, создаём
        conn.rollback()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'reader',
                token VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                host_name VARCHAR(100) NOT NULL,
                trigger_name VARCHAR(255) NOT NULL,
                severity VARCHAR(50) NOT NULL,
                comments TEXT,
                timestamp VARCHAR(30) NOT NULL,
                completed_at TIMESTAMP NULL DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                host_name VARCHAR(100) NOT NULL,
                problem_name VARCHAR(255) NOT NULL,
                severity VARCHAR(50) NOT NULL,
                message TEXT,
                timestamp VARCHAR(30) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_message_read (
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE,
                read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, message_id)
            )
        """)
        conn.commit()
        # Добавляем админа, если его ещё нет
        hashed = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s) ON CONFLICT (username) DO NOTHING", ('admin', hashed, 'admin'))
        conn.commit()
        print("✅ Таблицы PostgreSQL созданы, добавлен admin (пароль admin123)")
    finally:
        cur.close()
        conn.close()

def migrate_sqlite_to_postgres():
    sqlite_db = 'zabbix_messages.db'
    if not os.path.exists(sqlite_db):
        return
    conn_sqlite = sqlite3.connect(sqlite_db)
    cur_sqlite = conn_sqlite.cursor()
    try:
        cur_sqlite.execute("SELECT id, host_name, problem_name, severity, message_text, timestamp FROM messages")
    except sqlite3.OperationalError:
        conn_sqlite.close()
        return
    rows = cur_sqlite.fetchall()
    if not rows:
        conn_sqlite.close()
        return
    pg_conn = get_db_connection()
    pg_cur = pg_conn.cursor()
    for row in rows:
        try:
            pg_cur.execute("""
                INSERT INTO messages (host_name, problem_name, severity, message, timestamp, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (row[1], row[2], row[3], row[4], row[5], row[5]))
        except:
            pass
    pg_conn.commit()
    pg_cur.close()
    pg_conn.close()
    conn_sqlite.close()
    print("✅ Сообщения из SQLite перенесены в PostgreSQL (если были)")

# Выполняем один раз при старте
init_postgres_tables()
migrate_sqlite_to_postgres()

# === Проверка токена ===
def check_auth():
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '')
    if not token:
        return None, None
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, role FROM users WHERE token = %s", (token,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if not user:
        return None, None
    return user['id'], user['role']

# ==================== СТАРЫЕ МАРШРУТЫ ====================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "message": "Zabbix Server работает на Timeweb Cloud с PostgreSQL!",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.route('/api/zabbix-webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        print(f"📨 Получено: {data}")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO messages (host_name, problem_name, severity, message, timestamp, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data.get('host_name', 'Unknown'),
            data.get('problem_name', 'Unknown'),
            data.get('severity', 'Unknown'),
            data.get('message', ''),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now()
        ))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/messages', methods=['GET'])
def get_messages_old():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, host_name, problem_name, severity, message, timestamp
        FROM messages
        ORDER BY timestamp DESC
        LIMIT 50
    """)
    rows = cur.fetchall()
    messages = [dict(row) for row in rows]
    cur.close()
    conn.close()
    return jsonify({"success": True, "messages": messages})

# ==================== НОВЫЕ МАРШРУТЫ ДЛЯ ANDROID ====================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
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

@app.route('/api/check_auth', methods=['GET'])
def check_auth_route():
    user_id, role = check_auth()
    if user_id:
        return jsonify({'success': True, 'user_id': user_id, 'role': role})
    return jsonify({'error': 'Unauthorized'}), 401

@app.route('/api/get_messages_for_user', methods=['GET'])
def get_messages_for_user():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT m.id, m.host_name, m.problem_name, m.severity, m.message, m.timestamp,
               CASE WHEN urm.user_id IS NOT NULL THEN true ELSE false END as is_read
        FROM messages m
        LEFT JOIN user_message_read urm ON m.id = urm.message_id AND urm.user_id = %s
        ORDER BY m.timestamp DESC
    """, (user_id,))
    messages = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({'messages': messages})

@app.route('/api/mark_read', methods=['POST'])
def mark_read():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    message_id = data.get('id')
    if not message_id:
        return jsonify({'error': 'Missing id'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO user_message_read (user_id, message_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, message_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/get_tasks', methods=['GET'])
def get_tasks():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT id, host_name, trigger_name, severity, comments, timestamp, completed_at
        FROM tasks
        WHERE user_id = %s AND completed_at IS NULL
        ORDER BY created_at DESC
    """, (user_id,))
    tasks = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify({'tasks': tasks})

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    task_id = data.get('task_id')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET completed_at = NOW() WHERE id = %s AND user_id = %s", (task_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/restore_task', methods=['POST'])
def restore_task():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    task_id = data.get('task_id')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET completed_at = NULL WHERE id = %s AND user_id = %s", (task_id, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/stats', methods=['GET'])
def stats():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = %s AND completed_at IS NULL", (user_id,))
    active = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = %s AND completed_at >= NOW() - INTERVAL '1 day'", (user_id,))
    solved_day = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = %s AND completed_at >= NOW() - INTERVAL '7 days'", (user_id,))
    solved_week = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM tasks WHERE user_id = %s AND completed_at >= NOW() - INTERVAL '30 days'", (user_id,))
    solved_month = cur.fetchone()[0]
    cur.close()
    conn.close()
    return jsonify({'active': active, 'solved_day': solved_day, 'solved_week': solved_week, 'solved_month': solved_month})

@app.route('/api/list_users', methods=['GET'])
def list_users():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
    users = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(users)

@app.route('/api/create_user', methods=['POST'])
def create_user():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    user_role = data.get('role', 'reader')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    token = secrets.token_hex(32)
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO users (username, password_hash, token, role) VALUES (%s, %s, %s, %s)", (username, hashed, token, user_role))
        conn.commit()
        return jsonify({'success': True, 'id': cur.lastrowid})
    except psycopg2.IntegrityError:
        return jsonify({'error': 'Пользователь уже существует'}), 409
    finally:
        cur.close()
        conn.close()

@app.route('/api/update_user', methods=['POST'])
def update_user():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    user_id = data.get('user_id')
    new_role = data.get('role')
    new_password = data.get('password')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    if new_role:
        cur.execute("UPDATE users SET role = %s WHERE id = %s", (new_role, user_id))
    if new_password:
        hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed, user_id))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/delete_user', methods=['POST'])
def delete_user():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    user_id = data.get('user_id')
    current_id, _ = check_auth()
    if user_id == current_id:
        return jsonify({'error': 'Нельзя удалить себя'}), 400
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

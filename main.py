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

# Параметры подключения к базе данных (задаются в переменных окружения)
DB_HOST = os.environ.get('DB_HOST', '45.153.71.178')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'default_db')
DB_USER = os.environ.get('DB_USER', 'gen_user')
DB_PASS = os.environ.get('DB_PASS', 'mlas2024')

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=5
    )

# Создание таблиц (если не существуют)
def init_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                token VARCHAR(255) DEFAULT NULL,
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
        # Таблица задач (общая, без привязки к пользователю)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                host_name VARCHAR(100) NOT NULL,
                trigger_name VARCHAR(255) NOT NULL,
                severity VARCHAR(50) NOT NULL,
                comments TEXT,
                timestamp VARCHAR(30) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Таблица статуса выполнения задач по пользователям (индивидуально)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_task_status (
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
                completed_at TIMESTAMP NOT NULL,
                PRIMARY KEY (user_id, task_id)
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print("Ошибка инициализации таблиц:", e)

init_tables()

# Вспомогательная функция проверки токена
def check_auth():
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '')
    if not token:
        return None, None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, role FROM users WHERE token = %s", (token,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            return user['id'], user['role']
    except Exception:
        pass
    return None, None

# ----- Корневые маршруты для проверки работоспособности -----
@app.route('/')
def home():
    return "Zabbix monitoring API is running"

@app.route('/api')
def api_root():
    return jsonify({"status": "ok", "message": "API is running"})

# ----- Веб-перехватчик от Забикс (создаёт сообщение и общую задачу) -----
@app.route('/api/zabbix-webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        conn = get_db_connection()
        cur = conn.cursor()
        # Сохраняем сообщение
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
        # Создаём задачу (общую, без привязки к пользователю)
        cur.execute("""
            INSERT INTO tasks (host_name, trigger_name, severity, comments, timestamp, created_at)
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

# ----- Аутентификация -----
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

@app.route('/api/check_auth', methods=['GET'])
def check_auth_route():
    user_id, role = check_auth()
    if user_id:
        return jsonify({'success': True, 'user_id': user_id, 'role': role})
    return jsonify({'error': 'Unauthorized'}), 401

# ----- Сообщения (индивидуальное прочтение) -----
@app.route('/api/get_messages', methods=['GET'])
def get_messages():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
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
        return jsonify({"messages": messages})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/mark_read', methods=['POST'])
def mark_read():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    message_id = data.get('id')
    if not message_id:
        return jsonify({'error': 'Missing id'}), 400
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO user_message_read (user_id, message_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (user_id, message_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----- Задачи (индивидуальное выполнение) -----
@app.route('/api/get_tasks', methods=['GET'])
def get_tasks():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT t.id, t.host_name, t.trigger_name, t.severity, t.comments, t.timestamp
            FROM tasks t
            LEFT JOIN user_task_status uts ON t.id = uts.task_id AND uts.user_id = %s
            WHERE uts.user_id IS NULL
            ORDER BY t.created_at DESC
        """, (user_id,))
        tasks = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"tasks": tasks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'error': 'Missing task_id'}), 400
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO user_task_status (user_id, task_id, completed_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING", (user_id, task_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/restore_task', methods=['POST'])
def restore_task():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    task_id = data.get('task_id')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM user_task_status WHERE user_id = %s AND task_id = %s", (user_id, task_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----- Архив выполненных задач (индивидуально) -----
@app.route('/api/get_archive', methods=['GET'])
def get_archive():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT t.id, t.host_name, t.trigger_name, t.severity, t.comments, t.timestamp, uts.completed_at
            FROM tasks t
            JOIN user_task_status uts ON t.id = uts.task_id AND uts.user_id = %s
            ORDER BY uts.completed_at DESC
        """, (user_id,))
        tasks = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"tasks": tasks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----- Статистика (индивидуальная) -----
@app.route('/api/stats', methods=['GET'])
def stats():
    user_id, _ = check_auth()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM tasks t
            LEFT JOIN user_task_status uts ON t.id = uts.task_id AND uts.user_id = %s
            WHERE uts.user_id IS NULL
        """, (user_id,))
        active = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM user_task_status
            WHERE user_id = %s AND completed_at >= NOW() - INTERVAL '1 day'
        """, (user_id,))
        solved_day = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM user_task_status
            WHERE user_id = %s AND completed_at >= NOW() - INTERVAL '7 days'
        """, (user_id,))
        solved_week = cur.fetchone()[0]
        cur.execute("""
            SELECT COUNT(*) FROM user_task_status
            WHERE user_id = %s AND completed_at >= NOW() - INTERVAL '30 days'
        """, (user_id,))
        solved_month = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({'active': active, 'solved_day': solved_day, 'solved_week': solved_week, 'solved_month': solved_month})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ----- Администрирование (только для администратора) -----
@app.route('/api/list_users', methods=['GET'])
def list_users():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, username, role, created_at FROM users ORDER BY id")
        users = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"users": users})   # обернули в объект
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/create_user', methods=['POST'])
def create_user():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    user_role = data.get('role', 'user')
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    token = secrets.token_hex(32)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash, token, role) VALUES (%s, %s, %s, %s)", (username, hashed, token, user_role))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_user', methods=['POST'])
def update_user():
    _, role = check_auth()
    if role != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    new_role = data.get('role')
    new_password = data.get('password')
    try:
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
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ----- Тестовый маршрут для проверки соединения с БД -----
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

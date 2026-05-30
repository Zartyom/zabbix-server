#!/usr/bin/env python3
import sys
import traceback

# Принудительно сбрасываем буфер вывода
sys.stderr = sys.stdout

print("=== Starting main.py ===", flush=True)

try:
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    import psycopg2
    import psycopg2.extras
    import bcrypt
    import secrets
    import os
    from datetime import datetime
    import sqlite3
    print("✓ Imports successful", flush=True)
except Exception as e:
    print(f"✗ Import error: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

try:
    app = Flask(__name__)
    CORS(app)
    print("✓ Flask app created", flush=True)

    # === Параметры подключения к PostgreSQL ===
    # Используем публичный IP базы данных, так как внутри контейнера приватный может быть недоступен
    DB_HOST = os.environ.get('DB_HOST', '45.153.71.178')  # публичный IP
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME', 'default_db')
    DB_USER = os.environ.get('DB_USER', 'gen_user')
    DB_PASS = os.environ.get('DB_PASS', 'mlas2024')

    print(f"DB config: host={DB_HOST}, port={DB_PORT}, dbname={DB_NAME}, user={DB_USER}", flush=True)

    def get_db_connection():
        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )

    # === Инициализация таблиц (проверяем подключение) ===
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        print("✓ Database connection successful", flush=True)
    except Exception as e:
        print(f"✗ Database connection failed: {e}", flush=True)
        traceback.print_exc()
        # Не выходим, но предупреждаем

    def init_postgres_tables():
        try:
            conn = get_db_connection()
            cur = conn.cursor()
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
            cur.close()
            conn.close()
            print("✓ Tables created/verified", flush=True)
        except Exception as e:
            print(f"✗ Table creation error: {e}", flush=True)

    init_postgres_tables()

    # === Проверка токена ===
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
            return (user['id'], user['role']) if user else (None, None)
        except Exception as e:
            print(f"Auth check error: {e}", flush=True)
            return None, None

    # ==================== МАРШРУТЫ ====================
    @app.route('/')
    def home():
        return jsonify({"status": "online", "message": "Zabbix Server работает на Timeweb Cloud!"})

    @app.route('/api/get_messages', methods=['GET'])
    def get_messages():
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT id, host_name, problem_name, severity, message, timestamp FROM messages ORDER BY timestamp DESC LIMIT 50")
            messages = [dict(row) for row in cur.fetchall()]
            cur.close()
            conn.close()
            return jsonify({"messages": messages})
        except Exception as e:
            print(f"Error in /api/get_messages: {e}", flush=True)
            return jsonify({"error": str(e)}), 500

    @app.route('/api/login', methods=['POST'])
    def login():
        # ... (полный код как выше, но с try/except)
        pass

    # ... остальные маршруты (скопировать из предыдущего полного кода)

    print("✓ All routes registered", flush=True)

except Exception as e:
    print(f"✗ Fatal error: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

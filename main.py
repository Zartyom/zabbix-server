#!/usr/bin/env python3
import sys
import traceback 

# Перенаправляем stderr в stdout и отключаем буферизацию
sys.stderr = sys.stdout
print("=== STARTING APPLICATION ===", flush=True)

try:
    print("Importing modules...", flush=True)
    from flask import Flask, request, jsonify
    from flask_cors import CORS
    import psycopg2
    import psycopg2.extras
    import bcrypt
    import secrets
    import os
    from datetime import datetime
    import sqlite3
    print("✓ All modules imported", flush=True)

    print("Creating Flask app...", flush=True)
    app = Flask(__name__)
    CORS(app)
    print("✓ Flask app created", flush=True)

    # === Параметры подключения к PostgreSQL ===
    # Используем переменные окружения (должны быть заданы в панели)
    DB_HOST = os.environ.get('DB_HOST', '45.153.71.178')  # публичный IP базы данных
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

    # Проверка подключения к БД (не критично для запуска, но логируем)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        print("✓ Database connection successful", flush=True)
    except Exception as e:
        print(f"⚠ Database connection failed: {e}", flush=True)
        # Не выходим, приложение может работать без БД для теста

    # Создание таблиц (если нужно)
    def init_tables():
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
            print(f"⚠ Table creation error: {e}", flush=True)

    init_tables()

    # === Минимальный маршрут для проверки работоспособности ===
    @app.route('/')
    def home():
        return jsonify({"status": "online", "message": "Zabbix Server работает"})

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
            return jsonify({"error": str(e)}), 500

    # Добавьте остальные маршруты (login, tasks, admin и т.д.) ниже...

    print("✓ All routes registered", flush=True)

except Exception as e:
    print(f"❌ FATAL ERROR: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

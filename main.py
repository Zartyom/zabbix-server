import os
from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
from datetime import datetime

app = Flask(__name__)
CORS(app)

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

# Таблицы создаются один раз (можно выполнить вручную через Adminer)
# CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, host_name TEXT, trigger_name TEXT, severity TEXT, comments TEXT, timestamp TEXT, created_at TIMESTAMP, completed_at TIMESTAMP NULL);

@app.route('/api/get_tasks', methods=['GET'])
def get_tasks():
    # Временно без авторизации
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id, host_name, trigger_name, severity, comments, timestamp, completed_at FROM tasks ORDER BY created_at DESC")
        tasks = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify({"tasks": tasks})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    data = request.json
    task_id = data.get('task_id')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET completed_at = NOW() WHERE id = %s", (task_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/restore_task', methods=['POST'])
def restore_task():
    data = request.json
    task_id = data.get('task_id')
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET completed_at = NULL WHERE id = %s", (task_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/zabbix-webhook', methods=['POST'])
def webhook():
    data = request.json
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tasks (host_name, trigger_name, severity, comments, timestamp, created_at, completed_at)
        VALUES (%s, %s, %s, %s, %s, NOW(), NULL)
    """, (
        data.get('host_name', 'Unknown'),
        data.get('problem_name', 'Unknown'),
        data.get('severity', 'Unknown'),
        data.get('message', ''),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"success": True}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

from flask import Flask, request, jsonify, render_template
import sqlite3
from datetime import datetime, timezone

app = Flask(__name__)
DB_PATH = 'tasks.db'


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        priority INTEGER DEFAULT 1,
        completed INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    count = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    if count == 0:
        now = datetime.now(timezone.utc).isoformat()
        c.executemany(
            "INSERT INTO tasks (title, description, priority, completed, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("Купить молоко", "2 литра", 1, 0, now),
                ("Позвонить маме", "", 2, 0, now),
                ("Сдать отчёт", "до пятницы", 3, 1, now),
            ],
        )
    conn.commit()
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    status = request.args.get('status', 'all')
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))

    conn = get_db()
    c = conn.cursor()
    query = "SELECT * FROM tasks"
    if status == 'active':
        query += " WHERE completed = 0"        # BUG 1a
    elif status == 'completed':
        query += " WHERE completed = 1"        # BUG 1b

    offset = (page - 1) * per_page
    query += f" ORDER BY created_at DESC LIMIT {per_page} OFFSET {offset}"  # BUG 2

    rows = c.execute(query).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/tasks/search', methods=['GET'])
def search_tasks():
    q = request.args.get('q', '')
    conn = get_db()
    c = conn.cursor()
    query = f"SELECT * FROM tasks WHERE title LIKE ?"   # BUG 3: SQL-инъекция
    try:
        rows = c.execute(query(f'%{q}%',)).fetchall()
        result = [dict(r) for r in rows]
    except Exception as e:
        result = {"error": str(e)}
    conn.close()
    return jsonify(result)


@app.route('/api/tasks', methods=['POST'])
def create_task():
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    if not title:
        return jsonify({"error":"title is required"}), 400
    # BUG 4: нет валидации пустого title
    description = data.get('description', '')
    priority = data.get('priority', 1)
    created_at = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (title, description, priority, created_at) "
        "VALUES (?, ?, ?, ?)",
        (title, description, priority, created_at),
    )
    conn.commit()
    task_id = c.lastrowid
    conn.close()
    return jsonify({"id": task_id, "message": "created"}), 201   # BUG 5: должно быть 201


@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    data = request.get_json() or {}
    conn = get_db()
    c = conn.cursor()
    if 'completed' in data:
        c.execute("UPDATE tasks SET completed = ? WHERE id = ?", (data['completed'],))   # BUG 6: нет WHERE
    if 'title' in data:
        c.execute("UPDATE tasks SET title = ? WHERE id = ?", (data['title'], task_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "updated"})


@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("#DELETE FROM tasks WHERE id = ?", (task_id,))   # BUG 7: soft-delete
    conn.commit()
    conn.close()
    return jsonify({"message": "deleted"})


@app.route('/api/stats', methods=['GET'])
def stats():
    conn = get_db()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    completed = c.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1").fetchone()[0]
    conn.close()
    rate = round((completed / total) * 100, 2) if total > 0 else 0    # BUG 8: доля, а не проценты
    return jsonify({
        "total": total,
        "completed": completed,
        "active": total - completed,
        "rate": rate,
    })


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

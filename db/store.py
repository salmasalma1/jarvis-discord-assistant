"""db/store.py — SQLite (members / tasks / activity_log / knowledge).

Used for productivity (F5), activity tracking, and shared state.
Works with only the standard library.
"""
import os
import sqlite3
import threading
from datetime import datetime

from config import DB_PATH

_conn = None
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS members(
  id TEXT PRIMARY KEY, name TEXT, role TEXT, lane TEXT, score INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, title TEXT, owner TEXT, due TEXT, status TEXT, deps TEXT, repo TEXT);
CREATE TABLE IF NOT EXISTS activity_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, kind TEXT, detail TEXT,
  points INTEGER DEFAULT 0, ts TEXT);
CREATE TABLE IF NOT EXISTS knowledge(
  id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT, doc_name TEXT,
  content TEXT, metadata TEXT, ts TEXT);
"""


def _connect():
    global _conn
    if _conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def _run(sql, params=(), fetch=False):
    with _lock:
        c = _connect()
        cur = c.execute(sql, params)
        if fetch:
            return [dict(r) for r in cur.fetchall()]
        c.commit()
        return cur.lastrowid


# ---------- Productivity (F5) ----------
POINTS = {"query": 1, "task_done": 5, "commit": 3, "meeting": 2}


def log_activity(user_id, kind, detail=None, points=None, name=""):
    pts = points if points is not None else POINTS.get(kind, 0)
    _run("INSERT INTO activity_log(user_id,kind,detail,points,ts) VALUES(?,?,?,?,?)",
         (user_id, kind, detail, pts, datetime.utcnow().isoformat()))
    _run("""INSERT INTO members(id,name) VALUES(?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name""", (user_id, name))
    _run("UPDATE members SET score = score + ? WHERE id = ?", (pts, user_id))
    return pts


def add_member(member_id, name, role="", lane=""):
    _run("""INSERT INTO members(id,name,role,lane) VALUES(?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, role=excluded.role,
            lane=excluded.lane""", (member_id, name, role, lane))


def list_members():
    return _run("SELECT * FROM members", fetch=True)


def get_weekly_metrics(since=None):
    since = since or (datetime.utcnow() - __import__("datetime").timedelta(days=7)).isoformat()
    return _run(
        """SELECT m.name, m.id,
                  SUM(CASE WHEN a.kind='query' THEN 1 ELSE 0 END) queries,
                  SUM(CASE WHEN a.kind='task_done' THEN 1 ELSE 0 END) tasks,
                  SUM(CASE WHEN a.kind='commit' THEN 1 ELSE 0 END) commits,
                  COALESCE(SUM(a.points),0) score
           FROM members m LEFT JOIN activity_log a ON a.user_id=m.id AND a.ts>=?
           GROUP BY m.id ORDER BY score DESC""", (since,), fetch=True)


# ---------- Tasks (F3) ----------
def add_task(task_id, title, owner="", due="", status="Backlog", deps="", repo=""):
    _run("""INSERT OR REPLACE INTO tasks(id,title,owner,due,status,deps,repo)
            VALUES(?,?,?,?,?,?,?)""", (task_id, title, owner, due, status, deps, repo))


def update_task_status(task_id, status):
    _run("UPDATE tasks SET status=? WHERE id=?", (status, task_id))


def get_tasks(due_before=None):
    if due_before:
        return _run("SELECT * FROM tasks WHERE due <= ? AND status != 'Done'",
                    (due_before,), fetch=True)
    return _run("SELECT * FROM tasks", fetch=True)

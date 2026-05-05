import sqlite3
from typing import Any, Optional
from datetime import datetime
from pathlib import Path

# DB 路径：项目根目录/data/butler.db
_PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = str(_PROJECT_ROOT / "data" / "butler.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS courses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            location    TEXT,
            week_day    INTEGER NOT NULL CHECK(week_day BETWEEN 1 AND 7),
            start_node  INTEGER NOT NULL,
            end_node    INTEGER NOT NULL,
            weeks       TEXT    NOT NULL DEFAULT '1-16'
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            content       TEXT    NOT NULL,
            ddl           DATETIME,
            course_id     INTEGER,
            status        INTEGER NOT NULL DEFAULT 0 CHECK(status IN (0, 1)),
            remind_level  INTEGER NOT NULL DEFAULT 0 CHECK(remind_level BETWEEN 0 AND 2),
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS config (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            key       TEXT    NOT NULL UNIQUE,
            value     TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_actions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL,
            intent      TEXT    NOT NULL,
            data_json   TEXT    NOT NULL,
            confidence  REAL,
            status      TEXT    NOT NULL DEFAULT 'pending',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id     TEXT PRIMARY KEY,
            nickname    TEXT UNIQUE,
            platform    TEXT DEFAULT 'wechat',
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.executemany(
        "INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)",
        [
            ("admin_id", ""),
            ("bot_enabled", "1"),
            ("night_mute", "1"),
            ("night_mute_start", "01:00"),
            ("night_mute_end", "06:00"),
            ("cooldown_seconds", "300"),
        ],
    )

    # 迁移：给旧 tasks 表加 creator_id / creator_nickname / scope 列
    for col, col_type in [
        ("creator_id", "TEXT DEFAULT ''"),
        ("creator_nickname", "TEXT DEFAULT ''"),
        ("scope", "TEXT DEFAULT 'private'"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass  # 列已存在

    conn.commit()
    conn.close()


# ───────────────────────── courses CRUD ─────────────────────────

def add_course(
    name: str,
    week_day: int,
    start_node: int,
    end_node: int,
    location: str = "",
    weeks: str = "1-16",
) -> int:
    if week_day < 1:
        week_day = 1
    if week_day > 5:
        week_day = week_day % 5 or 5
    if start_node % 2 == 1 and end_node == start_node:
        end_node = start_node + 1
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO courses (name, location, week_day, start_node, end_node, weeks) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, location, week_day, start_node, end_node, weeks),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_course(course_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_courses() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM courses ORDER BY week_day, start_node").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_courses_by_weekday(week_day: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM courses WHERE week_day = ? ORDER BY start_node",
        (week_day,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_course(course_id: int, **kwargs: Any) -> bool:
    allowed = {"name", "location", "week_day", "start_node", "end_node", "weeks"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [course_id]
    conn = get_conn()
    cursor = conn.execute(f"UPDATE courses SET {set_clause} WHERE id = ?", values)
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def delete_course(course_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def clear_all_courses() -> int:
    conn = get_conn()
    cursor = conn.execute("DELETE FROM courses")
    conn.commit()
    count = cursor.rowcount
    conn.close()
    return count


# ───────────────────────── tasks CRUD ─────────────────────────

def add_task(
    content: str,
    ddl: Optional[str] = None,
    course_id: Optional[int] = None,
    creator_id: str = "",
    creator_nickname: str = "",
    scope: str = "private",
) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO tasks (content, ddl, course_id, creator_id, creator_nickname, scope) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (content, ddl, course_id, creator_id, creator_nickname, scope),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_task(task_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_tasks(user_id: str = None) -> list[dict]:
    conn = get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 0 "
            "AND (creator_id = ? OR scope = 'public') "
            "ORDER BY ddl ASC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 0 ORDER BY ddl ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tasks_by_course(course_id: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE course_id = ? ORDER BY ddl ASC",
        (course_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_due_tasks(hours: int) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks "
        "WHERE status = 0 "
        "AND ddl IS NOT NULL "
        "AND ddl <= datetime('now', ? || ' hours') "
        "AND ddl > datetime('now') "
        "ORDER BY ddl ASC",
        (f"+{hours}",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_overdue_tasks() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks "
        "WHERE status = 0 "
        "AND ddl IS NOT NULL "
        "AND ddl < datetime('now') "
        "ORDER BY ddl ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def complete_task(task_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute(
        "UPDATE tasks SET status = 1, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (task_id,),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def update_task_remind_level(task_id: int, level: int) -> bool:
    conn = get_conn()
    cursor = conn.execute(
        "UPDATE tasks SET remind_level = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (level, task_id),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def update_task(task_id: int, **kwargs: Any) -> bool:
    allowed = {"content", "ddl", "course_id", "status", "remind_level", "scope"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [task_id]
    conn = get_conn()
    cursor = conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def delete_task(task_id: int, user_id: str = None) -> bool:
    conn = get_conn()
    if user_id:
        cursor = conn.execute(
            "DELETE FROM tasks WHERE id = ? AND (creator_id = ? OR scope = 'public')",
            (task_id, user_id),
        )
    else:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


# ───────────────────────── config CRUD ─────────────────────────

def get_config(key: str) -> Optional[str]:
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else None


def set_config(key: str, value: str) -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO config (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_all_config() -> dict[str, str]:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM config").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


# ───────────────────────── pending_actions CRUD ─────────────────────────

def add_pending(user_id: str, intent: str, data_json: str, confidence: float = 0.0) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO pending_actions (user_id, intent, data_json, confidence) "
        "VALUES (?, ?, ?, ?)",
        (user_id, intent, data_json, confidence),
    )
    conn.commit()
    row_id = cursor.lastrowid
    conn.close()
    return row_id


def get_pending(pending_id: int) -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM pending_actions WHERE id = ?", (pending_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_pending() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM pending_actions ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def confirm_pending(pending_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute(
        "UPDATE pending_actions SET status = 'confirmed' WHERE id = ?",
        (pending_id,),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


def cancel_pending(pending_id: int) -> bool:
    conn = get_conn()
    cursor = conn.execute(
        "UPDATE pending_actions SET status = 'cancelled' WHERE id = ?",
        (pending_id,),
    )
    conn.commit()
    changed = cursor.rowcount > 0
    conn.close()
    return changed


# ───────────────────────── users CRUD ─────────────────────────

def register_user(user_id: str, nickname: str = "", platform: str = "wechat") -> bool:
    """注册用户，如果已存在则更新昵称"""
    if not nickname:
        nickname = user_id
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (user_id, nickname, platform) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "  nickname = CASE WHEN excluded.nickname != '' THEN excluded.nickname ELSE nickname END, "
            "  platform = excluded.platform",
            (user_id, nickname, platform),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def set_nickname(user_id: str, nickname: str) -> bool:
    """设置/更新用户昵称"""
    conn = get_conn()
    try:
        cursor = conn.execute(
            "UPDATE users SET nickname = ? WHERE user_id = ?",
            (nickname, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception:
        return False
    finally:
        conn.close()


def get_user_by_id(user_id: str) -> Optional[dict]:
    """通过 user_id 查询用户"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_nickname(nickname: str) -> Optional[dict]:
    """通过昵称查询用户（精确匹配）"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE nickname = ?", (nickname,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def search_users_by_nickname(keyword: str) -> list[dict]:
    """通过昵称模糊搜索用户，用于 @昵称 匹配"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM users WHERE nickname LIKE ? ORDER BY nickname",
        (f"%{keyword}%",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_user_id(identifier: str) -> Optional[str]:
    """解析用户标识符为 user_id：先按 nickname 查，再按 user_id 查"""
    # 先按昵称查
    user = get_user_by_nickname(identifier)
    if user:
        return user["user_id"]
    # 再按 user_id 查
    user = get_user_by_id(identifier)
    if user:
        return user["user_id"]
    return None


def get_all_users() -> list[dict]:
    """从 users 表获取所有注册用户"""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT user_id, nickname, platform, created_at FROM users ORDER BY nickname"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        conn.close()
        return []


def gc_pending(hours: int = 24) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "DELETE FROM pending_actions "
        "WHERE status = 'pending' "
        "AND created_at < datetime('now', ? || ' hours')",
        (f"-{hours}",),
    )
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted


if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)

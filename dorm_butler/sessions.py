"""
会话管理系统 - 支持多会话切换、归档、AI 摘要
"""
import os
import sqlite3
import datetime
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")
DB_PATH = str(_PROJECT_ROOT / "data" / "butler.db")

# 当前活跃会话 {user_id: session_id}
_active_sessions: dict[str, int] = {}


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_sessions_table():
    """初始化会话表 + 给 chat_history 加 session_id 列"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT NOT NULL,
            name       TEXT,
            status     TEXT DEFAULT 'active',
            summary    TEXT,
            message_count INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at   DATETIME
        );
    """)
    # 兼容：如果 chat_history 没有 session_id 列则添加
    try:
        conn.execute("SELECT session_id FROM chat_history LIMIT 0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE chat_history ADD COLUMN session_id INTEGER REFERENCES sessions(id)")
    conn.commit()
    conn.close()


def _get_active_or_create(user_id: str) -> int:
    """获取当前活跃会话，没有则创建"""
    if user_id in _active_sessions:
        sid = _active_sessions[user_id]
        # 验证仍然活跃
        conn = _get_conn()
        row = conn.execute("SELECT id, status FROM sessions WHERE id = ?", (sid,)).fetchone()
        conn.close()
        if row and row["status"] == "active":
            return sid

    return _create_session(user_id)


def _create_session(user_id: str, name: str = None) -> int:
    """创建新会话"""
    conn = _get_conn()
    cursor = conn.execute(
        "INSERT INTO sessions (user_id, name, status) VALUES (?, ?, 'active')",
        (user_id, name),
    )
    sid = cursor.lastrowid
    conn.commit()
    conn.close()

    _active_sessions[user_id] = sid
    return sid


def archive_session(user_id: str) -> dict:
    """归档当前会话，返回 (session_id, name, summary)"""
    if user_id not in _active_sessions:
        _get_active_or_create(user_id)

    sid = _active_sessions[user_id]

    # AI 生成摘要
    summary = _generate_summary(user_id, sid)

    # 统计消息数
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET status='archived', summary=?, ended_at=CURRENT_TIMESTAMP "
        "WHERE id = ?",
        (summary, sid),
    )
    conn.commit()
    conn.close()

    # 创建新会话
    old_sid = sid
    del _active_sessions[user_id]
    new_sid = _create_session(user_id)
    count = _count_sessions(user_id)

    return {
        "old_id": old_sid,
        "new_id": new_sid,
        "summary": summary,
        "total_sessions": count,
    }


def _count_sessions(user_id: str) -> int:
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def _generate_summary(user_id: str, session_id: int) -> str:
    """调用 DeepSeek 生成 1-2 句会话摘要"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content FROM chat_history WHERE user_id = ? AND session_id = ? "
        "ORDER BY id DESC LIMIT 10",
        (user_id, session_id),
    ).fetchall()
    conn.close()

    if not rows:
        return "（新对话）"

    messages_text = "\n".join([f"{r['role']}: {r['content'][:200]}" for r in reversed(rows)])

    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "用一句中文总结以下对话内容，不超过20字。"},
                {"role": "user", "content": messages_text},
            ],
            max_tokens=50,
            temperature=0.3,
            timeout=10,
        )
        return response.choices[0].message.content.strip() or "（对话记录）"
    except Exception:
        return "（对话记录）"


def get_current_session(user_id: str) -> int:
    """获取或创建当前活跃会话 ID"""
    return _get_active_or_create(user_id)


def list_sessions(user_id: str) -> list[dict]:
    """列出用户的所有会话"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT id, status, summary, created_at, ended_at, message_count "
        "FROM sessions WHERE user_id = ? ORDER BY id DESC LIMIT 20",
        (user_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "status": r["status"],
            "summary": r["summary"] or "",
            "created_at": r["created_at"],
            "ended_at": r["ended_at"],
            "message_count": r["message_count"],
        }
        for r in rows
    ]


def switch_session(user_id: str, session_id: int) -> dict:
    """切换到指定会话"""
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, status, summary FROM sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id),
    ).fetchone()
    conn.close()

    if not row:
        return {"success": False, "message": f"会话 #{session_id} 不存在"}

    # 归档旧会话（如果还在活跃）
    if user_id in _active_sessions:
        old_sid = _active_sessions[user_id]
        conn = _get_conn()
        conn.execute(
            "UPDATE sessions SET status='archived', ended_at=CURRENT_TIMESTAMP WHERE id = ?",
            (old_sid,),
        )
        conn.commit()
        conn.close()

    _active_sessions[user_id] = session_id

    # 如果切换目标是 archived，改为 active
    if row["status"] == "archived":
        conn = _get_conn()
        conn.execute("UPDATE sessions SET status='active' WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    return {
        "success": True,
        "session_id": session_id,
        "summary": row["summary"] or "",
    }


def get_session_summary(user_id: str) -> str:
    """用 AI 总结当前会话（/summary 指令）"""
    sid = get_current_session(user_id)
    return _generate_summary(user_id, sid)


def increment_message_count(user_id: str) -> None:
    """增加当前会话消息计数"""
    sid = _get_active_or_create(user_id)
    conn = _get_conn()
    conn.execute(
        "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?", (sid,)
    )
    conn.commit()
    conn.close()


# 初始化
init_sessions_table()

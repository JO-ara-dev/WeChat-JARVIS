"""
牛马管家记忆系统
- 对话历史：存储最近 N 轮对话，传给 DeepSeek 做上下文
- 用户画像：Agent 自己记录用户偏好、习惯、关键信息
"""

import os
import json
import datetime
import sqlite3
from pathlib import Path
from . import sessions as _sessions

# DB 路径：复用 db_manager 的同一个数据库
_PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = str(_PROJECT_ROOT / "data" / "butler.db")


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_memory_tables():
    """初始化记忆相关表"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,
            content     TEXT NOT NULL,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS user_memory (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT NOT NULL,
            key         TEXT NOT NULL,
            value       TEXT NOT NULL,
            scope       TEXT DEFAULT 'private',
            updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, key)
        );
    """)
    conn.commit()
    conn.close()


# ── 对话历史 ──

def add_message(user_id: str, role: str, content: str):
    """添加一条对话记录"""
    session_id = _sessions.get_current_session(user_id)
    conn = _get_conn()
    conn.execute(
        "INSERT INTO chat_history (user_id, role, content, session_id) VALUES (?, ?, ?, ?)",
        (user_id, role, content, session_id)
    )
    conn.commit()
    conn.close()
    _sessions.increment_message_count(user_id)


def get_history(user_id: str, limit: int = 20) -> list:
    """获取当前会话最近 N 条对话历史"""
    session_id = _sessions.get_current_session(user_id)
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content FROM chat_history "
        "WHERE user_id = ? AND session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (user_id, session_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def get_session_history(user_id: str, session_id: int, limit: int = 50) -> list:
    """获取指定会话的历史记录（用于 /session 切换）"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT role, content FROM chat_history "
        "WHERE user_id = ? AND session_id = ? "
        "ORDER BY id DESC LIMIT ?",
        (user_id, session_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_history(user_id: str):
    """清空用户对话历史"""
    conn = _get_conn()
    conn.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ── 用户画像 ──

def save_memory(user_id: str, key: str, value: str, scope: str = "private"):
    """保存/更新用户记忆"""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO user_memory (user_id, key, value, scope, updated_at) "
        "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id, key) DO UPDATE SET value = ?, scope = ?, updated_at = CURRENT_TIMESTAMP",
        (user_id, key, value, scope, value, scope)
    )
    conn.commit()
    conn.close()


def get_memory(user_id: str, key: str = None, include_public: bool = False) -> list:
    """获取用户记忆，key 为空则返回全部。include_public=True 时同时返回 scope='public' 的记忆"""
    conn = _get_conn()
    if key:
        if include_public:
            rows = conn.execute(
                "SELECT key, value, scope FROM user_memory WHERE key = ? AND (user_id = ? OR scope = 'public')",
                (key, user_id)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT key, value, scope FROM user_memory WHERE user_id = ? AND key = ?",
                (user_id, key)
            ).fetchall()
    else:
        if include_public:
            rows = conn.execute(
                "SELECT key, value, scope FROM user_memory WHERE user_id = ? OR scope = 'public' ORDER BY updated_at DESC",
                (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT key, value, scope FROM user_memory WHERE user_id = ? ORDER BY updated_at DESC",
                (user_id,)
            ).fetchall()
    conn.close()
    return [{"key": r["key"], "value": r["value"], "scope": r.get("scope", "private")} for r in rows]


def delete_memory(user_id: str, key: str):
    """删除用户记忆"""
    conn = _get_conn()
    conn.execute("DELETE FROM user_memory WHERE user_id = ? AND key = ?", (user_id, key))
    conn.commit()
    conn.close()


# ── 工具定义 ──

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "记住用户的信息/偏好。比如用户的说话风格、课程表规则、习惯等。每次对话中发现新的用户特征都应该调用此函数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "记忆的键名，如 'nickname'、'schedule_rule'、'speaking_style'"},
                    "value": {"type": "string", "description": "记忆的值"},
                    "scope": {"type": "string", "enum": ["private", "public"], "description": "private=仅自己可见，public=所有人可见。默认 private"}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_memory",
            "description": "查询已记住的用户信息。不传 key 则返回全部记忆。include_public=True 同时查询公共记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "要查询的键名，不传则返回全部"},
                    "include_public": {"type": "boolean", "description": "是否同时查询 scope='public' 的公共记忆"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_memory",
            "description": "删除一条用户记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "要删除的键名"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_code",
            "description": "执行 Python 代码。可以用来做复杂计算、数据处理、数据库查询、文件操作等。可用的模块：db_manager, datetime, json, os, sqlite3, re, sys, pathlib。变量 db_path 是数据库路径。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "要执行的 Python 代码"}
                },
                "required": ["code"]
            }
        }
    },
]


# ── 工具实现 ──

def _save_memory(user_id: str, key: str, value: str, scope: str = "private") -> dict:
    save_memory(user_id, key, value, scope)
    return {"success": True, "message": f"已记住: {key} = {value} (scope={scope})"}


def _get_memory(user_id: str, key: str = None, include_public: bool = False) -> dict:
    memories = get_memory(user_id, key, include_public)
    if not memories:
        return {"success": True, "data": [], "message": "还没有记住任何信息"}
    return {"success": True, "data": memories, "message": f"找到 {len(memories)} 条记忆"}


def _delete_memory(user_id: str, key: str) -> dict:
    delete_memory(user_id, key)
    return {"success": True, "message": f"已删除记忆: {key}"}


def _run_code(user_id: str, code: str) -> dict:
    """执行 Python 代码，返回输出"""
    import io
    import contextlib
    import sys
    import re
    from pathlib import Path

    # 安全限制
    forbidden = ["import os.system", "exec(", "eval(", "__import__", "open('/etc", "shutil.rmtree"]
    for f in forbidden:
        if f in code:
            return {"success": False, "message": f"安全限制：禁止 {f}"}

    # 导入本地模块
    from . import db_manager as _dbm

    local_vars = {
        "db_path": DB_PATH,
        "user_id": user_id,
        "db_manager": _dbm,
        "datetime": __import__("datetime"),
        "json": __import__("json"),
        "os": __import__("os"),
        "sqlite3": __import__("sqlite3"),
        "re": re,
        "sys": sys,
        "Path": Path,
        "subprocess": __import__("subprocess"),
        "socket": __import__("socket"),
        "threading": __import__("threading"),
        "http": __import__("http"),
        "urllib": __import__("urllib"),
        "time": __import__("time"),
    }

    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
            exec(code, {"__builtins__": __builtins__}, local_vars)

        output = stdout_capture.getvalue()
        if stderr_capture.getvalue():
            output += f"\n[stderr] {stderr_capture.getvalue()}"

        return {"success": True, "data": output.strip() or "执行完成，无输出", "message": "代码执行成功"}
    except Exception as e:
        return {"success": False, "message": f"执行错误: {str(e)}"}


# 工具分发表
TOOLS_MAP = {
    "save_memory": _save_memory,
    "get_memory": _get_memory,
    "delete_memory": _delete_memory,
    "run_code": _run_code,
}


# 初始化
init_memory_tables()

-- 微信贾维斯 数据库初始化脚本
-- 使用方法: sqlite3 data/butler.db < schema.sql

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
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    content          TEXT    NOT NULL,
    ddl              DATETIME,
    course_id        INTEGER,
    status           INTEGER NOT NULL DEFAULT 0 CHECK(status IN (0, 1)),
    remind_level     INTEGER NOT NULL DEFAULT 0 CHECK(remind_level BETWEEN 0 AND 2),
    creator_id       TEXT    DEFAULT '',
    creator_nickname TEXT    DEFAULT '',
    scope            TEXT    DEFAULT 'private',
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS config (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    key   TEXT    NOT NULL UNIQUE,
    value TEXT    NOT NULL
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
    user_id    TEXT PRIMARY KEY,
    nickname   TEXT UNIQUE,
    platform   TEXT DEFAULT 'wechat',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT    NOT NULL,
    session_id  INTEGER,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_memory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT    NOT NULL,
    key         TEXT    NOT NULL,
    value       TEXT    NOT NULL,
    scope       TEXT    DEFAULT 'private',
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, key)
);

-- 默认配置
INSERT OR IGNORE INTO config (key, value) VALUES
    ('admin_id', ''),
    ('bot_enabled', '1'),
    ('night_mute', '1'),
    ('night_mute_start', '01:00'),
    ('night_mute_end', '06:00'),
    ('cooldown_seconds', '300');

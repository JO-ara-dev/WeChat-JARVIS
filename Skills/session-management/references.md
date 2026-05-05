# 会话管理 - 源码引用

## dorm_butler/sessions.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `init_sessions_table()` | 26-42 | 创建 sessions 表 + ALTER chat_history |
| `_get_active_or_create()` | 45-56 | 获取或创建当前活跃会话 |
| `_create_session()` | 59-66 | 插入新会话 |
| `archive_session()` | 69-91 | 归档当前 + 创建新会话 + 返回摘要 |
| `_generate_summary()` | 101-126 | DeepSeek 生成 1-2 句摘要 |
| `get_current_session()` | 129-131 | 获取当前 session_id |
| `list_sessions()` | 134-150 | 列出所有会话 |
| `switch_session()` | 153-180 | 切换到指定会话 |
| `get_session_summary()` | 183-185 | AI 总结（/summary） |
| `increment_message_count()` | 188-193 | 增加消息计数 |

## dorm_butler/memory.py

| 变更 | 说明 |
|------|------|
| `add_message()` | 新增 session_id 参数，写入当前会话 ID |
| `get_history()` | 改为按 session_id 过滤，只取当前会话 |
| `get_session_history()` (新增) | 获取指定会话的历史记录 |

## wx4py_bridge.py

| 变更 | 说明 |
|------|------|
| `_handle_session_cmd()` (新增) | 拦截 4 个会话指令，直接处理不进入 Agent |
| `process_worker()` | 调用前先检查会话指令；适配 chat() 生成器 |
| `keywords` 列表 | 新增 "暂停" "/stop" "/sessions" "/session" "/summary" |

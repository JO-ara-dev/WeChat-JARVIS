# 记忆管理 - 源码引用

## 数据库初始化 — dorm_butler/memory.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `init_memory_tables()` | 25-46 | 创建 chat_history + user_memory 表 |

## 对话历史 — dorm_butler/memory.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `add_message()` | 51-59 | 添加一条对话记录 |
| `get_history()` | 62-70 | 获取最近 N 条（默认 20） |
| `clear_history()` | 73-78 | 清空用户对话历史 |

## 用户画像 — dorm_butler/memory.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `save_memory()` | 83-93 | 保存/更新记忆 (UPSERT) |
| `get_memory()` | 96-110 | 查询记忆 (key 可选) |
| `delete_memory()` | 113-118 | 删除一条记忆 |

## Agent 工具封装 — dorm_butler/memory.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `_save_memory()` | 186-188 | 工具：保存记忆 |
| `_get_memory()` | 191-195 | 工具：查询记忆 |
| `_delete_memory()` | 198-200 | 工具：删除记忆 |

## 工具 Schema — dorm_butler/memory.py

| 定义 | 行号 | 说明 |
|------|------|------|
| `TOOLS_SCHEMA` | 123-181 | save_memory, get_memory, delete_memory 的 OpenAPI 格式 |
| `TOOLS_MAP` | 256-261 | 工具映射表 |

## Agent 集成 — dorm_butler/butler_agent.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `_build_system_prompt()` | 117-133 | 构建含用户记忆的 System Prompt |
| `chat()` | 153-219 | 主循环：get_history → add_message(自动) → 工具调用 → add_message(自动) |

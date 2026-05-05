# 作业管理 - 源码引用

## dorm_butler/db_manager.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `add_task()` | 166-179 | 添加作业 |
| `get_task()` | 182-185 | 查询单条作业 |
| `get_pending_tasks()` | 189-195 | 查询待完成作业 (status=0) |
| `get_tasks_by_course()` | 198-205 | 按课程查询 |
| `get_due_tasks()` | 208-220 | 查询即将截止的作业 |
| `get_overdue_tasks()` | 223-233 | 查询已过期的作业 |
| `complete_task()` | 236-245 | 标记完成 (status=1) |
| `update_task_remind_level()` | 248-257 | 更新提醒等级 |
| `update_task()` | 260-272 | 更新作业字段 |
| `delete_task()` | 275-281 | 删除作业 |

## dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `query_tasks()` | 357-362 | 工具：查询待完成作业 |
| `add_task()` | 365-368 | 工具：添加作业 |
| `delete_task()` | 371-375 | 工具：删除指定作业 |

## 工具 Schema 定义

`tools.py:987-1023` — `TOOLS_SCHEMA` 中 `query_tasks`、`add_task`、`delete_task` 的 OpenAPI function calling 格式。

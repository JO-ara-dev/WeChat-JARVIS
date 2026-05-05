# 自进化 Pipeline - 源码引用

## 任务规划 — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `_agent_todos` | 22 | 全局 TODO 缓存 dict |
| `_todo_counter` | 23 | 步骤 ID 计数器 |
| `plan_task()` | 26-54 | 分解任务为步骤列表 |
| `update_todo()` | 57-67 | 更新步骤状态 |
| `get_todos()` | 70-81 | 查看任务进度 |

## 自愈与进化 — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `reflect()` | 84-101 | 总结 + 清理 TODO |
| `self_heal()` | 106-129 | 错误分析 + 修复建议 |
| `evolve_pipeline()` | 132-145 | 注册方案到 config 表 |
| `reuse_pipeline()` | 148-158 | 查找复用方案 |

## 自我更新 — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `self_update()` | 163-247 | 修改自身源码 |

安全流程：
1. confirmed=false → 备份到 backups/ + 返回预览
2. 用户说「确认更新」
3. confirmed=true → 校验 old_code 仍在文件 → 替换写入

限制：只能更新 dorm_butler/ 和根目录 .py 文件。

## create_tool — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `create_tool()` | 484-505 | 动态工具创建（禁止 subprocess/eval/exec） |

## 工具 Schema 定义

`tools.py:798-907` — plan_task, update_todo, get_todos, reflect, self_heal, evolve_pipeline, reuse_pipeline, self_update。
`tools.py:1081-1095` — create_tool。

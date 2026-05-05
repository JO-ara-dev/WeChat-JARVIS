# 代码/命令执行 - 源码引用

## run_code — dorm_butler/memory.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `_run_code()` | 203-261 | Python 代码沙箱执行 |
| `TOOLS_SCHEMA` (run_code) | 168-181 | Schema 定义 |
| `TOOLS_MAP` (run_code) | 260 | 工具映射 |

安全沙箱预置模块：`db_manager`, `datetime`, `json`, `os`, `sqlite3`, `re`, `sys`, `Path`, `subprocess`, `socket`, `threading`, `http`, `urllib`, `time`。

## run_cmd — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `run_cmd()` | 512-583 | 系统命令执行（需确认 + 后台模式） |
| `_pending_cmds` | 509 | 确认队列 |

安全机制：危险命令黑名单 (format, del /f, rm -rf, shutdown 等)，pip 自动修正到 venv。

## write_file — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `write_file()` | 430-450 | 写入文件，安全检查 |

## create_tool — dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `create_tool()` | 484-505 | 动态创建工具函数 |

## 工具 Schema 定义

`tools.py:1097-1113` — `run_cmd`, `tools.py:1052-1079` — `write_file`, `tools.py:1081-1095` — `create_tool`。

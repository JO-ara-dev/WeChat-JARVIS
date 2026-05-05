---
name: code-execution
description: 代码沙箱、系统命令、文件写入、动态工具创建。触发词：运行、执行、安装、写代码。
tools: run_code, run_cmd, write_file, create_tool
version: 1.0
---

# 代码/命令执行

## 能力描述

在安全沙箱内执行 Python 代码、执行系统命令（需确认）、写入文件、动态创建新工具。

## 工具参数

### run_code
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | Python 代码 |

预置安全模块：`db_manager`, `datetime`, `json`, `os`, `sqlite3`, `re`, `sys`, `Path`, `subprocess`, `socket`, `threading`, `http`, `urllib`, `time`。变量 `db_path` = data/butler.db。

安全限制：禁止 `eval()`, `exec()`, `__import__`, `os.system`。

### run_cmd
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| command | string | 是 | 命令（Windows cmd） |
| description | string | 是 | 命令说明 |
| background | boolean | 否 | 后台运行（default false） |
| confirmed | boolean | 否 | 是否已确认 |

安全机制：
- 黑名单：format, del /f, rm -rf, shutdown, reboot, diskpart
- pip 自动修正到 venv Python
- 首次 confirmed=false → 需用户说"确认"
- 普通命令 30s 超时

### write_file
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_path | string | 是 | 相对路径 |
| content | string | 是 | 文件内容 |

限制：只能写入项目目录内。

### create_tool
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tool_name | string | 是 | 工具名称 |
| tool_code | string | 是 | Python 函数定义 |
| tool_description | string | 是 | 工具描述 |

禁止：subprocess, os.system, eval, exec。

## 示例

**用户**: "统计一周有几门课"
**执行**: `run_code` 遍历 courses 表按 week_day 分组

**用户**: "安装 playwright"
**执行**: `run_cmd(command="pip install playwright", description="安装 Playwright")` → 自动修正到 venv → 需确认

**用户**: "创建 test.txt"
**执行**: `write_file(file_path="test.txt", content="Hello")`

## 注意事项

- 持续服务（http.server 等）必须传 background=true
- Windows 环境，命令用 cmd/PowerShell

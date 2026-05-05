# 信息获取 - 源码引用

## dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `web_search()` | 378-404 | Bing 联网搜索，返回前 2000 字符摘要 |
| `read_file()` | 407-427 | 读取项目内文件，安全检查 |
| `list_files()` | 453-481 | 列出目录内容，安全检查 |

## 安全限制

所有文件操作通过 `os.path.abspath()` 校验路径必须在项目根目录下。

## 工具 Schema 定义

`tools.py:1025-1079` — `TOOLS_SCHEMA` 中 `web_search`、`read_file`、`list_files` 的 OpenAPI function calling 格式。

# 课表管理 - 源码引用

## dorm_butler/db_manager.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `init_db()` | 19-76 | 建表 + 初始化配置 |
| `add_course()` | 81-104 | 添加课程 |
| `get_course()` | 107-111 | 查询单门课程 |
| `get_all_courses()` | 114-118 | 查询全部课程 |
| `get_courses_by_weekday()` | 121-128 | 按星期查询 |
| `update_course()` | 131-143 | 更新课程 |
| `delete_course()` | 146-152 | 删除课程 |
| `clear_all_courses()` | 155-161 | 清空全部课程 |
| `get_config()` | 286-290 | 读取配置（semester_start）|

## dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `get_current_week()` | 253-272 | 根据 semester_start 计算当前周 |
| `is_course_in_week()` | 275-292 | 判断课程是否在指定周 |
| `query_courses()` | 295-318 | 工具：查询课程（含周过滤+排序） |
| `add_courses()` | 321-339 | 工具：批量添加课程 |
| `delete_courses()` | 342-354 | 工具：删除课程 |

## 工具 Schema 定义

`tools.py:798-986` — `TOOLS_SCHEMA` 中 `query_courses`、`add_courses`、`delete_courses` 的 OpenAPI function calling 格式。

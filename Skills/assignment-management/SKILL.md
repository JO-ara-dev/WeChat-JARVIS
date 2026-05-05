---
name: assignment-management
description: 管理课程作业和截止日期。触发词：作业、DDL、截止、任务、还有什么没做。
tools: query_tasks, add_task, delete_task
version: 1.0
---

# 作业/DDL 管理

## 能力描述

管理课程作业：查询待完成列表、添加新任务（含 DDL）、删除已完成/错误任务。

## 适用场景

- 用户问"有什么作业没交"
- 记录新布置的作业和截止时间
- 标记任务完成
- 删除错误的作业记录

## 调用流程

```
用户问作业 → query_tasks() → 查 tasks 表 (status=0) → 按 DDL 排序 → 回复
用户说添加 → add_task(content, ddl?) → 写入 DB
用户说完成 → 查 ID → delete_task(id)
```

## 工具参数

### query_tasks
无参数，返回所有 status=0 的任务。

### add_task
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | 是 | 作业内容 |
| ddl | string | 否 | 截止时间 "YYYY-MM-DD HH:MM" |

### delete_task
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | integer | 是 | 任务 ID |

## 示例

**用户**: "最近有什么作业"
**执行**: `query_tasks()` → 返回待完成列表

**用户**: "高数作业下周五交，帮我记一下"
**执行**: `add_task(content="高数作业", ddl="2026-05-15 23:59")`

## 数据库字段

| 字段 | 说明 |
|------|------|
| content | 作业内容 |
| ddl | 截止日期时间 |
| course_id | 关联课程 (可选) |
| status | 0:未完成, 1:已完成 |
| remind_level | 提醒等级 0-2 |

## 注意事项

- DDL 不传则视为无截止日期
- 已完成任务 (status=1) 不出现在待办列表

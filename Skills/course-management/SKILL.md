---
name: course-management
description: 查询、添加、删除课程表。触发词：课表、课程、今天什么课、周一有什么课。
tools: query_courses, add_courses, delete_courses
version: 1.0
---

# 课表管理

## 能力描述

管理大学课程表，支持按星期筛选，自动根据学期起始日期过滤当前周课程。

## 适用场景

- 用户问"今天/明天/周几有什么课"
- 从课表图片识别结果批量导入课程
- 清理过期课表数据
- 查看全部课程安排

## 调用流程

```
用户问课 → query_courses(weekday?) → 查 courses 表 → 过滤当前周 → 按节次排序 → 回复
用户说添加 → add_courses([{course_name, week_day, start_node, end_node, ...}]) → 写入 DB
用户说删除 → delete_courses(weekday?) → 清理数据
```

## 工具参数

### query_courses
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| weekday | integer | 否 | 1-5 (周一到周五)，不传查全部 |

### add_courses
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| courses | array | 是 | 课程对象数组 |
| courses[].course_name | string | 是 | 课程名 |
| courses[].week_day | integer | 是 | 1-5 |
| courses[].start_node | integer | 是 | 起始节次 |
| courses[].end_node | integer | 是 | 结束节次 |
| courses[].location | string | 否 | 教室 |
| courses[].weeks | string | 否 | 周次，默认 "1-16" |

### delete_courses
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| weekday | integer | 否 | 1-5，不传清空全部 |

## 示例

**用户**: "今天有什么课"
**执行**: `query_courses(weekday=当前周几)` → 返回该天课表

**用户**: "帮我添加：高数 周一 1-2节 教1-101"
**执行**: `add_courses([{course_name:"高数", week_day:1, start_node:1, end_node:2, location:"教1-101"}])`

## 节次规则

- 每门课占连续两节：1-2、3-4、5-6、7-8
- 周末没有课；单节课程自动补齐为双节
- 课程数据按「周几 → 节次」排序显示

## 周次过滤

- 从 config 表读取 `semester_start` 计算当前第几周
- 自动过滤不在当前周范围内的课程

## 注意事项

- 必须先调用工具查询，禁止凭记忆回答课表信息
- 周六日 week_day 超范围自动修正到 1-5

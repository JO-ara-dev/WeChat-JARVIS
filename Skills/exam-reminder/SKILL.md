---
name: exam-reminder
description: 考试提醒技能 - 添加、查询、删除考试信息，并自动在指定天数前通过微信提醒用户
trigger:
  - 考试提醒
  - 添加考试
  - 查询考试
  - 删除考试
  - 考试时间
  - 什么时候考试
  - 考试安排
version: 1.0
---

# exam-reminder 考试提醒技能

## 功能
1. **添加考试**：记录课程名称、考试日期、起止时间、提醒天数
2. **查询考试**：查看所有已记录的考试信息
3. **删除考试**：删除指定考试记录
4. **自动提醒**：在考试前指定天数，通过微信自动发送提醒消息

## 数据存储
- 使用 `save_memory(key, value, scope='private')` 存储考试信息
- key 格式：`exam_<课程名拼音/英文>`
- value 格式：JSON 字符串，包含 course, date, start_time, end_time, reminder_days

## 工作流程

### 添加考试
1. 解析用户输入：课程名、日期、时间、提醒天数
2. 调用 `save_memory(key, value, scope='private')` 保存
3. 确认回复：✅ 已记录 [课程名] 考试，[日期] [时间]，提前 [N] 天提醒

### 查询考试
1. 调用 `get_memory(key='exam_*', include_public=False)` 或遍历所有记忆
2. 用 `run_code` 过滤出 exam_ 开头的记忆
3. 格式化输出表格

### 删除考试
1. 查询所有考试
2. 用户指定要删除的考试
3. 调用 `delete_memory(key)` 删除

### 自动提醒（后台调度）
1. 每天 08:00 检查所有考试记忆
2. 计算当前日期到考试日期的天数差
3. 如果天数差 == reminder_days，发送微信提醒
4. 提醒内容：[课程名] 考试将在 [N] 天后（[日期] [时间]）进行，请做好准备！

## 注意事项
- 日期格式统一为 YYYY-MM-DD
- 时间格式统一为 HH:MM
- 提醒天数默认为 3 天，用户可自定义
- 考试信息仅创建者可见（scope='private'）

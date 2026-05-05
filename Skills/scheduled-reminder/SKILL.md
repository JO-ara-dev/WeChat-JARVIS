---
name: scheduled-reminder
description: 定时提醒课程。每晚22:00自动提醒次日课程安排，支持周末跳过、无课不提醒。
tools: run_cmd, write_file, read_file, self_update, run_code
version: 1.0
---

# 定时提醒课程

## 能力描述

基于 APScheduler 的定时任务系统，每晚 22:00 自动查询次日课程并通过 wx4py HTTP API 发送提醒消息。

## 触发词

- 定时提醒
- 自动提醒
- 课程提醒
- 每晚提醒
- 定时任务
- 提醒我上课

## 架构

```
skills/scheduled-reminder/
├── SKILL.md          ← 技能指令文件（本文件）
├── references.md     ← 源码引用说明
└── scheduler.py      ← 调度器核心代码（独立脚本副本）

dorm_butler/
├── scheduler.py      ← 实际运行的调度器（主副本）
├── butler_agent.py   ← 启动时自动加载调度器
└── db_manager.py     ← 新增 get_all_users() 函数
```

## 工作流程

1. `butler_agent.py` 导入时自动实例化 `SchedulerManager`
2. `SchedulerManager.__init__()` 启动 BackgroundScheduler
3. 注册 cron 任务：每天 22:00 执行 `send_tomorrow_courses()`
4. `send_tomorrow_courses()` 逻辑：
   - 获取明天是周几（1=周一 … 5=周五）
   - 如果是周六(6)或周日(7)，跳过
   - 查询明天课程
   - 无课则跳过
   - 有课则通过 wx4py HTTP API 发送提醒
   - API 失败时写入消息队列文件降级

## 关键文件

| 文件 | 说明 |
|------|------|
| `skills/scheduled-reminder/scheduler.py` | 调度器核心代码（技能文件夹副本） |
| `dorm_butler/scheduler.py` | 实际运行的调度器 |
| `dorm_butler/butler_agent.py` | 启动入口（自动加载） |
| `dorm_butler/db_manager.py` | 数据库操作（get_all_users） |

## 示例

**用户**: "设置定时提醒"
**执行**: 检查 scheduler.py 是否正常运行，确认 cron 任务已注册

**用户**: "每晚提醒我明天的课"
**执行**: 确认调度器已运行，cron 表达式为 `0 22 * * *`

## 注意事项

- 周末（周六/周日）自动跳过
- 次日无课自动跳过
- 依赖 APScheduler 库（已安装）
- 消息发送失败时写入 `data/message_queue.json` 降级

# 定时提醒课程 - 源码引用

## 核心脚本

| 文件 | 说明 |
|:----|:----|
| `skills/scheduled-reminder/scheduler.py` | 调度器核心代码（独立副本） |
| `dorm_butler/scheduler.py` | 实际运行的调度器（主副本） |

## dorm_butler/scheduler.py

| 函数 | 行号 | 说明 |
|:----|:----:|:----|
| `_get_project_root()` | 17-19 | 获取项目根目录 |
| `_send_wechat_msg()` | 22-68 | 通过 wx4py HTTP API 发送微信消息，失败时写入消息队列文件降级 |
| `_query_tomorrow_courses()` | 71-107 | 查询次日课程，周末跳过，无课跳过 |
| `_nightly_reminder()` | 110-133 | 每晚 22:00 主逻辑：遍历所有用户发送提醒 |
| `start_scheduler()` | 136-157 | 启动 BackgroundScheduler，注册 cron 任务 |
| `stop_scheduler()` | 160-165 | 停止调度器 |

## dorm_butler/db_manager.py

| 函数 | 行号 | 说明 |
|:----|:----:|:----|
| `get_all_users()` | 新增 | 获取所有活跃用户（从 memory 表） |

## dorm_butler/butler_agent.py

| 位置 | 说明 |
|:----|:----|
| 导入部分 | `from dorm_butler.scheduler import start_scheduler` |
| 初始化部分 | 启动时调用 `start_scheduler()` |

## 依赖

| 库 | 版本 | 说明 |
|:----|:----:|:----|
| APScheduler | >=3.10 | 定时任务调度（BackgroundScheduler + CronTrigger） |

## 架构图

```
butler_agent.py (启动)
       │
       ▼
scheduler.py (BackgroundScheduler)
       │
       ├── cron: 每晚 22:00
       │       └── _nightly_reminder()
       │               ├── db_manager.get_all_users()
       │               ├── _query_tomorrow_courses()
       │               │       └── tools.query_courses(weekday)
       │               └── _send_wechat_msg()
       │                       └── wx4py HTTP API → 降级: message_queue.json
       │
       └── stop_scheduler() (关闭时调用)
```

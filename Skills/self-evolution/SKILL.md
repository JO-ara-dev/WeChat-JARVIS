---
name: self-evolution
description: Harness自进化框架。自动分解任务、自愈修复、沉淀方案、自我更新。触发词：复杂任务、自动修复、更新自己。
tools: plan_task, update_todo, get_todos, reflect, self_heal, evolve_pipeline, reuse_pipeline, self_update, create_tool
version: 1.0
---

# 自进化 Pipeline

## 能力描述

Harness 自进化框架：复杂任务自动分解步骤 → 失败时自愈修复 → 成功后沉淀为可复用 Pipeline → 必要时修改自身源代码。

## 核心循环

```
Plan → Act → Verify → Reflect
  ↓      ↓       ↓         ↓
plan   update  self_heal  reflect → evolve_pipeline
task   _todo                         ↓
                              reuse_pipeline（下次复用）
```

## 工具清单

### 任务规划
| 工具 | 说明 |
|------|------|
| `plan_task` | 将复杂任务分解为步骤列表 |
| `update_todo` | 更新步骤状态: pending/in_progress/completed/cancelled |
| `get_todos` | 查看当前任务进度 |

### 自愈与进化
| 工具 | 说明 |
|------|------|
| `self_heal` | 分析错误，自动生成修复建议 |
| `evolve_pipeline` | 成功方案注册到 config 表 (key=pipeline_xxx) |
| `reuse_pipeline` | 查找已注册方案直接复用 |
| `reflect` | 总结 + 清理 TODO |

### 自我更新
| 工具 | 说明 |
|------|------|
| `self_update` | 修改自身 .py 源码，自动备份到 backups/ |

### 扩展
| 工具 | 说明 |
|------|------|
| `create_tool` | 动态创建新工具函数 |

## self_update 安全流程

```
1. Agent 提议 → self_update(file, old, new, reason, confirmed=false)
2. 系统自动备份到 backups/
3. 返回预览："确认更新？[旧] → [新]"
4. 用户回复「确认更新」
5. self_update(confirmed=true) → 替换 → 写入
```

限制：只能更新 dorm_butler/ 和根目录 .py 文件。

## 示例

**用户**: "统计所有课程，按周几分组，生成报告"
**执行链**: plan_task → query_courses → run_code 分组 → reflect → evolve_pipeline("class_stats", ...)

## 注意事项

- 简单任务不需要 plan，直接执行
- self_update 前必须 think(deep)
- Pipeline 缓存在 config 表，JSON 格式

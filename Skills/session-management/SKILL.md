---
name: session-management
description: 多会话管理。暂停/归档/切换/总结对话。触发词：暂停、/stop、/sessions、/session、/summary。
version: 1.0
---

# 会话管理

## 能力描述

支持多会话切换、归档和历史管理。每个会话独立存储对话历史，可随时暂停当前对话并开启新会话，也可以切换到任意历史会话继续。

## 适用场景

- Agent 陷入循环或出错了 → 用户说"暂停"开新会话
- 想回顾之前的对话 → `/sessions` 列出 + `/session <id>` 切换
- 想总结当前对话 → `/summary`
- 对话话题切换 → 归档旧话题，开新会话

## 指令清单

| 指令 | 行为 |
|------|------|
| `暂停` 或 `/stop` | 归档当前会话 → AI 生成摘要 → 开新会话 |
| `/sessions` | 列出所有历史会话（id / 状态 / 摘要 / 时间）|
| `/session <id>` | 切换到指定会话，加载其对话历史 |
| `/summary` | AI 总结当前会话内容 |

## 调用流程

### 暂停
```
用户说"暂停" → bridge 层拦截
  ↓
1. 取当前会话最后 10 条消息 → DeepSeek 生成摘要
2. UPDATE sessions SET status='archived', summary=?, ended_at=NOW
3. INSERT 新会话
4. 回复：已存档 + 摘要 + 新会话 ID
```

### 列出会话
```
用户说"/sessions" → bridge 层拦截
  ↓
SELECT * FROM sessions WHERE user_id=? ORDER BY id DESC
  ↓
格式化回复：🟢 活跃 / 📁 已归档
```

### 切换会话
```
用户说"/session 3" → bridge 层拦截
  ↓
1. 归档当前会话
2. 设置 _active_sessions[user_id] = 3
3. 加载会话 #3 的 chat_history
4. 回复：已切换
```

### 总结
```
用户说"/summary" → bridge 层拦截
  ↓
取当前会话最后 10 条 → DeepSeek → 1-2 句摘要
```

## 数据库表

### sessions
| 字段 | 说明 |
|------|------|
| id | 自动递增 |
| user_id | 群聊/用户 ID |
| name | 会话名（可选） |
| status | active / archived |
| summary | AI 生成摘要 |
| message_count | 消息计数 |
| created_at | 创建时间 |
| ended_at | 归档时间 |

### chat_history 扩展
原有表新增 `session_id` 列关联 sessions.id。

## 注意事项

- 会话指令在 bridge 层直接拦截，不进入 Agent 处理
- 暂停后旧会话记忆保留，可随时切回
- 会话摘要由 DeepSeek 自动生成（超时 10s，失败则用占位）
- 切换会话后对话历史自动替换为新会话的最近 20 条

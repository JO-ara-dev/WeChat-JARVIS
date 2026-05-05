---
name: memory-management
description: 对话历史+用户画像记忆管理。触发词：记住、偏好、习惯、我是谁、你记得我什么。
tools: save_memory, get_memory, delete_memory
version: 1.0
---

# 记忆管理

## 能力描述

两套记忆系统：**对话历史**（最近 20 轮上下文）和 **用户画像**（长期记忆持久化到 SQLite）。

## 两套记忆

### 对话历史 (chat_history 表)
- 自动记录每轮 user/assistant 消息
- 每次调用 Agent 时取最近 20 条作为上下文
- 支持 `clear_history(user_id)` 清空

### 用户画像 (user_memory 表)
- Agent 主动调用 save_memory 记录
- 键值对 (key → value)，持久化存储
- 每次回复前自动加载到 System Prompt

## 工具参数

### save_memory
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 是 | 记忆键名 |
| value | string | 是 | 记忆值 |

### get_memory
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 否 | 不传返回全部 |

### delete_memory
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 是 | 要删除的键名 |

## System Prompt 规则

> "每次对话中发现用户的特征，都要调用 save_memory 记住"
> "回复前先查 get_memory 了解用户已知信息"

## 记忆类型举例

| key | value | 何时记录 |
|-----|-------|----------|
| nickname | 学霸 | 用户自称 |
| schedule_rule | 横排星期竖排节次 | 用户说明偏好 |
| speaking_style | 喜欢简洁 | 用户抱怨啰嗦 |
| major | 计算机科学 | 用户提到专业 |

## 示例

**用户**: "我叫小明，记住我"
**执行**: `save_memory(user_id="xxx", key="nickname", value="小明")`

**用户**: "你记得我什么"
**执行**: `get_memory(user_id="xxx")` → 返回全部记忆

## 注意事项

- 记忆按 user_id 隔离（群聊/私聊分别记录）
- 对话历史只取最近 20 轮
- 敏感信息不应存入记忆

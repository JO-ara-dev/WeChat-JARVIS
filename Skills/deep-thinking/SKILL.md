---
name: deep-thinking
description: 三档深度思考模式切换。触发词：分析、设计、为什么、原理、优化。
tools: think
models: deepseek-v4-flash, deepseek-v4-pro
version: 1.0
---

# 深度思考

## 能力描述

根据问题复杂度自动或手动选择不同深度的 AI 模型推理。简单问题用 flash 省时，复杂问题用 pro 保质量。

## 三档模式

| 模式 | 模型 | 适用场景 | 超时 | Max Tokens |
|------|------|----------|------|------------|
| `fast` | deepseek-v4-flash | 简单问答、查询、闲聊 | 60s | 2000 |
| `deep` | deepseek-v4-pro | 算法设计、代码优化、深度分析 | 120s | 4000 |
| `auto` | 自动判断 | 根据关键词选择 | — | — |

## auto 判断规则

```
含 [分析/设计/优化/算法/架构/证明/推导/比较/评估/为什么/原理/策略] 且不含 [查询/什么是/几点/天气/今天/明天/多少]
→ deep，否则 → fast
```

## 工具参数

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| question | string | 是 | 要思考的问题 |
| mode | string | 否 | "fast" / "deep" / "auto"（默认 auto） |

## 使用时机

```
简单问题 → fast 或直接回答
中等问题 → think(fast) 或直接回答
复杂问题 → think(deep)
不确定 → think(auto)
自更新前 → think(deep) 必须
```

## 示例

**用户**: "分析我的课表是否合理"
**执行**: 先 `query_courses()` → `think(question="分析此课表合理性...", mode="auto")` → auto 判定为 deep

**用户**: "高数和线代有什么区别"
**执行**: `think(question="高数和线代的区别", mode="fast")`

## 注意事项

- 日常对话不要滥用 deep 模式
- deep 模式超时 120s，注意等待

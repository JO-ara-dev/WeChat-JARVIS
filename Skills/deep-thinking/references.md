# 深度思考 - 源码引用

## dorm_butler/tools.py

| 函数 | 行号 | 说明 |
|------|------|------|
| `think()` | 586-655 | 深度思考工具 |

### 实现逻辑

```python
mode="auto": 关键词判断 → 复杂词(分析/设计/优化/算法/架构/证明/推导/比较/评估/为什么/原理/策略) → deep
mode="deep": deepseek-v4-pro, max_tokens=4000, timeout=120s
mode="fast": deepseek-v4-flash, max_tokens=2000, temperature=0.3, timeout=60s
```

### 工具 Schema

`tools.py:1115-1133` — `think` 的 OpenAPI function calling 格式。

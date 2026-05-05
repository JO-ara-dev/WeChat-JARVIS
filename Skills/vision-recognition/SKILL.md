---
name: vision-recognition
description: 双AI视觉识别链路。识别课表/作业截图。触发词：识别图片、课表截图、OCR。
tools: process_image (vision_processor.py)
models: Qwen-VL-Plus, DeepSeek
version: 1.0
---

# 视觉识别（双 AI 链路）

## 能力描述

对微信群聊中的课表/作业截图进行识别：Pillow 图像预处理 → Qwen-VL-Plus OCR 文字提取 → DeepSeek 意图分析与结构化 JSON 输出。

## 适用场景

- 群友发了课表截图，自动识别并入库
- 老师发了调课通知图片
- 作业布置截图提取信息

## 调用流程

```
微信图片
  ↓
Step 1: Pillow 预处理 (GaussianBlur + Contrast×1.6 + Sharpness×2.2 + Brightness×1.1)
  ↓
Step 2: Qwen-VL-Plus OCR (DashScope API, base64 data:image URL)
  ↓
Step 3: DeepSeek 意图分析 → JSON
  ↓
存入 pending_actions 表 → 等待用户确认
```

## 预处理参数

| 操作 | 参数 | 说明 |
|------|------|------|
| 高斯模糊 | radius=0.5 | 去除噪点 |
| 对比度增强 | factor=1.6 | 文字更清晰 |
| 锐化 | factor=2.2 | 边缘增强 |
| 亮度 | factor=1.1 | 暗图提亮 |
| 超长图压缩 | max_height=2000 | 等比缩放 |

## 意图分类

| Intent | 触发条件 |
|--------|----------|
| `add_courses` | 包含课表信息 |
| `update_course` | 调课/换地点 |
| `add_task` | 包含作业/DDL |
| `chat` | 无有效信息 |

## 确认机制

- 识别结果存入 `pending_actions` (status=pending)
- Agent 回复预览 → 用户说"对"/"确认" → 正式入库
- 超时 24h 未确认自动清理

## 示例

**用户**: [发送课表截图]
**执行**: `process_image(image_path, user_id)` → 预处理 → OCR → 分析 → pending_actions

## 注意事项

- 需要配置 DASHSCOPE_API_KEY
- OCR 超时 60s，DeepSeek 超时 30s
- 文字少于 5 字符视为无效
- 支持 jpg/jpeg/png/gif

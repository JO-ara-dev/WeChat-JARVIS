---
name: network-expose
description: 一键内网穿透，暴露本地文件到公网。触发词：发给我、分享、手机看、公网链接。
tools: expose
dependency: ngrok (需安装并加入 PATH)
version: 1.0
---

# 内网穿透

## 能力描述

一键将本地文件或动态 HTML 通过 ngrok 暴露到公网，生成可分享 URL。自动为 HTML 添加手机端 viewport 适配。

## 适用场景

- 用户说"把 xxx 发给我"
- 用户在手机上查看本地页面
- 分享动态生成的 HTML 内容
- 暴露静态页面如 `example.html`

## 调用流程

```
用户请求分享
  ↓
expose(user_id, file_path? / content?, port=8765, mobile_fix=true)
  ↓
1. 检查/启动 http.server (端口 8765)
2. 检查/启动 ngrok http 隧道（轮询最多 10s）
3. 拼接公网 URL
  ↓
返回链接给用户
```

## 工具参数

| 参数 | 类型 | 必填 | 说明 | 默认值 |
|------|------|------|------|--------|
| port | integer | 否 | 本地端口 | 8765 |
| file_path | string | 否 | 项目内文件路径 | — |
| content | string | 否 | 动态 HTML 字符串 | — |
| mobile_fix | boolean | 否 | 自动添加 viewport | true |

file_path 和 content 二选一。

## 手机端适配

mobile_fix=true 时自动检测并注入：
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
```

## 示例

**用户**: "把爱心页面发给我"
**执行**: `expose(user_id="xxx", file_path="example.html")` → 返回 `https://xxxx.ngrok-free.app/example.html` → 直接回复链接

**用户**: "生成一个课表网页并分享"
**执行**: 整理课表 → `expose(content="<html>...</html>")` → 回复链接

> **关键规则**: 调用 expose 后必须把公网链接直接回复给用户，绝不许只说"处理完了"。

## 注意事项

- ngrok 需手动安装并加入 PATH
- ngrok 免费版域名随机化，有连接数限制
- http.server 和 ngrok 以后台子进程运行
- file_path 限制在项目目录内

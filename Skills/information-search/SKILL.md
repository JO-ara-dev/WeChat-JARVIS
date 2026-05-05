---
name: information-search
description: 获取外部信息和项目内部数据。触发词：搜索、查一下、看看文件、目录。
tools: web_search, read_file, list_files
version: 1.0
---

# 信息获取

## 能力描述

获取外部信息和项目内部数据：Bing 联网搜索、读取项目文件、浏览目录结构。

## 适用场景

- 查实时信息（天气、新闻、资讯）
- 查看项目代码、配置文件、数据文件
- 浏览项目目录结构

## 工具参数

### web_search
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| query | string | 是 | 搜索关键词 |

超时 10s，返回前 2000 字符摘要，使用 Bing 中国区 (mkt=zh-CN)。

### read_file
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file_path | string | 是 | 相对项目根目录的路径 |

安全限制：只能读取项目目录内的文件。

### list_files
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| dir_path | string | 否 | 目录路径，默认当前目录 |

安全限制：只能列出项目目录内的内容。

## 示例

**用户**: "搜索 DeepSeek 最新消息"
**执行**: `web_search(query="DeepSeek 最新消息")`

**用户**: "看看 .env 文件"
**执行**: `read_file(file_path=".env")`

**用户**: "dorm_butler 下有什么文件"
**执行**: `list_files(dir_path="dorm_butler")`

## 注意事项

- 所有文件操作限制在项目根目录内
- 不确定的信息用 web_search 确认，禁止编造

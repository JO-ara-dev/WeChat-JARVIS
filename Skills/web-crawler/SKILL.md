---
name: web-crawler
description: 教务网课表爬虫，Playwright自动化抓取。触发词：更新课表、导入教务网、/update。
file: crawler.py
dependency: Playwright + Edge 浏览器
version: 1.0
---

# 教务网爬虫

## 能力描述

自动化登录教务网、检测课表页面、抓取 HTML、解析课程信息并写入数据库。需要用户在浏览器中手动完成登录和筛选操作。

> 这是独立脚本 (`python crawler.py`)，不是 Agent 工具，Agent 不能自动触发。

## 执行流程

```
python crawler.py
  ↓
1. 启动 Edge 浏览器（有头模式）
2. 打开教务网登录页
3. 用户手动登录 + 导航到课表查询页
4. 自动检测课表页面 URL (含 "Schedule/Query/Default.aspx")
5. 提示用户选好学期/班级，按回车确认
6. 抓取 HTML → 保存到 data/schedule_raw.html
7. 解析 table#TabSchedule → 写入 courses 表
8. 提示实践环节（不入库，仅展示）
```

## 解析规则

### 节次映射
| 行 ID | 节次 |
|--------|------|
| TableRow2 | 1-2 |
| TableRow3 | 3-4 |
| TableRow4 | 5-6 |
| TableRow5 | 7-8 |
| TableRow6 | 9-10 |

### 列→星期映射
列索引 1-5 → 周一到周五。

### 单元格格式
`课程名  地点  校区 | 教师名  班级号  周次`

### 提取正则
- 教室: `[AB]\d[A-Za-z-]?\d*`
- 周次: `(\d+(?:[-,]\d+)*)\s*周`
- 实践周: `第(\d+(?:-\d+)?)周`

## 示例

```bash
python crawler.py
# → Edge 打开登录页 → 用户手动登录 → 自动抓取 → 15 门课入库
```

## 注意事项

- 需要 `pip install playwright` + `playwright install msedge`
- crawler.py 是独立脚本，不在 Agent 工具链中
- 抓取前会清空旧课表 (DELETE FROM courses)
- 实践环节只展示不入库
- 需要校园网/内网连接教务系统

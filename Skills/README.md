# 贾维斯技能清单 (Skills Manifest)

> 这里是 J.V 的全部已习得技能。每次学会新技能，请在本清单添加一行索引，并在同目录下创建 `技能名/SKILL.md`。
>
> **结构化索引**: `manifest.json` 与本文档同步维护，供代码自动读取。

## 技能系统工作流

```
用户消息 → 前置意图分类(deepseek-v4-flash) → 查 manifest.json
  ├─ 命中技能 → 加载 SKILL.md → 注入 System Prompt → 按技能规范执行
  └─ 未命中 → AI 询问是否创建新技能 → propose_skill 生成方案 → 用户审阅 → register_skill 注册
```

## 技能索引

| # | 技能 | 文件夹 | 可执行 | 触发关键词 |
|---|------|--------|--------|------------|
| 1 | 查询、添加、删除课程表，支持按星期筛选和周次过滤 | [course-management/](course-management/) | — | 课表, 课程, 今天什么课, 明天什么课 |
| 2 | 管理作业任务，支持DDL追踪和待办查询 | [assignment-management/](assignment-management/) | — | 作业, DDL, ddl, 截止 |
| 3 | 双AI视觉识别链路，识别课表/作业截图并结构化入库 | [vision-recognition/](vision-recognition/) | run.py | 识别图片, 课表截图, OCR, 识别 |
| 4 | 联网搜索、文件读取、目录浏览等信息获取能力 | [information-search/](information-search/) | — | 搜索, 查一下, 看看文件, 搜索一下 |
| 5 | 执行Python代码和系统命令，读写文件 | [code-execution/](code-execution/) | — | 运行, 执行, 安装, 跑一下 |
| 6 | 深度思考模式，支持fast/deep/auto三档推理 | [deep-thinking/](deep-thinking/) | — | 分析, 设计, 为什么, 优化 |
| 7 | 一键内网穿透，将文件/HTML暴露到公网供手机访问 | [network-expose/](network-expose/) | — | 发给我, 分享, 手机看, 暴露 |
| 8 | 自进化Pipeline：Plan→Act→Verify→Reflect，支持自我修复和代码更新 | [self-evolution/](self-evolution/) | — | 复杂任务, 自动修复, 更新自己, 自我进化 |
| 9 | 管理用户画像和对话记忆，记住偏好和习惯 | [memory-management/](memory-management/) | — | 记住, 偏好, 习惯, 记忆 |
| 10 | 教务网爬虫，自动登录教务系统抓取课表数据 | [web-crawler/](web-crawler/) | crawler.py | 更新课表, 导入教务网, 爬取, 教务系统 |
| 11 | 定时提醒课程，每晚22:00自动提醒次日课程安排 | [scheduled-reminder/](scheduled-reminder/) | scheduler.py | 定时提醒, 自动提醒, 课程提醒, 每晚提醒 |
| 12 | 考试提醒技能 - 添加、查询、删除考试信息，并自动在指定天数前通过微信提醒用户 | [exam-reminder/](exam-reminder/) | — |  |
| 13 | 三Agent并行文档生成技能 - 自动将内容生成真正的PPT/Word/Excel文档 | [parallel-doc-generator/](parallel-doc-generator/) | — |  |
| 14 | 设计美学规范 — 所有生成网页/UI/文档/图表的通用审美标准 | [design-aesthetic/](design-aesthetic/) | — |  |

## 目录结构规范

```
Skills/
├── README.md                 ← 本清单
├── skill-name/               ← 每个技能一个文件夹
│   ├── SKILL.md              ← 核心指令文件（必须）
│   ├── run.py                ← 可选：独立可执行脚本
│   ├── references.md         ← 可选：源码引用说明
│   ├── 参考文档.md            ← 可选：补充文档
│   └── 素材/                 ← 可选：图片等静态资源
└── ...
```

## 已接入的执行文件

| 技能 | 文件 | 用法 |
|------|------|------|
| 视觉识别 | `vision-recognition/run.py` | `python run.py <图片路径>` |
| 教务爬虫 | `web-crawler/crawler.py` | `python crawler.py` |
| 定时提醒 | `scheduled-reminder/scheduler.py` | 由 `butler_agent.py` 自动加载 |

## 已接入的引用文档

| 技能 | 文件 | 指向源文件行号 |
|------|------|---------------|
| 课表管理 | `references.md` | `dorm_butler/tools.py:295-354` `dorm_butler/db_manager.py:81-162` |
| 作业管理 | `references.md` | `dorm_butler/tools.py:357-375` `dorm_butler/db_manager.py:166-281` |
| 信息获取 | `references.md` | `dorm_butler/tools.py:378-481` |
| 代码/命令执行 | `references.md` | `dorm_butler/tools.py:430-583` `dorm_butler/memory.py:203-261` |
| 深度思考 | `references.md` | `dorm_butler/tools.py:586-655` |
| 内网穿透 | `references.md` | `dorm_butler/tools.py:660-793` |
| 自进化 | `references.md` | `dorm_butler/tools.py:22-247` |
| 记忆管理 | `references.md` | `dorm_butler/memory.py:25-261` `dorm_butler/butler_agent.py:117-133` |
| 会话管理 | `references.md` | `dorm_butler/sessions.py` `wx4py_bridge.py` |
| 定时提醒 | `references.md` | `dorm_butler/scheduler.py` `skills/scheduled-reminder/scheduler.py` |

## 技能学习记录

| 日期 | 变更 |
|------|------|
| 2026-05-05 | 初始化技能库，注册 10 项已习得技能；接入 2 个可执行脚本 + 8 个引用文档 |
| 2026-05-05 | **技能系统升级**：新增 manifest.json 结构化索引；新增 skill_manager.py 管理器；新增前置意图分类(deepseek-v4-flash)；新增 propose_skill/register_skill 工具实现技能自动创建 |
| 2026-05-05 | **会话管理**：新增技能 #11；支持暂停/归档/切换/总结；Agent 回复前缀统一为 J.V；新增进度汇报规则 |
| 2026-05-05 | **定时提醒**：新增技能 #12；基于 APScheduler 每晚22:00自动提醒次日课程 |
| 2026-05-05 | **定时提醒补全**：按规范补全 `scheduler.py` 独立脚本 + `references.md` 源码引用 |

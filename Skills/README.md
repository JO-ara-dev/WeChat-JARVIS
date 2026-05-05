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
| 1 | 课表管理 | [course-management/](course-management/) | — | 课表、课程、今天什么课 |
| 2 | 作业管理 | [assignment-management/](assignment-management/) | — | 作业、DDL、截止、任务 |
| 3 | 视觉识别 | [vision-recognition/](vision-recognition/) | `run.py` | 识别图片、课表截图、OCR |
| 4 | 信息获取 | [information-search/](information-search/) | — | 搜索、查一下、看看文件 |
| 5 | 代码/命令执行 | [code-execution/](code-execution/) | — | 运行、执行、安装 |
| 6 | 深度思考 | [deep-thinking/](deep-thinking/) | — | 分析、设计、为什么、优化 |
| 7 | 内网穿透 | [network-expose/](network-expose/) | — | 发给我、分享、手机看 |
| 8 | 自进化 Pipeline | [self-evolution/](self-evolution/) | — | 复杂任务、自动修复、更新自己 |
| 9 | 记忆管理 | [memory-management/](memory-management/) | — | 记住、偏好、习惯 |
| 10 | 教务爬虫 | [web-crawler/](web-crawler/) | `crawler.py` | 更新课表、导入教务网 |
| 11 | 会话管理 | [session-management/](session-management/) | — | 暂停、/stop、/sessions、/session、/summary |
| 12 | 定时提醒 | [scheduled-reminder/](scheduled-reminder/) | `scheduler.py` | 定时提醒、自动提醒、课程提醒、每晚提醒 |

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

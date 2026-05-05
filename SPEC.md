# 微信贾维斯 技术规格说明书 (Spec)

## 1. 项目概述

- **名称**: 微信贾维斯 / WeChat J.A.R.V.I.S
- **定位**: 基于 wx4py 的自进化微信群聊 AI Agent
- **核心目标**: 课程管理、DDL 追踪、图片识别、技能自进化、内网穿透分享

## 2. 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 微信连接 | wx4py (WeChatClient) | 纯 Python，无需 DLL 注入 |
| AI 大脑 | DeepSeek (deepseek-chat/v4-pro/v4-flash) | 函数调用 + 深度思考 |
| 视觉识别 | 阿里云 Qwen-VL-Plus (DashScope) | 课表图片 OCR |
| 数据库 | SQLite3 (data/butler.db) | 本地持久化 |
| 图像处理 | Pillow | 图片预处理 |
| 内网穿透 | cpolar / ngrok + http.server | 一键公网暴露 |
| 爬虫 | Playwright + Edge | 教务系统自动化 |

## 3. 项目文件结构

```
.
├── wx4py_bridge.py          # 机器人入口，wx4py 消息桥接
├── run_bridge.ps1            # 启动脚本
├── .env.example              # 环境变量模板
├── .gitignore
├── requirements.txt          # Python 依赖
├── schema.sql                # 数据库建表语句
├── crawler.py                # 教务网爬虫（Playwright）
├── check_memory.py           # 记忆调试工具
├── db_manager.py             # 根目录数据库模块
├── dorm_butler/              # 核心模块
│   ├── __init__.py
│   ├── butler_agent.py       # Agent 主逻辑（DeepSeek 函数调用 + 意图分类）
│   ├── db_manager.py         # 数据库 CRUD 封装
│   ├── memory.py             # 对话历史 + 用户画像 + run_code 工具
│   ├── tools.py              # 工具集（24个工具）
│   ├── skill_manager.py      # 技能管理器（清单加载/意图分类/技能注册）
│   ├── agent_swarm.py        # 多 Agent 协作引擎（并行派发 + Agent间通信）
│   ├── sub_agent.py          # SubAgent 执行器（独立DeepSeek调用 + 模型路由）
│   ├── harness_guard.py      # HarnessGuard 死循环防护
│   ├── agents.json           # 子 Agent 配置
│   ├── scheduler.py          # 定时任务调度器
│   ├── sessions.py           # 多会话管理
│   └── vision_processor.py   # 双 AI 视觉识别链路
├── Skills/                   # 技能目录（Agent 自进化产物）
│   ├── README.md             # 人类可读技能清单
│   ├── manifest.json         # 结构化技能索引
│   ├── course-management/
│   ├── assignment-management/
│   └── ...                   # 10+ 个技能
├── backups/                  # self_update 自动备份目录
└── data/
    ├── butler.db             # SQLite 数据库（.gitignore 排除）
    └── temp_*.png            # 视觉处理临时图片
```

## 4. 架构与消息流

```
微信群消息
  ↓
wx4py WeChatClient → ButlerHandler
  ├── 被 @ → 直接进入队列
  ├── 含关键词 → 进入队列
  └── 自己的消息 → 过滤（防循环）
  ↓
msg_queue → process_worker 线程
  ↓
butler_agent.chat()
  ├── ① 前置意图分类（deepseek-v4-flash）
  │     ├─ 命中技能 → 加载 Skills/{name}/SKILL.md → 注入 System Prompt
  │     └─ 未命中 → 注入「建议创建技能」提示
  ├── ② 主 Agent 对话（DeepSeek Chat + 24 tools）
  │     ├─ 工具调用 → _execute_tool() → 返回结果 → 继续对话
  │     └─ 无技能时 → AI 询问用户是否创建 → propose_skill → 用户审阅
  └── ③ 技能注册 → register_skill → 创建目录/SKILL.md/更新 manifest.json
  ↓
ReplyAction → 发回群聊
```

## 5. Harness 自进化 Pipeline

```
Plan → Confirm → Act → Verify → Reflect
  ↓       ↓         ↓       ↓         ↓
plan_task  展示给用户  update_todo  self_heal  reflect → evolve_pipeline
                                    ↓
                              reuse_pipeline（下次复用）
```

| 阶段 | 工具 | 说明 |
|------|------|------|
| Plan | `plan_task` | 分解复杂任务为步骤列表 |
| Confirm | 文本展示 | 展示计划给用户，等用户确认 |
| Act | `update_todo`, `get_todos` | 逐步执行并标记状态 |
| Verify | `self_heal` | 失败时自动分析错误，生成修复方案 |
| Reflect | `reflect` | 总结 + 清理 TODO |
| Evolve | `evolve_pipeline` | 成功方案注册到 config 表持久化 |
| Reuse | `reuse_pipeline` | 同类任务先查缓存复用 |

## 6. 多 Agent 协作架构 (Agent Swarm)

```
用户消息 → 主 Agent 拆解任务
  ↓
AgentSwarm.launch_parallel()
  ├── code-executor (v4-pro) — 编写/运行代码、执行命令
  ├── web-designer (v4-pro)  — 网页设计、内网穿透分享
  ├── researcher (chat)      — 联网搜索、信息收集
  ├── course-manager (chat)  — 课表查询、作业管理
  ├── vision-analyst (qwen-vl)— 图片 OCR、课表识别
  └── system-admin (chat)    — 环境搭建、服务部署
  ↓
各 Agent 并行执行（独立 DeepSeek 上下文）
  ├── Agent 间可通过 [REQUEST:agent] 求助
  └── 主 Agent 审核结果 (review_result) → 通过则组装回复
```

### HarnessGuard 死循环防护
- `before_tool()`: 工具调用前检查同一参数重复次数
- 同一工具+同一参数连续调用 ≥3 次 → 自动阻断
- `after_tool()`: 调用后记录，新对话自动清空

## 7. 工具清单 (24个)

### 任务规划
| 工具 | 说明 |
|------|------|
| `plan_task` | 分解任务为步骤 |
| `update_todo` | 更新步骤状态 |
| `get_todos` | 查看任务进度 |
| `reflect` | 任务完成总结 |

### 自进化
| 工具 | 说明 |
|------|------|
| `self_heal` | 失败自动修复建议 |
| `evolve_pipeline` | 注册成功方案 |
| `reuse_pipeline` | 复用已有方案 |
| `self_update` | 更新自身源码（需确认 + 自动备份） |

### 课表 & 作业
| 工具 | 说明 |
|------|------|
| `query_courses` | 查询课表（支持指定 weekday） |
| `add_courses` | 批量添加课程 |
| `delete_courses` | 删除课程 |
| `query_tasks` | 查询待完成作业 |
| `add_task` | 添加作业（含 DDL） |
| `delete_task` | 删除作业 |

### 通用能力
| 工具 | 说明 |
|------|------|
| `web_search` | Bing 联网搜索 |
| `read_file` | 读取项目内文件 |
| `write_file` | 写入项目内文件 |
| `list_files` | 列出目录内容 |
| `create_tool` | 动态创建新工具（自进化） |
| `run_cmd` | 执行系统命令（需确认） |
| `run_code` | 执行 Python 代码（安全沙箱） |
| `think` | 深度思考（fast/deep/auto 三档） |
| `expose` | 一键内网穿透，暴露内容到公网 |

### 用户管理
| 工具 | 说明 |
|------|------|
| `identify_me` | 注册当前用户昵称 |
| `resolve_user` | 通过昵称查找用户 |
| `set_nickname` | 设置用户昵称 |

### 技能管理
| 工具 | 说明 |
|------|------|
| `propose_skill` | 无匹配技能时，AI 生成新技能 SKILL.md 方案草案 |
| `register_skill` | 用户确认后正式注册技能 |

### 记忆
| 工具 | 说明 |
|------|------|
| `save_memory` | 记住用户偏好 |
| `get_memory` | 查询用户记忆 |
| `delete_memory` | 删除记忆 |

## 8. 数据库设计

### 8.1 课表表 (courses)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| name | TEXT | 课程名称 |
| location | TEXT | 教室地点 |
| week_day | INTEGER | 周几 (1-7) |
| start_node | INTEGER | 起始节次 |
| end_node | INTEGER | 结束节次 |
| weeks | TEXT | 上课周次 (如 "1-16") |

### 8.2 任务表 (tasks)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| content | TEXT | 作业内容 |
| ddl | DATETIME | 截止日期 |
| course_id | INTEGER | 关联课程 ID |
| status | INTEGER | 0:未完成, 1:已完成 |
| remind_level | INTEGER | 提醒等级 |
| creator_id | TEXT | 创建者 ID |
| creator_nickname | TEXT | 创建者昵称 |
| scope | TEXT | private/public |

### 8.3 用户表 (users)
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT | 主键 |
| nickname | TEXT | 昵称（唯一） |
| platform | TEXT | wechat |
| created_at | DATETIME | 注册时间 |

### 8.4 配置表 (config)
| 字段 | 类型 | 说明 |
|------|------|------|
| key | TEXT | 配置键（唯一） |
| value | TEXT | 配置值 |

### 8.5 待确认表 (pending_actions)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| user_id | TEXT | 用户 ID |
| intent | TEXT | 意图类型 |
| data_json | TEXT | JSON 数据 |
| confidence | REAL | 置信度 |
| status | TEXT | pending/confirmed/cancelled |

### 8.6 对话历史 (chat_history)
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| user_id | TEXT | 用户 ID |
| session_id | INTEGER | 会话 ID |
| role | TEXT | user/assistant |
| content | TEXT | 消息内容 |

### 8.7 用户画像 (user_memory)
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT | 用户 ID |
| key | TEXT | 记忆键名 |
| value | TEXT | 记忆值 |
| scope | TEXT | private/public |
| (user_id, key) | UNIQUE | 联合唯一 |

## 9. 双 AI 视觉识别流

```
输入: 微信图片
  ↓
Pillow 预处理（降噪/增强对比度+60%/锐度+120%/亮度+10%）
  ↓
Qwen-VL-Plus OCR 提取文字
  ↓
DeepSeek 分析意图 → JSON
  ↓
存入 pending_actions 表 → 等待确认
```

## 10. 人设系统

- **自称**: J.V（贾维斯）
- **称呼用户**: 老大
- **风格**: 专业高效、简洁有条理、用 emoji 点缀
- **工作流**: Plan→Confirm→Act→Verify→Reflect

## 11. 安全与限流

### 工具安全
- `run_cmd`: 危险命令黑名单 (format, del, rm -rf, shutdown 等)
- `run_code`: 禁止 eval/exec/__import__/subprocess 系统命令
- `read_file` / `write_file` / `list_files`: 限制在项目目录内
- `self_update`: 限制 dorm_butler/ 和根目录 .py 文件 + 自动备份 + 需确认

### API 限流
- DeepSeek API: 60次/分钟
- DashScope Qwen-VL: 注意 QPS 限制

## 12. 环境变量配置

| 服务 | 必需配置项 |
|------|-----------|
| DeepSeek | DEEPSEEK_API_KEY, DEEPSEEK_API_BASE |
| 图片大模型 | DASHSCOPE_API_KEY |
| 内网穿透 | TUNNEL_PROVIDER (auto/cpolar/ngrok) |
| 教务爬虫 | CRAWLER_LOGIN_URL, CRAWLER_USERNAME, CRAWLER_PASSWORD |

## 13. 技能系统

### 12.1 技能清单目录
```
Skills/
├── README.md          # 人类可读清单
├── manifest.json      # 结构化索引（JSON，代码读取）
├── {skill-name}/      # 每个技能一个文件夹
│   ├── SKILL.md       # 核心指令文件
│   ├── run.py         # 可选：独立可执行脚本
│   └── references.md  # 可选：源码引用说明
└── ...
```

### 12.2 意图分类
```
用户消息
  ↓
_classify_intent() → deepseek-v4-flash (temperature=0)
  ├── 输入: 用户消息 + manifest.json 技能列表
  ├── 输出: {"matched_skill": "xxx", "confidence": 0.95, "keywords": [...]}
  └── confidence >= 0.5 → 加载 SKILL.md → 注入 System Prompt
```

### 12.3 技能注册流程
```
无匹配技能 → AI 询问用户是否创建
  ↓ (用户同意)
AI 调用 propose_skill → 生成 SKILL.md 草案 → 展示审阅
  ↓ (用户确认)
AI 调用 register_skill(confirmed=true)
  ├── 创建 Skills/{name}/SKILL.md
  ├── 更新 manifest.json
  └── 同步 README.md 表格
```

## 14. 模型架构（经济双模）

| 角色 | 模型 | 用途 |
|------|------|------|
| 🧠 大脑 | DeepSeek (deepseek-chat) | 对话推理、工具调用、代码执行 |
| 👁️ 眼睛 | Qwen-VL-Plus | 课表截图 OCR、图片内容识别 |

纯文本模型当大脑负责思考决策，多模态模型当眼睛负责"看"图片。两者按需调用。

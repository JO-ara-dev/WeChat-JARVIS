# 微信贾维斯 技术规格说明书

> 面向开发者和 AI 自进化，不包含模块函数 API（见 PROJECT.md），专注架构设计、数据流、数据库结构、安全规则。

---

## 1. 项目定位

- **名称**：微信贾维斯 / J.A.R.V.I.S
- **类型**：自进化微信群聊 AI Agent
- **入口**：`wx4py_bridge.py`
- **运行环境**：Windows + Python 3.12 + wx4py

---

## 2. 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 微信连接 | wx4py (WeChatClient) | 纯 Python，UIA 自动化，无需 DLL 注入 |
| AI 引擎 | DeepSeek (deepseek-chat) | 函数调用 + 多轮对话 + 深度思考 |
| 意图分类 | DeepSeek / GLM-4.7-Flash | 前置轻量分类 |
| 视觉识别 | 阿里云 Qwen-VL-Plus | OCR + 图片内容识别 |
| 数据库 | SQLite3 (data/butler.db) | 本地持久化 |
| 图像处理 | Pillow | 预处理（对比度/锐度/亮度） |
| 内网穿透 | cpolar / ngrok + http.server | 一键公网暴露 |
| 爬虫 | Playwright + Edge | 教务系统自动化 |
| 定时任务 | APScheduler | 每夜课程提醒 |

---

## 3. 项目文件结构

```
.
├── wx4py_bridge.py          # 主程序入口：微信连接、消息桥接、队列处理
├── run_bridge.ps1            # 一键启动脚本
├── .env.example              # 环境变量模板
├── requirements.txt          # Python 依赖
├── schema.sql                # 建表语句
├── crawler.py                # 教务网爬虫（Playwright + Edge）
├── check_memory.py           # 记忆调试工具
├── db_manager.py             # 根目录数据库（crawler 依赖）
├── dorm_butler/              # 核心模块包
│   ├── __init__.py
│   ├── butler_agent.py       # Agent 主逻辑（chat + 工具循环）
│   ├── db_manager.py         # 数据库 CRUD 封装
│   ├── memory.py             # 对话历史 + 用户画像 + run_code 沙箱
│   ├── tools.py              # 工具集（31 个函数 + schema + 分发表）
│   ├── skill_manager.py      # 技能管理器
│   ├── agent_swarm.py        # 多 Agent 协作引擎
│   ├── sub_agent.py          # SubAgent 执行器
│   ├── harness_guard.py      # HarnessGuard 死循环防护
│   ├── agent_config.json     # 子 Agent 配置
│   ├── agents.json           # 子 Agent 列表（兼容）
│   ├── scheduler.py          # 定时任务
│   ├── sessions.py           # 多会话管理
│   └── vision_processor.py   # 双 AI 视觉识别链路
├── Skills/                   # 技能目录（Agent 自进化产物）
│   ├── README.md
│   ├── manifest.json
│   └── {skill-name}/
│       └── SKILL.md
├── backups/                  # self_update 自动备份
└── data/
    ├── butler.db             # SQLite 数据库
    └── temp_*.png            # 视觉处理临时图片
```

---

## 4. 架构与消息流

```
微信群消息
  │
  ▼
wx4py WeChatClient → ButlerHandler
  ├── 被 @ → 入队
  ├── 含关键词 → 入队
  └── 自己的消息 → 过滤（防循环）
  │
  ▼
msg_queue (Queue)
  │
  ▼
process_worker 线程
  │
  ▼
butler_agent.chat()
  │
  ├── ① _classify_intent() → 前置意图分类
  │     ├─ 命中技能 → 读取 Skills/{name}/SKILL.md → 注入 System Prompt
  │     └─ 未命中 → 注入「建议创建技能」提示
  │
  ├── ② 主 Agent LLM 循环
  │     ├─ 工具调用 → harness_guard.before_tool() 检查
  │     ├─ _execute_tool() 分发执行
  │     ├─ harness_guard.after_tool() 记录
  │     └─ 结果送回 LLM 继续推理
  │
  └── ③ 回复生成 → yield chunk
  │
  ▼
action_emitter → ReplyAction → 微信发送
```

---

## 5. Harness 自进化 Pipeline

```
Plan → Confirm → Act → Verify → Reflect → Evolve → Reuse
  │       │        │       │         │         │        │
plan_task  发给用户  update_todo  self_heal  reflect  evolve_pipeline
  用户确认               │                                │
                         │                    reuse_pipeline（下次复用）
                         ▼
                  harness_guard 全程守护
```

| 阶段 | 工具 | 触发条件 |
|------|------|----------|
| Plan | `plan_task` | 复杂任务（≥2 步） |
| Confirm | 文本展示 | Plan 完成后，等用户回复"执行/确认/OK/批准" |
| Act | `update_todo` + 实际工具 | 用户确认后逐步执行 |
| Verify | `self_heal` | 工具返回 success=false 时自动触发 |
| Reflect | `reflect` | 任务完成后总结 |
| Evolve | `evolve_pipeline` | 成功方案持久化到 config 表 |
| Reuse | `reuse_pipeline` | 同类任务先查缓存 |

---

## 6. 多 Agent 协作架构 (Agent Swarm)

### 6.1 子 Agent 清单

| Agent | 模型 | 允许工具 | 职责 |
|-------|------|----------|------|
| code-executor | v4-pro | run_code, run_cmd, think | 编写/运行代码、执行命令 |
| web-designer | v4-pro | read_file, write_file, run_cmd, expose, think | 网页设计、内网穿透分享 |
| researcher | chat | web_search, think | 联网搜索、信息收集 |
| course-manager | chat | query_courses, add_courses, query_tasks, add_task | 课表查询、作业管理 |
| vision-analyst | qwen-vl | — (直接分析图片) | 图片 OCR、课表识别 |
| system-admin | chat | run_cmd, run_code, read_file, write_file, think | 环境搭建、服务部署 |

### 6.2 协作流程

```
用户消息 → 主 Agent 拆解任务
  ↓
AgentSwarm.launch_parallel()
  ├── 各 Agent 并行执行
  ├── Agent 间通过 REQUEST/RESULT 协议通信
  └── 主 Agent 审核结果 (review_result) → 通过则组装回复
```

### 6.3 Agent 间通信协议

```
Agent A → Agent B: "[REQUEST:{agent_name}] 需要 XXX 的帮助"
Agent B → Agent A: "[RESULT:{agent_name}] 这里是结果..."
```

消息通过 `agent_swarm.send_message()` / `check_messages()` 在内存队列中传递。

---

## 7. HarnessGuard 死循环防护

```
before_tool(user_id, tool_name, args)
  ├── 计算 (tool_name + hash(args)) 指纹
  ├── 检查最近 10 次调用中同指纹出现次数
  ├── ≥ 3 次 → 返回阻断原因字符串
  └── < 3 次 → 返回 None（放行）

after_tool(user_id, tool_name, args)
  └── 追加记录到内存队列（最多保留 20 条）

clear_user(user_id)
  └── 新对话开始时清空
```

---

## 8. 数据库设计

### 8.1 courses（课表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT | 课程名称 |
| location | TEXT | 教室 |
| week_day | INTEGER | 1-7（周一~周日） |
| start_node | INTEGER | 起始节次（1-8） |
| end_node | INTEGER | 结束节次（1-8） |
| weeks | TEXT | 周次范围："1-16" 或 "1,3,5-8" |

### 8.2 tasks（作业/DDL）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| content | TEXT | 作业内容 |
| ddl | DATETIME | 截止时间 |
| course_id | INTEGER | 关联课程 ID（可空） |
| status | INTEGER | 0=未完成, 1=已完成 |
| remind_level | INTEGER | 0=普通, 1=重要, 2=紧急 |
| creator_id | TEXT | 创建者 user_id |
| creator_nickname | TEXT | 创建者昵称 |
| scope | TEXT | "private" / "public" |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 8.3 users（用户）

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT PK | 用户 ID（群聊 ID） |
| nickname | TEXT UNIQUE | 昵称 |
| platform | TEXT | "wechat" |
| created_at | DATETIME | 注册时间 |

### 8.4 config（配置 + Pipeline 缓存）

| 字段 | 类型 | 说明 |
|------|------|------|
| key | TEXT PK | 配置键 |
| value | TEXT | 配置值 |

关键键名：
- `semester_start` — 学期起始日期 (YYYY-MM-DD)
- `pipeline:{task_type}` — Pipeline 缓存

### 8.5 pending_actions（待确认操作）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户 ID |
| intent | TEXT | 意图类型 (add_courses/add_task) |
| data_json | TEXT | JSON 数据 |
| confidence | REAL | 置信度 (0-1) |
| status | TEXT | "pending" / "confirmed" / "cancelled" |
| created_at | DATETIME | 创建时间 |

### 8.6 chat_history（对话历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户 ID |
| session_id | INTEGER FK→sessions.id | 会话 ID |
| role | TEXT | "user" / "assistant" / "tool" |
| content | TEXT | 消息内容 |
| created_at | DATETIME | 创建时间 |

### 8.7 user_memory（用户画像）

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | TEXT | 用户 ID |
| key | TEXT | 记忆键名 |
| value | TEXT | 记忆值 |
| scope | TEXT | "private" / "public" |
| updated_at | DATETIME | 更新时间 |
| UNIQUE(user_id, key) | — | 联合唯一约束 |

### 8.8 sessions（会话）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | TEXT | 用户 ID |
| name | TEXT | 会话名称 |
| status | TEXT | "active" / "archived" |
| summary | TEXT | AI 生成摘要 |
| message_count | INTEGER | 消息计数 |
| created_at | DATETIME | 创建时间 |
| ended_at | DATETIME | 结束时间 |

---

## 9. 安全与限流规则

### 9.1 工具安全

| 工具 | 限制 |
|------|------|
| `run_cmd` | 黑名单：format, del /s, rm -rf, shutdown, taskkill /f system 等。需用户确认。 |
| `run_code` | 禁止 eval/exec/__import__/subprocess 系统命令/os.system。沙箱执行。 |
| `read_file` / `write_file` / `list_files` | 限制在项目根目录内 |
| `self_update` | 仅允许 dorm_butler/*.py 和根目录 *.py。自动备份到 backups/。需用户确认。 |
| `expose` | 仅暴露项目目录下文件 |

### 9.2 API 限流

| 服务 | 限制 |
|------|------|
| DeepSeek API | 60次/分钟 |
| DashScope (Qwen-VL) | 注意 QPS 限制 |

### 9.3 网络约束

- pip 安装用清华源：`-i https://pypi.tuna.tsinghua.edu.cn/simple`
- npm 用淘宝源：`--registry https://registry.npmmirror.com`
- 禁止依赖被墙服务（Google、Docker Hub、GitHub Raw、HuggingFace 直连、OpenAI 等）
- 工具选型必须免费/开源

### 9.4 微信风控

- 使用小号运行，避免主号被封
- 控制回复频率，不过度刷屏
- wx4py 纯 Python 方案，不会触发杀毒软件

---

## 10. 环境变量配置

| 变量 | 必需 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API Key |
| `DEEPSEEK_API_BASE` | 否 | 默认 https://api.deepseek.com/v1 |
| `DASHSCOPE_API_KEY` | 是 | 阿里云 DashScope Key（图片识别） |
| `TUNNEL_PROVIDER` | 否 | auto/cpolar/ngrok，默认 auto |
| `CRAWLER_LOGIN_URL` | 否 | 教务系统登录页 URL |
| `CRAWLER_USERNAME` | 否 | 教务系统用户名 |
| `CRAWLER_PASSWORD` | 否 | 教务系统密码 |

---

## 11. 双 AI 视觉识别流

```
输入：微信图片
  ↓
Pillow 预处理（降噪、对比度+60%、锐度+120%、亮度+10%）
  ↓
Qwen-VL-Plus OCR 提取文字
  ↓
DeepSeek 意图分析 → JSON
  ↓
存入 pending_actions 表 → 等待用户确认
```

---

## 12. 技能系统规格

### 12.1 目录结构

```
Skills/
├── README.md          # 人类可读清单（自动同步）
├── manifest.json      # 结构化索引（JSON，代码读取）
├── {skill-name}/
│   ├── SKILL.md       # 核心指令文件（Markdown）
│   ├── run.py         # 可选：独立可执行脚本
│   └── references.md  # 可选：源码引用说明
└── ...
```

### 12.2 manifest.json 格式

```json
{
  "skills": [
    {
      "name": "course-management",
      "description": "课表查询与管理",
      "keywords": ["课表", "课程", "上课", "教室"],
      "intent_patterns": ["查课表", "今天有什么课", "明天有什么课"],
      "created_at": "2025-01-01"
    }
  ]
}
```

### 12.3 意图分类流程

```
用户消息
  ↓
_load_manifest() → skills 列表
  ↓
classify_intent(user_message, client, skills)
  ↓ deepseek-v4-flash / GLM-4.7-Flash (temperature=0)
  ↓
{matched_skill: "xxx", confidence: 0.95, keywords: [...]}
  ↓
confidence >= 0.5 → 加载 Skills/{name}/SKILL.md → 注入 System Prompt
```

### 12.4 技能注册流程

```
无匹配技能 → AI 询问用户是否创建
  ↓ 用户同意
propose_skill → generate_skill_proposal() → 生成 SKILL.md 草案 → 展示
  ↓ 用户确认
register_skill(confirmed=true)
  ├── 创建 Skills/{name}/ 目录
  ├── 写入 SKILL.md
  ├── 更新 manifest.json
  └── sync_readme() 刷新 README.md 技能表
```

---

## 13. 模型架构

| 角色 | 模型 | 用途 |
|------|------|------|
| 主脑 | DeepSeek (deepseek-chat) | 对话推理、工具调用、代码执行 |
| 眼睛 | Qwen-VL-Plus | 课表截图 OCR、图片内容识别 |
| 意图分类 | DeepSeek / GLM-4.7-Flash | 前置轻量分类（temperature=0） |

---

## 14. 内网穿透

```
expose(user_id, port, file_path, content)
  ↓
_find_tunnel_provider() → "cpolar" / "ngrok" / None
  ↓
启动 http.server（如未监听）
  ↓
启动隧道（cpolar: 解析日志提取 URL / ngrok: API 轮询）
  ↓
返回公网链接
```

cpolar 优先（国内稳定），ngrok 降级，30s 超时。

---

## 15. 消息触发规则

| 条件 | 行为 |
|------|------|
| 被 @ | 直接入队处理 |
| 消息含关键词 | 入队处理 |
| 自己的消息（以 PREFIX 开头） | 过滤，防循环 |
| 图片消息 | 走视觉识别链路 |
| 其他消息 | 忽略 |

---

## 16. 启动与停止

```powershell
# 启动
.\venv\Scripts\python.exe wx4py_bridge.py

# 停止
Ctrl+C → 贾维斯下班 → 恢复系统休眠策略
```

启动后自动：
1. 连接已登录微信
2. 预打开群聊窗口（GROUPS 列表）
3. 启动 UIA 监听线程（最小化窗口静默恢复，30s 冷却）
4. 启动后台处理线程
5. 启动定时任务调度器

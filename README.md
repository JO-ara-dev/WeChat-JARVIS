# 微信贾维斯 (WeChat J.A.R.V.I.S)

> 基于 wx4py + DeepSeek 的微信群聊 AI Agent，支持多 Agent 协作、课表管理、DDL 追踪、图片识别、自我进化。

## 核心特点

* **多 Agent 协作**：6 个子 Agent（code-executor / web-designer / researcher / course-manager / vision-analyst / system-admin）并行分工，Swarm 引擎自动编排任务、Agent 间可直接 REQUEST/RESULT 通信。
* **Self-Harness 自进化**：Plan→Confirm→Act→Verify→Reflect 闭环 + HarnessGuard 死循环防护。失败自动修复，重复调用 3 次自动阻断，成功方案沉淀为可复用 Pipeline。
* **自动造工具**：遇到不会的任务，AI 自行分析、生成方案、创建新技能，无需人工编码。
* **自我反思**：任务完成后自动总结得失，evolve_pipeline 存档供下次复用。
* **自定义人设**：可以自己取名字（默认"贾维斯"），称呼用户为"老大"。

> ⚠️ **缺点**：DeepSeek 模型推理链较长，非简单查询的响应时间约 2~5 分钟。适合异步场景（群聊丢一个任务，回头来看结果）。

---

## 模型架构（经济双模）

出于成本考虑，采用**纯文本模型 + 多模态模型**搭配策略：

| 角色 | 模型 | 用途 | 费用 |
|------|------|------|------|
| 🧠 大脑 | DeepSeek (deepseek-chat/v4-pro/v4-flash) | 对话推理、工具调用、代码执行 | 极低 |
| 🧠 备选大脑 | 智谱 GLM (BigModel.cn) | 国产替代，网络更稳定 | 中等 |
| 👁️ 眼睛 | 阿里云 Qwen-VL-Plus | 课表截图 OCR、图片内容识别 | 按量 |

> 💡 通过 `agent_config.json` 可在 DeepSeek / 智谱 / 阿里三家 API 间无缝切换，无需改代码。

---

## Agent Swarm 架构

复杂任务自动拆解为子任务，由 6 个专业化子 Agent 并行执行：

```
用户消息
  ↓
主 Agent（大脑）拆解任务
  ↓
┌──────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│  code-   │   web-   │ resear-  │ course-  │ vision-  │ system-  │
│ executor │ designer │  cher    │ manager  │ analyst  │  admin   │
│ 写代码    │ 做网页   │ 搜资料   │ 管课表   │ 识图片   │ 管环境   │
└──────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
  ↓ 各Agent并行执行，Agent间可 [REQUEST:agent] 消息求助
Swarm 汇总结果 → 组装最终回复
```

| 子 Agent | 模型 | 负责 |
|----------|------|------|
| `code-executor` | deepseek-v4-pro | 代码编写、运行、命令执行 |
| `web-designer` | deepseek-v4-pro | 网页设计、内网穿透分享 |
| `researcher` | deepseek-chat | 联网搜索、信息收集分析 |
| `course-manager` | deepseek-chat | 课表查询、作业管理 |
| `vision-analyst` | qwen-vl-plus | 图片 OCR、课表截图识别 |
| `system-admin` | deepseek-chat | 环境搭建、服务部署 |
| `exam-reminder` | deepseek-chat | 考试日期追踪、考前提醒 |
| `parallel-doc-generator` | deepseek-v4-pro | 多 Agent 并行生成复杂文档 |

---

## 核心能力

* **课表管理**：查询、添加、删除课程，自动识别当前教学周并过滤。
* **作业追踪**：记录 DDL，支持个人与全局双作用域查询。
* **图片 OCR**：基于图片预处理（降噪、增强对比度等）与 Qwen-VL 提取文字，自动解析意图入库。
* **联网搜索**：整合 Bing web_search 实时检索能力。
* **内网穿透**：通过 expose 工具（http.server + ngrok），一键将本地文件或页面生成公网链接分享。
* **代码执行**：提供安全沙箱 Python 代码执行能力及需确认的系统命令运行环境。
* **技能系统**：AI 自动注册新技能到 `Skills/` 目录并更新 `manifest.json`，下次同类任务直接复用。
* **向量长期记忆**：ChromaDB 向量数据库 + Sentence Transformer 语义检索，AI 自动保存用户偏好/DDL/报错经验，下次对话自动回忆。
* **每日早报**：每天早 08:00 自动推送（今日课程 + 临近 DDL + 天气 + LLM 口语化）。
* **Web 仪表盘**：`http://127.0.0.1:9021` — FastAPI 后端 + WebSocket 实时日志 + ECharts 可视化。
* **Self-Harness 防护**：HarnessGuard 监控工具调用频率，同一参数连续重复 3 次自动阻断，防止死循环。

---

## 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 微信连接 | wx4py (WeChatClient) | 纯 Python，无需 DLL 注入 |
| AI 大脑 | DeepSeek (deepseek-chat/v4-pro/v4-flash) | 函数调用 + 深度思考 |
| 视觉识别 | 阿里云 Qwen-VL-Plus (DashScope) | 课表图片 OCR |
| 数据库 | SQLite3 (data/butler.db) | 本地持久化 |

---

## 快速开始

1.  **安装依赖**：`pip install -r requirements.txt`。
2.  **配置环境变量**：复制模板并填入自己的 Key，命令为 `cp .env.example .env`。
3.  **初始化数据库**：运行 `sqlite3 data/butler.db < schema.sql`。
4.  **启动项目**：执行 `.\run_bridge.ps1` 一键启动，或手动运行 `.\venv\Scripts\python.exe wx4py_bridge.py`。

---

## 环境变量 (.env)

| 变量 | 说明 | 必填 |
|------|------|------|
| DEEPSEEK_API_KEY | DeepSeek API 密钥（纯文本大脑） | 是 |
| DEEPSEEK_API_BASE | DeepSeek 接口地址 | 否（默认官方） |
| ZHIPU_API_KEY | 智谱 GLM API 密钥（备选纯文本大脑） | 否 |
| DASHSCOPE_API_KEY | 多模态图片大模型密钥（阿里云 DashScope） | 否 |
| DB_PATH | 数据库文件路径 | 否（默认 ./data/butler.db） |
| TUNNEL_PROVIDER | 内网穿透工具：auto/cpolar/ngrok | 否（默认 auto） |
| CRAWLER_USERNAME | 教务系统登录用户名 | 否（爬虫用） |
| CRAWLER_PASSWORD | 教务系统登录密码 | 否（爬虫用） |
| CRAWLER_LOGIN_URL | 教务系统登录页 URL | 否（爬虫用） |

---

## 项目结构

```
.
├── wx4py_bridge.py              # 消息桥接入 口
├── dorm_butler/                 # 核心 Agent 模块
│   ├── butler_agent.py          # 主对话逻辑
│   ├── tools.py                 # 工具集（24个工具）
│   ├── memory.py                # 记忆系统 + run_code
│   ├── skill_manager.py         # 技能注册
│   ├── agent_swarm.py           # 多 Agent 协作引擎
│   ├── sub_agent.py             # SubAgent 执行器
│   ├── agent_manager.py         # Agent 配置管理器（三合一客户端）
│   ├── agent_config.json         # Agent 配置中心（热更新）
│   ├── agents.json              # 子 Agent 定义
│   ├── harness_guard.py         # 死循环防护
│   ├── morning_report.py        # 每日早报
│   └── vision_processor.py      # 双 AI 视觉链路
├── dashboard/                   # Web 仪表盘（FastAPI + WebSocket）
│   ├── server.py                # API 端点 + 静态文件
│   ├── log_bridge.py            # 实时日志广播
│   └── static/index.html        # 前端（ECharts + Mermaid）
├── Skills/                      # 技能目录（Agent 自进化产物）
├── crawler.py                   # 教务系统爬虫
├── schema.sql                   # 数据库建表语句
├── CHANGELOG.md                 # 更新日志
└── .env.example                 # 环境变量模板
```

---

## 交互说明

Agent 通过自然语言交互，无需特定指令格式。在群聊中满足以下条件将被触发：
* **被 @ 提及**：直接进入处理队列。
* **命中关键词**：消息包含课表、作业、课程、这门课、DDL、ddl 等关键词。
* **防循环机制**：以"贾维斯"开头的自身消息会被过滤。

---

## 安全提醒

* **微信风控**：强烈建议使用微信小号运行，控制回复频率，避免主号被封禁。
* **隐私与安全**：`.env` 文件已在 `.gitignore` 中排除，切勿将真实 API 密钥提交至版本库。
* **文件权限**：`self_update` 工具具备自动备份与用户确认机制，并严格限制修改范围为 `dorm_butler/` 和根目录的 `.py` 文件。

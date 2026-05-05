# 微信贾维斯 (WeChat J.A.R.V.I.S)

> 基于 wx4py + DeepSeek 的微信群聊 AI Agent，支持课表管理、DDL 追踪、图片识别、自我进化。

## 核心特点

* **自进化**：真正的 Plan→Act→Verify→Reflect 闭环。失败时自动修复，成功后沉淀为可复用 Pipeline。
* **自动造工具**：遇到不会的任务，AI 自行分析、生成方案、创建新技能，无需人工编码。
* **自我反思**：任务完成后自动总结得失，evolve_pipeline 存档供下次复用。
* **自定义人设**：可以自己取名字（默认"贾维斯"），称呼用户为"老大"。

> ⚠️ **缺点**：DeepSeek 模型推理链较长，非简单查询的响应时间约 2~5 分钟。适合异步场景（群聊丢一个任务，回头来看结果）。

---

## 模型架构（经济双模）

出于成本考虑，采用**纯文本模型 + 多模态模型**搭配策略：

| 角色 | 模型 | 用途 | 费用 |
|------|------|------|------|
| 🧠 大脑 | DeepSeek (deepseek-chat) | 对话推理、工具调用、代码执行、技能生成 | 极低 |
| 👁️ 眼睛 | 阿里云 Qwen-VL-Plus | 课表截图 OCR、图片内容识别 | 按量 |

纯文本模型当大脑负责思考决策，多模态模型当眼睛负责"看"图片。两者按需调用，不浪费 token。

---

## 核心能力

* **课表管理**：查询、添加、删除课程，自动识别当前教学周并过滤。
* **作业追踪**：记录 DDL，支持个人与全局双作用域查询。
* **图片 OCR**：基于图片预处理（降噪、增强对比度等）与 Qwen-VL 提取文字，自动解析意图入库。
* **联网搜索**：整合 Bing web_search 实时检索能力。
* **内网穿透**：通过 expose 工具（http.server + ngrok），一键将本地文件或页面生成公网链接分享。
* **代码执行**：提供安全沙箱 Python 代码执行能力及需确认的系统命令运行环境。
* **技能系统**：AI 自动注册新技能到 `Skills/` 目录并更新 `manifest.json`，下次同类任务直接复用。

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
| DASHSCOPE_API_KEY | 多模态图片大模型密钥（阿里云 DashScope） | 否（图片识别用） |
| TUNNEL_PROVIDER | 内网穿透工具：auto/cpolar/ngrok | 否（默认 auto） |
| CRAWLER_USERNAME | 教务系统登录用户名 | 否（爬虫用） |
| CRAWLER_PASSWORD | 教务系统登录密码 | 否（爬虫用） |
| CRAWLER_LOGIN_URL | 教务系统登录页 URL | 否（爬虫用） |

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

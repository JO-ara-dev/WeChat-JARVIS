# 微信贾维斯 - 项目开发文档

## 1. 项目概述

- **项目名称**: 微信贾维斯 / J.A.R.V.I.S
- **项目类型**: 微信群聊 AI Agent
- **核心框架**: wx4py (纯 Python WeChatClient，无需 DLL 注入)
- **AI 引擎**: DeepSeek (deepseek-chat) + 阿里云 Qwen-VL-Plus
- **数据库**: SQLite (data/butler.db)
- **运行入口**: `venv\Scripts\python.exe wx4py_bridge.py`

## 2. 启动方式

```powershell
# 使用 run_bridge.ps1 一键启动
.\run_bridge.ps1

# 或手动启动
.\venv\Scripts\python.exe wx4py_bridge.py
```

启动后：
1. wx4py 自动连接已登录的微信
2. 监听指定群聊（GROUPS 列表配置）
3. 被 @ 或含关键词的消息自动触发 Agent 处理

## 3. 已实现功能

### Agent 核心能力
- [x] DeepSeek 函数调用（工具链 24 个工具）
- [x] 对话上下文（最近 20 轮记忆）
- [x] 用户画像（Agent 自动记录用户偏好）
- [x] Harness 自进化 Pipeline（Plan→Confirm→Act→Verify→Reflect）
- [x] 深度思考模式（fast/deep/auto 三档 think 工具）
- [x] run_code 安全沙箱（Python 代码执行）
- [x] run_cmd 系统命令（需确认）
- [x] 联网搜索（Bing web_search）

### 课表管理
- [x] 查询课表（今天/明天/周几/全部，自动过滤当前周）
- [x] 批量添加课程
- [x] 删除课程
- [x] 学期起始日期配置

### 作业/DDL 管理
- [x] 查询待完成作业
- [x] 添加作业（含 DDL）
- [x] 删除作业
- [x] 个人/全局双作用域 (private / public)

### 视觉识别
- [x] 图片预处理（降噪/增强对比度/锐化）
- [x] Qwen-VL-Plus OCR 提取文字
- [x] DeepSeek 意图分析 → JSON
- [x] 待确认队列（pending_actions 表）

### 教务网爬虫
- [x] Playwright + Edge 浏览器自动化
- [x] 登录页 → 手动登录 → 自动检测课表页
- [x] HTML 解析 → courses 表
- [x] 实践环节识别（不入库，仅提示）

### 内网穿透
- [x] expose 工具：http.server + cpolar/ngrok
- [x] 公网链接分享文件/HTML
- [x] 自动添加手机端 viewport 适配

### 自我更新
- [x] self_update 工具（修改自身源码）
- [x] 自动备份到 backups/ 目录
- [x] 需用户确认 + 最高模型深度思考

### 技能系统
- [x] propose_skill / register_skill 自动创建新技能
- [x] manifest.json 结构化技能索引
- [x] 前置意图分类自动匹配技能

## 4. 指令说明

Agent 通过自然语言交互，无需特定指令格式。常用交互：

| 用户说 | Agent 行为 |
|--------|-----------|
| "今天有什么课" | 自动查课表并回复 |
| "周一有什么课" | 查指定星期课程 |
| "帮我记一个作业" | 调用 add_task |
| "最近有什么作业" | 查询待完成作业 |
| "识别这张图片" | 走视觉识别链路 |
| "搜索一下xxx" | web_search 联网搜索 |
| "把这个网页发给我" | expose 内网穿透 |
| "确认更新" | 执行 self_update |

## 5. 消息触发规则

| 条件 | 行为 |
|------|------|
| 被 @ | 直接进入处理队列 |
| 消息包含关键词（课表/作业/课程/这门课/DDL/ddl） | 进入处理队列 |
| 自己的消息（以"贾维斯"开头） | 过滤，防止循环 |
| 其他消息 | 忽略 |

## 6. 数据库表

```
courses          - 课表
tasks            - 作业/DDL（含 creator_id/creator_nickname/scope）
config           - 配置 + Pipeline 缓存
pending_actions  - 待确认操作
users            - 用户注册（user_id + 昵称）
chat_history     - 对话历史（含 session_id）
user_memory      - 用户画像
```

完整建表语句见 `schema.sql`

## 7. 环境变量配置 (.env)

```
# DeepSeek（纯文本大脑）
DEEPSEEK_API_KEY=your_deepseek_key
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# 多模态图片大模型
DASHSCOPE_API_KEY=your_dashscope_key

# 数据库
DB_PATH=./data/butler.db

# 内网穿透
TUNNEL_PROVIDER=auto

# 教务爬虫（可选）
CRAWLER_LOGIN_URL=
CRAWLER_USERNAME=
CRAWLER_PASSWORD=
```

模板文件见 `.env.example`

## 8. 项目结构

```
.
├── wx4py_bridge.py          # 机器人入口
├── run_bridge.ps1            # 启动脚本
├── .env.example              # 环境变量模板
├── requirements.txt          # Python 依赖
├── schema.sql                # 数据库建表语句
├── crawler.py                # 教务网爬虫
├── check_memory.py           # 记忆调试
├── db_manager.py             # 根目录数据库（crawler 依赖）
├── dorm_butler/              # 核心模块
│   ├── butler_agent.py       # Agent 主逻辑
│   ├── db_manager.py         # 数据库 CRUD
│   ├── memory.py             # 记忆系统 + run_code
│   ├── tools.py              # 24个工具定义
│   ├── skill_manager.py      # 技能管理
│   ├── scheduler.py          # 定时任务
│   ├── sessions.py           # 会话管理
│   └── vision_processor.py   # 视觉识别链路
├── Skills/                   # 技能目录
├── backups/                  # 自动备份
└── data/
    ├── butler.db
    └── temp_*.png
```

## 9. 注意事项

### 安全
- .env 不要提交到 Git（已在 .gitignore）
- API Key 不要硬编码在代码中
- self_update 工具有安全限制（文件路径/类型 + 自动备份 + 确认机制）

### 微信风控
- 机器人账号使用小号，避免主号被封
- 控制回复频率，不过度刷屏
- wx4py 是纯 Python 方案，不会触发杀毒软件

### 网络
- 内网穿透依赖 cpolar 或 ngrok 需要手动安装并加入 PATH
- 教务网爬虫需要系统安装 Edge 浏览器
- DashScope 和 DeepSeek API 需要稳定网络连接

# 微信贾维斯 — 模块调用手册

> 本文档按「主程序入口 → 模块 → 函数 API」组织，供 AI 自进化（self_update）和开发者查阅。
> 每个函数均标注完整签名、返回类型，AI 可按需调用。

---

## 1. 主程序入口：wx4py_bridge.py

```
启动
  ↓
wx4py WeChatClient 连接微信
  ↓
ButlerHandler 监听群聊（GROUPS 列表配置）
  ├── 被 @ → 入队
  ├── 含关键词 → 入队
  └── 自己的消息 → 过滤
  ↓
msg_queue → process_worker 线程
  ↓
butler_agent.chat(content, user_id=group) → 生成回复
  ↓
action_emitter → 发送回群聊
```

### 全局配置

| 变量 | 值 | 说明 |
|------|-----|------|
| `GROUPS` | `["测试"]` | 监听群聊列表 |
| `GROUP_NICKNAMES` | `{"测试": "贾维斯"}` | 群内机器人昵称 |
| `PREFIX` | `"J.A.R.V.I.S "` | 回复前缀 |

### 消息触发规则

| 条件 | 行为 |
|------|------|
| 被 @ | 入队处理 |
| 含关键词：课表/作业/课程/DDL/ddl/贾维斯/jarvis | 入队处理 |
| 自己的消息（以 PREFIX 开头） | 过滤 |
| 含图片标记 | 走视觉识别链路 |

### 启动命令

```powershell
.\run_bridge.ps1
# 或
.\venv\Scripts\python.exe wx4py_bridge.py
```

---

## 2. butler_agent.py — Agent 主控

| 函数 | 签名 | 返回 | 说明 |
|------|------|------|------|
| `chat` | `(user_message: str, user_id: str = "default", image_text: str = None, progress_callback=None)` | generator→str | **主对话入口**：注册用户 → 意图分类 → 加载技能 → 构建 system prompt → LLM 工具调用循环 → 压缩/重试 → yield 最终回复 |
| `_execute_tool` | `(tool_name: str, arguments: dict, user_id: str, progress_callback=None)` | `str` | 工具分发执行：guard 检查 → 执行 → 最多 3 次重试 → 返回 JSON |
| `_classify_intent` | `(user_message: str)` | `dict` | 前置意图分类调用 → `{matched_skill, confidence, keywords}` |
| `_build_system_prompt` | `(user_id: str, skill_instructions: str = "", skill_name: str = "")` | `str` | 组装完整 system prompt（含用户画像、当前时间/周次、技能指令） |

---

## 3. tools.py — 工具集

> 每个工具函数返回 `{"success": bool, "data": ..., "message": str}`
> 注册位置：`TOOLS_SCHEMA`(schema) + `TOOLS_MAP`(分发表)

### 3.1 任务规划

| 函数 | 参数 | 说明 |
|------|------|------|
| `plan_task` | `user_id, task_description` | 分解任务为步骤列表 |
| `update_todo` | `user_id, step_id, status` | 更新步骤状态（pending/in_progress/completed/cancelled） |
| `get_todos` | `user_id` | 查看任务进度 |
| `reflect` | `user_id, summary` | 任务完成总结 |

### 3.2 自进化

| 函数 | 参数 | 说明 |
|------|------|------|
| `self_heal` | `user_id, error_context` | 失败自动分析修复建议 |
| `evolve_pipeline` | `user_id, task_type, solution, tools_used` | 注册成功 Pipeline 到 config 表 |
| `reuse_pipeline` | `user_id, task_type` | 查询复用已有 Pipeline |
| `self_update` | `user_id, file_path, old_code, new_code, reason, confirmed=False` | 修改自身源码（首次备份+请求确认，confirmed=True 才写入） |

### 3.3 课表 & 作业

| 函数 | 参数 | 说明 |
|------|------|------|
| `query_courses` | `weekday=None` | 查询课表（按天/全部，自动过滤当前周） |
| `add_courses` | `courses: list` | 批量添加课程 |
| `delete_courses` | `weekday=None` | 删除课程（按天/全部） |
| `query_tasks` | `user_id=""` | 查询待完成作业（private+public） |
| `add_task` | `user_id, content, ddl=None, scope="private"` | 添加作业 |
| `delete_task` | `user_id, task_id` | 删除作业 |

### 3.4 用户管理

| 函数 | 参数 | 说明 |
|------|------|------|
| `identify_me` | `user_id, nickname` | 注册"我是 XXX" |
| `set_nickname` | `user_id, nickname` | 设置用户昵称 |
| `resolve_user` | `identifier` | 通过昵称/user_id 查找用户 |

### 3.5 通用能力

| 函数 | 参数 | 说明 |
|------|------|------|
| `web_search` | `query` | Bing 联网搜索，返回 5 条结果 |
| `read_file` | `file_path, limit=None, offset=0` | 读取项目内文件，支持分页 |
| `write_file` | `file_path, content` | 写入项目内文件，自动创建目录 |
| `list_files` | `dir_path="."` | 列出目录内容 |
| `create_tool` | `tool_name, tool_code, tool_description` | 动态注册新工具 |
| `run_cmd` | `user_id, command, description, confirmed=False, background=False` | 执行 Windows 命令（危险命令黑名单拦截） |
| `think` | `question, mode="auto"` | 深度思考（fast/deep/auto） |
| `expose` | `user_id, port=8765, file_path=None, content=None, mobile_fix=True` | 一键内网穿透：启动 http.server + cpolar/ngrok，返回公网 URL |

### 3.6 技能管理

| 函数 | 参数 | 说明 |
|------|------|------|
| `propose_skill` | `user_id, intent_description, user_message=""` | AI 生成 SKILL.md 草案 |
| `register_skill` | `user_id, name, skill_md_content, confirmed=False` | 确认后注册技能（创建目录+写入+更新 manifest） |

### 3.7 多 Agent 协作

| 函数 | 参数 | 说明 |
|------|------|------|
| `delegate_task` | `user_id, agent_name, task_description, context="", progress_callback=None` | 派发异步任务给子 Agent |
| `get_pending_result` | `user_id` | 非阻塞获取子 Agent 结果 |
| `swarm_execute` | `user_id, workflow_json="", progress_callback=None` | 并行多 Agent 工作流编排 |
| `list_agents` | `user_id=""` | 列出子 Agent 状态 |

### 3.8 公共辅助函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `get_current_week` | `() → int` | 计算当前教学周次（基于 semester_start 配置） |
| `is_course_in_week` | `(course: dict, week: int) → bool` | 判断课程 weeks 字段是否覆盖指定周 |

---

## 4. db_manager.py — 数据库 CRUD 层

> 数据库路径：`data/butler.db`（SQLite）

### 4.1 初始化

| 函数 | 签名 | 说明 |
|------|------|------|
| `init_db` | `() → None` | 建表 + 默认配置 + 迁移 |
| `get_conn` | `() → Connection` | 获取 SQLite 连接 |

### 4.2 课程 (courses 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `add_course` | `(name, week_day, start_node, end_node, location="", weeks="1-16") → int` | 添加课程，返回 ID |
| `get_course` | `(course_id) → Optional[dict]` | 按 ID 查课程 |
| `get_all_courses` | `() → list[dict]` | 全部课程（按周几+节次排序） |
| `get_courses_by_weekday` | `(week_day) → list[dict]` | 指定 weekday 课程 |
| `update_course` | `(course_id, **kwargs) → bool` | 更新课程字段 |
| `delete_course` | `(course_id) → bool` | 删除课程 |
| `clear_all_courses` | `() → int` | 清空全部课程 |

### 4.3 作业 (tasks 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `add_task` | `(content, ddl=None, course_id=None, creator_id="", creator_nickname="", scope="private") → int` | 添加作业 |
| `get_task` | `(task_id) → Optional[dict]` | 按 ID 查作业 |
| `get_pending_tasks` | `(user_id=None) → list[dict]` | 未完成作业（按 user_id 过滤 scope） |
| `get_tasks_by_course` | `(course_id) → list[dict]` | 某课程关联作业 |
| `get_due_tasks` | `(hours) → list[dict]` | N 小时内到期作业 |
| `get_overdue_tasks` | `() → list[dict]` | 已过期未完成作业 |
| `complete_task` | `(task_id) → bool` | 标记完成 |
| `update_task` | `(task_id, **kwargs) → bool` | 更新作业字段 |
| `delete_task` | `(task_id, user_id=None) → bool` | 删除作业（user_id 传则校验权限） |

### 4.4 配置 (config 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `get_config` | `(key) → Optional[str]` | 读取配置 |
| `set_config` | `(key, value) → None` | 写入配置 |
| `get_all_config` | `() → dict[str,str]` | 全部配置 |

### 4.5 待确认操作 (pending_actions 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `add_pending` | `(user_id, intent, data_json, confidence=0.0) → int` | 添加待确认 |
| `get_pending` | `(pending_id) → Optional[dict]` | 查询单个 |
| `get_all_pending` | `() → list[dict]` | 全部待确认 |
| `confirm_pending` | `(pending_id) → bool` | 确认 |
| `cancel_pending` | `(pending_id) → bool` | 取消 |
| `gc_pending` | `(hours=24) → int` | 清理过期记录 |

### 4.6 用户 (users 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `register_user` | `(user_id, nickname="", platform="wechat") → bool` | 注册/更新用户 |
| `set_nickname` | `(user_id, nickname) → bool` | 设置昵称 |
| `get_user_by_id` | `(user_id) → Optional[dict]` | 按 ID 查 |
| `get_user_by_nickname` | `(nickname) → Optional[dict]` | 按昵称精确查 |
| `search_users_by_nickname` | `(keyword) → list[dict]` | 模糊搜索 |
| `resolve_user_id` | `(identifier) → Optional[str]` | 昵称/ID→user_id |
| `get_all_users` | `() → list[dict]` | 全部用户 |

---

## 5. memory.py — 记忆系统

### 5.1 对话历史 (chat_history 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `init_memory_tables` | `() → None` | 建表 |
| `add_message` | `(user_id, role, content) → None` | 写入一条对话（自动绑定当前 session） |
| `get_history` | `(user_id, limit=20) → list[dict]` | 当前会话最近 N 条（正序） |
| `get_session_history` | `(user_id, session_id, limit=50) → list[dict]` | 指定会话历史 |
| `clear_history` | `(user_id) → None` | 清空用户全部对话 |

### 5.2 用户画像 (user_memory 表)

| 函数 | 签名 | 说明 |
|------|------|------|
| `save_memory` | `(user_id, key, value, scope="private") → None` | 保存用户记忆 |
| `get_memory` | `(user_id, key=None, include_public=False) → list[dict]` | 查询记忆 |
| `delete_memory` | `(user_id, key) → None` | 删除记忆 |

### 5.3 工具封装（TOOLS_MAP 中的实现）

| 函数 | 签名 | 说明 |
|------|------|------|
| `_save_memory` | `(user_id, key, value, scope="private") → dict` | save_memory 工具封装 |
| `_get_memory` | `(user_id, key=None, include_public=False) → dict` | get_memory 工具封装 |
| `_delete_memory` | `(user_id, key) → dict` | delete_memory 工具封装 |
| `_run_code` | `(user_id, code) → dict` | Python 代码沙箱执行（安全限制 + stdout/stderr 捕获） |

---

## 6. sessions.py — 多会话管理

| 函数 | 签名 | 说明 |
|------|------|------|
| `init_sessions_table` | `() → None` | 建表 + 迁移 |
| `get_current_session` | `(user_id) → int` | 获取/创建当前活跃会话 ID |
| `archive_session` | `(user_id) → dict` | 归档当前会话（AI 摘要）并创建新会话 |
| `list_sessions` | `(user_id) → list[dict]` | 列出最近 20 个会话 |
| `switch_session` | `(user_id, session_id) → dict` | 切换到指定会话 |
| `get_session_summary` | `(user_id) → str` | AI 生成当前会话一句话摘要 |
| `increment_message_count` | `(user_id) → None` | 消息计数 +1 |

---

## 7. vision_processor.py — 视觉识别

| 函数 | 签名 | 说明 |
|------|------|------|
| `preprocess_image` | `(image_path) → str` | Pillow 图片增强（对比度+60%/锐度+120%/亮度+10%/去噪），返回处理后路径 |
| `ocr_with_wanx` | `(image_path) → str` | 阿里云 Qwen-VL-Plus OCR 提取文字 |
| `analyze_with_deepseek` | `(text) → dict` | DeepSeek 分析 OCR 结果 → 意图分类 + JSON |
| `process_image` | `(image_path, user_id="unknown") → dict` | **完整视觉链路**：预处理→OCR→分析→存入 pending_actions |

---

## 8. skill_manager.py — 技能系统

| 函数 | 签名 | 说明 |
|------|------|------|
| `load_manifest` | `() → list[dict]` | 加载 Skills/manifest.json |
| `classify_intent` | `(user_message, client, skills=None, model="GLM-4.7-Flash") → dict` | LLM 意图分类 → `{matched_skill, confidence, keywords}` |
| `load_skill_instructions` | `(skill_name) → str` | 读取 Skills/{name}/SKILL.md |
| `get_skill_by_name` | `(name) → Optional[dict]` | 按名查技能 |
| `generate_skill_proposal` | `(intent_desc, user_message, client) → str` | AI 生成 SKILL.md 草案 |
| `register_skill` | `(name, skill_md_content) → dict` | 创建目录→写 SKILL.md→更新 manifest.json→同步 README |
| `sync_readme` | `() → None` | 刷新 Skills/README.md 技能表 |

---

## 9. agent_swarm.py — 多 Agent 协作引擎

### 模块级函数

| 函数 | 签名 | 说明 |
|------|------|------|
| `send_message` | `(from_agent, to_agent, content) → None` | Agent 间消息传递 |
| `check_messages` | `(agent_name) → list[dict]` | 获取并清空收件箱 |
| `clear_all_messages` | `() → None` | 清空消息队列 |
| `register_task` | `(key) → None` | 注册异步任务槽 |
| `set_task_result` | `(key, result) → None` | 写入任务结果 |
| `wait_task` | `(key, timeout=300) → Optional[dict]` | 阻塞等待结果 |
| `get_task_result` | `(key) → Optional[dict]` | 非阻塞查结果 |
| `pop_task_result` | `(key) → Optional[dict]` | 取走并删除结果 |

### AgentSwarm 类

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(user_id)` | 初始化编排器 |
| `add_task` | `(task_id, agent_name, task_description) → None` | 添加任务 |
| `launch_parallel` | `(progress_callback=None) → dict` | **并行执行**：多线程启动→等待→Agent 间 REQUEST/RESULT→汇总结果 |

---

## 10. sub_agent.py — 子 Agent 执行器

| 函数 | 签名 | 说明 |
|------|------|------|
| `init_agent_states` | `() → None` | 初始化所有子 Agent 状态 |
| `load_agents` | `() → list[dict]` | 加载 agent_config.json |
| `match_agent` | `(keywords, user_message) → Optional[dict]` | 关键词匹配子 Agent |
| `review_result` | `(client, task, sub_output) → Optional[str]` | AI 审核子 Agent 输出（PASS→None / FAIL→原因） |

### SubAgent 类

| 方法 | 签名 | 说明 |
|------|------|------|
| `__init__` | `(name, config, user_id)` | 初始化（模型+工具+客户端） |
| `execute` | `(task, context="") → dict` | 执行任务（max_turns 循环）→ `{success, output, tools_used}` |

---

## 11. harness_guard.py — 死循环防护

| 函数 | 签名 | 说明 |
|------|------|------|
| `before_tool` | `(user_id, tool_name, args) → Optional[str]` | 调用前检查：同工具+同参数≥3次连续调用→阻断，返回原因 |
| `after_tool` | `(user_id, tool_name, args) → None` | 调用后记录（工具名+哈希参数+时间戳） |
| `clear_user` | `(user_id) → None` | 清除用户调用历史（新对话开始时调用） |

---

## 12. scheduler.py — 定时任务

| 函数 | 签名 | 说明 |
|------|------|------|
| `start_scheduler` | `() → None` | 启动 APScheduler 后台（每晚 22:00 课程+考试提醒） |
| `stop_scheduler` | `() → None` | 停止调度器 |

---

## 13. 如何新增功能（AI 自进化操作指南）

当需要扩展新能力时，按以下步骤操作：

### Step 1：加工具函数
在 `dorm_butler/tools.py` 中：
1. 编写函数，返回 `{"success": bool, "data": ..., "message": str}`
2. 在 `TOOLS_SCHEMA` 列表末尾添加 OpenAI function calling schema
3. 在 `TOOLS_MAP` 字典中添加 `"function_name": function_name`

```python
# 示例：新增一个 say_hello 工具
def say_hello(user_id: str, name: str) -> dict:
    return {"success": True, "data": {"greeting": f"你好 {name}"}, "message": "ok"}

# 注册到 TOOLS_SCHEMA
TOOLS_SCHEMA.append({
    "type": "function",
    "function": {
        "name": "say_hello",
        "description": "向指定用户打招呼",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "name": {"type": "string"}
            },
            "required": ["user_id", "name"]
        }
    }
})

# 注册到 TOOLS_MAP
TOOLS_MAP["say_hello"] = say_hello
```

### Step 2（可选）：加数据库表
在 `dorm_butler/db_manager.py` 的 `init_db()` 中加 `CREATE TABLE IF NOT EXISTS`，然后添加对应 CRUD 函数。

### Step 3（可选）：加技能
1. 调用 `skill_manager.register_skill(name, content)` 创建技能
2. 或让 AI 用 `propose_skill` 生成草案，用户确认后 `register_skill`

### Step 4：更新本文档
在对应的模块章节下新增函数条目，保持参数签名完整。

---

## 14. 常量字典（供 Agent 调用时参考）

| 字段 | 含义 | 可选值 |
|------|------|--------|
| `week_day` | 星期 | 1=周一 ~ 7=周日 |
| `start_node / end_node` | 节次 | 1~8，成对：1-2, 3-4, 5-6, 7-8 |
| `weeks` | 上课周次 | "1-16" 或 "1,3,5-8" |
| `status` (task) | 作业状态 | 0=未完成, 1=已完成 |
| `remind_level` | 提醒等级 | 0=普通, 1=重要, 2=紧急 |
| `scope` | 可见范围 | "private" / "public" |
| `status` (pending) | 确认状态 | "pending" / "confirmed" / "cancelled" |
| `status` (todo step) | 步骤状态 | "pending" / "in_progress" / "completed" / "cancelled" |
| `think mode` | 思考深度 | "fast" / "deep" / "auto" |
| `TUNNEL_PROVIDER` | 内网穿透 | "auto" / "cpolar" / "ngrok" |

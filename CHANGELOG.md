# 更新日志 (Changelog)

## v1.3 (2026-05-05)

### 新增
- **Web 仪表盘** (`dashboard/`) — FastAPI 后端 + WebSocket 实时日志流 + ECharts 可视化 + Mermaid 流程图
- **向量长期记忆** (`VectorMemory`) — 基于 ChromaDB + sentence-transformers，AI 自动保存用户偏好、DDL、报错经验
- `add_vector_memory` 工具 — LLM 主动调用，一句话总结记忆内容并永久保存
- **每日早报** (`morning_report.py`) — 08:00 自动推送（课程 + DDL + 天气 + LLM 口语化）

### 优化
- `scheduler.py`：新增每日 08:00 早报任务 + `schedule_queue` 消息队列
- `butler_agent.py`：向量记忆注入 System Prompt + 仪表盘后台自动启动
- `skill_manager.py`：意图分类增加 Provider 容灾 fallback
- `requirements.txt`：新增 chromadb / sentence-transformers / fastapi / uvicorn

---

## v1.2 (2026-05-05)

### 新增
- **Agent 配置中心** (`agent_config.json` + `agent_manager.py`) — 集中化管理，支持智谱 GLM / DeepSeek / 阿里 DashScope 三家 API 提供商热切换
- **考试提醒技能** (`Skills/exam-reminder/`) — 自动追踪考试日期并提前提醒
- **并行文档生成技能** (`Skills/parallel-doc-generator/`) — 多 SubAgent 并行生成复杂文档
- **CHANGELOG.md** — 本文件

### 优化
- `wx4py_bridge.py` 大幅重构，接口稳定性提升
- SubAgent 模型路由优化，v4-pro / flash / qwen-vl 自动选择
- 定时任务调度器增强
- 会话管理增强，支持多会话上下文隔离
- 工具体系扩充
- researcher 子 Agent 最大轮数由 5 提升至 8

### 修复
- `read_file` 工具支持 `limit`/`offset` 参数分段读取
- Agent 调用未知参数时自动过滤（不再崩溃）
- 意图分类 JSON 解析三级降级策略

### 文档
- `PROJECT.md` / `SPEC.md` 全面重写
- `README.md` 新增 Agent Swarm 架构图
- 技能清单同步更新

---

## v1.0 (2026-05-05)

### 首个公开版本
- 基于 wx4py + DeepSeek 的微信群聊 AI Agent
- 24 个工具（课表、作业、联网搜索、内网穿透、代码执行等）
- Harness 自进化 Pipeline（Plan→Confirm→Act→Verify→Reflect）
- 6 个专业化 SubAgent 并行协作
- HarnessGuard 死循环防护
- 经济双模架构（纯文本大脑 + 多模态图片识别）

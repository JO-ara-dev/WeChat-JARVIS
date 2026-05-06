"""
SubAgent 系统 — 用户可配置的多 Agent 协作
"""
import os
import json
import logging
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).parent.parent
_AGENTS_PATH = _PROJECT_ROOT / "dorm_butler" / "agent_config.json"
load_dotenv(_PROJECT_ROOT / ".env")

# Agent 状态追踪
import time as _time
import threading as _threading
_agent_states: dict[str, dict] = {}
_states_lock = _threading.Lock()


def init_agent_states():
    """从 agents.json 初始化所有 Agent 为空闲"""
    agents = load_agents()
    with _states_lock:
        for a in agents:
            if a["name"] not in _agent_states:
                _agent_states[a["name"]] = {"status": "idle", "task": None, "user_id": None, "description": a.get("description", "")}


def _set_busy(name: str, task: str, user_id: str):
    with _states_lock:
        desc = _agent_states.get(name, {}).get("description", "")
        _agent_states[name] = {"status": "busy", "task": task[:80], "user_id": user_id,
                               "started_at": _time.time(), "description": desc}


def _set_idle(name: str):
    with _states_lock:
        desc = _agent_states.get(name, {}).get("description", "")
        _agent_states[name] = {"status": "idle", "task": None, "user_id": None, "description": desc}


def get_agent_states() -> dict:
    init_agent_states()
    with _states_lock:
        return {name: {"status": s["status"], "task": s.get("task"), "description": s.get("description", "")}
                for name, s in _agent_states.items()}

logger = logging.getLogger("WCF")

SUBAGENT_SYSTEM_PROMPT = (
    "你是 J.A.R.V.I.S 的执行单元。你的唯一任务是完成分配给你的任务，完成后立即返回结果。\n"
    "规则：\n"
    "- 只使用给你的工具，不要调用未提供的工具\n"
    "- 不要闲聊、不要询问、不要计划——只执行\n"
    "- 任务完成后输出最终结果（文件路径、链接、数据等）\n"
    "- 如果工具执行失败，最多重试 2 次然后报告失败\n"
    "- 输出简洁，只包含用户需要的实际内容"
)


def load_agents() -> list[dict]:
    """加载 agent_config.json 中的子Agent定义"""
    if not _AGENTS_PATH.exists():
        logger.warning(f"agent_config.json 不存在: {_AGENTS_PATH}")
        return []
    with open(_AGENTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("sub_agents", [])


def get_defaults() -> dict:
    """获取 agent_config.json 的默认配置"""
    if not _AGENTS_PATH.exists():
        return {"max_turns": 5, "review_model": "GLM-4.7-Flash", "review_provider": "zhipu"}
    with open(_AGENTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("defaults", {"max_turns": 5, "review_model": "GLM-4.7-Flash", "review_provider": "zhipu"})


def match_agent(keywords: list[str], user_message: str) -> dict | None:
    """根据关键词匹配最合适的子Agent，返回 agent 配置或 None"""
    agents = load_agents()
    if not agents:
        return None

    msg_lower = user_message.lower()
    best_match = None
    best_score = 0

    for agent in agents:
        triggers = agent.get("trigger_keywords", [])
        score = sum(1 for kw in triggers if kw.lower() in msg_lower)
        # keywords 权重加分
        for kw in keywords:
            if kw.lower() in msg_lower:
                score += 0.5
        if score > best_score:
            best_score = score
            best_match = agent

    if best_score > 0:
        return best_match
    return None


def _get_tool_schemas(tool_names: list[str]) -> list[dict]:
    """从 tools.py 和 memory.py 中提取指定工具的 schema"""
    from .tools import TOOLS_SCHEMA as BASE_SCHEMA
    from .memory import TOOLS_SCHEMA as MEMORY_SCHEMA

    all_schemas = {}
    for s in BASE_SCHEMA + MEMORY_SCHEMA:
        name = s["function"]["name"]
        all_schemas[name] = s

    result = []
    for name in tool_names:
        if name in all_schemas:
            result.append(all_schemas[name])
    return result


class SubAgent:
    """子Agent执行器：通过 AgentManager 创建对应提供商的客户端，精简 prompt + 专属工具"""

    def __init__(self, name: str, config: dict, user_id: str):
        self.name = name
        self.description = config.get("description", "")
        self.model = config.get("model", "glm-4-flash")
        self.tool_names = config.get("tools", [])
        self.max_turns = config.get("max_turns", 5)
        self.user_id = user_id
        self.provider = config.get("provider", "zhipu")
        self.is_reasoning = "v4-pro" in self.model

        # 通过 AgentManager 创建对应提供商的客户端
        from .agent_manager import AgentManager
        mgr = AgentManager(str(Path(__file__).parent / "agent_config.json"))
        self.client = mgr.create_client(self.provider)

    def execute(self, task: str, context: str = "") -> dict:
        """
        执行任务，返回 {"success": bool, "output": str, "tools_used": int}
        """
        _set_busy(self.name, task, self.user_id)
        try:
            from .tools import TOOLS_MAP as BASE_TOOLS_MAP
            from .memory import TOOLS_MAP as MEMORY_TOOLS_MAP
            from .harness_guard import before_tool, after_tool

            all_tool_map = {**BASE_TOOLS_MAP, **MEMORY_TOOLS_MAP}
            tool_schemas = _get_tool_schemas(self.tool_names)

            system_content = SUBAGENT_SYSTEM_PROMPT + f"\n\n当前任务：{task}\n" + (f"额外上下文：{context}\n" if context else "")

            messages = [{"role": "system", "content": system_content}]
            messages.append({"role": "user", "content": task})

            tools_used = 0
            for _ in range(self.max_turns):
                try:
                    # 根据提供商路由调用参数
                    if self.provider == "deepseek" and self.is_reasoning:
                        call_kwargs = {"max_tokens": 8000}
                    elif self.provider == "zhipu":
                        call_kwargs = {"temperature": 0.3, "max_tokens": 3000, "timeout": 90}
                    elif self.provider == "dashscope":
                        call_kwargs = {"temperature": 0.3, "max_tokens": 3000, "timeout": 90}
                    else:
                        call_kwargs = {"temperature": 0.3, "max_tokens": 3000, "timeout": 90}

                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        tools=tool_schemas if tool_schemas else None,
                        tool_choice="auto" if tool_schemas else "none",
                        **call_kwargs,
                    )
                except Exception as e:
                    logger.error(f"[SubAgent {self.name}] API调用失败: {e}")
                    return {"success": False, "output": f"SubAgent API错误: {e}", "tools_used": tools_used}

                choice = response.choices[0]

                # 推理模型（v4-pro 等）的思考内容在 reasoning_content 字段
                if self.is_reasoning:
                    msg = choice.message
                    content = msg.content or getattr(msg, "reasoning_content", None) or ""

                if choice.finish_reason == "tool_calls":
                    messages.append(choice.message)

                    for tool_call in choice.message.tool_calls:
                        func_name = tool_call.function.name
                        try:
                            func_args = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            func_args = {}

                        # Guard check
                        block = before_tool(self.user_id, func_name, func_args)
                        if block:
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps({"success": False, "message": block}, ensure_ascii=False),
                            })
                            continue

                        try:
                            func = all_tool_map.get(func_name)
                            if not func:
                                result = json.dumps({"success": False, "message": f"未知工具: {func_name}"}, ensure_ascii=False)
                            elif func_name in ("save_memory", "get_memory", "delete_memory", "run_code", "run_cmd", "expose", "plan_task", "update_todo", "get_todos", "reflect", "self_heal", "evolve_pipeline", "reuse_pipeline", "self_update", "propose_skill", "register_skill", "add_task", "query_tasks", "delete_task", "set_nickname", "resolve_user", "identify_me", "delegate_task", "get_pending_result", "swarm_execute", "list_agents"):
                                func_args.pop("user_id", None)
                                result = json.dumps(func(user_id=self.user_id, **func_args), ensure_ascii=False)
                            else:
                                result = json.dumps(func(**func_args), ensure_ascii=False)
                            tools_used += 1
                        except Exception as e:
                            result = json.dumps({"success": False, "message": str(e)}, ensure_ascii=False)

                        after_tool(self.user_id, func_name, func_args)
                        logger.info(f"[SubAgent {self.name}] {func_name}: {result[:100]}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        })
                    continue

                # 模型不再调工具，返回结果
                if self.is_reasoning:
                    msg = choice.message
                    output = msg.content or getattr(msg, "reasoning_content", None) or ""
                else:
                    output = choice.message.content or ""
                return {"success": True, "output": output, "tools_used": tools_used}

            # 达到最大轮数
            try:
                if self.is_reasoning:
                    fkw = {"max_tokens": 4000}
                elif self.provider == "zhipu":
                    fkw = {"temperature": 0.3, "max_tokens": 2000, "timeout": 60}
                elif self.provider == "dashscope":
                    fkw = {"temperature": 0.3, "max_tokens": 2000, "timeout": 60}
                else:
                    fkw = {"temperature": 0.3, "max_tokens": 2000, "timeout": 60}
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages + [{"role": "user", "content": "请总结当前任务的完成情况和结果。"}],
                    **fkw,
                )
                if self.is_reasoning:
                    msg = response.choices[0].message
                    output = msg.content or getattr(msg, "reasoning_content", None) or ""
                else:
                    output = response.choices[0].message.content or ""
                return {"success": True, "output": output, "tools_used": tools_used}
            except Exception:
                return {"success": False, "output": f"SubAgent 达到最大轮数({self.max_turns})，任务未完成", "tools_used": tools_used}
        finally:
            _set_idle(self.name)


def review_result(client: OpenAI, task: str, sub_output: str) -> str | None:
    """
    主Agent审核SubAgent结果。
    返回: None=通过, 或失败原因字符串
    """
    if not sub_output or len(sub_output.strip()) < 5:
        return "SubAgent 返回空内容"

    review_prompt = (
        "你是质检员。判断以下SubAgent的输出是否完成了任务。\n\n"
        f"## 任务要求\n{task[:500]}\n\n"
        f"## SubAgent输出\n{sub_output[:800]}\n\n"
        "如果输出完成了任务要求、有实质内容（文件/链接/数据/代码），回复 PASS。\n"
        "如果输出不完整、跑偏、报错、空话，回复 FAIL: <原因>。\n"
        "只回复 PASS 或 FAIL: 加简短原因。"
    )

    try:
        response = client.chat.completions.create(
            model="GLM-4.7-Flash",
            messages=[{"role": "user", "content": review_prompt}],
            temperature=0,
            max_tokens=150,
            timeout=30,
        )
        verdict = (response.choices[0].message.content or "").strip().upper()
        if verdict.startswith("PASS"):
            return None
        return verdict.replace("FAIL:", "").strip() or "审核不通过"
    except Exception as e:
        logger.error(f"[Review] 审核调用失败: {e}")
        return None  # 审核失败时放行，避免阻塞

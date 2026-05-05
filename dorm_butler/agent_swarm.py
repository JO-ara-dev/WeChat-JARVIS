"""
Agent Swarm — 多 Agent 协作引擎

功能:
1. Agent 间消息传递（REQUEST/RESULT 协议）
2. Swarm 编排（并行派发 + 结果汇总 + 最终组装）
3. 线程安全（Lock 保护共享状态）
"""
import threading
import logging

logger = logging.getLogger("WCF")

# Agent 间消息队列（Agent → Agent 通信）
_inter_agent_messages: dict[str, list[dict]] = {}
_messages_lock = threading.Lock()


def send_message(from_agent: str, to_agent: str, content: str):
    """Agent A 向 Agent B 发送消息"""
    with _messages_lock:
        if to_agent not in _inter_agent_messages:
            _inter_agent_messages[to_agent] = []
        _inter_agent_messages[to_agent].append({"from": from_agent, "content": content})
    logger.info(f"[Swarm] {from_agent} → {to_agent}: {content[:60]}")


def check_messages(agent_name: str) -> list[dict]:
    """Agent 检查是否有发给自己的消息"""
    with _messages_lock:
        msgs = _inter_agent_messages.pop(agent_name, [])
        return msgs


def clear_all_messages():
    with _messages_lock:
        _inter_agent_messages.clear()


# Swarm 任务池（异步派发的结果收集）
_swarm_lock = threading.Lock()
_pending_results: dict[str, dict] = {}  # key → {"result": ..., "done": bool}
_result_events: dict[str, threading.Event] = {}  # key → Event


def register_task(key: str):
    """注册一个待执行任务"""
    with _swarm_lock:
        _pending_results[key] = {"result": None, "done": False}
        _result_events[key] = threading.Event()


def set_task_result(key: str, result: dict):
    """设置任务结果并通知等待者"""
    with _swarm_lock:
        _pending_results[key] = {"result": result, "done": True}
        if key in _result_events:
            _result_events[key].set()


def wait_task(key: str, timeout: int = 300) -> dict | None:
    """等待任务完成（阻塞当前线程）"""
    event = _result_events.get(key)
    if not event:
        return None
    if event.wait(timeout):
        with _swarm_lock:
            entry = _pending_results.get(key)
            return entry["result"] if entry else None
    return None


def get_task_result(key: str) -> dict | None:
    """非阻塞获取任务结果"""
    with _swarm_lock:
        entry = _pending_results.get(key)
        if entry and entry["done"]:
            return entry["result"]
    return None


def pop_task_result(key: str) -> dict | None:
    """获取并移除任务结果"""
    with _swarm_lock:
        entry = _pending_results.pop(key, None)
        _result_events.pop(key, None)
        if entry and entry["done"]:
            return entry["result"]
    return None


class AgentSwarm:
    """多 Agent 协作编排器"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.tasks: dict[str, dict] = {}  # id → {agent, task, status, result}
        self.interop = True  # 是否启用 Agent 间通信
        self._lock = threading.Lock()

    def add_task(self, task_id: str, agent_name: str, task_description: str):
        """添加任务到编排"""
        with self._lock:
            self.tasks[task_id] = {
                "agent": agent_name,
                "task": task_description,
                "status": "pending",
                "result": None,
            }

    def launch_parallel(self, progress_callback=None) -> dict:
        """并行启动所有任务，等待全部完成"""
        from .sub_agent import load_agents, SubAgent

        agents_config = {a["name"]: a for a in load_agents()}
        threads = []
        results = {}

        def _run_one(task_id, info):
            agent_cfg = agents_config.get(info["agent"])
            if not agent_cfg:
                with self._lock:
                    results[task_id] = {"success": False, "output": f"未知Agent: {info['agent']}"}
                    self.tasks[task_id]["status"] = "failed"
                return

            sub = SubAgent(info["agent"], agent_cfg, self.user_id)
            if progress_callback:
                progress_callback(f"[{info['agent']}] 开始执行: {info['task'][:50]}")

            # 注入 Agent 间消息到 system prompt
            context = ""
            if self.interop:
                msgs = check_messages(info["agent"])
                if msgs:
                    context = "来自其他Agent的求助信息:\n" + "\n".join(
                        f"[{m['from']}] {m['content']}" for m in msgs
                    )

            result = sub.execute(info["task"], context)

            # 检查输出中的 REQUEST 标记
            output = result.get("output", "")
            import re
            request_matches = re.findall(r'\[REQUEST:(\w[\w-]*)\]\s*(.+?)(?=\[REQUEST|\Z)', output, re.DOTALL)
            for target_agent, req_task in request_matches:
                req_task = req_task.strip()[:200]
                logger.info(f"[Swarm] {info['agent']} 请求 {target_agent}: {req_task[:60]}")
                send_message(info["agent"], target_agent, req_task)

            with self._lock:
                results[task_id] = result
                self.tasks[task_id]["status"] = "completed"
                self.tasks[task_id]["result"] = result

            if progress_callback:
                progress_callback(f"[{info['agent']}] 完成")

        # 启动所有并行线程
        for tid, info in self.tasks.items():
            t = threading.Thread(target=_run_one, args=(tid, info), daemon=True)
            threads.append(t)
            t.start()

        # 等待全部完成
        for t in threads:
            t.join(timeout=600)

        # 检查是否有 inter-agent REQUEST → 二次派发
        retry_count = 0
        while retry_count < 3:
            has_new_requests = False
            for tid, info in list(self.tasks.items()):
                if info["status"] != "completed":
                    continue
                output_text = info["result"].get("output", "") if info["result"] else ""
                import re as re2
                reqs = re2.findall(r'\[REQUEST:(\w[\w-]*)\]\s*(.+?)(?=\[REQUEST|\Z)', output_text, re2.DOTALL)
                for target_agent, req_task in reqs:
                    req_task = req_task.strip()[:200]
                    # 检查是否已有此任务的结果
                    result_key = f"{tid}_request_{target_agent}"
                    existing = get_task_result(result_key)
                    if existing:
                        continue  # 已处理过
                    has_new_requests = True
                    # 派发子请求
                    sub_cfg = agents_config.get(target_agent)
                    if sub_cfg:
                        sub2 = SubAgent(target_agent, sub_cfg, self.user_id)
                        sub_result = sub2.execute(req_task)
                        key = f"{tid}_request_{target_agent}"
                        set_task_result(key, sub_result)
                        logger.info(f"[Swarm] 子请求完成: {target_agent}")
            if not has_new_requests:
                break
            retry_count += 1

        return {"success": True, "data": results, "task_states": {
            tid: info["status"] for tid, info in self.tasks.items()
        }, "message": f"Swarm 完成: {len(results)} 个任务"}

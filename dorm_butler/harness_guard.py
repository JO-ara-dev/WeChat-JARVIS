"""
Harness Guard — 重复动作防护 + 死循环检测

Self-Harness 核心机制：工具调用前检查，防止同一参数重复执行导致死循环。
"""
import logging
import hashlib

logger = logging.getLogger("WCF")

# user_id → [(tool_name, args_hash, timestamp)]
_recent_calls: dict[str, list[tuple[str, str, float]]] = {}
MAX_WINDOW = 8   # 保留最近几次调用记录
REPEAT_LIMIT = 3  # 同一调用超过几次视为死循环


def _hash_args(args: dict) -> str:
    """对参数字典做稳定哈希"""
    raw = str(sorted(args.items()))
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def before_tool(user_id: str, tool_name: str, args: dict) -> str | None:
    """
    工具调用前的防护检查。
    返回: None=放行，否则返回拦截原因字符串（Agent 会收到这个原因）
    """
    if user_id not in _recent_calls:
        _recent_calls[user_id] = []

    args_hash = _hash_args(args)
    recent = _recent_calls[user_id]

    # 统计最近窗口内同一工具+同一参数的调用次数
    count = sum(1 for n, a, _ in recent[-MAX_WINDOW:] if n == tool_name and a == args_hash)
    if count >= REPEAT_LIMIT:
        reason = (
            f"[GUARD] 工具 {tool_name}({list(args.values())[:3]}) "
            f"已连续重复调用 {count} 次（上限 {REPEAT_LIMIT}）。"
            f"请换一种方式或换不同的参数完成任务。"
        )
        logger.warning(f"[Guard] 拦截重复调用: {tool_name} x{count}")
        return reason

    return None


def after_tool(user_id: str, tool_name: str, args: dict):
    """工具调用后记录（成功或失败都记录）"""
    import time
    if user_id not in _recent_calls:
        _recent_calls[user_id] = []
    args_hash = _hash_args(args)
    _recent_calls[user_id].append((tool_name, args_hash, time.time()))
    # 只保留最近窗口
    _recent_calls[user_id] = _recent_calls[user_id][-MAX_WINDOW * 2:]


def clear_user(user_id: str):
    """新对话开始时清空监控记录"""
    _recent_calls.pop(user_id, None)

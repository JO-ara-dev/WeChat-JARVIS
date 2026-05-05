"""
wx4py 群聊机器人桥接脚本
异步处理，过滤自己的消息
"""

import logging
import sys
import threading
import os
import json
import glob
from pathlib import Path
from queue import Queue

_PROJECT_ROOT = Path(__file__).parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("WX4PY")

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from dorm_butler import db_manager
from dorm_butler.memory import init_memory_tables
from dorm_butler import butler_agent
from dorm_butler import sessions as _sessions
from dorm_butler.vision_processor import process_image

init_memory_tables()
db_manager.init_db()

msg_queue = Queue()

# 微信图片缓存目录（可能需要根据实际情况调整）
WECHAT_IMAGE_DIRS = [
    os.path.expanduser("~/Documents/WeChat Files"),
    os.path.expanduser("~/Documents/Tencent Files"),
]


def _format_reply(text: str) -> str:
    PREFIX = "J.V "
    return f"{PREFIX}{text}"


def _extract_nickname(content: str) -> str | None:
    """从消息中解析用户声明的昵称"""
    import re
    patterns = [
        r'我是\s*(\S{1,10})', r'我叫\s*(\S{1,10})', r'叫我\s*(\S{1,10})',
        r'我是\s*([\u4e00-\u9fa5a-zA-Z0-9]{1,10})',
    ]
    for p in patterns:
        m = re.search(p, content)
        if m:
            return m.group(1)
    return None


def _is_image_message(content: str) -> bool:
    """检测是否是图片消息"""
    image_markers = ["[图片]", "[图片消息]"]
    return any(marker in content for marker in image_markers)


def _find_latest_image() -> str:
    """查找最新的图片文件"""
    import time
    
    # 常见的微信图片缓存路径
    possible_paths = []
    
    # 用户目录下的微信文件夹
    for base_dir in WECHAT_IMAGE_DIRS:
        if os.path.exists(base_dir):
            # 递归查找图片文件
            for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif"]:
                possible_paths.extend(glob.glob(os.path.join(base_dir, "**", ext), recursive=True))
    
    # 临时目录
    temp_dir = _PROJECT_ROOT / "data"
    for ext in ["*.jpg", "*.jpeg", "*.png", "*.gif"]:
        possible_paths.extend(glob.glob(str(temp_dir / ext)))
    
    if not possible_paths:
        return None
    
    # 按修改时间排序，返回最新的
    possible_paths.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest = possible_paths[0]
    
    # 只返回最近 30 秒内修改的文件
    if time.time() - os.path.getmtime(latest) < 30:
        return latest
    
    return None


def _wait_for_image(timeout: int = 10) -> str:
    """等待图片文件出现"""
    import time
    
    start = time.time()
    while time.time() - start < timeout:
        image_path = _find_latest_image()
        if image_path:
            return image_path
        time.sleep(1)
    
    return None


def _handle_session_cmd(user_id: str, content: str) -> str | None:
    """处理会话管理指令，返回回复文本或 None（非会话指令）"""
    stripped = content.strip()
    # 暂停
    if stripped in ("暂停", "/stop"):
        result = _sessions.archive_session(user_id)
        return (
            f"已存档 ✅ 会话 #{result['old_id']}\n"
            f"摘要：{result['summary']}\n"
            f"新会话 #{result['new_id']} 已开启 ｜ /sessions 查看历史"
        )
    # 列出会话
    if stripped == "/sessions":
        sessions_list = _sessions.list_sessions(user_id)
        if not sessions_list:
            return "还没有历史会话记录"
        lines = ["📋 历史会话："]
        for s in sessions_list:
            marker = "🟢" if s["status"] == "active" else "📁"
            summary = s["summary"][:30] if s["summary"] else "（无摘要）"
            lines.append(f"  {marker} #{s['id']} {summary} | {s['created_at'][:16]}")
        return "\n".join(lines)
    # 切换会话
    if stripped.startswith("/session "):
        try:
            sid = int(stripped.split()[1])
        except (IndexError, ValueError):
            return "用法：/session <会话ID>"
        result = _sessions.switch_session(user_id, sid)
        if result["success"]:
            return f"已切换到会话 #{sid} | 摘要：{result['summary']}"
        return result["message"]
    # 总结
    if stripped == "/summary":
        summary = _sessions.get_session_summary(user_id)
        return f"📝 当前会话摘要：{summary}"
    return None


def process_worker(action_emitter):
    """后台处理线程，通过 action_emitter 发送回复（走独立窗口）"""
    from wx4py.features.messaging.processor import ReplyAction

    while True:
        try:
            item = msg_queue.get()
            if item is None:
                break

            group, content = item

            # 自动注册用户
            db_manager.register_user(group, "")
            # 从消息中解析昵称声明
            nickname = _extract_nickname(content)
            if nickname:
                db_manager.register_user(group, nickname)
                db_manager.set_nickname(group, nickname)

            # 会话指令拦截（不进入 Agent）
            session_reply = _handle_session_cmd(group, content)
            if session_reply is not None:
                reply = _format_reply(session_reply)
                logger.info(f"[会话指令] {reply[:80]}")
                action_emitter(ReplyAction(group=group, content=reply))
                msg_queue.task_done()
                continue

            # ── 正常 Agent 处理（生成器模式）──
            logger.info(f"[处理] 调用DeepSeek...")

            try:
                def on_progress(msg: str):
                    action_emitter(ReplyAction(group=group, content=_format_reply(msg)))

                gen = butler_agent.chat(content, user_id=group, progress_callback=on_progress)
                final_reply = None
                for chunk in gen:
                    if chunk is None:
                        continue
                    # 判断是否为进度更新（以 emoji 开头）
                    progress_markers = ("📋", "✅", "🔄", "⏳", "❌", "📊")
                    if chunk.strip().startswith(progress_markers):
                        logger.info(f"[进度] {chunk[:80]}")
                        action_emitter(ReplyAction(group=group, content=f"J.V {chunk}"))
                    else:
                        final_reply = chunk

                if final_reply:
                    reply = _format_reply(final_reply)
                else:
                    reply = "J.V 处理完了"
                logger.info(f"[回复] {reply[:80]}")
                action_emitter(ReplyAction(group=group, content=reply))
            except Exception as e:
                logger.error(f"[错误] {e}")
                action_emitter(ReplyAction(group=group, content=f"J.V 出问题了: {str(e)[:50]}"))

            msg_queue.task_done()
        except Exception as e:
            logger.error(f"[工作线程错误] {e}")


def main():
    from wx4py import WeChatClient
    from wx4py.features.messaging import MessageHandler, MessageEvent
    from wx4py.features.messaging.processor import ReplyAction

    class ButlerHandler(MessageHandler):
        requires_group_nickname = True

        def __init__(self):
            self._emit = None

        def set_action_emitter(self, emit_action) -> None:
            self._emit = emit_action

        def handle(self, event: MessageEvent):
            content = event.content or ""
            group = event.group or ""
            is_at_me = event.is_at_me or False

            # 过滤自己的消息（防止循环）
            stripped = content.strip()
            if stripped.startswith("J.V ") or stripped.startswith("J.V\t"):
                return None
            if "贾维斯" in stripped[:20] and any(kw in stripped[:80] for kw in ["老大", "作业", "课表"]):
                return None

            # 被艾特：直接处理
            if is_at_me:
                # 检测图片消息
                if _is_image_message(stripped):
                    logger.info(f"[收到] {group} (at=True): [图片消息]")
                    
                    # 提示用户发送图片文件
                    msg_queue.put((group, "老板，您发的图片我这边暂时无法直接接收 😅\n\n"
                                  "请直接发送图片文件（不要引用），或者把图片保存到本地后告诉我文件路径，小的立马帮您识别！📸"))
                else:
                    logger.info(f"[收到] {group} (at=True): {content[:80]}")
                    msg_queue.put((group, content))
                return None

            # 未被艾特：包含关键词才处理
            keywords = ["课表", "作业", "课程", "这门课", "DDL", "ddl", "贾维斯", "jarvis", "Jarvis", "JARVIS", "暂停", "/stop", "/sessions", "/session", "/summary"]
            if any(kw in content for kw in keywords):
                logger.info(f"[收到] {group} (keyword): {content[:80]}")
                msg_queue.put((group, content))

            return None

    GROUPS = ["测试"]
    # 手动指定机器人在各群的昵称，用于判断是否被 @
    GROUP_NICKNAMES = {"测试": "贾维斯"}

    logger.info("=" * 50)
    logger.info("  贾维斯 wx4py 群聊机器人")
    logger.info("=" * 50)

    with WeChatClient(auto_connect=True) as wx:
        logger.info("[wx4py] 已连接微信")
        logger.info(f"[wx4py] 监听群聊: {GROUPS}")
        logger.info("[就绪] 贾维斯为老大服务！")

        handler = ButlerHandler()
        processor = wx.process_groups(GROUPS, [handler], block=False, group_nicknames=GROUP_NICKNAMES)
        handler_ref = handler

        worker = threading.Thread(
            target=process_worker,
            args=(lambda act: handler_ref._emit(act) if handler_ref._emit else None,),
            daemon=True,
        )
        worker.start()

        try:
            import time
            while processor.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("[退出] 贾维斯下班了！")
            msg_queue.put(None)


if __name__ == "__main__":
    main()

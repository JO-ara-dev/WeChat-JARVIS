"""
wx4py 群聊机器人桥接脚本
异步处理，过滤自己的消息
"""

import logging
import sys
import threading
import os
import json
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


def _format_reply(text: str) -> str:
    PREFIX = "J.V "
    return f"{PREFIX}{text}"


def _is_image_message(content: str) -> bool:
    """检测是否是图片消息"""
    image_markers = ["[图片]", "[图片消息]"]
    return any(marker in content for marker in image_markers)


def _dump_uia_tree(control, depth: int = 0, max_depth: int = 5):
    """诊断：打印 UIA 子树结构，用于确认 ImageControl 位置"""
    from wx4py.core import uiautomation as _ua
    if depth > max_depth:
        return
    try:
        c = _ua.control.SetControlFromControl(control)
        ct = c.ControlTypeName
        cn = c.ClassName
        nm = (c.Name or "").strip()
        rect = c.BoundingRectangle
        w = rect.width() if rect else 0
        h = rect.height() if rect else 0
        logger.info(f"[UIA] {'  ' * depth}{ct}({cn}) '{nm[:30]}' {w}x{h}")
        for child in c.GetChildren():
            _dump_uia_tree(child, depth + 1, max_depth)
    except Exception:
        pass


def _capture_from_viewer(image_ctrl, hwnd: int) -> str | None:
    """双击 ImageControl -> 打开查看器 -> 截图 -> 关闭。返回路径或 None。"""
    import time
    import win32gui
    from wx4py.core import uiautomation as _ua

    save_path = str(_PROJECT_ROOT / "data" / "temp_image.png")

    try:
        # 1. 激活窗口
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        time.sleep(0.2)

        # 2. 双击图片打开查看器
        try:
            image_ctrl.DoubleClick(simulateMove=False)
        except Exception:
            try:
                image_ctrl.Click(simulateMove=False)
                time.sleep(0.3)
                image_ctrl.Click(simulateMove=False)
            except Exception as e:
                logger.error(f"[图片] 点击失败: {e}")
                return None

        time.sleep(0.8)

        # 3. 查找图片查看器窗口（独立顶级窗口），用hwnd定位
        import win32gui
        viewer_hwnd = [None]  # 用list绕过nonlocal限制

        def _find_viewer(enum_hwnd, _):
            if not win32gui.IsWindowVisible(enum_hwnd):
                return True
            if enum_hwnd == hwnd:  # 排除微信主窗口
                return True
            rect = win32gui.GetWindowRect(enum_hwnd)
            w, h = rect[2] - rect[0], rect[3] - rect[1]
            if w < 100 or h < 100:  # 太小不是查看器
                return True
            # 前台窗口优先判断
            fg = win32gui.GetForegroundWindow()
            if fg == enum_hwnd:
                viewer_hwnd[0] = enum_hwnd
                return False
            return True

        win32gui.EnumWindows(_find_viewer, None)

        # 兜底：用前台窗口
        if not viewer_hwnd[0]:
            fg_hwnd = win32gui.GetForegroundWindow()
            if fg_hwnd and fg_hwnd != hwnd:
                viewer_hwnd[0] = fg_hwnd

        if not viewer_hwnd[0]:
            logger.warning("[图片] 未找到图片查看器窗口")
            return None

        # 4. 截图
        from PIL import ImageGrab
        rect = win32gui.GetWindowRect(viewer_hwnd[0])
        img = ImageGrab.grab(bbox=rect)
        img.save(save_path)
        logger.info(f"[图片] 已保存 {save_path} ({rect[2]-rect[0]}x{rect[3]-rect[1]})")

        # 5. 关闭查看器（用Win32消息，不用UIA）
        time.sleep(0.2)
        try:
            win32gui.PostMessage(viewer_hwnd[0], 0x0100, 0x1B, 0)  # WM_KEYDOWN + ESC
        except Exception:
            try:
                win32gui.PostMessage(viewer_hwnd[0], 0x0010, 0, 0)  # WM_CLOSE
            except Exception:
                pass

        return save_path

    except Exception as e:
        logger.error(f"[图片] 截取失败: {e}", exc_info=True)
        return None


def _capture_image_from_message(raw_control, hwnd: int, group: str) -> str | None:
    """在消息子树中找 ImageControl，然后双击 -> 查看器 -> 截图。"""
    from wx4py.core import uiautomation as _ua

    image_ctrl = None
    ctrl_wrapper = _ua.control.SetControlFromControl(raw_control)
    for ctrl, _ in _ua.WalkControl(ctrl_wrapper, includeTop=True, maxDepth=4):
        try:
            if ctrl.ControlTypeName != "ImageControl":
                continue
            rect = ctrl.BoundingRectangle
            if rect and rect.width() >= 30 and rect.height() >= 30:
                image_ctrl = ctrl
                break
        except Exception:
            continue

    if not image_ctrl:
        logger.warning("[图片] 未在消息中找到 ImageControl")
        _dump_uia_tree(raw_control)
        return None

    return _capture_from_viewer(image_ctrl, hwnd)


def _get_message_rect(hwnd: int):
    """获取聊天消息区域的屏幕坐标 (left, top, right, bottom)。先试 UIA，失败则按窗口比例估算。"""
    import win32gui
    try:
        from wx4py.core import uiautomation as _ua
        win_ctrl = _ua.ControlFromHandle(hwnd)
        msg_list = None
        try:
            msg_list = win_ctrl.ListControl(AutomationId="chat_message_list")
            if not msg_list.Exists(maxSearchSeconds=1):
                msg_list = None
        except Exception:
            pass
        if msg_list:
            r = msg_list.BoundingRectangle
            if r and r.width() > 100 and r.height() > 100:
                logger.info(f"[图片扫描] 消息区域(UIA): {r.left},{r.top} {r.width()}x{r.height()}")
                return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass

    # 兜底：按窗口比例估算
    rect = win32gui.GetWindowRect(hwnd)
    w, h = rect[2] - rect[0], rect[3] - rect[1]
    # 消息区域约占窗口 50%-95% 高度，宽度留 10px 边距
    left = rect[0] + 10
    top = rect[1] + int(h * 0.15)
    right = rect[2] - 10
    bottom = rect[3] - int(h * 0.08)
    logger.info(f"[图片扫描] 消息区域(估算): {left},{top} {right-left}x{bottom-top}")
    return (left, top, right, bottom)


def _scan_for_image_diff(hwnd: int, timeout: float = 15.0) -> str | None:
    """截图差异比对扫描：收到图片指令后截消息区域，对比帧找新出现的图片块。
    返回保存路径，超时返回 None。"""
    import time
    import win32gui
    from PIL import ImageGrab, ImageChops, Image

    save_path = str(_PROJECT_ROOT / "data" / "temp_image.png")
    MIN_DIFF_AREA = 15000  # 最小差异像素数，过滤文字变化
    INTERVAL = 0.3

    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.3)

    msg_rect = _get_message_rect(hwnd)
    logger.info(f"[图片扫描(diff)] 开始监控 (min_diff={MIN_DIFF_AREA}px, interval={INTERVAL}s)")

    try:
        baseline = ImageGrab.grab(bbox=msg_rect)
    except Exception as e:
        logger.error(f"[图片扫描(diff)] 截图失败: {e}")
        return None

    deadline = time.time() + timeout

    while time.time() < deadline:
        time.sleep(INTERVAL)

        try:
            frame = ImageGrab.grab(bbox=msg_rect)
        except Exception:
            continue

        try:
            diff = ImageChops.difference(baseline, frame)
            bbox = diff.getbbox()
        except Exception:
            baseline = frame
            continue

        if bbox is None:
            # 无变化
            continue

        diff_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
        if diff_area < MIN_DIFF_AREA:
            # 变化太小（纯文字）→ 忽略，更新基线
            baseline = frame
            continue

        logger.info(f"[图片扫描(diff)] 检测到变化区域: {bbox} ({diff_area}px)")

        # 抠出新图片区域（用当前帧的变化区域）
        image_region = frame.crop(bbox)
        image_region.save(save_path)
        logger.info(f"[图片扫描(diff)] 已保存 {save_path} ({bbox[2]-bbox[0]}x{bbox[3]-bbox[1]})")
        return save_path

    logger.info(f"[图片扫描(diff)] 超时 {timeout}s，未检测到图片")
    return None


def _handle_session_cmd(user_id: str, content: str) -> str | None:
    """处理会话管理指令"""
    stripped = content.strip()
    # /new — 开启新会话
    if stripped == "/new":
        result = _sessions.archive_session(user_id)
        return (
            f"已结束旧会话 #{result['old_id']}\n"
            f"新会话 #{result['new_id']} 已开启 ｜ /sessions 查看历史"
        )
    # /stop — 同 /new
    if stripped in ("暂停", "/stop"):
        result = _sessions.archive_session(user_id)
        return (
            f"已存档 ✅ 会话 #{result['old_id']}\n"
            f"摘要：{result['summary']}\n"
            f"新会话 #{result['new_id']} 已开启 ｜ /sessions 查看历史"
        )
    # /clear — 清空所有对话记录
    if stripped == "/clear":
        result = _sessions.clear_user_sessions(user_id)
        return result["message"]
    # /delete <id> — 删除指定会话
    if stripped.startswith("/delete "):
        try:
            sid = int(stripped.split()[1])
        except (IndexError, ValueError):
            return "用法：/delete <会话ID>"
        result = _sessions.delete_session(user_id, sid)
        return result["message"]
    # /sessions — 列出历史会话
    if stripped == "/sessions":
        sessions_list = _sessions.list_sessions(user_id)
        if not sessions_list:
            return "还没有历史会话记录 ｜ /new 开始新对话"
        lines = ["📋 历史会话："]
        for s in sessions_list:
            marker = "🟢" if s["status"] == "active" else "📁"
            summary = s["summary"][:30] if s["summary"] else "（无摘要）"
            lines.append(f"  {marker} #{s['id']} {summary} | {s['created_at'][:16]}")
        lines.append("")
        lines.append("回复 /session <id> 切换 ｜ /delete <id> 删除 ｜ /new 新对话 ｜ /clear 清空")
        return "\n".join(lines)
    # /session <id> — 切换会话
    if stripped.startswith("/session "):
        try:
            sid = int(stripped.split()[1])
        except (IndexError, ValueError):
            return "用法：/session <会话ID>"
        result = _sessions.switch_session(user_id, sid)
        if result["success"]:
            return f"已切换到会话 #{sid} | 摘要：{result['summary']}"
        return result["message"]
    # /summary — 总结当前会话
    if stripped == "/summary":
        summary = _sessions.get_session_summary(user_id)
        return f"📝 当前会话摘要：{summary}"
    return None


def process_worker(action_emitter):
    """后台处理线程，通过 action_emitter 发送回复（走独立窗口）"""
    from wx4py.features.messaging.processor import ReplyAction
    from dorm_butler.scheduler import schedule_queue

    while True:
        try:
            # ── 优先检查定时任务队列（非阻塞）──
            try:
                sched_msg = schedule_queue.get_nowait()
                sched_group = sched_msg.get("group", "测试")
                sched_content = sched_msg.get("content", "")
                if sched_content:
                    reply = _format_reply(sched_content)
                    logger.info(f"[定时推送] 发送早报到: {sched_group}")
                    action_emitter(ReplyAction(group=sched_group, content=reply))
                continue
            except Exception:
                pass

            # ── 常规消息处理 ──
            item = msg_queue.get()
            if item is None:
                break

            group, content = item

            # ── 图片主动扫描 ──
            if content.startswith("__IMAGE_SCAN__::"):
                scan_hwnd = int(content.split("::", 1)[1])
                action_emitter(ReplyAction(group=group, content="J.V 收到，正在等待图片..."))
                save_path = _scan_for_image_diff(scan_hwnd, timeout=15)
                if save_path:
                    # 转入 OCR 流程
                    content = f"__IMAGE__::{save_path}"
                else:
                    action_emitter(ReplyAction(group=group, content="J.V 未检测到图片，请重新发送并 @我 说'识别图片'"))
                    msg_queue.task_done()
                    continue

            # ── 图片消息处理（被动检测或扫描后转入）──
            if content.startswith("__IMAGE__::"):
                image_path = content.split("::", 1)[1]
                logger.info(f"[处理] 图片识别中: {image_path}")
                try:
                    from dorm_butler.vision_processor import process_image
                    ocr_result = process_image(image_path, user_id=group)
                    ocr_text = ocr_result.get("extracted_text", "").strip()
                    if ocr_text:
                        content = f"[图片OCR结果]\n{ocr_text}"
                        logger.info(f"[OCR] 识别成功 ({len(ocr_text)} 字)")
                    else:
                        logger.warning(f"[OCR] 识别结果为空")
                        action_emitter(ReplyAction(group=group, content="J.V 图片已收到，但未识别到文字"))
                        msg_queue.task_done()
                        continue
                except Exception as e:
                    logger.error(f"[OCR] 识别失败: {e}")
                    action_emitter(ReplyAction(group=group, content=f"J.V 图片识别失败: {str(e)[:50]}"))
                    msg_queue.task_done()
                    continue

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
                prev_chunk = None
                for chunk in gen:
                    if chunk is None:
                        continue
                    if prev_chunk is not None:
                        # 非最后一条 → 进度更新
                        logger.info(f"[进度] {prev_chunk[:80]}")
                        action_emitter(ReplyAction(group=group, content=f"J.V {prev_chunk}"))
                    prev_chunk = chunk

                # 最后一条 yield 一定是最终回复
                final_reply = prev_chunk

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
    import ctypes
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    logger.info("[系统] 已禁止系统自动休眠")

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

            # 图片扫描请求（无论是否艾特都检测）
            _IMAGE_SCAN_KW = ["识别图片", "识别这张图", "看看这张图", "图片识别",
                              "识别一下", "识别上面", "识别这个", "看图识", "识别这",
                              "图片分析", "分析图片", "读图", "提取图片"]
            if any(kw in stripped for kw in _IMAGE_SCAN_KW):
                logger.info(f"[收到] {group}: 图片扫描请求")
                msg_queue.put((group, f"__IMAGE_SCAN__::{wx.window.hwnd}"))
                return None

            # 被艾特：直接处理
            if is_at_me:
                if _is_image_message(stripped):
                    logger.info(f"[收到] {group} (at=True): [图片消息]")
                    image_path = _capture_image_from_message(event.raw, wx.window.hwnd, group)
                    if image_path:
                        msg_queue.put((group, f"__IMAGE__::{image_path}"))
                    else:
                        msg_queue.put((group, "无法获取图片，请重新发送或发送图片文件"))
                else:
                    logger.info(f"[收到] {group} (at=True): {content[:80]}")
                    msg_queue.put((group, content))
                return None

            # 未被艾特：检测图片
            if _is_image_message(stripped):
                logger.info(f"[收到] {group} (keyword): [图片消息]")
                image_path = _capture_image_from_message(event.raw, wx.window.hwnd, group)
                if image_path:
                    msg_queue.put((group, f"__IMAGE__::{image_path}"))
                return None

            # 未被艾特：包含关键词才处理
            keywords = ["课表", "作业", "课程", "这门课", "DDL", "ddl", "贾维斯", "jarvis", "Jarvis", "JARVIS", "暂停", "/stop", "/new", "/clear", "/delete", "/sessions", "/session", "/summary"]
            if any(kw in content for kw in keywords):
                logger.info(f"[收到] {group} (keyword): {content[:80]}")
                msg_queue.put((group, content))

            return None

    GROUPS = ["测试"]
    GROUP_NICKNAMES = {"测试": "贾维斯"}

    logger.info("=" * 50)
    logger.info("  贾维斯 wx4py 群聊机器人")
    logger.info("=" * 50)

    with WeChatClient(auto_connect=True) as wx:
        logger.info("[wx4py] 已连接微信")
        logger.info(f"[wx4py] 监听群聊: {GROUPS}")

        # 启动时自动归档旧会话，防止重启后续跑上次没完成的任务
        for group in GROUPS:
            try:
                _sessions.archive_session(group)
            except Exception:
                pass
        logger.info("[会话] 已归档旧会话，新对话从零开始")

        logger.info("[就绪] 贾维斯为老大服务！")

        import time

        # 预打开群聊子窗口
        from wx4py.features.messaging.listener import (
            _find_session_item, _find_window_by_title, _double_click_control,
        )
        for group in GROUPS:
            try:
                hwnd = _find_window_by_title(group, exclude_hwnd=wx.window.hwnd)
                if not hwnd:
                    item = _find_session_item(wx.window.uia.root, group)
                    if item and _double_click_control(item):
                        logger.info(f"[窗口] 已从会话列表打开群聊: {group}")
                    else:
                        logger.warning(f"[窗口] 无法从会话列表打开: {group}")
            except Exception:
                logger.debug(f"[窗口] 跳过预打开: {group}", exc_info=True)

        handler = ButlerHandler()
        processor = wx.process_groups(GROUPS, [handler], block=False, group_nicknames=GROUP_NICKNAMES)
        handler_ref = handler

        # Monkey-patch _poll_session：窗口最小化时静默恢复再扫 UIA
        # Monkey-patch _read_visible_items：检测 Name 为空的图片消息
        if hasattr(processor, '_listener'):
            import win32gui, win32con
            import wx4py.features.messaging.listener as _lm
            from wx4py.core import uiautomation as _ua

            # --- patch 1: _poll_session ---
            _poll_fn = processor._listener._poll_session
            _RESTORE_COOLDOWN = 30
            _last_restore = {}

            def _poll_with_activate(self, session):
                hwnd = session.hwnd
                was_iconic = win32gui.IsIconic(hwnd) if hwnd else False
                if was_iconic:
                    now = time.time()
                    last = _last_restore.get(hwnd, 0)
                    if now - last <= _RESTORE_COOLDOWN:
                        return None
                    try:
                        win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
                        time.sleep(0.15)
                        _last_restore[hwnd] = now
                    except Exception:
                        pass
                return _poll_fn(session)

            processor._listener._poll_session = _poll_with_activate.__get__(
                processor._listener, type(processor._listener)
            )
            logger.info("[patch] 已启用最小化窗口 UIA 刷新（30s 冷却）")

            # --- patch 2: _read_visible_items ---
            _orig_read = _lm._read_visible_items

            def _read_with_images(msg_list):
                items = _orig_read(msg_list)
                for child in _lm._safe_children(msg_list):
                    name = _lm._safe_text(child, "Name").strip()
                    if name:
                        continue
                    cls = _lm._safe_text(child, "ClassName")
                    if cls not in _lm.MESSAGE_CLASSES:
                        continue
                    has_image = False
                    try:
                        for sub, _d in _ua.WalkControl(child, includeTop=True, maxDepth=4):
                            try:
                                if sub.ControlTypeName == "ImageControl":
                                    has_image = True
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass
                    if has_image:
                        rid = _lm._safe_runtime_id(child)
                        if not any(item.runtime_id == rid for item in items):
                            items.append(_lm._VisibleItem(
                                kind="message",
                                name="[图片]",
                                class_name=cls,
                                runtime_id=rid,
                                control=child,
                            ))
                return items

            _lm._read_visible_items = _read_with_images
            logger.info("[patch] 已启用图片消息 Name 为空时的检测")

        worker = threading.Thread(
            target=process_worker,
            args=(lambda act: handler_ref._emit(act) if handler_ref._emit else None,),
            daemon=True,
        )
        worker.start()

        try:
            last_health_check = time.time()
            HEALTH_CHECK_INTERVAL = 30  # 每 30 秒检查一次

            while processor.is_running:
                time.sleep(1)

                # 定期健康检查
                now = time.time()
                if now - last_health_check >= HEALTH_CHECK_INTERVAL:
                    last_health_check = now
                    try:
                        if not processor.is_running:
                            logger.warning("[健康检查] 监听已停止，尝试重启...")
                            processor.stop()
                            processor = wx.process_groups(GROUPS, [handler], block=False, group_nicknames=GROUP_NICKNAMES)
                            handler_ref = processor._listener
                            logger.info("[健康检查] 监听已重启")
                    except Exception as e:
                        logger.error(f"[健康检查] 重启监听失败: {e}")
        except KeyboardInterrupt:
            logger.info("[退出] 贾维斯下班了！")
            msg_queue.put(None)
        finally:
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
            logger.info("[系统] 已恢复系统休眠策略")


if __name__ == "__main__":
    main()

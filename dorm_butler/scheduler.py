"""
贾维斯定时任务调度器
- 每晚 22:00 提醒次日课程
- 使用 APScheduler 后台运行
"""

import os
import sys
import json
import logging
import datetime
from pathlib import Path

logger = logging.getLogger("WCF")

# 全局调度器实例
_scheduler = None


def _get_project_root() -> str:
    """获取项目根目录"""
    return str(Path(__file__).parent.parent)


def _send_wechat_msg(user_id: str, content: str) -> bool:
    """通过微信机器人发送消息（调用 wx4py 的 HTTP API）"""
    try:
        import urllib.request

        # 读取配置中的微信机器人端口
        from . import db_manager
        wx_port = db_manager.get_config("wx_bot_port")
        if not wx_port:
            wx_port = "8765"  # 默认端口

        # 尝试多种 API 路径
        api_paths = ["/send_msg", "/send", "/api/send_msg", "/api/send"]
        for path in api_paths:
            try:
                data = json.dumps({
                    "user_id": user_id,
                    "content": content,
                    "msg_type": "text",
                }).encode("utf-8")

                req = urllib.request.Request(
                    f"http://127.0.0.1:{wx_port}{path}",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    if result.get("success", False):
                        return True
            except Exception:
                continue

        # 如果 HTTP API 都失败，尝试写入消息队列文件
        try:
            msg_dir = Path(_get_project_root()) / "data" / "pending_msgs"
            msg_dir.mkdir(parents=True, exist_ok=True)
            msg_file = msg_dir / f"{user_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(msg_file, "w", encoding="utf-8") as f:
                json.dump({"user_id": user_id, "content": content, "time": datetime.datetime.now().isoformat()}, f, ensure_ascii=False)
            logger.info(f"[定时任务] 消息已写入队列文件: {msg_file}")
            return True
        except Exception as e2:
            logger.error(f"[定时任务] 写入消息队列也失败: {e2}")
            return False

    except Exception as e:
        logger.error(f"[定时任务] 发送微信消息失败: {e}")
        return False


def _query_tomorrow_courses() -> str:
    """查询次日课程，返回格式化文本"""
    try:
        # 动态导入避免循环引用
        sys.path.insert(0, _get_project_root())
        from dorm_butler.tools import query_courses, get_current_week, WEEKDAY_NAMES

        now = datetime.datetime.now()
        tomorrow = now + datetime.timedelta(days=1)
        weekday = tomorrow.weekday() + 1  # 1=周一 ... 7=周日

        # 周末不提醒
        if weekday > 5:
            return None  # 周末没课，不提醒

        current_week = get_current_week()
        result = query_courses(weekday=weekday)

        if not result.get("success") or not result.get("data"):
            return None  # 没课，不提醒

        courses = result["data"]
        day_name = WEEKDAY_NAMES[weekday] if 1 <= weekday <= 7 else f"周{weekday}"

        lines = [f"🌅 明日课程提醒（{day_name}，第{current_week}周）\n"]
        for c in courses:
            start = c.get("start_node", "?")
            end = c.get("end_node", "?")
            name = c.get("course_name", "未知课程")
            loc = c.get("location", "待定")
            lines.append(f"📚 第{start}-{end}节 | {name} | 📍 {loc}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[定时任务] 查询课程失败: {e}")
        return None


def _check_exam_reminders(user_id: str) -> str:
    """检查考试提醒，返回提醒消息（如果有）"""
    try:
        sys.path.insert(0, _get_project_root())
        from dorm_butler import db_manager

        # 从 memory 表读取所有 exam_ 开头的记忆
        conn = db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT key, value FROM memory WHERE user_id=? AND key LIKE 'exam_%'",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        today = datetime.date.today()
        reminders = []

        for key, value in rows:
            try:
                exam_info = json.loads(value)
                exam_date_str = exam_info.get("date", "")
                reminder_days = exam_info.get("reminder_days", 3)
                course_name = exam_info.get("course", key.replace("exam_", ""))
                start_time = exam_info.get("start_time", "")
                end_time = exam_info.get("end_time", "")

                if not exam_date_str:
                    continue

                exam_date = datetime.datetime.strptime(exam_date_str, "%Y-%m-%d").date()
                remind_date = exam_date - datetime.timedelta(days=reminder_days)

                if today == remind_date:
                    time_str = f"{start_time}-{end_time}" if start_time and end_time else ""
                    msg_parts = [f"📢 考试提醒！"]
                    msg_parts.append(f"📚 课程：{course_name}")
                    msg_parts.append(f"📅 日期：{exam_date_str}（{reminder_days}天后）")
                    if time_str:
                        msg_parts.append(f"⏰ 时间：{time_str}")
                    msg_parts.append(f"💪 老大加油，抓紧复习！")
                    reminders.append("\n".join(msg_parts))
            except (json.JSONDecodeError, ValueError, KeyError) as e:
                logger.warning(f"[定时任务] 解析考试记忆失败: {key} -> {e}")
                continue

        return "\n\n".join(reminders) if reminders else None

    except Exception as e:
        logger.error(f"[定时任务] 检查考试提醒失败: {e}")
        return None


def _nightly_reminder():
    """每晚 22:00 执行的定时任务（课程提醒 + 考试提醒）"""
    logger.info("[定时任务] 执行晚间提醒...")

    try:
        sys.path.insert(0, _get_project_root())
        from dorm_butler import db_manager

        # 获取所有用户
        users = db_manager.get_all_users()
        if not users:
            logger.info("[定时任务] 没有活跃用户，跳过提醒")
            return

        for user in users:
            user_id = user.get("user_id") or user.get("id")
            if not user_id:
                continue

            # 1. 课程提醒
            course_msg = _query_tomorrow_courses()
            if course_msg:
                _send_wechat_msg(user_id, course_msg)
                logger.info(f"[定时任务] 已向 {user_id} 发送明日课程提醒")

            # 2. 考试提醒
            exam_msg = _check_exam_reminders(user_id)
            if exam_msg:
                _send_wechat_msg(user_id, exam_msg)
                logger.info(f"[定时任务] 已向 {user_id} 发送考试提醒")

            if not course_msg and not exam_msg:
                logger.info(f"[定时任务] {user_id} 明日无课且无考试提醒，跳过")
    except Exception as e:
        logger.error(f"[定时任务] 执行失败: {e}")


def start_scheduler():
    """启动定时任务调度器"""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.info("[定时任务] 调度器已在运行")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger

        _scheduler = BackgroundScheduler()
        # 每晚 22:00 执行
        _scheduler.add_job(
            _nightly_reminder,
            CronTrigger(hour=22, minute=0),
            id="nightly_course_reminder",
            name="晚间课程提醒",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("[定时任务] 调度器已启动，每晚 22:00 提醒次日课程")
    except Exception as e:
        logger.error(f"[定时任务] 启动失败: {e}")
        _scheduler = None


def stop_scheduler():
    """停止定时任务调度器"""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[定时任务] 调度器已停止")

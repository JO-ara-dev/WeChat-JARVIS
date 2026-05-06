"""
贾维斯每日早报模块
- 查询今日课表 + 近3天DDL
- 获取天气信息 (wttr.in)
- 调用 LLM 生成口语化早报
- 推送到 schedule_queue 供 wx4py_bridge 发送
"""

import os
import sys
import json
import logging
import datetime
from pathlib import Path

logger = logging.getLogger("WCF")

_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _fetch_today_courses():
    """
    查询今日课程。
    返回 (courses_list, day_name, week_num)
    周末返回 ([], day_name, week_num)
    """
    from dorm_butler.tools import query_courses, get_current_week, WEEKDAY_NAMES

    now = datetime.datetime.now()
    weekday = now.weekday() + 1

    current_week = get_current_week()
    day_name = WEEKDAY_NAMES.get(weekday, f"周{weekday}")

    if weekday > 5:
        return [], day_name, current_week

    result = query_courses(weekday=weekday)
    courses = result.get("data", []) if result.get("success") else []
    return courses, day_name, current_week


def _fetch_upcoming_ddls(days=3):
    """
    查询未来 N 天内到期的 DDL。
    返回任务列表（排除已完成的）。
    """
    from dorm_butler import db_manager

    now = datetime.datetime.now()
    end_date = now + datetime.timedelta(days=days)

    conn = db_manager.get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status = 0 "
        "AND ddl IS NOT NULL AND ddl <= ? "
        "ORDER BY ddl ASC",
        (end_date.strftime("%Y-%m-%d %H:%M:%S"),),
    ).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def _fetch_weather(city="Jinhua"):
    """
    从 wttr.in 获取简易天气字符串。
    失败返回 None，不阻塞流程。
    """
    try:
        import urllib.request

        url = f"https://wttr.in/{city}?format=%C+%t+%w+%h&lang=zh"
        req = urllib.request.Request(url, headers={"User-Agent": "curl"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8").strip()
            if raw and raw != city:
                return raw
    except Exception as e:
        logger.warning(f"[早报] 天气获取失败: {e}")
    return None


def _format_course_line(c) -> str:
    """格式化单门课程信息"""
    name = c.get("name") or c.get("course_name", "未知课程")
    start = c.get("start_node", "?")
    end = c.get("end_node", "?")
    loc = c.get("location", "待定")
    return f"  {start}-{end}节 {name} @ {loc}"


def _format_ddl_line(t) -> str:
    """格式化单条 DDL 信息"""
    content = t.get("content", "未知任务")
    ddl = t.get("ddl", "")
    if ddl:
        try:
            dt = datetime.datetime.fromisoformat(ddl)
            ddl_str = dt.strftime("%m月%d日 %H:%M")
        except (ValueError, TypeError):
            ddl_str = ddl
    else:
        ddl_str = "无截止日期"
    return f"  [{ddl_str}] {content}"


def build_early_bird_prompt(courses, ddls, weather, day_name, week_num):
    """
    构建用于生成早报的 LLM prompt。
    将所有数据作为『当前事实上下文』注入，让 LLM 生成贴心口语化报告。
    """
    now = datetime.datetime.now()
    today_str = now.strftime("%Y年%m月%d日")

    lines = []
    lines.append(f"你是贾维斯(J.V)，一位贴心的大学宿舍 AI 管家。请为老大撰写今日早报。")
    lines.append(f"现在是 {today_str}，{day_name}，第{week_num if week_num > 0 else '?'}教学周。")
    lines.append("")
    lines.append("## 当前事实上下文（严禁编造）")
    lines.append("")

    if weather:
        lines.append(f"### 天气\n{weather}")
    else:
        lines.append("### 天气\n暂无天气数据")

    lines.append("")
    lines.append("### 今日课表")
    if courses:
        for c in courses:
            lines.append(_format_course_line(c))
    else:
        lines.append("  今天没有课！")

    lines.append("")
    lines.append(f"### 近3天DDL（截止日期）")
    if ddls:
        for t in ddls:
            lines.append(_format_ddl_line(t))
    else:
        lines.append("  近3天没有待完成的作业/任务")

    lines.append("")
    lines.append("## 撰写要求")
    lines.append("- 总字数严格控制在 500 字以内")
    lines.append("- 语气亲切、口语化，像室友之间的早晨问候")
    lines.append("- 称呼用户为「老大」")
    lines.append("- 如果今天有课，请简要列出课程时间和教室，提醒老大别迟到")
    lines.append("- 如果有即将到期的 DDL，请用温和但关切的方式提醒")
    lines.append("- 如果天气有雨、大风或气温剧变，请给出相应的着装/携带建议")
    lines.append("- 如果周末或今天没课，那就写一句轻松愉快的早安问候")
    lines.append("- 以「早安老大！☀️」或类似的亲切问候开头")
    lines.append("- 不要在回复中包含任何 markdown 代码块标记")
    lines.append("- 直接输出纯文本早报内容")

    return "\n".join(lines)


def generate_early_bird_report(courses, ddls, weather, day_name, week_num):
    """
    调用 LLM 生成早报文本。
    返回生成的口语化早报文本，或 None（LLM 调用失败时）。
    """
    from dorm_butler.agent_manager import AgentManager

    _AGENT_CFG_PATH = str(Path(__file__).parent / "agent_config.json")
    mgr = AgentManager(_AGENT_CFG_PATH)

    main = mgr.get_main_agent()
    provider = main.get("provider", "deepseek")
    model = main.get("model", "deepseek-chat")

    client = mgr.create_client(provider)

    prompt = build_early_bird_prompt(courses, ddls, weather, day_name, week_num)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "请根据以上上下文，生成今日早报。"},
            ],
            temperature=0.7,
            max_tokens=800,
            timeout=60,
        )
        text = response.choices[0].message.content
        if text:
            return text.strip()
    except Exception as e:
        logger.error(f"[早报] LLM 生成失败: {e}")

    return None


def run_morning_report(target_group="测试"):
    """
    执行早报生成并推送到消息队列。
    这是定时任务的实际入口函数。

    返回: 早报文本 或 None（生成失败时）
    """
    logger.info("[早报] 开始生成每日早报...")

    courses, day_name, week_num = _fetch_today_courses()
    ddls = _fetch_upcoming_ddls(days=3)
    weather = _fetch_weather()

    logger.info(
        f"[早报] 数据采集完成: "
        f"课程={len(courses)}门, DDL={len(ddls)}条, "
        f"天气={'有' if weather else '无'}"
    )

    report = generate_early_bird_report(courses, ddls, weather, day_name, week_num)

    if not report:
        logger.warning("[早报] LLM 生成失败，推送已取消")
        return None

    from .scheduler import schedule_queue

    msg = {
        "group": target_group,
        "content": report,
    }
    schedule_queue.put(msg)

    logger.info(f"[早报] 已推送到消息队列（{len(report)} 字）")
    return report
